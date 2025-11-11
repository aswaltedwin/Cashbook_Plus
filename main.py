
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext

from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session

# ---------------- CONFIG ----------------
APP_TITLE = "CashBook+"
app = FastAPI(title=APP_TITLE)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

SESSION_COOKIE = "cb_session"
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# ---------------- DATABASE ----------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is missing")
engine = create_engine(DATABASE_URL, connect_args={"sslmode": "require"})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    cashbooks = relationship("Cashbook", back_populates="owner")


class Cashbook(Base):
    __tablename__ = "cashbooks"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"))
    entries = relationship("Entry", back_populates="cashbook", cascade="all, delete")
    owner = relationship("User", back_populates="cashbooks")


class Entry(Base):
    __tablename__ = "entries"
    id = Column(String, primary_key=True, index=True)
    cashbook_id = Column(Integer, ForeignKey("cashbooks.id"))
    date = Column(String)
    type = Column(String)
    amount = Column(Float)
    note = Column(String)
    cashbook = relationship("Cashbook", back_populates="entries")


class SessionToken(Base):
    __tablename__ = "sessions"
    token = Column(String, primary_key=True, index=True)
    username = Column(String, ForeignKey("users.username"))

Base.metadata.create_all(bind=engine)

# ---------------- HELPERS ----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = db.query(SessionToken).filter(SessionToken.token == token).first()
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = db.query(User).filter(User.username == session.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def sanitize_cashbook_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Cashbook name required")
    if len(name) > 64:
        raise HTTPException(status_code=400, detail="Cashbook name too long")
    return name

def summarize(entries: List[Entry]) -> Dict[str, Any]:
    total_in = sum(e.amount for e in entries if e.type == "cash_in")
    total_out = sum(e.amount for e in entries if e.type == "cash_out")
    return {"total_in": round(total_in, 2), "total_out": round(total_out, 2), "balance": round(total_in - total_out, 2)}

# ------------------- PAGES --------------------
@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse("static/index.html")

@app.get("/login", include_in_schema=False)
async def login_page() -> FileResponse:
    return FileResponse("static/login.html")

@app.get("/register", include_in_schema=False)
async def register_page() -> FileResponse:
    return FileResponse("static/register.html")

@app.get("/dashboard", include_in_schema=False)
async def dashboard_page() -> FileResponse:
    return FileResponse("static/dashboard.html")

@app.get("/cashbooks", include_in_schema=False)
async def cashbooks_page() -> FileResponse:
    return FileResponse("static/cashbooks.html")

# -------------------- AUTH --------------------
@app.post("/api/register")
def register(payload: Dict[str, Any], db: Session = Depends(get_db)):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if len(username) < 3 or len(password) < 6:
        raise HTTPException(status_code=400, detail="Username or password too short")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(username=username, password_hash=pwd_context.hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Registered successfully"}

@app.post("/api/login")
def login(payload: Dict[str, Any], response: Response, db: Session = Depends(get_db)):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = str(uuid.uuid4())
    session = SessionToken(token=token, username=username)
    db.add(session)
    db.commit()
    response.set_cookie(key=SESSION_COOKIE, value=token, httponly=True, samesite="lax", secure=False, max_age=60*60*24*7)
    return {"message": "Logged in", "username": username}

@app.post("/api/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        session = db.query(SessionToken).filter(SessionToken.token == token).first()
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(SESSION_COOKIE)
    return {"message": "Logged out"}

# ---------------- CASHBOOKS -------------------
@app.post("/api/create_cashbook")
def create_cashbook(payload: Dict[str, Any], user: User = Depends(require_user), db: Session = Depends(get_db)):
    name = sanitize_cashbook_name(payload.get("name", ""))
    if db.query(Cashbook).filter(Cashbook.owner == user, Cashbook.name == name).first():
        raise HTTPException(status_code=409, detail="Cashbook already exists")
    cashbook = Cashbook(name=name, owner=user)
    db.add(cashbook)
    db.commit()
    db.refresh(cashbook)
    return {"message": "Cashbook created", "name": name}

@app.get("/api/get_cashbooks")
def get_cashbooks(user: User = Depends(require_user)):
    return {"username": user.username, "cashbooks": [c.name for c in user.cashbooks]}

@app.delete("/api/delete_cashbook")
def delete_cashbook(payload: Dict[str, Any], user: User = Depends(require_user), db: Session = Depends(get_db)):
    name = sanitize_cashbook_name(payload.get("name", ""))
    cashbook = db.query(Cashbook).filter(Cashbook.owner == user, Cashbook.name == name).first()
    if not cashbook:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    db.delete(cashbook)
    db.commit()
    return {"message": f"Cashbook '{name}' deleted successfully"}

@app.post("/api/add_entry")
def add_entry(payload: Dict[str, Any], user: User = Depends(require_user), db: Session = Depends(get_db)):
    name = sanitize_cashbook_name(payload.get("cashbook", ""))
    cashbook = db.query(Cashbook).filter(Cashbook.owner == user, Cashbook.name == name).first()
    if not cashbook:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    entry_type = payload.get("type")
    if entry_type not in ("cash_in", "cash_out"):
        raise HTTPException(status_code=400, detail="Invalid type")
    try:
        date_str = payload.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
        datetime.strptime(date_str, "%Y-%m-%d")
        amount = float(payload.get("amount") or 0)
        if amount <= 0:
            raise ValueError()
    except:
        raise HTTPException(status_code=400, detail="Invalid date or amount")
    note = payload.get("note") or ""
    entry = Entry(id=str(uuid.uuid4()), cashbook=cashbook, date=date_str, type=entry_type, amount=amount, note=note)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"message": "Entry added", "entry": {"id": entry.id, "date": entry.date, "type": entry.type, "amount": entry.amount, "note": entry.note}}

@app.get("/api/get_entries")
def get_entries(cashbook: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    name = sanitize_cashbook_name(cashbook)
    cb = db.query(Cashbook).filter(Cashbook.owner == user, Cashbook.name == name).first()
    if not cb:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    entries = cb.entries
    return {"entries": [{"id": e.id, "date": e.date, "type": e.type, "amount": e.amount, "note": e.note} for e in entries]}

@app.delete("/api/delete_entry/{entry_id}")
def delete_entry(entry_id: str, cashbook: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    name = sanitize_cashbook_name(cashbook)
    cb = db.query(Cashbook).filter(Cashbook.owner == user, Cashbook.name == name).first()
    if not cb:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    entry = db.query(Entry).filter(Entry.cashbook == cb, Entry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"message": "Entry deleted"}

@app.get("/api/summary/{cashbook}")
def summary_api(cashbook: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    name = sanitize_cashbook_name(cashbook)
    cb = db.query(Cashbook).filter(Cashbook.owner == user, Cashbook.name == name).first()
    if not cb:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    return summarize(cb.entries)

@app.get("/api/export")
def export(cashbook: Optional[str] = None, user: User = Depends(require_user), db: Session = Depends(get_db)):
    if cashbook:
        name = sanitize_cashbook_name(cashbook)
        cb = db.query(Cashbook).filter(Cashbook.owner == user, Cashbook.name == name).first()
        if not cb:
            raise HTTPException(status_code=404, detail="Cashbook not found")
        payload = {
            "username": user.username,
            "cashbooks": {
                name: [{"id": e.id, "date": e.date, "type": e.type, "amount": e.amount, "note": e.note} for e in cb.entries]
            }
        }
    else:
        payload = {
            "username": user.username,
            "cashbooks": {
                c.name: [{"id": e.id, "date": e.date, "type": e.type, "amount": e.amount, "note": e.note} for e in c.entries] for c in user.cashbooks
            }
        }
    return JSONResponse(payload)

@app.get("/api/health", include_in_schema=False)
def health():
    return {"status": "ok"}

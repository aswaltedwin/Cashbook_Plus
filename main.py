import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from passlib.context import CryptContext
from fastapi.middleware.cors import CORSMiddleware

# ---------------- CONFIG ----------------
APP_TITLE = "CashBook+"
app = FastAPI(title=APP_TITLE)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins (for development)
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

SESSION_COOKIE = "cb_session"
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# ---------------- IN-MEMORY STORAGE ----------------
# Vercel serverless functions cannot persist files
USERS: List[Dict[str, Any]] = []
SESSIONS: Dict[str, str] = {}

# ---------------- HELPERS ----------------
def read_users() -> List[Dict[str, Any]]:
    return USERS

def write_users(users: List[Dict[str, Any]]) -> None:
    global USERS
    USERS = users

def read_sessions() -> Dict[str, str]:
    return SESSIONS

def write_sessions(sessions: Dict[str, str]) -> None:
    global SESSIONS
    SESSIONS = sessions

def find_user(users: List[Dict[str, Any]], username: str) -> Optional[Dict[str, Any]]:
    for user in users:
        if user.get("username") == username:
            return user
    return None

def require_user(request: Request) -> Dict[str, Any]:
    """Dependency to get the current user from session cookie, or raise 401."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    sessions = read_sessions()
    username = sessions.get(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid session")
    users = read_users()
    user = find_user(users, username)
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

def summarize(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_in = 0.0
    total_out = 0.0
    for e in entries:
        amount = float(e.get("amount", 0) or 0)
        if e.get("type") == "cash_in":
            total_in += amount
        else:
            total_out += amount
    return {
        "total_in": round(total_in, 2),
        "total_out": round(total_out, 2),
        "balance": round(total_in - total_out, 2),
    }

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
async def register(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if len(username) < 3 or len(password) < 6:
        raise HTTPException(status_code=400, detail="Username or password too short")
    users = read_users()
    if find_user(users, username):
        raise HTTPException(status_code=409, detail="Username already exists")
    password_hash = pwd_context.hash(password)
    users.append({
        "username": username,
        "password_hash": password_hash,
        "cashbooks": {},
    })
    write_users(users)
    return {"message": "Registered successfully"}

@app.post("/api/login")
async def login(payload: Dict[str, Any], response: Response) -> Dict[str, Any]:
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    users = read_users()
    user = find_user(users, username)
    if not user or not pwd_context.verify(password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = str(uuid.uuid4())
    sessions = read_sessions()
    sessions[token] = username
    write_sessions(sessions)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24 * 7,
    )
    return {"message": "Logged in", "username": username}

@app.post("/api/logout")
async def logout(request: Request, response: Response) -> Dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        sessions = read_sessions()
        if token in sessions:
            del sessions[token]
            write_sessions(sessions)
    response.delete_cookie(SESSION_COOKIE)
    return {"message": "Logged out"}

# ---------------- CASHBOOKS -------------------
@app.post("/api/create_cashbook")
async def create_cashbook(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    name = sanitize_cashbook_name(payload.get("name", ""))
    cashbooks = user.setdefault("cashbooks", {})
    if name in cashbooks:
        raise HTTPException(status_code=409, detail="Cashbook already exists")
    cashbooks[name] = []
    users = read_users()
    for u in users:
        if u["username"] == user["username"]:
            u["cashbooks"] = cashbooks
            break
    write_users(users)
    return {"message": "Cashbook created", "name": name}

@app.get("/api/get_cashbooks")
async def get_cashbooks(user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    return {"username": user.get("username"), "cashbooks": list(user.get("cashbooks", {}).keys())}

@app.delete("/api/delete_cashbook")
async def delete_cashbook(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    name = sanitize_cashbook_name(payload.get("name", ""))
    cashbooks = user.get("cashbooks", {})
    if name not in cashbooks:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    del cashbooks[name]
    users = read_users()
    for u in users:
        if u["username"] == user["username"]:
            u["cashbooks"] = cashbooks
            break
    write_users(users)
    return {"message": f"Cashbook '{name}' deleted successfully"}

@app.post("/api/add_entry")
async def add_entry(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    cashbook = sanitize_cashbook_name(payload.get("cashbook", ""))
    entry_type = payload.get("type")
    if entry_type not in ("cash_in", "cash_out"):
        raise HTTPException(status_code=400, detail="Invalid type")
    date_str = payload.get("date")
    amount = payload.get("amount")
    note = payload.get("note") or ""
    try:
        if date_str:
            datetime.strptime(date_str, "%Y-%m-%d")
        else:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
        amount = float(amount)
        if amount <= 0:
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date or amount")
    cashbooks = user.get("cashbooks", {})
    if cashbook not in cashbooks:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    entry = {
        "id": str(uuid.uuid4()),
        "date": date_str,
        "type": entry_type,
        "amount": amount,
        "note": note,
    }
    cashbooks[cashbook].append(entry)
    users = read_users()
    for u in users:
        if u["username"] == user["username"]:
            u["cashbooks"] = cashbooks
            break
    write_users(users)
    return {"message": "Entry added", "entry": entry}

@app.get("/api/get_entries")
async def get_entries(cashbook: str, user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    cashbook = sanitize_cashbook_name(cashbook)
    cashbooks = user.get("cashbooks", {})
    if cashbook not in cashbooks:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    return {"entries": cashbooks[cashbook]}

@app.delete("/api/delete_entry/{entry_id}")
async def delete_entry(entry_id: str, cashbook: str, user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    cashbook = sanitize_cashbook_name(cashbook)
    cashbooks = user.get("cashbooks", {})
    if cashbook not in cashbooks:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    entries = cashbooks[cashbook]
    new_entries = [e for e in entries if e.get("id") != entry_id]
    if len(new_entries) == len(entries):
        raise HTTPException(status_code=404, detail="Entry not found")
    cashbooks[cashbook] = new_entries
    users = read_users()
    for u in users:
        if u["username"] == user["username"]:
            u["cashbooks"] = cashbooks
            break
    write_users(users)
    return {"message": "Entry deleted"}

@app.get("/api/summary/{cashbook}")
async def summary(cashbook: str, user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    cashbook = sanitize_cashbook_name(cashbook)
    cashbooks = user.get("cashbooks", {})
    if cashbook not in cashbooks:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    return summarize(cashbooks[cashbook])

@app.get("/api/export")
async def export(cashbook: Optional[str] = None, user: Dict[str, Any] = Depends(require_user)) -> JSONResponse:
    if cashbook:
        name = sanitize_cashbook_name(cashbook)
        entries = user.get("cashbooks", {}).get(name)
        if entries is None:
            raise HTTPException(status_code=404, detail="Cashbook not found")
        payload = {"username": user["username"], "cashbooks": {name: entries}}
    else:
        payload = {"username": user["username"], "cashbooks": user.get("cashbooks", {})}
    return JSONResponse(payload)

@app.get("/api/health", include_in_schema=False)
def health() -> Dict[str, Any]:
    return {"status": "ok"}

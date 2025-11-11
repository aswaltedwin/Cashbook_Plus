# init_db.py (optional file for testing)
import sqlite3
conn = sqlite3.connect("data/cashbook.db")  # Local path
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password_hash TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS cashbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    UNIQUE(user_id, name),
    FOREIGN KEY(user_id) REFERENCES users(id)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    cashbook_id INTEGER,
    date TEXT,
    type TEXT,
    amount REAL,
    note TEXT,
    FOREIGN KEY(cashbook_id) REFERENCES cashbooks(id)
)""")

conn.commit()
conn.close()

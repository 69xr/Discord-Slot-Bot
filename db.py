import sqlite3
import secrets
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Optional, Any
from config import config

log = logging.getLogger("slotbot")

def init_db():
    """Initialize SQLite database with WAL mode and tables."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        cur.execute("PRAGMA journal_mode = WAL;")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER UNIQUE NOT NULL,
                owner_id INTEGER NOT NULL,
                slot_name TEXT NOT NULL,
                custom_id TEXT NOT NULL,
                purchase_date TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                thumbnail_url TEXT,
                banner_url TEXT,
                contact_link TEXT NOT NULL,
                rating REAL DEFAULT 5.0,
                vouch_count INTEGER DEFAULT 0,
                max_daily_pings INTEGER DEFAULT 2,
                penalties INTEGER DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS slot_pings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id INTEGER NOT NULL,
                ping_date TEXT NOT NULL,
                ping_count INTEGER DEFAULT 0,
                UNIQUE(slot_id, ping_date),
                FOREIGN KEY(slot_id) REFERENCES slots(id) ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS vouches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                stars INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(slot_id, user_id),
                FOREIGN KEY(slot_id) REFERENCES slots(id) ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

@contextmanager
def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()

def audit(event: str, user_id: int, details: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO audit_log (event, user_id, details, created_at) VALUES (?, ?, ?, ?)",
            (event, user_id, details, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

def generate_custom_id() -> str:
    return str(secrets.randbelow(10**16)).zfill(16)

# --- Slot CRUD ---

def get_slot_by_id(slot_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()

def get_slot_by_channel(channel_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM slots WHERE channel_id = ?", (channel_id,)).fetchone()

def get_all_slots() -> List[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM slots").fetchall()

def create_slot(
    guild_id: int,
    channel_id: int,
    owner_id: int,
    slot_name: str,
    custom_id: str,
    purchase_date: str,
    expiry_date: str,
    duration_days: int,
    thumbnail_url: Optional[str],
    banner_url: Optional[str],
    contact_link: str,
    max_daily_pings: int = 2,
) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO slots
            (guild_id, channel_id, owner_id, slot_name, custom_id,
             purchase_date, expiry_date, duration_days,
             thumbnail_url, banner_url, contact_link, max_daily_pings, penalties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                guild_id, channel_id, owner_id, slot_name, custom_id,
                purchase_date, expiry_date, duration_days,
                thumbnail_url, banner_url, contact_link, max_daily_pings,
            ),
        )
        conn.commit()
        return cur.lastrowid

def update_slot(slot_id: int, **kwargs) -> bool:
    if not kwargs:
        return False
    keys = list(kwargs.keys())
    set_clause = ", ".join(f"{k} = ?" for k in keys)
    values = [kwargs[k] for k in keys] + [slot_id]
    with get_db() as conn:
        conn.execute(f"UPDATE slots SET {set_clause} WHERE id = ?", values)
        conn.commit()
    return True

def delete_slot(slot_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        conn.commit()

# --- Pings & Penalties ---

def get_daily_pings(slot_id: int, ping_date: str) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT ping_count FROM slot_pings WHERE slot_id = ? AND ping_date = ?",
            (slot_id, ping_date),
        ).fetchone()
        return row["ping_count"] if row else 0

def increment_daily_pings(slot_id: int, ping_date: str) -> int:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO slot_pings (slot_id, ping_date, ping_count)
            VALUES (?, ?, 1)
            ON CONFLICT(slot_id, ping_date) DO UPDATE SET ping_count = ping_count + 1
        """, (slot_id, ping_date))
        conn.commit()
        row = conn.execute(
            "SELECT ping_count FROM slot_pings WHERE slot_id = ? AND ping_date = ?",
            (slot_id, ping_date),
        ).fetchone()
        return row["ping_count"] if row else 1

def add_penalty(slot_id: int) -> int:
    with get_db() as conn:
        conn.execute("UPDATE slots SET penalties = penalties + 1 WHERE id = ?", (slot_id,))
        conn.commit()
        row = conn.execute("SELECT penalties FROM slots WHERE id = ?", (slot_id,)).fetchone()
        return row["penalties"] if row else 0

def reset_penalties(slot_id: int):
    with get_db() as conn:
        conn.execute("UPDATE slots SET penalties = 0 WHERE id = ?", (slot_id,))
        conn.commit()

def set_global_ping_limit(limit: int):
    with get_db() as conn:
        conn.execute("UPDATE slots SET max_daily_pings = ?", (limit,))
        conn.commit()

# --- Vouches ---

def has_vouched(slot_id: int, user_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM vouches WHERE slot_id = ? AND user_id = ?", (slot_id, user_id)
        ).fetchone()
        return row is not None

def record_vouch(slot_id: int, user_id: int, stars: int):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO vouches (slot_id, user_id, stars, created_at) VALUES (?, ?, ?, ?)",
            (slot_id, user_id, stars, datetime.now(timezone.utc).isoformat()),
        )
        slot = conn.execute("SELECT rating, vouch_count FROM slots WHERE id = ?", (slot_id,)).fetchone()
        new_count = slot["vouch_count"] + 1
        new_rating = round(((slot["rating"] * slot["vouch_count"]) + stars) / new_count, 2)
        conn.execute(
            "UPDATE slots SET rating = ?, vouch_count = ? WHERE id = ?",
            (new_rating, new_count, slot_id),
        )
        conn.commit()

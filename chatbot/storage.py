"""SQLite-backed chat history storage.

Keeps a record of every exchange (per browser session) so the demo can
show conversation history / a simple "personalised support" trail —
without requiring a full user auth system.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "chat_history.db")


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                student_name TEXT,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                intent TEXT,
                confidence REAL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def log_message(session_id, student_name, message, response, intent, confidence):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_logs
                (session_id, student_name, message, response, intent, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                student_name,
                message,
                response,
                intent,
                confidence,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def get_history(session_id, limit=50):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT message, response, intent, confidence, created_at
            FROM chat_logs
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

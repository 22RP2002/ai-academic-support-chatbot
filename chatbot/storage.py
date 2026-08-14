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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_log_id INTEGER NOT NULL UNIQUE REFERENCES chat_logs(id),
                session_id TEXT NOT NULL,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                intent TEXT,
                rating TEXT NOT NULL CHECK (rating IN ('up', 'down')),
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def log_message(session_id, student_name, message, response, intent, confidence):
    with get_connection() as conn:
        cursor = conn.execute(
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
        return cursor.lastrowid


def get_history(session_id, limit=50):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT c.id, c.message, c.response, c.intent, c.confidence, c.created_at,
                   f.rating AS feedback_rating
            FROM chat_logs c
            LEFT JOIN feedback f ON f.chat_log_id = c.id
            WHERE c.session_id = ?
            ORDER BY c.id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def get_chat_log(chat_log_id, session_id):
    """Fetch a single logged turn, scoped to the requesting session."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, message, response, intent
            FROM chat_logs
            WHERE id = ? AND session_id = ?
            """,
            (chat_log_id, session_id),
        ).fetchone()
        return dict(row) if row else None


def log_feedback(chat_log_id, session_id, message, response, intent, rating):
    """Record a 👍/👎 rating for a chat turn.

    Returns True if a new row was inserted, False if feedback for this
    chat_log_id already existed (the UNIQUE constraint silently ignores
    the duplicate insert instead of raising).
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO feedback
                (chat_log_id, session_id, message, response, intent, rating, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_log_id,
                session_id,
                message,
                response,
                intent,
                rating,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0

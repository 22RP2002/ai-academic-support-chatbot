"""SQLite-backed chat history storage.

Keeps a record of every exchange (per browser session) so the demo can
show conversation history / a simple "personalised support" trail —
without requiring a full user auth system.

Messages are grouped into named "conversations" (a ChatGPT-style sidebar
concept). session_id remains the durable per-browser identity; a
conversation just groups a subset of that session's chat_logs rows under
a title, so the sidebar can list/switch/delete threads independently.
"""
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "chat_history.db")

TITLE_MAX_LEN = 40


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                share_id TEXT UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # Non-destructive migration: older databases (pre-sidebar feature)
        # have chat_logs without conversation_id. Existing rows simply stay
        # unattached to any conversation (they predate the concept).
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(chat_logs)")
        }
        if "conversation_id" not in existing_columns:
            conn.execute(
                "ALTER TABLE chat_logs ADD COLUMN conversation_id TEXT "
                "REFERENCES conversations(id)"
            )

        conn.commit()


def log_message(session_id, student_name, message, response, intent, confidence, conversation_id=None):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO chat_logs
                (session_id, student_name, message, response, intent, confidence, created_at, conversation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                student_name,
                message,
                response,
                intent,
                confidence,
                datetime.utcnow().isoformat(),
                conversation_id,
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


def generate_title(message):
    """Derive a short sidebar title from the first message of a conversation."""
    title = " ".join((message or "").split())
    if not title:
        return "New conversation"
    if len(title) > TITLE_MAX_LEN:
        title = title[:TITLE_MAX_LEN].rstrip() + "…"
    return title[0].upper() + title[1:]


def create_conversation(session_id, title):
    conversation_id = uuid.uuid4().hex
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, session_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, session_id, title, now, now),
        )
        conn.commit()
    return conversation_id


def touch_conversation(conversation_id):
    """Bump updated_at so recently-active conversations sort to the top."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), conversation_id),
        )
        conn.commit()


def list_conversations(session_id):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE session_id = ?
            ORDER BY updated_at DESC
            """,
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_conversation(conversation_id, session_id):
    """Fetch a conversation, scoped to the requesting session (ownership check)."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, title, share_id, created_at, updated_at
            FROM conversations
            WHERE id = ? AND session_id = ?
            """,
            (conversation_id, session_id),
        ).fetchone()
        return dict(row) if row else None


def get_conversation_messages(conversation_id, session_id, limit=200):
    """Fetch a conversation's turns, scoped to the requesting session."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT c.id, c.message, c.response, c.intent, c.confidence, c.created_at,
                   f.rating AS feedback_rating
            FROM chat_logs c
            JOIN conversations conv ON conv.id = c.conversation_id
            LEFT JOIN feedback f ON f.chat_log_id = c.id
            WHERE c.conversation_id = ? AND conv.session_id = ?
            ORDER BY c.id ASC
            LIMIT ?
            """,
            (conversation_id, session_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def delete_conversation(conversation_id, session_id):
    """Delete a conversation and its messages/feedback, scoped to the owner.

    Returns True if a conversation was actually deleted.
    """
    with get_connection() as conn:
        owned = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ? AND session_id = ?",
            (conversation_id, session_id),
        ).fetchone()
        if not owned:
            return False

        conn.execute(
            """
            DELETE FROM feedback
            WHERE chat_log_id IN (SELECT id FROM chat_logs WHERE conversation_id = ?)
            """,
            (conversation_id,),
        )
        conn.execute("DELETE FROM chat_logs WHERE conversation_id = ?", (conversation_id,))
        conn.execute(
            "DELETE FROM conversations WHERE id = ? AND session_id = ?",
            (conversation_id, session_id),
        )
        conn.commit()
        return True


def set_conversation_share(conversation_id, session_id):
    """Enable sharing for a conversation, returning its share_id.

    Idempotent: re-sharing an already-shared conversation returns the
    same share_id instead of rotating it.
    """
    conversation = get_conversation(conversation_id, session_id)
    if conversation is None:
        return None
    if conversation["share_id"]:
        return conversation["share_id"]

    share_id = secrets.token_urlsafe(16)
    with get_connection() as conn:
        conn.execute(
            "UPDATE conversations SET share_id = ? WHERE id = ? AND session_id = ?",
            (share_id, conversation_id, session_id),
        )
        conn.commit()
    return share_id


def get_conversation_by_share_id(share_id):
    """Public lookup for the read-only share view. No session/ownership check —
    the share_id itself (an unguessable token) is the access credential.
    Only non-sensitive fields are returned (no session_id).
    """
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, title FROM conversations WHERE share_id = ?",
            (share_id,),
        ).fetchone()
        return dict(row) if row else None


def get_share_messages(conversation_id):
    """Read-only transcript for a shared conversation: message/response text
    only — no intent, confidence, session_id, or internal row ids.
    """
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT message, response
            FROM chat_logs
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

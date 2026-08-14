"""AI Academic Support Chatbot — Flask application.

Serves the chat UI and a small JSON API backed by a Scikit-learn /
NLTK intent-classification chatbot engine (see chatbot/engine.py).
"""
import os
import uuid
from datetime import timedelta

from flask import Flask, abort, jsonify, render_template, request, session

from chatbot.engine import ChatEngine
from chatbot.preprocessing import extract_name
from chatbot.storage import (
    create_conversation,
    delete_conversation,
    generate_title,
    get_chat_log,
    get_conversation,
    get_conversation_by_share_id,
    get_conversation_messages,
    get_history,
    get_share_messages,
    init_db,
    list_conversations,
    log_feedback,
    log_message,
    set_conversation_share,
    touch_conversation,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
# Sidebar history relies on session_id as a durable per-browser identity, so
# the cookie needs to outlive a single browser session (default Flask
# behaviour expires it when the browser closes).
app.permanent_session_lifetime = timedelta(days=365)

init_db()
engine = ChatEngine()


@app.before_request
def ensure_session():
    session.permanent = True
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    session.setdefault("student_name", None)
    session.setdefault("conversation_id", None)


@app.route("/")
def index():
    conversation_id = session.get("conversation_id")
    current_conversation = None
    history = []

    if conversation_id:
        current_conversation = get_conversation(conversation_id, session["session_id"])
        if current_conversation is None:
            # Conversation was deleted (or belongs to a stale cookie) — fall
            # back to a fresh, empty chat instead of erroring.
            session["conversation_id"] = None
        else:
            history = get_conversation_messages(conversation_id, session["session_id"])

    return render_template(
        "index.html",
        history=history,
        student_name=session.get("student_name"),
        conversations=list_conversations(session["session_id"]),
        current_conversation_id=session.get("conversation_id"),
        current_conversation=current_conversation,
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "message is required"}), 400

    detected_name = extract_name(message)
    if detected_name:
        session["student_name"] = detected_name
        result = {
            "response": f"Nice to meet you, {detected_name}! How can I help with your studies today?",
            "intent": "introduce_name",
            "confidence": 1.0,
        }
    else:
        result = engine.get_response(message, name=session.get("student_name"))

    conversation_id = session.get("conversation_id")
    is_new_conversation = conversation_id is None
    if is_new_conversation:
        conversation_id = create_conversation(session["session_id"], generate_title(message))
        session["conversation_id"] = conversation_id
    else:
        touch_conversation(conversation_id)

    message_id = log_message(
        session_id=session["session_id"],
        student_name=session.get("student_name"),
        message=message,
        response=result["response"],
        intent=result["intent"],
        confidence=result["confidence"],
        conversation_id=conversation_id,
    )

    return jsonify(
        {
            "message_id": message_id,
            "response": result["response"],
            "intent": result["intent"],
            "confidence": result["confidence"],
            "student_name": session.get("student_name"),
            "conversation_id": conversation_id,
            "is_new_conversation": is_new_conversation,
        }
    )


@app.route("/api/history")
def history():
    return jsonify(get_history(session["session_id"]))


@app.route("/api/feedback", methods=["POST"])
def feedback():
    data = request.get_json(silent=True) or {}
    rating = data.get("rating")
    message_id = data.get("message_id")

    if rating not in ("up", "down"):
        return jsonify({"error": "rating must be 'up' or 'down'"}), 400

    try:
        message_id = int(message_id)
    except (TypeError, ValueError):
        return jsonify({"error": "message_id is required"}), 400

    chat_log = get_chat_log(message_id, session["session_id"])
    if chat_log is None:
        return jsonify({"error": "message not found for this session"}), 404

    try:
        inserted = log_feedback(
            chat_log_id=chat_log["id"],
            session_id=session["session_id"],
            message=chat_log["message"],
            response=chat_log["response"],
            intent=chat_log["intent"],
            rating=rating,
        )
    except Exception:
        return jsonify({"error": "failed to save feedback"}), 500

    return jsonify({"status": "ok", "duplicate": not inserted})


@app.route("/api/reset", methods=["POST"])
def reset():
    """Start a new chat: clears the *active* conversation pointer only.

    session_id (the durable per-browser identity) is intentionally never
    rotated here — doing so would orphan all of this browser's existing
    conversations from the sidebar. Nothing is deleted.
    """
    session["conversation_id"] = None
    session["student_name"] = None
    return jsonify({"status": "ok"})


@app.route("/api/conversations")
def conversations():
    return jsonify(list_conversations(session["session_id"]))


@app.route("/api/conversations/<conversation_id>")
def conversation_detail(conversation_id):
    conversation = get_conversation(conversation_id, session["session_id"])
    if conversation is None:
        return jsonify({"error": "conversation not found"}), 404

    session["conversation_id"] = conversation_id
    messages = get_conversation_messages(conversation_id, session["session_id"])
    return jsonify({"conversation": conversation, "messages": messages})


@app.route("/api/conversations/<conversation_id>", methods=["DELETE"])
def conversation_delete(conversation_id):
    deleted = delete_conversation(conversation_id, session["session_id"])
    if not deleted:
        return jsonify({"error": "conversation not found"}), 404

    if session.get("conversation_id") == conversation_id:
        session["conversation_id"] = None

    return jsonify({"status": "ok"})


@app.route("/api/conversations/<conversation_id>/share", methods=["POST"])
def conversation_share(conversation_id):
    share_id = set_conversation_share(conversation_id, session["session_id"])
    if share_id is None:
        return jsonify({"error": "conversation not found"}), 404

    return jsonify({"share_id": share_id, "share_url": f"/share/{share_id}"})


@app.route("/share/<share_id>")
def share_view(share_id):
    conversation = get_conversation_by_share_id(share_id)
    if conversation is None:
        abort(404)

    messages = get_share_messages(conversation["id"])
    return render_template("share.html", title=conversation["title"], messages=messages)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

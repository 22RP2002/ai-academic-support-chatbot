"""AI Academic Support Chatbot — Flask application.

Serves the chat UI and a small JSON API backed by a Scikit-learn /
NLTK intent-classification chatbot engine (see chatbot/engine.py).
"""
import os
import uuid

from flask import Flask, jsonify, render_template, request, session

from chatbot.engine import ChatEngine
from chatbot.preprocessing import extract_name
from chatbot.storage import get_chat_log, get_history, init_db, log_feedback, log_message

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

init_db()
engine = ChatEngine()


@app.before_request
def ensure_session():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    session.setdefault("student_name", None)


@app.route("/")
def index():
    history = get_history(session["session_id"])
    return render_template(
        "index.html", history=history, student_name=session.get("student_name")
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

    message_id = log_message(
        session_id=session["session_id"],
        student_name=session.get("student_name"),
        message=message,
        response=result["response"],
        intent=result["intent"],
        confidence=result["confidence"],
    )

    return jsonify(
        {
            "message_id": message_id,
            "response": result["response"],
            "intent": result["intent"],
            "confidence": result["confidence"],
            "student_name": session.get("student_name"),
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
    session["session_id"] = str(uuid.uuid4())
    session["student_name"] = None
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

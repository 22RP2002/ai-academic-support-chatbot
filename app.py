"""AI Academic Support Chatbot — Flask application.

Serves the chat UI and a small JSON API backed by a Scikit-learn /
NLTK intent-classification chatbot engine (see chatbot/engine.py).
"""
import os
import uuid

from flask import Flask, jsonify, render_template, request, session

from chatbot.engine import ChatEngine
from chatbot.preprocessing import extract_name
from chatbot.storage import get_history, init_db, log_message

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

    log_message(
        session_id=session["session_id"],
        student_name=session.get("student_name"),
        message=message,
        response=result["response"],
        intent=result["intent"],
        confidence=result["confidence"],
    )

    return jsonify(
        {
            "response": result["response"],
            "intent": result["intent"],
            "confidence": result["confidence"],
            "student_name": session.get("student_name"),
        }
    )


@app.route("/api/history")
def history():
    return jsonify(get_history(session["session_id"]))


@app.route("/api/reset", methods=["POST"])
def reset():
    session["session_id"] = str(uuid.uuid4())
    session["student_name"] = None
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

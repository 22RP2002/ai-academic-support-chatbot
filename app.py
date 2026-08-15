"""Study Workspace — Flask application.

Serves the study-workspace chat UI and a small JSON API backed by a
Scikit-learn / NLTK intent-classification chatbot engine (see
chatbot/engine.py). Academic-admin topics (exams, attendance, etc.) remain
answerable as a secondary capability; they are not the product's identity.
"""
import os
import re
import uuid
from datetime import timedelta
from functools import wraps

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from chatbot.engine import ChatEngine
from chatbot.preprocessing import extract_name
from chatbot.storage import (
    DuplicateUserError,
    create_conversation,
    create_user,
    delete_conversation,
    generate_title,
    get_chat_log_for_user,
    get_conversation,
    get_conversation_by_share_id,
    get_conversation_messages,
    get_history,
    get_share_messages,
    get_user_by_email,
    get_user_by_id,
    init_db,
    list_conversations,
    log_feedback,
    log_message,
    set_conversation_share,
    touch_conversation,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NAME_MIN_LEN = 2
NAME_MAX_LEN = 100

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
# Sidebar history relies on session_id as a durable per-browser identity, so
# the cookie needs to outlive a single browser session (default Flask
# behaviour expires it when the browser closes).
app.permanent_session_lifetime = timedelta(days=365)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,  # JS can never read the session cookie
    SESSION_COOKIE_SAMESITE="Lax",  # sent on top-level navigation, blocked cross-site
    # Only require HTTPS for the cookie once actually deployed — enforcing
    # it locally would silently break login over plain http://127.0.0.1.
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
)

init_db()
engine = ChatEngine()


@app.before_request
def ensure_session():
    session.permanent = True
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    session.setdefault("student_name", None)
    session.setdefault("conversation_id", None)


def login_required_page(view):
    """For HTML routes: redirect anonymous visitors to the login page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login_page", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def login_required_api(view):
    """For JSON API routes: a redirect is useless to fetch(), so return 401."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "authentication required"}), 401
        return view(*args, **kwargs)
    return wrapped


@app.route("/signup", methods=["GET", "POST"])
def signup_page():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("signup.html")

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""
    form_values = {"name": name, "email": email}

    if not (NAME_MIN_LEN <= len(name) <= NAME_MAX_LEN):
        flash(f"Full name must be {NAME_MIN_LEN}-{NAME_MAX_LEN} characters.", "error")
        return render_template("signup.html", **form_values), 400
    if not EMAIL_RE.match(email):
        flash("Enter a valid email address.", "error")
        return render_template("signup.html", **form_values), 400
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return render_template("signup.html", **form_values), 400
    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return render_template("signup.html", **form_values), 400
    if get_user_by_email(email):
        flash("An account with that email already exists.", "error")
        return render_template("signup.html", **form_values), 400

    try:
        user = create_user(name, email, password)
    except DuplicateUserError:
        flash("An account with that email already exists.", "error")
        return render_template("signup.html", **form_values), 400

    session.clear()
    session["user_id"] = user["id"]
    flash(f"Welcome, {user['name']}! Your account was created.", "success")
    return redirect(url_for("index"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("login.html", next=request.args.get("next", ""))

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    next_url = request.form.get("next") or ""

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.", "error")
        return render_template("login.html", email=email, next=next_url), 401

    session.clear()
    session["user_id"] = user["id"]
    flash(f"Welcome back, {user['name']}!", "success")
    return redirect(next_url if next_url.startswith("/") else url_for("index"))


@app.route("/logout", methods=["POST"])
def logout_page():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login_page"))


@app.route("/profile")
@login_required_page
def profile_page():
    user = get_user_by_id(session["user_id"])
    return render_template("profile.html", user=user)


@app.route("/")
@login_required_page
def index():
    conversation_id = session.get("conversation_id")
    current_conversation = None
    history = []

    if conversation_id:
        current_conversation = get_conversation(conversation_id, session["user_id"])
        if current_conversation is None:
            # Conversation was deleted (or belongs to a stale cookie) — fall
            # back to a fresh, empty chat instead of erroring.
            session["conversation_id"] = None
        else:
            history = get_conversation_messages(conversation_id, session["user_id"])

    return render_template(
        "index.html",
        history=history,
        student_name=session.get("student_name"),
        current_user=get_user_by_id(session["user_id"]),
        conversations=list_conversations(session["user_id"]),
        current_conversation_id=session.get("conversation_id"),
        current_conversation=current_conversation,
    )


@app.route("/api/chat", methods=["POST"])
@login_required_api
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
        conversation_id = create_conversation(
            session["user_id"], session["session_id"], generate_title(message)
        )
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
@login_required_api
def history():
    return jsonify(get_history(session["session_id"]))


@app.route("/api/feedback", methods=["POST"])
@login_required_api
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

    chat_log = get_chat_log_for_user(message_id, session["user_id"])
    if chat_log is None:
        return jsonify({"error": "message not found for this account"}), 404

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
@login_required_api
def reset():
    """Start a new chat: clears the *active* conversation pointer only.

    Nothing is deleted, and the user stays logged in.
    """
    session["conversation_id"] = None
    session["student_name"] = None
    return jsonify({"status": "ok"})


@app.route("/api/conversations")
@login_required_api
def conversations():
    return jsonify(list_conversations(session["user_id"]))


@app.route("/api/conversations/<conversation_id>")
@login_required_api
def conversation_detail(conversation_id):
    conversation = get_conversation(conversation_id, session["user_id"])
    if conversation is None:
        return jsonify({"error": "conversation not found"}), 404

    session["conversation_id"] = conversation_id
    messages = get_conversation_messages(conversation_id, session["user_id"])
    return jsonify({"conversation": conversation, "messages": messages})


@app.route("/api/conversations/<conversation_id>", methods=["DELETE"])
@login_required_api
def conversation_delete(conversation_id):
    deleted = delete_conversation(conversation_id, session["user_id"])
    if not deleted:
        return jsonify({"error": "conversation not found"}), 404

    if session.get("conversation_id") == conversation_id:
        session["conversation_id"] = None

    return jsonify({"status": "ok"})


@app.route("/api/conversations/<conversation_id>/share", methods=["POST"])
@login_required_api
def conversation_share(conversation_id):
    share_id = set_conversation_share(conversation_id, session["user_id"])
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

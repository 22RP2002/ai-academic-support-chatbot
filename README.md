# AI Academic Support Chatbot

AI-powered chatbot for personalised academic support, built with **Flask**, **NLTK**, and **Scikit-learn**.

The chatbot answers common student queries — exam schedules, assignment
deadlines, attendance policy, grading, library info, study tips, and more —
using a lightweight **intent classification** pipeline, and gives a light
personalised touch by remembering the student's name during a session.

## How it works (architecture)

```
User message
   │
   ▼
NLTK preprocessing (chatbot/preprocessing.py)
   - lowercase, strip punctuation/digits
   - tokenize (nltk.word_tokenize)
   - lemmatize (WordNetLemmatizer)
   │
   ▼
Scikit-learn pipeline (chatbot/engine.py)
   - TfidfVectorizer  → converts text to numeric features
   - LogisticRegression → predicts the intent (tag) + confidence
   │
   ▼
Response selection
   - if confidence < threshold → fallback ("noanswer") response
   - else → random response chosen from data/intents.json for that tag
   - {name} placeholder filled in if the student has shared their name
   │
   ▼
Flask app (app.py)
   - serves the chat UI (templates/index.html)
   - /api/chat JSON endpoint
   - logs every exchange to chat_history.db (SQLite) per session
```

The intent dataset (`data/intents.json`) defines ~28 intents (greetings,
course info, syllabus, timetable, exams, assignments, attendance, grading,
results, library, study tips, time management, stress management,
motivation, scholarships, fees, hostel, placements, faculty contact,
technical support, feedback, small talk, and a fallback) — each with
several example patterns and a few varied responses.

## Project structure

```
ai-academic-support-chatbot/
├── app.py                  # Flask app (routes + API)
├── train_model.py          # Standalone training script
├── requirements.txt
├── data/
│   └── intents.json        # Intents: patterns + responses
├── chatbot/
│   ├── preprocessing.py    # NLTK cleaning/tokenizing + name extraction
│   ├── engine.py           # TF-IDF + Logistic Regression training/inference
│   └── storage.py          # SQLite chat history logging
├── model/
│   └── chatbot_model.pkl   # Trained model (generated, not committed)
├── templates/
│   └── index.html          # Chat UI
└── static/
    ├── css/style.css
    └── js/script.js
```

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Train the intent classifier
#    (NLTK data - punkt/wordnet - downloads automatically on first run)
python train_model.py

# 4. Run the app
python app.py
```

Then open **http://localhost:5000** in your browser.

> Note: if you skip step 3, the app will train the model automatically
> on first startup — but running `train_model.py` explicitly is
> recommended so you can see training output for your demo/report.

## Using the chatbot

Try asking things like:

- "When are the exams?"
- "Give me some study tips"
- "What is the attendance policy?"
- "My name is Rohan" (chatbot will greet you by name afterwards)
- "How do I submit my assignment?"
- "I am stressed about exams"

Each bot reply shows the predicted **intent** and **confidence score**
under the message bubble — useful for demonstrating the ML pipeline live.

## Response feedback (👍 / 👎)

Every bot reply that comes from a real chat turn (i.e. not the static
welcome message) shows a 👍 **Helpful** / 👎 **Not Helpful** pair of
buttons under it.

How it works:

- `POST /api/chat` now also returns a `message_id` — the row id of that
  turn in the `chat_logs` table (`chatbot/storage.py`).
- Clicking a button sends `POST /api/feedback` with `{"message_id": ..., "rating": "up" | "down"}`
  via `fetch` (no page reload). `static/js/script.js` uses one delegated
  click handler on the chat window, so it works for both freshly-sent
  replies and history re-rendered from the database on page load.
- Feedback is stored in a dedicated `feedback` table in `chat_history.db`,
  alongside `chat_logs`:

  ```sql
  CREATE TABLE feedback (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      chat_log_id INTEGER NOT NULL UNIQUE REFERENCES chat_logs(id),
      session_id TEXT NOT NULL,
      message TEXT NOT NULL,
      response TEXT NOT NULL,
      intent TEXT,
      rating TEXT NOT NULL CHECK (rating IN ('up', 'down')),
      created_at TEXT NOT NULL
  )
  ```

- **Duplicate prevention** happens twice: the UI disables both buttons the
  instant one is clicked (before the request even completes), and the
  `UNIQUE` constraint on `chat_log_id` means the database itself rejects a
  second rating for the same turn even if the UI is bypassed — the insert
  is silently ignored (`INSERT OR IGNORE`) and the API reports
  `"duplicate": true` instead of erroring.
- Reloading the page preserves rated state: `get_history()` left-joins
  `feedback` onto `chat_logs`, so a previously-rated turn re-renders with
  its button already marked selected/disabled.
- Errors (network failure, bad request, DB error) never break the chat —
  `/api/feedback` returns a JSON `error` field with an appropriate status
  code (`400`/`404`/`500`), and the frontend re-enables the buttons with a
  small inline "Couldn't save feedback — try again" message on failure.
- Intent classification itself is untouched — feedback is purely additive
  logging alongside the existing `chat_logs` table.

## Extending the project

- Add more intents/patterns to `data/intents.json`, then re-run
  `python train_model.py`.
- Swap `LogisticRegression` for another classifier (e.g. `LinearSVC`,
  `MultinomialNB`) in `chatbot/engine.py` to compare accuracy.
- `chat_history.db` (SQLite) stores every conversation turn — query it
  directly, or extend `/api/history` to build an analytics dashboard.

## Tech stack

- **Flask** – web server, routing, JSON API
- **NLTK** – tokenization, lemmatization
- **Scikit-learn** – TF-IDF vectorization + Logistic Regression intent classifier
- **SQLite** – lightweight persistence for chat history
- Vanilla **HTML/CSS/JS** – chat UI (no frontend framework needed)

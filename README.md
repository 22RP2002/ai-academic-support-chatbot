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

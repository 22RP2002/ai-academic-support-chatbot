"""Intent classification engine: trains and serves the chatbot model.

Approach: TF-IDF vectorization (Scikit-learn) over lemmatized text
(NLTK) feeding a Logistic Regression classifier over intent tags
defined in data/intents.json. This is a standard bag-of-words intent
classifier — simple, explainable, and fast enough to train in seconds,
which suits a viva/demo setting.
"""
import json
import os
import random

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from chatbot.preprocessing import clean_text, ensure_nltk_data

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTENTS_PATH = os.path.join(BASE_DIR, "data", "intents.json")

# data/intents.json is always deployed (it's source, not gitignored), so
# INTENTS_PATH is fine as-is on Vercel's read-only filesystem. The trained
# model artifact is gitignored and regenerated locally, so it's normally
# absent from the deployment bundle — cache it under /tmp there instead of
# the read-only source tree. Training takes ~1-2s, so retraining on cold
# start (rather than ever finding a cached file) is an acceptable cost.
if os.environ.get("VERCEL"):
    MODEL_PATH = "/tmp/chatbot_model.pkl"
else:
    MODEL_PATH = os.path.join(BASE_DIR, "model", "chatbot_model.pkl")

CONFIDENCE_THRESHOLD = 0.35


def load_intents():
    with open(INTENTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["intents"]


def train_model(save: bool = True) -> Pipeline:
    """Train the TF-IDF + Logistic Regression intent classifier."""
    ensure_nltk_data()
    intents = load_intents()

    X, y = [], []
    for intent in intents:
        for pattern in intent["patterns"]:
            X.append(clean_text(pattern))
            y.append(intent["tag"])

    # Unigrams + sublinear TF keep the vocabulary dense enough for a small
    # pattern set; C=10 sharpens softmax probabilities so confident matches
    # score well above CONFIDENCE_THRESHOLD while genuinely unmatched input
    # still falls back to "noanswer" (see notebook exploration in README).
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 1), min_df=1, sublinear_tf=True)),
        ("clf", LogisticRegression(max_iter=2000, C=10)),
    ])
    pipeline.fit(X, y)

    if save:
        try:
            os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
            joblib.dump(pipeline, MODEL_PATH)
        except OSError:
            # Read-only filesystem (or similar) — the trained pipeline is
            # still returned and usable in-memory, just not cached to disk.
            pass

    return pipeline


class ChatEngine:
    """Loads (or trains) the model and answers user messages."""

    def __init__(self):
        ensure_nltk_data()
        self.intents = load_intents()
        self.responses_by_tag = {i["tag"]: i["responses"] for i in self.intents}

        if os.path.exists(MODEL_PATH):
            self.model = joblib.load(MODEL_PATH)
        else:
            self.model = train_model(save=True)

    def predict_intent(self, text: str):
        cleaned = clean_text(text)
        if not cleaned.strip():
            return "noanswer", 0.0

        probs = self.model.predict_proba([cleaned])[0]
        classes = self.model.classes_
        best_idx = probs.argmax()
        return classes[best_idx], float(probs[best_idx])

    def get_response(self, text: str, name: str | None = None):
        tag, confidence = self.predict_intent(text)

        if confidence < CONFIDENCE_THRESHOLD:
            tag = "noanswer"

        candidates = self.responses_by_tag.get(tag, self.responses_by_tag["noanswer"])
        response = random.choice(candidates)

        name_suffix = f" {name}" if name else ""
        response = response.replace("{name}", name_suffix)

        return {
            "response": response,
            "intent": tag,
            "confidence": round(confidence, 3),
        }

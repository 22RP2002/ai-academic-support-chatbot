"""Text preprocessing utilities built on NLTK.

Used both at training time (to vectorize intent patterns) and at
inference time (to vectorize the user's incoming message) so the
model sees text in a consistent form.
"""
import re
import string

import nltk
from nltk.stem import WordNetLemmatizer

_REQUIRED_NLTK_DATA = {
    "tokenizers/punkt": "punkt",
    "tokenizers/punkt_tab": "punkt_tab",
    "corpora/wordnet": "wordnet",
    "corpora/omw-1.4": "omw-1.4",
}


def ensure_nltk_data():
    """Download required NLTK data to a writable directory."""
    nltk_data_dir = "/tmp/nltk_data"
    os.makedirs(nltk_data_dir, exist_ok=True)

    if nltk_data_dir not in nltk.data.path:
        nltk.data.path.insert(0, nltk_data_dir)

    for path, package in _REQUIRED_NLTK_DATA.items():
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(
                package,
                download_dir=nltk_data_dir,
                quiet=True
            )


_lemmatizer = WordNetLemmatizer()
_punct_table = str.maketrans("", "", string.punctuation)


def clean_text(text: str) -> str:
    """Lowercase, strip punctuation/digits, tokenize and lemmatize."""
    text = text.lower().translate(_punct_table)
    text = re.sub(r"\d+", " ", text)

    try:
        tokens = nltk.word_tokenize(text)
    except LookupError:
        ensure_nltk_data()
        tokens = nltk.word_tokenize(text)

    lemmas = [_lemmatizer.lemmatize(tok) for tok in tokens if tok.strip()]
    return " ".join(lemmas)


_NAME_PATTERNS = [
    re.compile(r"\bmy name is ([a-zA-Z]+)\b", re.IGNORECASE),
    re.compile(r"\bcall me ([a-zA-Z]+)\b", re.IGNORECASE),
    re.compile(r"\bthis is ([a-zA-Z]+) speaking\b", re.IGNORECASE),
]


def extract_name(text: str):
    """Best-effort extraction of a student's name from free text.

    Powers the light personalization touch (README: 'personalised
    academic support') without needing a login/auth system for the demo.

    Deliberately narrow: only unambiguous introduction phrases ("my name
    is X", "call me X") are matched. Broader patterns like "I am X" or
    "I'm X" were tried and dropped — they misfire constantly on ordinary
    sentences ("I am stressed about exams" -> name "Stressed").
    """
    for pattern in _NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).capitalize()
    return None

"""Standalone training script.

Run this once (or whenever data/intents.json changes) to (re)build the
TF-IDF + Logistic Regression intent classifier and save it to
model/chatbot_model.pkl.

    python train_model.py
"""
from chatbot.engine import train_model


def main():
    print("Downloading NLTK data (if needed) and training the intent classifier...")
    pipeline = train_model(save=True)
    n_intents = len(pipeline.named_steps["clf"].classes_)
    print(f"Done. Trained on {n_intents} intents.")
    print("Model saved to model/chatbot_model.pkl")


if __name__ == "__main__":
    main()

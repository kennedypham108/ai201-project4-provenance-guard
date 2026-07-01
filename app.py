import json
import math
import os
import re
import statistics
import string
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from groq import Groq

load_dotenv()

app = Flask(__name__)

AUDIT_LOG_PATH = Path("audit_log.json")
MODEL_NAME = "llama-3.3-70b-versatile"


def get_utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_audit_log() -> list[dict[str, Any]]:
    """Read all audit-log entries from disk."""
    if not AUDIT_LOG_PATH.exists():
        return []

    try:
        with AUDIT_LOG_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_audit_entry(entry: dict[str, Any]) -> None:
    """Append one structured entry to the JSON audit log."""
    entries = load_audit_log()
    entries.append(entry)

    with AUDIT_LOG_PATH.open("w", encoding="utf-8") as file:
        json.dump(entries, file, indent=2)


def parse_llm_score(raw_content: str) -> tuple[float, str]:
    """
    Parse the Groq response.

    The model is instructed to return JSON with:
    {
      "score": 0.0-1.0,
      "reasoning": "short explanation"
    }
    """
    cleaned = raw_content.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1)
        cleaned = cleaned.replace("```", "").strip()

    parsed = json.loads(cleaned)

    score = float(parsed["score"])
    reasoning = str(parsed.get("reasoning", "")).strip()

    if not 0.0 <= score <= 1.0:
        raise ValueError("The LLM score must be between 0.0 and 1.0.")

    return round(score, 2), reasoning


def analyze_with_llm(text: str) -> dict[str, Any]:
    """
    Use Groq as the first attribution signal.

    A score near 1.0 means the text appears more AI-like.
    A score near 0.0 means the text appears more human-like.
    """
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Add it to a .env file before running the app."
        )

    client = Groq(api_key=api_key)

    system_prompt = """
You are one signal in a text-attribution system. Analyze the submitted text for
patterns that may appear AI-generated, including unusually uniform sentence
structure, generic transitions, repetitive phrasing, predictable organization,
and overly neutral or polished language.

Do not claim certainty or proof of authorship.

Return ONLY valid JSON in exactly this structure:
{
  "score": 0.0,
  "reasoning": "One short sentence explaining the main patterns."
}

The score must be between 0.0 and 1.0:
- 0.0 means strongly human-like
- 0.5 means uncertain
- 1.0 means strongly AI-like
""".strip()

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Analyze this text:\n\n{text}",
            },
        ],
    )

    raw_content = response.choices[0].message.content or ""
    score, reasoning = parse_llm_score(raw_content)

    return {
        "llm_score": score,
        "reasoning": reasoning,
    }


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Keep a numeric value inside the requested range."""
    return max(minimum, min(maximum, value))


def split_sentences(text: str) -> list[str]:
    """Split text into non-empty sentence-like units."""
    parts = re.split(r"[.!?]+", text)
    return [part.strip() for part in parts if part.strip()]


def tokenize_words(text: str) -> list[str]:
    """Return lowercase word tokens."""
    return re.findall(r"\b[\w'-]+\b", text.lower())


def analyze_stylometrics(text: str) -> dict[str, Any]:
    """
    Compute a structural AI-likelihood score using pure Python.

    Higher scores mean the writing appears more uniform and AI-like.
    """
    words = tokenize_words(text)
    sentences = split_sentences(text)

    if not words:
        return {
            "stylometric_score": 0.5,
            "metrics": {
                "sentence_length_variance": 0.0,
                "type_token_ratio": 0.0,
                "punctuation_density": 0.0,
                "average_sentence_length": 0.0,
                "word_count": 0,
                "sentence_count": 0,
            },
        }

    sentence_lengths = [
        len(tokenize_words(sentence))
        for sentence in sentences
        if tokenize_words(sentence)
    ]

    if not sentence_lengths:
        sentence_lengths = [len(words)]

    sentence_length_variance = (
        statistics.pvariance(sentence_lengths)
        if len(sentence_lengths) > 1
        else 0.0
    )

    type_token_ratio = len(set(words)) / len(words)

    punctuation_count = sum(1 for char in text if char in string.punctuation)
    punctuation_density = punctuation_count / max(len(text), 1)

    average_sentence_length = sum(sentence_lengths) / len(sentence_lengths)

    # Convert raw metrics into AI-like partial scores.
    # Lower sentence variance is treated as more uniform and therefore more AI-like.
    variance_score = 1.0 - clamp(sentence_length_variance / 120.0)

    # Moderate vocabulary diversity is often more typical of polished generated prose.
    # Very high diversity, common in short informal writing, lowers the AI-like score.
    ttr_score = clamp((0.85 - type_token_ratio) / 0.45)

    # Very low punctuation density can indicate smooth, uniform prose.
    punctuation_score = 1.0 - clamp(punctuation_density / 0.12)

    # Medium-length sentences contribute more than very short or extremely long ones.
    distance_from_target = abs(average_sentence_length - 18.0)
    average_length_score = 1.0 - clamp(distance_from_target / 18.0)

    # Very short text is unreliable, so move the score toward uncertainty.
    reliability = clamp(len(words) / 80.0, 0.25, 1.0)

    raw_score = (
        variance_score * 0.35
        + ttr_score * 0.30
        + punctuation_score * 0.20
        + average_length_score * 0.15
    )

    stylometric_score = 0.5 + (raw_score - 0.5) * reliability
    stylometric_score = round(clamp(stylometric_score), 2)

    return {
        "stylometric_score": stylometric_score,
        "metrics": {
            "sentence_length_variance": round(sentence_length_variance, 2),
            "type_token_ratio": round(type_token_ratio, 2),
            "punctuation_density": round(punctuation_density, 4),
            "average_sentence_length": round(average_sentence_length, 2),
            "word_count": len(words),
            "sentence_count": len(sentence_lengths),
        },
    }


def combine_scores(llm_score: float, stylometric_score: float) -> float:
    """Combine both signals using the Milestone 2 weighting."""
    combined = (llm_score * 0.60) + (stylometric_score * 0.40)
    return round(clamp(combined), 2)


def classify_attribution(combined_score: float) -> str:
    """
    Map the combined score to one of three categories.

    0.00-0.34 -> likely_human
    0.35-0.74 -> uncertain
    0.75-1.00 -> likely_ai
    """
    if combined_score <= 0.34:
        return "likely_human"
    if combined_score <= 0.74:
        return "uncertain"
    return "likely_ai"


@app.route("/health", methods=["GET"])
def health() -> tuple[Any, int]:
    """Simple endpoint for checking whether the API is running."""
    return jsonify({"status": "ok"}), 200


@app.route("/submit", methods=["POST"])
def submit() -> tuple[Any, int]:
    """
    Accept text and creator_id, run both signals, combine their scores,
    save an audit entry, and return a structured response.
    """
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be valid JSON."}), 400

    text = data.get("text")
    creator_id = data.get("creator_id")

    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "The text field is required and cannot be empty."}), 400

    if not isinstance(creator_id, str) or not creator_id.strip():
        return (
            jsonify({"error": "The creator_id field is required and cannot be empty."}),
            400,
        )

    text = text.strip()
    creator_id = creator_id.strip()

    try:
        llm_result = analyze_with_llm(text)
        stylometric_result = analyze_stylometrics(text)
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 500
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return (
            jsonify(
                {
                    "error": "The LLM returned an invalid response.",
                    "details": str(error),
                }
            ),
            502,
        )
    except Exception as error:
        return (
            jsonify(
                {
                    "error": "The attribution service could not complete the request.",
                    "details": str(error),
                }
            ),
            502,
        )

    content_id = str(uuid.uuid4())
    llm_score = llm_result["llm_score"]
    stylometric_score = stylometric_result["stylometric_score"]

    confidence = combine_scores(llm_score, stylometric_score)
    attribution = classify_attribution(confidence)

    # The exact transparency label will be added in Milestone 5.
    label = "Final transparency label will be added in Milestone 5."
    status = "classified"

    audit_entry = {
        "event_type": "classification",
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": get_utc_timestamp(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "stylometric_score": stylometric_score,
        "stylometric_metrics": stylometric_result["metrics"],
        "llm_reasoning": llm_result["reasoning"],
        "status": status,
    }

    try:
        save_audit_entry(audit_entry)
    except OSError as error:
        return (
            jsonify(
                {
                    "error": "The result was generated but could not be saved.",
                    "details": str(error),
                }
            ),
            500,
        )

    response_body = {
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "status": status,
        "signals": {
            "llm_score": llm_score,
            "llm_reasoning": llm_result["reasoning"],
            "stylometric_score": stylometric_score,
            "stylometric_metrics": stylometric_result["metrics"],
        },
    }

    return jsonify(response_body), 200


@app.route("/log", methods=["GET"])
def get_log() -> tuple[Any, int]:
    """Return the most recent audit-log entries."""
    entries = load_audit_log()
    return jsonify({"entries": entries[-50:]}), 200


if __name__ == "__main__":
    app.run(debug=True)

import json
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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from groq import Groq

load_dotenv()

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

AUDIT_LOG_PATH = Path("audit_log.json")
MODEL_NAME = "llama-3.3-70b-versatile"

AI_LABEL = (
    "Likely AI-generated: Our automated analysis found strong AI-like patterns "
    "in this text. This result is not proof of authorship and may be appealed "
    "by the creator."
)

HUMAN_LABEL = (
    "Likely human-written: Our automated analysis found stronger human-like "
    "patterns in this text. Automated analysis can make mistakes and does not "
    "verify authorship."
)

UNCERTAIN_LABEL = (
    "Uncertain: Our automated analysis could not confidently determine whether "
    "this text is human-written or AI-generated. No definitive attribution "
    "should be made from this result."
)


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


def write_audit_log(entries: list[dict[str, Any]]) -> None:
    """Write the full structured audit log."""
    with AUDIT_LOG_PATH.open("w", encoding="utf-8") as file:
        json.dump(entries, file, indent=2)


def save_audit_entry(entry: dict[str, Any]) -> None:
    """Append one structured entry to the audit log."""
    entries = load_audit_log()
    entries.append(entry)
    write_audit_log(entries)


def find_original_classification(content_id: str) -> dict[str, Any] | None:
    """Return the first classification entry matching a content ID."""
    for entry in load_audit_log():
        if (
            entry.get("event_type") == "classification"
            and entry.get("content_id") == content_id
        ):
            return entry
    return None


def update_classification_status(content_id: str, new_status: str) -> bool:
    """Update the original classification status in the audit log."""
    entries = load_audit_log()
    updated = False

    for entry in entries:
        if (
            entry.get("event_type") == "classification"
            and entry.get("content_id") == content_id
        ):
            entry["status"] = new_status
            updated = True

    if updated:
        write_audit_log(entries)

    return updated


def parse_llm_score(raw_content: str) -> tuple[float, str]:
    """Parse the structured JSON returned by Groq."""
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
    """Use Groq as the semantic and stylistic attribution signal."""
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
            {"role": "user", "content": f"Analyze this text:\n\n{text}"},
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
    """Compute the structural AI-likelihood signal."""
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

    variance_score = 1.0 - clamp(sentence_length_variance / 120.0)
    ttr_score = clamp((0.85 - type_token_ratio) / 0.45)
    punctuation_score = 1.0 - clamp(punctuation_density / 0.12)

    distance_from_target = abs(average_sentence_length - 18.0)
    average_length_score = 1.0 - clamp(distance_from_target / 18.0)

    reliability = clamp(len(words) / 80.0, 0.25, 1.0)

    raw_score = (
        variance_score * 0.35
        + ttr_score * 0.30
        + punctuation_score * 0.20
        + average_length_score * 0.15
    )

    stylometric_score = 0.5 + (raw_score - 0.5) * reliability

    return {
        "stylometric_score": round(clamp(stylometric_score), 2),
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
    """Combine both signals using the planned 60/40 weighting."""
    combined = (llm_score * 0.60) + (stylometric_score * 0.40)
    return round(clamp(combined), 2)


def classify_attribution(combined_score: float) -> str:
    """Map a combined score to one of the three attribution categories."""
    if combined_score <= 0.34:
        return "likely_human"
    if combined_score <= 0.74:
        return "uncertain"
    return "likely_ai"


def generate_label(attribution: str) -> str:
    """Return the exact transparency-label text from planning.md."""
    if attribution == "likely_ai":
        return AI_LABEL
    if attribution == "likely_human":
        return HUMAN_LABEL
    return UNCERTAIN_LABEL


@app.errorhandler(429)
def rate_limit_exceeded(error: Exception) -> tuple[Any, int]:
    """Return a structured rate-limit response."""
    return (
        jsonify(
            {
                "error": "Rate limit exceeded.",
                "details": str(error),
            }
        ),
        429,
    )


@app.route("/health", methods=["GET"])
def health() -> tuple[Any, int]:
    """Confirm that the API is running."""
    return jsonify({"status": "ok"}), 200


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit() -> tuple[Any, int]:
    """Run both signals, score the text, label it, and write the audit log."""
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

    if len(text) > 20000:
        return jsonify({"error": "Text must be 20,000 characters or fewer."}), 400

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
    label = generate_label(attribution)
    status = "classified"

    audit_entry = {
        "event_type": "classification",
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": get_utc_timestamp(),
        "text": text,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "llm_score": llm_score,
        "stylometric_score": stylometric_score,
        "stylometric_metrics": stylometric_result["metrics"],
        "llm_reasoning": llm_result["reasoning"],
        "appeal_filed": False,
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

    return (
        jsonify(
            {
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
        ),
        200,
    )


@app.route("/appeal", methods=["POST"])
@limiter.limit("5 per hour")
def appeal() -> tuple[Any, int]:
    """Accept a creator appeal and mark the original content under review."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be valid JSON."}), 400

    content_id = data.get("content_id")
    creator_id = data.get("creator_id")
    creator_reasoning = data.get("creator_reasoning")

    if not isinstance(content_id, str) or not content_id.strip():
        return jsonify({"error": "content_id is required."}), 400

    if not isinstance(creator_id, str) or not creator_id.strip():
        return jsonify({"error": "creator_id is required."}), 400

    if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
        return jsonify({"error": "creator_reasoning is required."}), 400

    content_id = content_id.strip()
    creator_id = creator_id.strip()
    creator_reasoning = creator_reasoning.strip()

    original = find_original_classification(content_id)

    if original is None:
        return jsonify({"error": "No classification was found for that content_id."}), 404

    if original.get("creator_id") != creator_id:
        return jsonify({"error": "creator_id does not match the original submission."}), 403

    if original.get("status") == "under_review":
        return jsonify({"error": "This content is already under review."}), 409

    if not update_classification_status(content_id, "under_review"):
        return jsonify({"error": "The original status could not be updated."}), 500

    entries = load_audit_log()
    for entry in entries:
        if (
            entry.get("event_type") == "classification"
            and entry.get("content_id") == content_id
        ):
            entry["appeal_filed"] = True
    write_audit_log(entries)

    appeal_entry = {
        "event_type": "appeal",
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": get_utc_timestamp(),
        "original_attribution": original.get("attribution"),
        "original_confidence": original.get("confidence"),
        "llm_score": original.get("llm_score"),
        "stylometric_score": original.get("stylometric_score"),
        "creator_reasoning": creator_reasoning,
        "status": "under_review",
    }

    try:
        save_audit_entry(appeal_entry)
    except OSError as error:
        return (
            jsonify(
                {
                    "error": "The status was updated but the appeal could not be logged.",
                    "details": str(error),
                }
            ),
            500,
        )

    return (
        jsonify(
            {
                "content_id": content_id,
                "message": "Your appeal has been received.",
                "status": "under_review",
            }
        ),
        200,
    )


@app.route("/log", methods=["GET"])
def get_log() -> tuple[Any, int]:
    """Return the most recent structured audit entries."""
    entries = load_audit_log()
    return jsonify({"entries": entries[-50:]}), 200


if __name__ == "__main__":
    app.run(debug=True)

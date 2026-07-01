import json
import os
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


@app.route("/health", methods=["GET"])
def health() -> tuple[Any, int]:
    """Simple endpoint for checking whether the API is running."""
    return jsonify({"status": "ok"}), 200


@app.route("/submit", methods=["POST"])
def submit() -> tuple[Any, int]:
    """
    Accept text and creator_id, run the first signal, save an audit entry,
    and return a structured response.

    Confidence and label are placeholders until Milestones 4 and 5.
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
        signal_result = analyze_with_llm(text)
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
    llm_score = signal_result["llm_score"]

    # Milestone 3 placeholders.
    attribution = "signal_1_complete"
    confidence = llm_score
    label = "First detection signal complete. Final label will be added in Milestone 5."
    status = "classified"

    audit_entry = {
        "event_type": "classification",
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": get_utc_timestamp(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "llm_reasoning": signal_result["reasoning"],
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
            "llm_reasoning": signal_result["reasoning"],
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

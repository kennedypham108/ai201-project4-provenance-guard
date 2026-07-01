# ai201-project4-provenance-guard
# Provenance Guard

Provenance Guard is a Flask API that estimates whether submitted text appears more likely to be AI-generated or human-written. It uses two independent signals, combines them into a confidence score, displays a plain-language transparency label, supports creator appeals, rate-limits submissions, and records every decision in a structured audit log.

This system does not prove authorship. Its purpose is to communicate uncertainty honestly and provide creators with a way to contest automated classifications.

## Architecture Overview

A creator sends text and a creator ID to `POST /submit`.

The system validates the request and creates a unique content ID. The submitted text then passes through two independent detection signals:

1. A Groq LLM-based signal that evaluates overall semantic and stylistic patterns.
2. A stylometric signal that measures structural properties such as sentence-length variance, vocabulary diversity, punctuation density, and average sentence length.

The two scores are combined into one AI-likelihood confidence score. That score is mapped to one of three attribution categories:

- `likely_human`
- `uncertain`
- `likely_ai`

The system then generates the matching transparency label, saves the full decision in the audit log, and returns the result as JSON.

If a creator disputes the result, they can submit the content ID, creator ID, and appeal reasoning to `POST /appeal`. The system changes the content status to `under_review` and adds the appeal to the audit log.

```text
SUBMISSION FLOW

Creator
   |
   | text + creator_id
   v
POST /submit
   |
   v
Input Validation
   |
   | validated text + generated content_id
   +-----------------------------+
   |                             |
   v                             v
Groq LLM Signal           Stylometric Signal
   |                             |
   | llm_score                  | stylometric_score
   +--------------+--------------+
                  |
                  v
          Confidence Scoring
                  |
                  v
          Attribution Decision
                  |
                  v
       Transparency Label Generator
                  |
                  v
              Audit Log
                  |
                  v
           JSON API Response


APPEAL FLOW

Creator
   |
   | content_id + creator_id + creator_reasoning
   v
POST /appeal
   |
   v
Validate Original Submission
   |
   v
Update Status to under_review
   |
   v
Save Appeal in Audit Log
   |
   v
Return Confirmation
```

## Detection Signals

### Signal 1: Groq LLM-Based Classification

The first signal uses Groq's `llama-3.3-70b-versatile` model.

It evaluates the text for patterns such as:

- Repetitive phrasing
- Generic transitions
- Uniform sentence structure
- Predictable organization
- Overly polished or neutral wording
- Semantic and stylistic consistency

The signal returns a score from `0.0` to `1.0`.

- `0.0` means strongly human-like.
- `0.5` means uncertain.
- `1.0` means strongly AI-like.

I chose this signal because an LLM can evaluate the text as a complete piece and notice patterns that are difficult to represent with simple formulas.

Its main limitation is that it may mistake formal human writing for AI-generated writing. Academic writing, professional writing, and writing from non-native English speakers may appear unusually polished or consistent. It may also miss AI-generated text that has been heavily edited by a person.

### Signal 2: Stylometric Heuristics

The second signal uses pure Python to measure structural properties of the text.

It calculates:

- Sentence-length variance
- Type-token ratio
- Punctuation density
- Average sentence length
- Word count
- Sentence count

The raw metrics are converted into a stylometric score from `0.0` to `1.0`, where higher values represent more uniform patterns associated with AI-generated writing.

I chose this signal because it is structurally different from the LLM signal. The LLM evaluates meaning and style holistically, while the stylometric signal uses measurable statistics.

Its main limitation is that short text may not provide enough data. Poetry, repetitive creative writing, and formal human writing may also receive misleading scores.

## Confidence Scoring

The final score combines the two signals using this formula:

```text
combined_score = (llm_score × 0.60) + (stylometric_score × 0.40)
```

The LLM signal receives slightly more weight because it evaluates the full writing context. The stylometric signal still contributes significantly so the system does not rely on only one detector.

The final score is rounded to two decimal places.

### Thresholds

| Combined score | Attribution | Meaning |
|---|---|---|
| `0.00–0.34` | `likely_human` | The signals lean toward human-written content. |
| `0.35–0.74` | `uncertain` | The signals are mixed or not strong enough for a confident decision. |
| `0.75–1.00` | `likely_ai` | The signals strongly lean toward AI-generated content. |

The uncertain range is intentionally wide. A false positive is more harmful than a false negative on a writing platform, so the system requires a score of at least `0.75` before displaying a likely AI-generated label.

A score of `0.60` does not mean that the system has scientifically proven a 60% chance of AI authorship. It means that the combined signals lean somewhat toward AI-like characteristics, but the evidence is not strong enough for a high-confidence AI label.

## Confidence Validation

I tested the scoring system with four categories of writing:

- Clearly AI-generated writing
- Clearly human-written informal writing
- Formal human writing
- Lightly edited AI-generated writing

For each test, I reviewed:

- LLM score
- Stylometric score
- Combined score
- Final attribution
- Stylometric metrics
- LLM reasoning

The scores are considered meaningful when clearly different writing styles produce noticeably different results and when all three attribution categories are reachable.

### Example Results

Replace these example values with the exact scores produced by your own run of `python test_scoring.py`.

#### Higher-confidence example

```text
Input type: Clearly AI-generated
LLM score: 0.88
Stylometric score: 0.72
Combined confidence: 0.82
Attribution: likely_ai
```

#### Lower-confidence example

```text
Input type: Informal human-written text
LLM score: 0.20
Stylometric score: 0.42
Combined confidence: 0.29
Attribution: likely_human
```

These results demonstrate that the scoring system does not return the same value for every input.

## Transparency Labels

The README includes the exact written text of all three required label variants.

### High-Confidence AI Label

> "Likely AI-generated: Our automated analysis found strong AI-like patterns in this text. This result is not proof of authorship and may be appealed by the creator."

### High-Confidence Human Label

> "Likely human-written: Our automated analysis found stronger human-like patterns in this text. Automated analysis can make mistakes and does not verify authorship."

### Uncertain Label

> "Uncertain: Our automated analysis could not confidently determine whether this text is human-written or AI-generated. No definitive attribution should be made from this result."

The wording avoids absolute claims. The system never says that it has proven who wrote the content.

## Appeals Workflow

Creators can contest a classification through `POST /appeal`.

The endpoint accepts:

```json
{
  "content_id": "generated-content-id",
  "creator_id": "test-user-1",
  "creator_reasoning": "I wrote this myself and can provide earlier drafts."
}
```

When an appeal is received, the system:

1. Checks that the content ID exists.
2. Confirms that the creator ID matches the original submission.
3. Stores the creator's reasoning.
4. Changes the original status from `classified` to `under_review`.
5. Marks the original classification with `appeal_filed: true`.
6. Adds a separate structured appeal entry to the audit log.
7. Returns a confirmation response.

Automated reclassification is not performed.

A human reviewer would be able to view:

- Original text
- Content ID
- Creator ID
- Attribution result
- Combined confidence score
- LLM score
- Stylometric score
- Transparency label
- Creator reasoning
- Submission timestamp
- Appeal timestamp
- Current status

## Rate Limiting

The submission endpoint uses:

```text
10 submissions per minute
100 submissions per day
```

The appeal endpoint uses:

```text
5 appeals per hour
```

Ten submissions per minute allows a normal creator to test several pieces of writing while slowing simple automated flooding attempts.

The daily limit prevents large-scale repeated use from one source.

Appeals use a stricter limit because a normal creator should not need to submit many appeals in a short period.

Flask-Limiter uses in-memory storage for local development:

```python
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)
```

### Rate-Limit Test Evidence

Run:

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://127.0.0.1:5000/submit \
    -H "Content-Type: application/json" \
    -d '{"text": "This is a test submission for rate limit testing purposes only.", "creator_id": "ratelimit-test"}'
done
```

Expected behavior:

```text
200
200
200
200
200
200
200
200
200
200
429
429
```

Replace this sample with your actual terminal output after testing.

## Audit Log

Every classification is stored in `audit_log.json`.

A classification entry includes:

```json
{
  "event_type": "classification",
  "content_id": "example-id-1",
  "creator_id": "test-user-1",
  "timestamp": "2026-06-30T12:00:00Z",
  "text": "Submitted text appears here.",
  "attribution": "uncertain",
  "confidence": 0.61,
  "label": "Uncertain: Our automated analysis could not confidently determine whether this text is human-written or AI-generated. No definitive attribution should be made from this result.",
  "llm_score": 0.66,
  "stylometric_score": 0.54,
  "appeal_filed": false,
  "status": "classified"
}
```

An appeal entry includes:

```json
{
  "event_type": "appeal",
  "content_id": "example-id-1",
  "creator_id": "test-user-1",
  "timestamp": "2026-06-30T12:15:00Z",
  "original_attribution": "uncertain",
  "original_confidence": 0.61,
  "llm_score": 0.66,
  "stylometric_score": 0.54,
  "creator_reasoning": "I wrote this myself and can provide earlier drafts.",
  "status": "under_review"
}
```

The `GET /log` endpoint returns up to the 50 most recent entries.

Before submitting the project, generate at least three real entries and replace the sample below with the actual output from your system.

### Three-Entry Audit Sample

```json
{
  "entries": [
    {
      "event_type": "classification",
      "content_id": "example-id-1",
      "creator_id": "test-user-1",
      "attribution": "likely_ai",
      "confidence": 0.82,
      "llm_score": 0.88,
      "stylometric_score": 0.72,
      "appeal_filed": true,
      "status": "under_review"
    },
    {
      "event_type": "classification",
      "content_id": "example-id-2",
      "creator_id": "test-user-2",
      "attribution": "likely_human",
      "confidence": 0.29,
      "llm_score": 0.20,
      "stylometric_score": 0.42,
      "appeal_filed": false,
      "status": "classified"
    },
    {
      "event_type": "appeal",
      "content_id": "example-id-1",
      "creator_id": "test-user-1",
      "original_attribution": "likely_ai",
      "original_confidence": 0.82,
      "creator_reasoning": "I wrote this myself and can provide earlier drafts.",
      "status": "under_review"
    }
  ]
}
```

## API Endpoints

### `GET /health`

Confirms that the application is running.

```json
{
  "status": "ok"
}
```

### `POST /submit`

Accepts text and a creator ID.

```json
{
  "text": "The text being analyzed.",
  "creator_id": "test-user-1"
}
```

Returns:

```json
{
  "content_id": "generated-id",
  "attribution": "uncertain",
  "confidence": 0.61,
  "label": "Uncertain: Our automated analysis could not confidently determine whether this text is human-written or AI-generated. No definitive attribution should be made from this result.",
  "status": "classified",
  "signals": {
    "llm_score": 0.66,
    "stylometric_score": 0.54
  }
}
```

### `POST /appeal`

Accepts a content ID, creator ID, and creator reasoning.

```json
{
  "content_id": "generated-id",
  "creator_id": "test-user-1",
  "creator_reasoning": "I wrote this myself and can provide earlier drafts."
}
```

Returns:

```json
{
  "content_id": "generated-id",
  "message": "Your appeal has been received.",
  "status": "under_review"
}
```

### `GET /log`

Returns structured classification and appeal entries.

## Setup

### 1. Clone the repository

```bash
git clone YOUR-REPOSITORY-URL
cd YOUR-REPOSITORY-NAME
```

### 2. Create a virtual environment

Mac or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

Windows Command Prompt:

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Create `.env`

```text
GROQ_API_KEY=your_real_groq_api_key
```

Do not commit `.env`.

### 5. Start the application

```bash
python app.py
```

### 6. Run tests

```bash
python test_signal.py
python test_scoring.py
python test_labels.py
```

## Known Limitations

### Formal Human Writing

Formal academic or professional writing may be misclassified as AI-generated because it often contains polished grammar, consistent sentence structure, and formal transitions. Both the LLM and stylometric signals may associate those traits with generated text.

### Short Text

A short caption or one-sentence poem may not contain enough words or sentences for reliable stylometric analysis. The system moves short-text scores closer to uncertainty, but the result may still be unreliable.

### Repetitive Poetry

Poetry may intentionally repeat words or structures. The stylometric signal may incorrectly treat this artistic repetition as AI-like uniformity.

### Non-Native English Writing

A non-native English writer may use repeated structures or formal textbook-style language. The system may mistake this consistency for AI-like writing.

### Human-Edited AI Writing

AI-generated text that has been heavily rewritten by a person may appear human-like to both signals.

### No Writing-Process Evidence

The system analyzes only the final text. It does not have access to drafts, revision history, keystroke history, or source documents.

## Spec Reflection

### How the Spec Helped

Writing the spec before implementation forced me to define the signal outputs, scoring formula, thresholds, label text, appeal behavior, and API responses before writing code.

This made implementation more consistent because the code had clear targets. For example, the exact confidence thresholds and label strings were already defined before the label-generation function was written.

### How the Implementation Diverged

The original plan treated the stylometric signal as a simple average of structural metrics. During implementation, I added a reliability adjustment for short text.

Short submissions do not provide enough statistical evidence, so the stylometric score is moved closer to `0.5`, which represents uncertainty. This change reduced the chance that one short sentence would receive an overly confident structural classification.

## AI Usage

### AI Usage Example 1: Flask App and First Signal

I directed an AI tool to generate a Flask application skeleton, a `POST /submit` endpoint, a Groq signal function, and structured JSON logging.

The AI produced the initial route and helper functions.

I reviewed and revised the output by:

- Adding request validation
- Adding UUID content IDs
- Adding structured error handling
- Requiring JSON-only Groq responses
- Adding `GET /health`
- Adding `GET /log`
- Making sure the API key came from `.env`

### AI Usage Example 2: Stylometric Signal and Confidence Scoring

I directed an AI tool to generate a second signal using sentence-length variance, type-token ratio, punctuation density, and average sentence length.

The AI produced the metric calculations and score-combination logic.

I revised the output by:

- Matching the exact `60/40` weighting from the planning document
- Matching the exact three score thresholds
- Adding a short-text reliability adjustment
- Adding raw metrics to the audit log
- Testing four different writing categories

### AI Usage Example 3: Production Features

I directed an AI tool to generate the transparency-label function, appeal endpoint, and Flask-Limiter setup.

I revised the output by:

- Matching the exact label text from `planning.md`
- Adding creator ID verification
- Preventing duplicate appeals
- Updating the original classification status
- Adding separate appeal audit entries
- Adding structured HTTP `429` responses

## Project Files

```text
app.py
planning.md
README.md
requirements.txt
test_signal.py
test_scoring.py
test_labels.py
.env.example
.gitignore
```

Generated locally:

```text
.env
audit_log.json
.venv/
```

These generated files should not be committed.
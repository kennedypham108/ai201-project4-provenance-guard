# Provenance Guard Planning

## System Overview

Provenance Guard is a text-attribution system that estimates whether a submitted piece of writing is more likely to be AI-generated or human-written. The system does not claim to prove authorship. Instead, it uses multiple detection signals, combines their results into a confidence score, and displays a transparency label that communicates uncertainty clearly.

The system also allows creators to appeal a classification. Every submission, classification decision, signal score, confidence score, and appeal is stored in a structured audit log.

## Detection Signals

### Signal 1: LLM-Based Classification

#### What It Measures

The first signal uses the Groq API with the `llama-3.3-70b-versatile` model to evaluate the writing holistically.

It examines characteristics such as:

- Repetitive phrasing
- Overly balanced sentence structure
- Generic transitions
- Predictable organization
- Excessively polished or neutral language
- Semantic and stylistic consistency

#### Output

The signal returns a floating-point score between `0.0` and `1.0`.

- `0.0` means strongly human-like.
- `0.5` means uncertain.
- `1.0` means strongly AI-like.

The function will return a structure similar to:

```json
{
  "llm_score": 0.82,
  "reasoning": "The text uses highly uniform sentence structures and generic transitions."
}
```

Only the numeric score is used in the combined confidence calculation. The short reasoning may be retained for debugging but will not be presented as proof of authorship.

#### Why This Signal Was Chosen

An LLM can evaluate the writing as a complete piece rather than only looking at individual statistics. It can notice generic transitions, unusually balanced organization, repetitive explanations, and highly polished language.

#### Blind Spots

The LLM may incorrectly classify formal human writing as AI-generated. Academic writing, professional reports, and writing from non-native English speakers may appear structured or polished even when written entirely by a person.

It may also fail to identify AI-generated text that has been heavily edited by a human.

---

### Signal 2: Stylometric Heuristics

#### What It Measures

The second signal measures structural properties of the writing using pure Python.

The signal will calculate:

1. **Sentence-length variance**
   Low variation may indicate highly uniform writing.

2. **Type-token ratio**
   This measures vocabulary diversity by dividing the number of unique words by the total number of words.

3. **Punctuation density**
   This measures how often punctuation appears compared with the total number of characters or words.

4. **Average sentence length**
   Extremely consistent medium-length sentences may contribute to a more AI-like score.

#### Output

Each metric will be converted into a partial score between `0.0` and `1.0`. These partial scores will be averaged into one stylometric score:

```json
{
  "stylometric_score": 0.67,
  "metrics": {
    "sentence_length_variance": 8.2,
    "type_token_ratio": 0.58,
    "punctuation_density": 0.04,
    "average_sentence_length": 18.5
  }
}
```

A higher stylometric score means the text contains more uniform patterns associated with AI-generated writing.

#### Why This Signal Was Chosen

This signal is independent from the LLM signal because it uses measurable statistics instead of semantic interpretation. Combining a semantic signal with a structural signal reduces dependence on a single detection method.

#### Blind Spots

Short texts may not contain enough words or sentences for reliable statistical analysis.

Poetry, repetitive creative writing, formal academic writing, and intentionally simple writing may also produce misleading results.

---

## Confidence Scoring and Uncertainty Representation

### Combined Score

Both signals produce values between `0.0` and `1.0`, where higher values mean more AI-like.

The combined AI-likelihood score will use this weighted formula:

```text
combined_score = (llm_score × 0.60) + (stylometric_score × 0.40)
```

The LLM signal receives slightly more weight because it evaluates semantic and stylistic patterns across the full text. The stylometric score still contributes significantly so the system does not rely entirely on the LLM.

The final result will be rounded to two decimal places.

### Meaning of a 0.60 Score

A score of `0.60` does not mean the system is 60% certain that AI wrote the text in a scientifically proven sense.

It means the combined signals lean somewhat toward AI-like characteristics, but the evidence is not strong enough to display a high-confidence AI label.

A `0.60` result will therefore be placed in the uncertain category.

### Classification Thresholds

The system will use three score ranges:

| Combined score | Attribution | Meaning |
|---|---|---|
| `0.00–0.34` | `likely_human` | The signals lean toward human-written content. |
| `0.35–0.74` | `uncertain` | The signals are mixed or not strong enough for a confident decision. |
| `0.75–1.00` | `likely_ai` | Both signals provide strong enough evidence for an AI-like classification. |

The uncertain range is intentionally wide because false positives are more harmful than false negatives on a writing platform.

The system requires a score of at least `0.75` before displaying the likely AI-generated label.

### Score Calibration and Testing

The scoring system will be tested with at least four types of text:

- Clearly AI-generated writing
- Clearly human-written informal writing
- Formal human writing
- Lightly edited AI-generated writing

For every test, the individual LLM score, stylometric score, combined score, and final label will be inspected.

The scores are considered meaningful when clearly different writing styles produce noticeably different results and all three label categories can be reached.

If the system consistently labels formal human writing as AI-generated, the AI threshold will be raised or the stylometric weight will be reduced.

---

## Transparency Label Design

The transparency label will communicate the result in plain language. It will not claim that the system has proven who wrote the content.

### High-Confidence AI Variant

Exact label text:

> "Likely AI-generated: Our automated analysis found strong AI-like patterns in this text. This result is not proof of authorship and may be appealed by the creator."

This label is shown when the combined score is between `0.75` and `1.00`.

### High-Confidence Human Variant

Exact label text:

> "Likely human-written: Our automated analysis found stronger human-like patterns in this text. Automated analysis can make mistakes and does not verify authorship."

This label is shown when the combined score is between `0.00` and `0.34`.

### Uncertain Variant

Exact label text:

> "Uncertain: Our automated analysis could not confidently determine whether this text is human-written or AI-generated. No definitive attribution should be made from this result."

This label is shown when the combined score is between `0.35` and `0.74`.

### Label Design Principle

The wording avoids absolute claims such as “This was written by AI.” Each label explains that automated classification is imperfect.

The AI label also reminds creators that they may appeal the decision.

---

## Appeals Workflow

### Who Can Submit an Appeal

A creator who has the submission's `content_id` may submit an appeal.

For this project, the system will also require the creator to provide the same `creator_id` connected to the original submission. This creates a basic ownership check.

### Appeal Request Information

The `POST /appeal` endpoint accepts:

```json
{
  "content_id": "generated-unique-id",
  "creator_id": "user-123",
  "creator_reasoning": "I wrote this myself and can provide earlier drafts."
}
```

The creator reasoning must not be empty.

### What Happens When an Appeal Is Received

The system will:

1. Validate that the content ID exists.
2. Confirm that the creator ID matches the original submission.
3. Store the creator's reasoning.
4. Change the content status from `classified` to `under_review`.
5. Create a structured appeal entry in the audit log.
6. Return a confirmation response.

Automated reclassification is not required.

### Information Stored in the Appeal Log

The appeal record will include:

```json
{
  "event_type": "appeal",
  "content_id": "generated-unique-id",
  "creator_id": "user-123",
  "timestamp": "2026-06-30T12:15:00Z",
  "original_attribution": "likely_ai",
  "original_confidence": 0.82,
  "creator_reasoning": "I wrote this myself and can provide earlier drafts.",
  "status": "under_review"
}
```

### What a Human Reviewer Would See

A human reviewer should be able to see:

- Content ID
- Creator ID
- Original submitted text
- Original attribution
- Combined confidence score
- LLM score
- Stylometric score
- Transparency label
- Creator's appeal reasoning
- Submission timestamp
- Appeal timestamp
- Current status

The reviewer would use this information to evaluate the appeal without treating the automated classification as definitive proof.

---

## Anticipated Edge Cases

### 1. Short Text

A one-sentence caption or very short poem may not contain enough words or sentences for reliable stylometric analysis.

The system may return an uncertain result or give the stylometric signal less influence when the text is below a minimum length.

### 2. Formal Human Academic Writing

A human-written research paragraph may use polished grammar, consistent structure, and formal transitions. Both signals may incorrectly associate these traits with AI-generated writing.

The wide uncertain range and high AI threshold reduce the risk of a strong false-positive label.

### 3. Repetitive Poetry

A poem may intentionally repeat words, phrases, or sentence structures. The stylometric signal may treat this artistic choice as AI-like uniformity.

The system should avoid making a high-confidence decision on very short or highly repetitive creative work.

### 4. Human-Edited AI Writing

A creator may heavily revise AI-generated text by adding personal details, sentence fragments, unusual punctuation, and varied vocabulary.

The text may appear human-like to both signals even though AI was involved.

This is a limitation because the system evaluates only the final text and does not have access to the writing process.

### 5. Non-Native English Writing

A non-native English writer may use repeated sentence structures or formal language learned from textbooks.

The model and heuristics may interpret this regularity as AI-like. The transparency labels and appeal process must therefore avoid treating the result as proof.

### 6. Extremely Long Text

Very long text may exceed the Groq model's request limits or increase processing time.

The API may enforce a maximum character count and return a validation error when the limit is exceeded.

---

## API Surface

### POST /submit

Accepts a new piece of text for attribution analysis.

#### Request

```json
{
  "text": "The text being analyzed.",
  "creator_id": "user-123"
}
```

#### Response

```json
{
  "content_id": "generated-unique-id",
  "attribution": "likely_ai",
  "confidence": 0.86,
  "label": "Likely AI-generated: Our automated analysis found strong AI-like patterns in this text. This result is not proof of authorship and may be appealed by the creator.",
  "status": "classified",
  "signals": {
    "llm_score": 0.90,
    "stylometric_score": 0.80
  }
}
```

### POST /appeal

Allows a creator to contest a classification.

#### Request

```json
{
  "content_id": "generated-unique-id",
  "creator_id": "user-123",
  "creator_reasoning": "I wrote this myself and can provide drafts showing my writing process."
}
```

#### Response

```json
{
  "content_id": "generated-unique-id",
  "message": "Your appeal has been received.",
  "status": "under_review"
}
```

### GET /log

Returns structured audit-log entries for testing and documentation.

#### Response

```json
{
  "entries": [
    {
      "event_type": "classification",
      "content_id": "generated-unique-id",
      "creator_id": "user-123",
      "timestamp": "2026-06-30T12:00:00Z",
      "attribution": "likely_ai",
      "confidence": 0.86,
      "llm_score": 0.90,
      "stylometric_score": 0.80,
      "status": "classified"
    }
  ]
}
```

### Optional GET /health

Confirms that the Flask API is running.

#### Response

```json
{
  "status": "ok"
}
```

---

## Architecture

```text
SUBMISSION FLOW

Creator
   |
   | raw text + creator_id
   v
POST /submit
   |
   | validated text
   v
Input Validation
   |
   | text + generated content_id
   +-----------------------------+
   |                             |
   v                             v
LLM Detection Signal      Stylometric Signal
   |                             |
   | llm_score                  | stylometric_score
   +--------------+--------------+
                  |
                  v
          Confidence Scoring
                  |
                  | combined AI-likelihood score
                  v
          Attribution Decision
                  |
                  | likely_human / uncertain / likely_ai
                  v
       Transparency Label Generator
                  |
                  | attribution + confidence + label
                  v
              Audit Log
                  |
                  | saved structured decision
                  v
          JSON Response to Creator


APPEAL FLOW

Creator
   |
   | content_id + creator_id + creator_reasoning
   v
POST /appeal
   |
   | validated appeal information
   v
Find Original Classification
   |
   | original decision + appeal reasoning
   v
Update Status to "under_review"
   |
   v
Store Appeal in Audit Log
   |
   v
Return Appeal Confirmation
```

The submission flow sends raw text through two independent detection signals, combines their scores, generates a transparency label, records the result in the audit log, and returns a structured response. The appeal flow uses the original content ID and creator ID, records the creator's reasoning, changes the status to `under_review`, and adds the appeal to the audit log.

---

## AI Tool Plan

### Milestone 3: Submission Endpoint and First Signal

#### Spec Sections Provided to the AI Tool

- System Overview
- Signal 1: LLM-Based Classification
- API Surface
- Architecture diagram

#### Request to the AI Tool

Ask the AI tool to generate:

- A Flask application skeleton
- A `POST /submit` route
- JSON request validation
- UUID-based content IDs
- A standalone Groq LLM signal function
- A structured JSON audit-log helper
- A `GET /log` endpoint
- Clear error handling

The first version of the endpoint may use placeholder confidence and label values until Milestone 4 and Milestone 5.

#### Verification

Before connecting the LLM function to the endpoint:

1. Call the signal function directly with several sample texts.
2. Confirm that it returns a numeric score between `0.0` and `1.0`.
3. Confirm that malformed Groq responses are handled safely.
4. Start Flask and test `POST /submit` with `curl`.
5. Verify that every submission receives a unique content ID.
6. Verify that the audit log records the submission.

### Milestone 4: Second Signal and Confidence Scoring

#### Spec Sections Provided to the AI Tool

- Detection Signals
- Confidence Scoring and Uncertainty Representation
- Anticipated Edge Cases
- Architecture diagram

#### Request to the AI Tool

Ask the AI tool to generate:

- A standalone stylometric signal function
- Sentence-length variance calculation
- Type-token ratio calculation
- Punctuation-density calculation
- Average sentence-length calculation
- Conversion of those metrics into a `0.0–1.0` stylometric score
- The weighted combined-score function
- The three-way attribution function using the exact thresholds in this document

#### Verification

Test at least four inputs:

1. Clearly AI-generated text
2. Clearly human-written informal text
3. Formal human writing
4. Lightly edited AI-generated text

For each test:

- Print the LLM score.
- Print the stylometric score.
- Print the combined score.
- Print the attribution result.
- Confirm that noticeably different texts receive noticeably different scores.
- Confirm that the calculation uses `60%` LLM and `40%` stylometric weighting.
- Confirm that the thresholds exactly match this planning document.

### Milestone 5: Production Layer

#### Spec Sections Provided to the AI Tool

- Transparency Label Design
- Appeals Workflow
- API Surface
- Architecture diagram

#### Request to the AI Tool

Ask the AI tool to generate:

- A label-generation function using the exact three label strings
- A `POST /appeal` endpoint
- Creator ID ownership validation
- Status updates to `under_review`
- Structured appeal audit entries
- Flask-Limiter configuration
- A limit of `10 submissions per minute` and `100 submissions per day`

#### Verification

1. Test inputs that reach all three label categories.
2. Confirm that each label exactly matches the written text in this document.
3. Submit an appeal using a valid content ID and matching creator ID.
4. Confirm that the content status changes to `under_review`.
5. Confirm that the appeal reasoning appears in `GET /log`.
6. Submit an appeal with an invalid content ID and confirm that it returns an error.
7. Submit an appeal with a mismatched creator ID and confirm that it is rejected.
8. Send 12 rapid submission requests and confirm that requests after the tenth receive HTTP `429`.
9. Confirm that at least three structured audit-log entries are visible.

---

## Planned Rate Limits

The submission endpoint will use:

```text
10 submissions per minute
100 submissions per day
```

Ten submissions per minute allows a normal creator to test several pieces of content without interruption. It also slows down simple scripts attempting to flood the endpoint.

The daily limit allows regular use while reducing large-scale automated abuse.

The appeal endpoint may use a stricter limit, such as:

```text
5 appeals per hour
```

Creators normally should not need to submit many appeals in a short period.

---

## Milestone 2 Completion Checklist

- [x] The detection signals are defined with specific outputs.
- [x] The signal-combination formula is defined.
- [x] A score of `0.60` is explained.
- [x] Three exact confidence ranges are defined.
- [x] The exact text for all three transparency labels is written.
- [x] The appeals workflow is fully defined.
- [x] A human reviewer's required information is listed.
- [x] At least two specific edge cases are identified.
- [x] The `## Architecture` section contains both flows.
- [x] The `## AI Tool Plan` covers Milestones 3, 4, and 5.

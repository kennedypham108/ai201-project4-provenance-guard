# Provenance Guard Planning

## System Overview

Provenance Guard is a text-attribution system that estimates whether a submitted piece of writing is more likely to be AI-generated or human-written. The system does not claim to prove authorship. Instead, it uses multiple detection signals, combines their results into a confidence score, and displays a transparency label that communicates uncertainty clearly.

The system also allows creators to appeal a classification. Every submission, classification decision, signal score, confidence score, and appeal is stored in a structured audit log.

## Submission Flow

A creator submits a piece of text and their creator ID through the `POST /submit` endpoint.

The system first validates that both the text and creator ID were provided. It then creates a unique content ID for the submission.

The submitted text is sent through two separate detection signals:

1. An LLM-based classification signal.
2. A stylometric heuristic signal.

Each signal returns a score between 0 and 1, where a score closer to 1 means the text appears more likely to be AI-generated.

The confidence-scoring component combines the two signal scores into one final AI-likelihood score. The system then maps that score to one of three attribution results:

- Likely human-written
- Uncertain
- Likely AI-generated

The transparency-label component selects the appropriate plain-language label based on the final score.

The system stores the full decision in the audit log, including the content ID, creator ID, timestamp, attribution result, confidence score, both signal scores, and the status of the submission.

Finally, the API returns a structured JSON response containing the content ID, attribution result, confidence score, transparency label, and status.

## Detection Signal 1: LLM-Based Classification

### What It Measures

The first signal uses the Groq API with the `llama-3.3-70b-versatile` model to evaluate the overall writing style.

It examines characteristics such as:

- Repetitive phrasing
- Overly balanced sentence structure
- Generic transitions
- Predictable organization
- Excessively polished or neutral language
- Semantic and stylistic consistency

### Output

The signal returns a score between `0.0` and `1.0`.

- `0.0` means the model believes the text strongly appears human-written.
- `1.0` means the model believes the text strongly appears AI-generated.

### Why This Signal Is Useful

An LLM can evaluate the writing holistically. It can notice patterns that may be difficult to capture with simple mathematical rules, including unnatural transitions, generic explanations, and highly uniform tone.

### Blind Spots

The LLM may incorrectly classify formal human writing as AI-generated. Academic writing, professional reports, and writing from non-native English speakers may appear structured or polished even when written entirely by a person.

It may also fail to identify AI-generated text that has been heavily edited by a human.

## Detection Signal 2: Stylometric Heuristics

### What It Measures

The second signal uses measurable properties of the writing rather than semantic interpretation.

The stylometric signal will examine:

- Sentence-length variation
- Vocabulary diversity
- Punctuation density
- Average sentence length

AI-generated writing often has more consistent sentence lengths and a more uniform writing style. Human writing may contain more irregular sentences, informal punctuation, fragments, and greater variation.

### Output

The stylometric signal returns a score between `0.0` and `1.0`.

- A lower score means the writing contains more human-like variation.
- A higher score means the writing contains more uniform patterns associated with AI-generated text.

### Why This Signal Is Useful

This signal is independent from the LLM signal because it uses mathematical measurements instead of a model's interpretation of the content.

Using both signals reduces the system's dependence on a single detection method.

### Blind Spots

Short texts may not contain enough words or sentences for reliable statistical analysis.

Poems, repetitive creative writing, formal academic writing, and intentionally simple writing may also produce misleading results.

## False-Positive Scenario

A false positive occurs when the system labels human-written work as likely AI-generated.

Because a false positive could unfairly harm a creator, the system should avoid making a strong AI classification unless the combined score is high.

For example, suppose a non-native English speaker submits a formal essay. The essay may have consistent sentence structure and careful grammar. Both signals could incorrectly interpret this consistency as evidence of AI generation.

To reduce harm, moderate scores should produce the uncertain label rather than the likely AI-generated label.

The label should explain that the system is not certain and that automated detection can make mistakes.

The creator can submit an appeal using the content ID and explain why they believe the classification is incorrect. The system will change the content status from `classified` to `under_review` and save the appeal reasoning in the audit log.

A human reviewer would then be able to examine the original submission, classification scores, and creator's explanation.

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
  "label": "This content is likely AI-generated based on our automated analysis.",
  "status": "classified"
}
```

### POST /appeal

Allows a creator to contest a classification.

#### Request

```json
{
  "content_id": "generated-unique-id",
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
   | content_id + creator_reasoning
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

The submission flow sends raw text through two independent detection signals, combines their scores, generates a transparency label, records the result in the audit log, and returns a structured response. The appeal flow uses the original content ID, records the creator's reasoning, changes the status to `under_review`, and adds the appeal to the audit log.

## Milestone 1 Completion Checklist

- [x] The complete submission path is described.
- [x] Two distinct detection signals have been selected.
- [x] Each signal's purpose, output, strengths, and blind spots are explained.
- [x] The false-positive scenario is addressed.
- [x] The required API endpoints are identified.
- [x] The submission flow and appeal flow are shown in the architecture diagram.

# Meeting Record Matching — ML Engineer Assessment

An explainable Python solution that matches CRM meetings to calendar events, reports evidence and confidence, evaluates partial labels, flags calendar duplicates, and serves predictions through a REST API.

## Quick start

Requires Python 3.10+ and the IANA timezone database. Linux/macOS with system timezone data need no pip packages. On Windows, install the small timezone-data dependency first:

```bash
python -m pip install -r requirements.txt
```

From the extracted `record-matching-assignment` directory, run the complete matching and evaluation pipeline with one command:

```bash
python -m matcher
```

The command writes `outputs/predictions.json` and `outputs/evaluation.json`. These generated results are also included in this submission. Predictions contain all 440 pairs, feature scores, reasons, warnings, duplicate candidates, unmatched IDs, and data quality findings.

Optional configuration:

```bash
python -m matcher --data-dir data --output-dir outputs --timezone America/New_York --threshold 0.68
python -m unittest discover -s tests -v
python -m matcher.api --port 8000
```

If a minimal Linux installation reports `ZoneInfoNotFoundError`, install `tzdata` with `python -m pip install tzdata`. The API uses the same pipeline and thresholds as the command-line runner. It computes results once on startup, reads no evaluation labels, and must be restarted after changing input files.

## REST API

The API binds to localhost by default. Open these URLs in a browser or use curl:

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Status and source/pair counts |
| `GET /matches` | All automatic matches |
| `GET /matches?crm_id=CRM-1001` | Matches for a CRM record |
| `GET /predict?crm_id=CRM-1001&calendar_id=CAL-A1` | Full decision and explanation for an existing pair |
| `GET /duplicates` | Possible calendar duplicate pairs |

```bash
curl "http://127.0.0.1:8000/predict?crm_id=CRM-1001&calendar_id=CAL-A1"
```

Missing required query parameters return HTTP 400. Unknown IDs/routes return HTTP 404. Responses are JSON. This is an intentionally small read-only assessment API using `ThreadingHTTPServer`, not a production internet-facing server. It accepts record IDs from the configured files, not arbitrary record uploads.

## Design and trade-offs

1. **Ingestion:** Read the two JSON arrays, preserve input files, require unique nonempty IDs, and quarantine invalid rows with reasons. Missing/invalid dates remain visible but cannot auto-match. Invalid JSON or a non-array document fails the run rather than silently dropping a source.
2. **Normalization:** Lowercase and normalize punctuation/accents for text comparison. Recognize ISO CRM dates and the explicitly observed `MM-DD/YYYY` variant (`03-15/2025`). Repair `[at]` email notation; ignore non-email participant placeholders. Do not invent people from missing values.
3. **Time:** Interpret naive timestamps in configurable `America/New_York`, based on the US East Coast locations. Respect explicit UTC/offset timestamps and compare UTC instants. Convert dates to the configured local timezone before blocking. This is an assumption, not a fact from the schema. DST is respected: the Crestview pair differs by 60 minutes after conversion, not zero. Ambiguous/nonexistent DST-local wall times are not specially resolved in this prototype.
4. **Candidates:** Exhaustively score 20 × 22 = 440 pairs; different or unknown local dates cannot auto-match. Exhaustive comparison is simple and auditable at this size. At scale, block/index by date and client before scoring. The same-day constraint will miss meetings moved across dates.
5. **Features:** Name/email-local-part equality or company token overlap supplies client evidence. Owner membership considers both organizer and attendees, because a coordinator may organize an owner's meeting. Topic uses overlap of informative subject/content tokens. Location is weak evidence: stale or conflicting modality should not veto stronger evidence.
6. **Score:** Weighted average of available features: time 0.30, client identity 0.25, topic 0.25, owner 0.15, location 0.05. Missing features are excluded from the denominator. Start-time similarity is 1.0 at ≤15 minutes, 0.85 at ≤45, 0.65 at ≤90, 0.4 at ≤180, otherwise zero. Topic is the maximum of title overlap and 0.85 × full-content overlap. Token overlap divides intersection size by the smaller token set size. Require strong client (≥0.8) or topic (≥0.5) evidence; otherwise cap the score at 0.49.
7. **Decisions:** Score ≥0.68 is `match`, 0.50–0.68 is `review`, below 0.50 is `non_match`. A review is not an automatic match. Confidence means heuristic similarity, **not a calibrated probability**; even 1.0 does not mean certainty. Thresholds and weights are hand-selected design choices, not learned probabilities. Labels were visible during development; reported performance is descriptive, not held-out validation.
8. **Duplicates/cardinality:** Flag same-day calendar pairs within 60 minutes with high participant overlap and supporting topic/location evidence. Retain both originals; label them `possible_duplicate` for review rather than destructively merging. Permit multiple cross-source matches because duplicate calendar records may represent one meeting. Flag competing matches; no forced one-to-one assignment.
9. **Status and recurrence:** Cancellation does not remove historical identity: CRM-1009 can match CAL-A10 while warning that the CRM meeting was cancelled. Recurring meetings on different dates remain separate occurrences. This system identifies meetings, not whether they actually took place.

No IDs, specific labeled outcomes, or evaluation labels are embedded in the matching logic. A test runs inference without the labels file. Embeddings/LLMs and supervised models were considered, but add dependencies, cost, or overfitting risk for only 13 labeled pairs. Plain token evidence is easier to inspect here, with known semantic-recall limitations.

## Measured results

Run on the supplied data using the default settings:

| Cross-source labeled metric | Result |
| --- | ---: |
| Evaluated pairs | 13 |
| True positives | 8 |
| True negatives | 5 |
| False positives | 0 |
| False negatives | 0 |
| Precision / Recall / F1 | 1.00 / 1.00 / 1.00 |

Only explicitly labeled pairs are evaluated. The other 427 pairs are unknown, not negatives. Label coverage is 13/440 (2.95%). Review decisions count as negative for binary metrics. No separate training/test split is claimed for this tiny label set.

The one labeled calendar duplicate, CAL-A5/CAL-A6, is detected. With one positive and no labeled negative duplicate pairs, duplicate precision/generalization cannot be established despite the nominal labeled-subset metrics of 1.0.

The pipeline emits 17 automatic matching pairs covering 16 CRM records. Unmatched CRM IDs: CRM-1003, CRM-1010, CRM-1013, CRM-1020. Some may genuinely have no counterpart; absence of a prediction is not proof of absence.

## Failure analysis and limitations

- **Known qualitative miss:** CRM-1013 and CAL-A14 appear to refer to the LP Advisory Committee prep meeting. The current token scoring does not confidently bridge the acronym/title variation and returns a non-match. This pair is unlabeled, so it is a suspected miss, not a measured false negative. More context-aware phrase/acronym normalization or semantic retrieval could help.
- **Near-duplicate ambiguity:** CAL-A5/CAL-A6 could be duplicate invitations or separate related meetings; both match CRM-1005. They are preserved and flagged. Duplicate detection can over-merge nearby similar meetings if treated as authoritative.
- **Time drift:** CRM-1016/CAL-A17 matches despite a two-hour shift, supported by client/topic evidence; a warning calls for verification. Cross-date rescheduling is deliberately not matched automatically.
- **Cancellation:** CRM-1009/CAL-A10 is a historical identity match with a cancellation warning. Consumers must not use it as an active-attendance assertion.
- **Text bias:** Short/common topic tokens and company substrings can produce false positives; exact email/name matching misses nicknames and aliases. Missing-feature reweighting can overstate scores. There is no confidence calibration or independently verified performance on unlabeled predictions.
- **Scope:** Calendar duplicate detection only; no CRM duplicate clustering, authoritative field reconciliation, recurring-series expansion, authentication, persistence, or live upstream API connectors. Supplied JSON files serve as source snapshots. End-time validity is not used in scoring. Unexpected field types outside the supplied schema are not comprehensively validated.

With more time: obtain representative hard negatives and adjudicate uncertain pairs; add timezone metadata and reschedule links; implement full schema validation; compare a semantic baseline; calibrate thresholds on a separate validation set; report independent precision/recall and confidence intervals; add candidate indexing and a production API framework with authentication and observability.

## Code organization

```text
matcher/
  normalize.py   normalization and quality warnings
  scoring.py     cross-source scores and calendar duplicate candidates
  pipeline.py    ingestion and orchestration
  evaluate.py    partial-label metrics and error report
  api.py         read-only JSON REST service
  __main__.py    single-command batch runner
 tests/          regression, edge cases, and real HTTP checks
 data/           original supplied source snapshots and labels
 outputs/        reproducible generated predictions and evaluation
```

## AI usage and time spent

This solution was generated with OpenAI Codex assistance for implementation, documentation, and test creation. Codex executed the pipeline and test suite against the supplied files. Decisions requiring review included timezone assumptions, the distinction between similarity and probability, preserving duplicate records, and excluding unlabeled pairs from evaluation. The token-based approach leaves the LPAC acronym case unresolved; this is documented rather than claiming complete recall.

Candidate time spent: **fill in your actual preparation, review, and testing time before submission**. The assistant cannot verify the candidate's total time or claim independent manual work. Review the code and assumptions before representing this submission in an interview.

## GitHub submission

The recruiter requests a GitHub repository link. Extract this ZIP, create a repository in your GitHub account, and upload the contents of this directory (including the README, source, data, tests, and outputs). Do not upload the recruiter email screenshot. Alternatively, after creating an empty repository:

```bash
git init
git add .
git commit -m "Implement explainable meeting record matcher"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Use the repository visibility and reviewer access appropriate for your assessment. This deliverable does not create or publish a GitHub repository automatically.

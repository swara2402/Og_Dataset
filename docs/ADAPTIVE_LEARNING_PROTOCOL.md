# Adaptive Learning and Human Feedback Protocol

## Purpose
Og_Dataset should improve the quality and relevance of its writing suggestions over time. The learning signal is explicit human feedback about writing quality and preservation of meaning—not AI-detector scores.

## User workflow
1. A user uploads a document and chooses a task, audience, discipline, and style.
2. The parser creates a structured representation and marks protected spans (citations, references, equations, code, names, numbers, URLs, quotations, and user-defined terms).
3. The system proposes edits with rationale, confidence, scope, and a review requirement.
4. The user accepts, rejects, or edits each suggestion, or provides an overall preference rating.
5. With separate opt-in, the system records the minimum necessary feedback and provenance.
6. Feedback is validated and aggregated. It does not immediately modify production weights or rules.
7. Periodic offline evaluation determines whether a new ranker, rule set, or model version improves results without increasing meaning drift or formatting defects.
8. A versioned release is deployed only after regression tests and rollback readiness.

## Feedback schema (conceptual)
Each feedback event should include:
- event_id, timestamp, consent_version, pseudonymous user/session ID;
- document/job ID and paragraph/suggestion ID;
- task, discipline, section, language, and selected style;
- original passage, proposed passage, and final user-approved passage only when retention is explicitly enabled;
- action: accepted, rejected, edited_then_accepted, or rated;
- optional structured reason: grammar, clarity, tone, terminology, factual drift, citation issue, verbosity, or other;
- protected-span integrity and automated quality-check results;
- dataset/model/rule/prompt versions.

Do not store full documents by default. Prefer local-only processing and aggregate feedback. Provide deletion and retention controls. Never use document content for training without explicit opt-in.

## Learning strategy
### Phase A — supervised baselines
Use rights-cleared source/revision pairs for grammar correction, clarity, simplification, coherence, and style transfer. Keep each task label and source provenance. Establish fixed train/validation/test splits before model selection.

### Phase B — preference learning
Create pairwise comparisons from explicit user choices and expert review. Train or tune a small suggestion ranker to prefer edits that users choose, subject to hard constraints for factual/meaning preservation and document integrity.

### Phase C — contextual bandit (preferred first online method)
Treat a context as task + discipline + section + style + document constraints. Actions are candidate edit strategies or candidate suggestions. Rewards come from explicit acceptance, edited acceptance, rejection, and structured quality ratings, with conservative weights and minimum sample thresholds. Use a holdout/control group, per-user privacy boundaries, exploration limits, and a rollback switch. Do not explore by making unreviewed edits to user documents.

### Phase D — offline RL / preference optimization
Only consider more complex RLHF or offline preference optimization after there is sufficient high-quality, consented preference data and a reliable reward model. Compare against supervised and contextual-bandit baselines. Prevent reward hacking with human audits and independent evaluation.

## Reward design
Positive signals: explicit acceptance; acceptance with a small user edit; expert-rated clarity, fluency, and style fit; preservation of citations and protected spans.
Negative signals: explicit rejection; user correction of factual drift; damaged citations/equations; unsupported additions; meaning changes; formatting defects.
Neutral/unknown: no action, timeout, or detector output. Absence of feedback is not acceptance.

Detector scores, including "zero AI" results, must never be used as a reward, label, success criterion, or proxy for human authorship. They are not reliable enough for that role and would incentivize detector gaming rather than good writing.

## Safety and quality gates
- Hard constraints: no invented facts/citations, no altered protected spans, no unsupported strengthening of claims, no silent edits.
- Meaning-preservation checks and human review for high-impact edits.
- Evaluate by discipline, language, document type, and user cohort to avoid optimizing only for one writing style.
- Detect feedback poisoning, repeated automated submissions, and anomalous user activity.
- Keep a frozen benchmark and compare each candidate release against the current production baseline.
- Require a minimum number of independent feedback events before any learned change is promoted.
- Keep a full model/rule/data lineage and one-step rollback path.

## Evaluation protocol
Report human pairwise preference, grammar/fluency, clarity/coherence, meaning preservation, factual drift, citation integrity, formatting fidelity, and subgroup performance. Publish confidence intervals and sample sizes. Detector scores may appear only in a separate exploratory appendix with clear limitations and no optimization claim.

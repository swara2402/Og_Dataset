# ARIES ingestion and local academic retrieval

## Safety contract

Reconstructed ARIES pairs are candidate examples, not proof of human review or semantic equivalence. The importer always sets review_status to pending_review and meaning_preserved to false. It never writes human_approved. Exact and normalized parity remain audit metadata only. A human reviewer must independently check the edit, claims, uncertainty, citations and terminology, then record reviewer_id and meaning_preserved=true before approval.

Only explicitly licensed sources with text-mining permission, licence evidence, attribution and a source URL can be imported. The allowlist is a technical gate, not legal advice; verify each source's terms and intended redistribution.

## Normalized ARIES JSONL contract

Each line must contain pair_id, paper_id, discipline, section, original_text, edited_text, edit_types, rationale, source_url, license, license_evidence, attribution, text_mining_permitted=true, exact_parity, normalized_parity and reconstruction_version. Section and edit_type values must match the canonical schema. Missing/unsupported metadata, duplicates and no-op pairs are rejected rather than inferred.

## Import command

    python scripts/import_aries_revision_pairs.py --input /path/to/aries_normalized_pairs.jsonl --output knowledge_base/datasets/aries_import_pending.jsonl --report reports/aries_import_report.json

Inspect the rejection report and every imported record. Do not merge into the canonical dataset until human review and licence clearance are complete.

## API

GET /api/v1/retrieval/examples?query=neural%20network&discipline=computer%20science&section=methods&edit_type=clarity&limit=5

The endpoint filters metadata before BM25 ranking and returns only human-approved, meaning-preserved, reviewer-attributed, licence-eligible pairs. It returns original/revised examples, rationale, attribution, source licence, paper ID and parity audit metadata. It never applies edits. BM25 is pure Python and makes no network or model calls. The frontend examples panel is implemented in the Document Workspace.

## Retrieval evaluation

Evaluation requires a separately prepared JSONL file of human relevance judgements. Each line has a query, a non-empty list of relevant eligible pair IDs, and optional filters:

    {"query":"neural network classification","relevant_pair_ids":["pair-001"],"filters":{"discipline":"computer science","section":"methods"}}

Run:

    python scripts/evaluate_retrieval.py --judgements /path/to/relevance_judgements.jsonl --k 1 --k 3 --k 5 --output reports/retrieval-evaluation.json

The report includes macro-averaged precision@k, recall@k and reciprocal-rank@k, plus per-query metrics. Labels are never inferred by the evaluator. IDs absent from the currently eligible corpus are rejected, preventing pending/unreviewed examples from being treated as ground truth. Use independent reviewers and keep query/judgement creation separate from corpus reconstruction; split relevance sets by paper ID when developing and tuning ranking behavior to avoid paper-level leakage.

No real labelled query set is bundled, so no relevance score is claimed. Once a licensed, human-approved corpus and independently judged query set exist, run the evaluator and record the results.

## Evaluation limits

Split train/evaluation by paper ID to prevent leakage. Measure precision@k and recall@k with human relevance labels. Test discipline/section/edit filters, approval gating, protected claims, uncertainty, citations, terminology, latency and index memory independently.

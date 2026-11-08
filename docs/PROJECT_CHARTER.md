# Og_Dataset Product Charter

## Working title
**Og_Dataset — Context-Aware Writing Improvement and Document Intelligence**

## Problem statement
People working with academic, technical, educational, and professional documents often need help making their writing clear, fluent, consistent, and correctly formatted without changing the underlying meaning. Existing tools commonly solve only part of this problem: grammar checkers make local corrections, paraphrasers can alter meaning or flatten disciplinary voice, and document converters can damage layout, equations, citations, tables, and styles. A further problem is that many writing tools do not learn from the preferences and corrections of the people who use them.

Og_Dataset will address this gap by providing a document-first writing improvement system that understands document structure and context, proposes transparent and reviewable edits, preserves protected content and formatting, and improves its suggestions from consented human feedback.

## Product goal
Given a supported document, the system should:
1. Parse its text and structure, including headings, paragraphs, lists, tables, citations, references, equations, code blocks, and document styles where supported.
2. Identify the document's purpose, discipline, section, audience, and requested tone.
3. Suggest context-aware improvements to grammar, clarity, coherence, concision, vocabulary, flow, and consistency.
4. Preserve factual claims, uncertainty, technical terminology, numerical values, citations, quotations, equations, and author intent.
5. Let the author compare, accept, reject, or edit every proposed change.
6. Export a professionally formatted document and a change report.
7. Learn from explicit, consented feedback, with safeguards against low-quality or unrepresentative feedback.

## Non-goals
- Do not promise or optimize for a zero score from AI-writing detectors.
- Do not claim that a detector score proves human authorship. Detector outputs can be stored only as optional, clearly labelled research observations and must not be a training reward.
- Do not fabricate citations, sources, human edits, annotations, or claims of meaning preservation.
- Do not silently rewrite or submit a user's work.
- Do not train on private uploaded documents or feedback unless the user has explicitly opted in.
- Do not ingest or redistribute a dataset merely because it is publicly downloadable.

## Research questions
- Which editing interventions improve human-rated clarity and fluency while preserving meaning?
- How do editing preferences differ by discipline, document section, language, and audience?
- Can explicit accept/reject/revision feedback improve the ranking of editing suggestions?
- Which document-parsing and export strategies best preserve DOCX, PDF, and LaTeX structure?
- How can we detect factual drift, citation damage, unsupported additions, and style homogenization?

## Success measures
Evaluate against held-out, rights-cleared data and human review. Report:
- Human preference / pairwise win rate for revised passages.
- Meaning and claim preservation, including entailment review and factual-drift rate.
- Grammar and fluency ratings.
- Clarity, coherence, concision, and discipline-appropriate style ratings.
- Citation, equation, table, and protected-token integrity.
- DOCX/LaTeX round-trip preservation and export defect rate.
- Suggestion acceptance, rejection, and user-edited acceptance rates, reported by task and user cohort.
- Privacy opt-in, deletion, and provenance completeness.

No single metric, including AI-detector output, defines success.

## System boundaries
- **Og-AWC** is the data and research layer: source registry, licence/provenance review, acquisition, normalization, deduplication, splitting, evaluation datasets, and human annotation.
- **Og_Dataset** is the product and runtime layer: document parsing, editing proposals, user review, formatting preservation, export, feedback capture, and controlled model/rule updates.
- The two repositories communicate through a versioned, validated data contract. Raw source corpora remain local or in approved storage; raw corpus text and user documents are not committed to Git.

## Delivery principles
- Start with reproducible baselines and small, rights-cleared datasets.
- Keep source-only style references separate from genuine revision pairs.
- Keep synthetic examples separate from human-authored or human-reviewed examples.
- Use deterministic rules for safe, explainable corrections and a contextual model for edits requiring semantic understanding.
- Make every suggestion reviewable and reversible.
- Promote data to training/retrieval only after rights, provenance, quality, and human-review gates pass.
- Version datasets, prompts, rules, models, and evaluation results.

# Canonical rule library

`master_rules.json` is the sole rule-pack manifest. Runtime loads only the
files registered in its `rule_sets` array. Add a pack there when introducing a
new rule family; do not create compatibility copies elsewhere in the repository.

| Pack | Responsibility |
| --- | --- |
| `grammar.json` | Conservative grammar and mechanical corrections |
| `vocabulary.json` | Context-qualified word choice, repetition and terminology consistency |
| `morphology.json` | Morphology-informed proposals from optional local NLP |
| `academic_writing.json` | Clarity, precision, coherence, evidence, genre and structure guidance |

Every rule must satisfy `schemas/rule.schema.json`. Rule records describe
decision boundaries and preservation constraints. Their presence in the
library does not imply that an automatic transformation exists: code must
implement the behavior, tests must cover it, and uncertain cases must abstain.

The deterministic engine is the only editing authority. spaCy may identify
morphological context and produce reviewable suggestions, but it does not
generate replacement paragraphs or apply edits.

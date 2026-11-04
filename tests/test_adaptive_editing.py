import json
import shutil

from backend.app.humanisation.adaptive_editing import (
    assess_editing_needs,
    load_dataset,
    load_quality_rules,
)
from backend.app.humanisation.engine import ContextualSynonymSelector, HumanisationEngine
from backend.app.core.config import Settings
from backend.app.humanisation import adaptive_editing


def test_clear_academic_text_is_a_no_op():
    result = assess_editing_needs(
        "The model was evaluated on the test set. The results are reported in Table 2."
    )
    assert result["level"] == "minimal"
    assert result["issues"] == []

    engine = HumanisationEngine(Settings())
    edit = engine._apply_rules_to_text(
        "The model was evaluated on the test set.",
        result,
        paragraph_type="body",
    )
    assert edit["revised_text"] == edit["original_text"]
    assert edit["applied_rule_ids"] == []
    assert edit["edit_scope"] == "none"


def test_local_mechanical_issues_receive_only_minimal_corrections():
    engine = HumanisationEngine(Settings())
    original = "The the model was evaluated ,and results were recorded."
    profile = assess_editing_needs(original)
    edit = engine._apply_rules_to_text(original, profile, paragraph_type="body")
    assert edit["revised_text"] == "The model was evaluated, and results were recorded."
    assert edit["applied_rule_ids"] == ["GRAMMAR-001"]
    assert edit["edit_scope"] == "phrase"
    assert edit["requires_human_review"] is True


def test_sentence_spacing_preserves_common_abbreviations_and_decimals():
    engine = HumanisationEngine(Settings())
    original = "For example, e.g.This value is 3.14 and i.e.Results are stable."
    profile = assess_editing_needs(original)
    result = engine._apply_rules_to_text(original, profile, paragraph_type="body")
    assert "e.g. This" in result["revised_text"]
    assert "i.e. Results" in result["revised_text"]
    assert "3.14" in result["revised_text"]
    assert "e. g." not in result["revised_text"]


def test_punctuation_assessment_ignores_valid_abbreviations_and_initialisms():
    clean = assess_editing_needs(
        "For example, e.g. this method uses 3.14 and i.e. the results remain stable."
    )
    assert "punctuation_spacing" not in clean["issues"]

    initialism = "The U.S.A. team reports 3.14 results."
    profile = assess_editing_needs(initialism)
    assert "punctuation_spacing" not in profile["issues"]
    result = HumanisationEngine(Settings())._apply_rules_to_text(
        initialism, profile, paragraph_type="body"
    )
    assert result["revised_text"] == initialism


def test_non_function_word_repetition_is_flagged_not_replaced():
    engine = HumanisationEngine(Settings())
    original = "The model model processes input."
    edit = engine._apply_rules_to_text(
        original, assess_editing_needs(original), paragraph_type="body"
    )
    assert edit["revised_text"] == original
    assert edit["requires_human_review"] is True


def test_long_sentences_are_review_cues_not_rewrite_orders():
    text = " ".join(["The system processes the collected data"] * 8) + "."
    result = assess_editing_needs(text)
    assert "long_sentence" in result["issues"]
    assert result["requires_human_review"] is True


def test_contextual_synonym_selection_abstains_when_uncertain_or_protected():
    selector = ContextualSynonymSelector()
    candidates = [
        {"word": "use", "part_of_speech": "verb", "context_terms": ["model"]},
        {"word": "apply", "part_of_speech": "verb", "context_terms": ["model"]},
    ]
    assert selector.select(
        "utilize", candidates, "The model will utilize the data.",
        source_part_of_speech="verb",
    ) is None
    assert selector.select(
        "CNN", [{"word": "network", "context_terms": ["image"]}],
        "The image CNN identifies disease.", protected_terms=["CNN"],
    ) is None
    assert selector.select(
        "utilize",
        [{"word": "use", "part_of_speech": "verb", "context_terms": ["model"]}],
        "The model will utilize the data.", source_part_of_speech="verb",
    ) == "use"
    assert selector.select(
        "utilize",
        [{
            "word": "use",
            "part_of_speech": "verb",
            "context_terms": ["model"],
            "domains": ["technical"],
            "sentence_structures": ["active"],
        }],
        "The model will utilize the data.",
        source_part_of_speech="verb",
        academic_domain="academic",
        sentence_structure="active",
    ) is None


def test_latest_og_dataset_rules_policy_examples_and_profile_load():
    dataset = load_dataset()
    identifiers = {rule["id"] for rule in load_quality_rules()}
    assert dataset["version"] == "1.1.0"
    assert {"GRAMMAR-001", "WORDCHOICE-001", "EVIDENCE-001"} <= identifiers
    assert len(dataset["examples"]) == 5
    assert any(example["edit_scope"] == "none" for example in dataset["examples"])
    assert "AgriSense" in dataset["reference_profile"]
    assert dataset["policy"]["default_strategy"] == "minimal_edit"
    assert dataset["terminology"] == []


def test_dataset_updates_are_reloaded_for_each_job(monkeypatch, tmp_path):
    source = adaptive_editing._DATASET_ROOT
    copied = tmp_path / "Og_Dataset"
    shutil.copytree(source, copied)
    monkeypatch.setattr(adaptive_editing, "_DATASET_ROOT", copied)
    engine = HumanisationEngine(Settings())

    rules_path = copied / "rules" / "master_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rules["version"] = "test-update"
    rules_path.write_text(json.dumps(rules), encoding="utf-8")
    engine._load_dataset()

    assert engine.dataset_version == "test-update"


def test_repeated_vocabulary_is_flagged_but_not_automatically_replaced():
    text = "The method uses the model. The model tests the model and the model repeatedly."
    engine = HumanisationEngine(Settings())
    profile = assess_editing_needs(text)
    result = engine._apply_rules_to_text(text, profile, paragraph_type="body")
    assert "repeated_vocabulary" in profile["issues"]
    assert result["revised_text"] == text
    assert result["requires_human_review"] is True



def test_custom_refinement_instruction_is_rejected_instead_of_ignored():
    import asyncio
    from backend.app.core.jobs import ParagraphState

    engine = HumanisationEngine(Settings())
    state = ParagraphState(
        id="p1",
        index=0,
        original_text="The original sentence remains unchanged.",
        paragraph_type="body",
        category="ordinary_prose",
        section=None,
        eligible=True,
    )

    try:
        asyncio.run(
            engine.refine_paragraph(
                None, state, instruction="Make this paragraph more concise."
            )
        )
    except ValueError as exc:
        assert "not supported yet" in str(exc)
    else:
        raise AssertionError("Unsupported instructions must not be silently ignored")


def test_unimplemented_style_transformation_is_rejected():
    import asyncio
    from backend.app.core.jobs import ParagraphState

    engine = HumanisationEngine(Settings())
    state = ParagraphState(
        id="p1",
        index=0,
        original_text="The original sentence remains unchanged.",
        paragraph_type="body",
        category="ordinary_prose",
        section=None,
        eligible=True,
    )

    try:
        asyncio.run(engine.refine_paragraph(None, state, style="concise"))
    except ValueError as exc:
        assert "not implemented yet" in str(exc)
    else:
        raise AssertionError("Unsupported style transformations must be rejected")

def test_runtime_terminology_rejects_unapproved_licence(monkeypatch, tmp_path):
    import json
    import shutil
    import pytest

    source = adaptive_editing._DATASET_ROOT
    copied = tmp_path / "knowledge_base"
    shutil.copytree(source, copied)
    monkeypatch.setattr(adaptive_editing, "_DATASET_ROOT", copied)
    record = {
        "term_id": "TERM-BAD",
        "term": "sample term",
        "definition": "A test-only definition.",
        "disciplines": ["computer_science"],
        "contexts": ["test context"],
        "context_terms": ["test"],
        "variants": ["sample-term"],
        "preferred_form": "sample term",
        "avoid_substitutions": [],
        "usage_note": "Test fixture.",
        "source": {"kind": "expert_curated", "reference": "test", "license": "UNKNOWN", "attribution": "test"},
        "review_status": "reviewed",
        "reviewer_id": "test-reviewer",
    }
    with (copied / "datasets" / "terminology.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")
    with pytest.raises(RuntimeError, match="unapproved licence"):
        adaptive_editing.load_terminology()



def test_sentence_segmentation_preserves_common_abbreviations_initialisms_and_decimals():
    from backend.app.text.sentences import split_sentences

    text = (
        "Dr. Smith evaluated the U.S.A. sample at 3.14 units. "
        "The result is shown in Fig. 2. It remained stable, e.g. across trials."
    )
    assert split_sentences(text) == [
        "Dr. Smith evaluated the U.S.A. sample at 3.14 units.",
        "The result is shown in Fig. 2.",
        "It remained stable, e.g. across trials.",
    ]


def test_sentence_segmentation_handles_question_and_exclamation_boundaries():
    from backend.app.text.sentences import split_sentences

    assert split_sentences("Does it work? Yes! It does.") == [
        "Does it work?", "Yes!", "It does."
    ]


def test_editing_profile_uses_abbreviation_aware_sentence_count():
    text = "Dr. Lee used the U.S.A. dataset. The model was evaluated."
    profile = assess_editing_needs(text)
    assert profile["sentence_count"] == 2

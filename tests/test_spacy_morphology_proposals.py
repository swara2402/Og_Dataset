from backend.app.engine.spacy_rule_adapter import SpacyMorphologyProposalEngine
from backend.app.providers.spacy_provider import SpacyContextProvider


class FakeMorphologyProvider:
    model_name = "fake-offline-model"

    def suggest_agreement_edits(self, text):
        start = text.index("shows")
        return [{
            "start": start,
            "end": start + len("shows"),
            "original": "shows",
            "replacement": "show",
            "subject": "results",
            "reason": "Plural subject with singular verb form."
        }]


def test_spacy_morphology_creates_reviewable_agreement_proposal():
    text = "The results shows improvement [12]."
    engine = SpacyMorphologyProposalEngine(FakeMorphologyProvider())
    proposals = engine.analyze("p1", text)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.suggested_text == "The results show improvement [12]."
    assert proposal.source_engine.value == "nlp_engine"
    assert proposal.rule_id == "MORPHOLOGY-AGREEMENT-001"
    assert proposal.requires_review is True
    assert proposal.validation["checks"]["citations"] is True


def test_spacy_morphology_skips_when_no_candidate_exists():
    class NoEditProvider(FakeMorphologyProvider):
        def suggest_agreement_edits(self, text):
            return []

    assert SpacyMorphologyProposalEngine(NoEditProvider()).analyze("p1", "The results show improvement.") == []


def test_regular_third_person_singular_inflection():
    assert SpacyContextProvider._third_person_singular("study") == "studies"
    assert SpacyContextProvider._third_person_singular("watch") == "watches"
    assert SpacyContextProvider._third_person_singular("have") == "has"

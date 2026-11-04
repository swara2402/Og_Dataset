from backend.app.providers.spacy_provider import SpacyContextProvider


def test_spacy_provider_is_optional_and_never_auto_downloads(monkeypatch):
    provider = SpacyContextProvider("model-that-does-not-exist")
    result = provider.analyze_context("The model was evaluated.")
    assert result["available"] is False
    assert provider.status()["available"] is False

class _Morph:
    def __init__(self, number):
        self.number = number

    def get(self, key):
        return [self.number] if key == "Number" and self.number else []


class _Token:
    def __init__(self, text, lemma, tag, pos, number=None, dep="", idx=0, children=None):
        self.text = text
        self.lemma_ = lemma
        self.tag_ = tag
        self.pos_ = pos
        self.lower_ = text.lower()
        self.morph = _Morph(number)
        self.dep_ = dep
        self.idx = idx
        self.children = children or []


def _agreement_provider(subject_number, verb_tag, verb_lemma, verb_text, subject_pos="NOUN", subject_dep="nsubj", coordinated=False):
    subject = _Token("results", "result", "NNS", subject_pos, subject_number, subject_dep)
    if coordinated:
        subject.children.append(_Token("and", "and", "CC", "CCONJ", dep="cc"))
        subject.children.append(_Token("models", "model", "NNS", "NOUN", "Plur", dep="conj"))
    verb = _Token(verb_text, verb_lemma, verb_tag, "VERB", idx=8, children=[subject])
    provider = SpacyContextProvider()
    provider._nlp = lambda _text: [subject, verb]
    provider.load = lambda: True
    return provider


def test_morphology_proposes_only_unambiguous_number_agreement():
    plural = _agreement_provider("Plur", "VBZ", "show", "shows")
    edits = plural.suggest_agreement_edits("The results shows improvement.")
    assert len(edits) == 1
    assert edits[0]["replacement"] == "show"
    assert edits[0]["subject"] == "results"

    singular = _agreement_provider("Sing", "VBP", "study", "study")
    edits = singular.suggest_agreement_edits("The result study the pattern.")
    assert len(edits) == 1
    assert edits[0]["replacement"] == "studies"


def test_morphology_handles_common_irregular_agreement_forms():
    cases = [
        ("Plur", "VBZ", "be", "is", "are"),
        ("Plur", "VBZ", "have", "has", "have"),
        ("Plur", "VBZ", "do", "does", "do"),
        ("Sing", "VBP", "have", "have", "has"),
        ("Sing", "VBP", "do", "do", "does"),
    ]
    for number, tag, lemma, original, expected in cases:
        provider = _agreement_provider(number, tag, lemma, original)
        edits = provider.suggest_agreement_edits(f"The subject {original} it.")
        assert edits[0]["replacement"] == expected


def test_morphology_skips_pronouns_coordinated_and_ambiguous_subjects():
    pronoun = _agreement_provider("Sing", "VBP", "show", "show", subject_pos="PRON")
    assert pronoun.suggest_agreement_edits("They show it.") == []

    coordinated = _agreement_provider("Sing", "VBP", "show", "show", coordinated=True)
    assert coordinated.suggest_agreement_edits("The result and model show it.") == []

    ambiguous = _agreement_provider(None, "VBP", "show", "show")
    assert ambiguous.suggest_agreement_edits("The result show it.") == []

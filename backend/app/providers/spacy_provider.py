"""Optional spaCy context analysis; never rewrites text or downloads models."""
from __future__ import annotations

from typing import Any


class SpacyContextProvider:
    name = "spacy"

    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        self.model_name = model_name
        self._nlp = None
        self._load_error: str | None = None

    @property
    def available(self) -> bool:
        return self._nlp is not None

    def load(self) -> bool:
        if self._nlp is not None:
            return True
        if self._load_error is not None:
            return False
        try:
            import spacy
            self._nlp = spacy.load(self.model_name)
            return True
        except (ImportError, OSError) as exc:
            self._load_error = str(exc)
            return False

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "available": self.available,
            "model": self.model_name,
            "error": self._load_error,
        }

    @staticmethod
    def _third_person_singular(lemma: str) -> str:
        irregular = {"be": "is", "have": "has", "do": "does"}
        if lemma in irregular:
            return irregular[lemma]
        if lemma.endswith(("s", "x", "z", "ch", "sh", "o")):
            return lemma + "es"
        if len(lemma) > 1 and lemma.endswith("y") and lemma[-2] not in "aeiou":
            return lemma[:-1] + "ies"
        return lemma + "s"

    def suggest_agreement_edits(self, text: str) -> list[dict[str, Any]]:
        """Return conservative subject/finite-verb agreement candidates.

        This is morphology-guided deterministic inflection, not text generation.
        Ambiguous subjects, pronouns, coordinated subjects and unsupported verb
        forms are deliberately skipped. Suggestions still require user review.
        """
        if not self.load():
            return []
        doc = self._nlp(text)
        edits: list[dict[str, Any]] = []
        for verb in doc:
            if verb.pos_ not in {"VERB", "AUX"} or verb.tag_ not in {"VBZ", "VBP", "VBD"}:
                continue
            subjects = [child for child in verb.children if child.dep_ in {"nsubj", "nsubjpass"}]
            if len(subjects) != 1:
                continue
            subject = subjects[0]
            if subject.pos_ == "PRON" or subject.lower_ in {"i", "you"}:
                continue
            if any(child.dep_ == "conj" for child in subject.children):
                continue
            numbers = subject.morph.get("Number")
            if len(numbers) != 1:
                continue
            number = numbers[0]
            lemma = verb.lemma_.casefold()
            replacement = None
            if verb.tag_ == "VBD" and lemma == "be":
                replacement = "were" if number == "Plur" else "was"
            elif verb.tag_ == "VBZ" and number == "Plur":
                if lemma == "be":
                    replacement = "are"
                elif lemma == "have":
                    replacement = "have"
                elif lemma == "do":
                    replacement = "do"
                else:
                    replacement = lemma
            elif verb.tag_ == "VBP" and number == "Sing":
                replacement = self._third_person_singular(lemma)
            if not replacement or replacement.casefold() == verb.text.casefold():
                continue
            if verb.text[:1].isupper():
                replacement = replacement[:1].upper() + replacement[1:]
            edits.append({
                "start": verb.idx,
                "end": verb.idx + len(verb.text),
                "original": verb.text,
                "replacement": replacement,
                "subject": subject.text,
                "reason": f"Finite verb form may disagree with the parsed {number.lower()} subject.",
            })
        return edits

    def analyze_context(self, text: str) -> dict[str, Any]:
        if not self.load():
            return {"available": False, "provider": self.name, "error": self._load_error}
        doc = self._nlp(text)
        return {
            "available": True,
            "provider": self.name,
            "model": self.model_name,
            "sentences": [
                {"text": sent.text, "start": sent.start_char, "end": sent.end_char,
                 "token_count": len(sent),
                 "dependency_root": sent.root.lemma_ if sent.root is not None else None}
                for sent in doc.sents
            ],
            "entities": [
                {"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char}
                for ent in doc.ents
            ],
            "tokens": [
                {"text": token.text, "pos": token.pos_, "tag": token.tag_,
                 "lemma": token.lemma_, "is_stop": token.is_stop}
                for token in doc if not token.is_space
            ],
            "note": "Context analysis only; this provider does not generate or apply edits.",
        }

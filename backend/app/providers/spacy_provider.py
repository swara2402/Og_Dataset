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

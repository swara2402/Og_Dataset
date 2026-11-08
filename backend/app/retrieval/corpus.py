from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from jsonschema import Draft202012Validator, FormatChecker
from backend.app.retrieval.bm25 import BM25Index
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "knowledge_base/datasets/revision_pairs.jsonl"
SCHEMA_PATH = ROOT / "knowledge_base/schemas/revision_pair.schema.json"
ALLOWED_LICENSES = {"CC-BY-4.0", "CC0-1.0", "CC-BY-SA-4.0", "CC-BY-3.0", "CC-BY-SA-3.0"}
def _is_https_url(value: Any) -> bool:
    """Require an absolute HTTPS URL without whitespace, credentials or bad ports."""
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        return False
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(hostname)
        and hostname.strip(".") != ""
        and parsed.username is None
        and parsed.password is None
        and (port is None or 1 <= port <= 65535)
    )


def eligible(pair: dict[str, Any]) -> bool:
    src = pair.get("source") or {}
    if not (
        pair.get("review_status") == "human_approved"
        and pair.get("meaning_preserved") is True
        and bool(pair.get("reviewer_id"))
        and src.get("kind") in {"human_revision", "public_dataset"}
        and src.get("license") in ALLOWED_LICENSES
    ):
        return False
    if src.get("kind") == "public_dataset":
        # Dataset records must retain verifiable source and licence evidence;
        # JSON Schema's optional format checking alone is not sufficient here.
        return (
            src.get("text_mining_permitted") is True
            and _is_https_url(src.get("url"))
            and _is_https_url(src.get("license_evidence"))
        )
    return True
class RevisionCorpus:
    def __init__(self, pairs: list[dict[str, Any]]):
        self.pairs = [pair for pair in pairs if eligible(pair)]
        self._indexes: dict[tuple[str | None, str | None, str | None], tuple[list[dict[str, Any]], BM25Index]] = {}
    @classmethod
    def load(cls, path: Path = DEFAULT_DATASET):
        if not path.exists(): return cls([])
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8")); validator = Draft202012Validator(schema, format_checker=FormatChecker())
        pairs=[]; ids=set(); fingerprints=set()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip(): continue
            try: pair=json.loads(line)
            except json.JSONDecodeError as exc: raise ValueError(f"Invalid JSON on line {line_no}") from exc
            errors=sorted(validator.iter_errors(pair), key=lambda e:list(e.absolute_path))
            if errors: raise ValueError(f"Invalid pair on line {line_no}: {errors[0].message}")
            if pair["pair_id"] in ids: raise ValueError(f"Duplicate pair ID on line {line_no}")
            ids.add(pair["pair_id"])
            fp=(" ".join(pair["original_text"].casefold().split()), " ".join(pair["edited_text"].casefold().split()))
            if fp in fingerprints: raise ValueError(f"Duplicate normalized pair on line {line_no}")
            fingerprints.add(fp)
            if eligible(pair): pairs.append(pair)
        return cls(pairs)
    @staticmethod
    def document(p):
        return " ".join([p["original_text"],p["edited_text"],p["rationale"],p["discipline"],p["section"],*p["edit_types"]])
    def search(self, query: str, *, discipline: str|None=None, section: str|None=None, edit_type: str|None=None, limit: int=8):
        key=(discipline.casefold() if discipline else None, section, edit_type)
        cached=self._indexes.get(key)
        if cached is None:
            rows=[p for p in self.pairs if (discipline is None or p["discipline"].casefold()==discipline.casefold())
                  and (section is None or p["section"]==section) and (edit_type is None or edit_type in p["edit_types"])]
            if not rows: return []
            cached=(rows, BM25Index([self.document(p) for p in rows]))
            self._indexes[key]=cached
        rows,index=cached
        result=[]
        for hit in index.search(query, limit=limit):
            p=rows[hit.index]; src=p["source"]; meta=p.get("aries_metadata",{})
            result.append({"pair_id":p["pair_id"],"discipline":p["discipline"],"section":p["section"],
              "edit_types":p["edit_types"],"original_text":p["original_text"],"edited_text":p["edited_text"],
              "rationale":p["rationale"],"score":round(hit.score,6),"review_status":p["review_status"],
              "paper_id":meta.get("paper_id"),"parity":{"exact":meta.get("exact_parity"),"normalized":meta.get("normalized_parity")},
              "provenance":{"kind":src["kind"],"reference":src["reference"],"url":src.get("url"),
                            "license":src["license"],"attribution":src.get("attribution")}})
        return result

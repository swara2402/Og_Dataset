from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator
from backend.app.retrieval.bm25 import BM25Index
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "knowledge_base/datasets/revision_pairs.jsonl"
SCHEMA_PATH = ROOT / "knowledge_base/schemas/revision_pair.schema.json"
ALLOWED_LICENSES = {"CC-BY-4.0", "CC0-1.0", "CC-BY-SA-4.0", "CC-BY-3.0", "CC-BY-SA-3.0"}
def eligible(pair: dict[str, Any]) -> bool:
    src = pair.get("source") or {}
    return (pair.get("review_status") == "human_approved" and pair.get("meaning_preserved") is True
            and bool(pair.get("reviewer_id")) and src.get("kind") in {"human_revision", "public_dataset"}
            and src.get("license") in ALLOWED_LICENSES
            and (src.get("kind") != "public_dataset" or src.get("text_mining_permitted") is True))
class RevisionCorpus:
    def __init__(self, pairs: list[dict[str, Any]]): self.pairs = [pair for pair in pairs if eligible(pair)]
    @classmethod
    def load(cls, path: Path = DEFAULT_DATASET):
        if not path.exists(): return cls([])
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8")); validator = Draft202012Validator(schema)
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
        rows=[p for p in self.pairs if (discipline is None or p["discipline"].casefold()==discipline.casefold())
              and (section is None or p["section"]==section) and (edit_type is None or edit_type in p["edit_types"])]
        if not rows: return []
        index=BM25Index([self.document(p) for p in rows]); result=[]
        for hit in index.search(query, limit=limit):
            p=rows[hit.index]; src=p["source"]; meta=p.get("aries_metadata",{})
            result.append({"pair_id":p["pair_id"],"discipline":p["discipline"],"section":p["section"],
              "edit_types":p["edit_types"],"original_text":p["original_text"],"edited_text":p["edited_text"],
              "rationale":p["rationale"],"score":round(hit.score,6),"review_status":p["review_status"],
              "paper_id":meta.get("paper_id"),"parity":{"exact":meta.get("exact_parity"),"normalized":meta.get("normalized_parity")},
              "provenance":{"kind":src["kind"],"reference":src["reference"],"url":src.get("url"),
                            "license":src["license"],"attribution":src.get("attribution")}})
        return result

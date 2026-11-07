from backend.app.retrieval.bm25 import BM25Index,tokenize
from backend.app.retrieval.corpus import RevisionCorpus
from scripts.import_aries_revision_pairs import map_record
from jsonschema import Draft202012Validator
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def test_tokenize(): assert tokenize("Neural-network METHODS")==["neural-network","methods"]
def test_tokenize_preserves_unicode_academic_terms():
    assert tokenize("Méthodes naïve-Bayes Ελληνικά") == ["méthodes", "naïve-bayes", "ελληνικά"]
def test_bm25_retrieves_unicode_terms():
    hits=BM25Index(["Analyse des données scientifiques","qualitative interview discussion"]).search("données scientifiques")
    assert hits and hits[0].index==0 and hits[0].score>0
def test_bm25_relevant_first():
    hits=BM25Index(["neural network classification methods","qualitative interview discussion"]).search("neural network")
    assert hits and hits[0].index==0 and hits[0].score>0
def test_empty_query(): assert BM25Index(["academic text"]).search("!!!")==[]
def test_pending_pairs_are_not_retrieved():
    p={"pair_id":"p1","discipline":"cs","section":"methods","original_text":"neural model use","edited_text":"neural model uses","edit_types":["grammar"],"rationale":"grammar fix","meaning_preserved":False,"review_status":"pending_review","reviewer_id":None,"source":{"kind":"public_dataset","reference":"paper","license":"CC-BY-4.0","attribution":"author","url":"https://example.org/paper","license_evidence":"https://example.org/license","text_mining_permitted":True}}
    assert RevisionCorpus([p]).search("neural model")==[]
def test_filtering():
    base={"section":"methods","edit_types":["clarity"],"original_text":"plant sample measurement","edited_text":"plant samples measured","rationale":"clarified","review_status":"human_approved","meaning_preserved":True,"reviewer_id":"reviewer","source":{"kind":"human_revision","reference":"r1","license":"CC0-1.0","attribution":"reviewed"}}
    a={**base,"pair_id":"a","discipline":"biology"}; b={**base,"pair_id":"b","discipline":"physics"}
    result=RevisionCorpus([a,b]).search("measurement",discipline="biology")
    assert [item["pair_id"] for item in result]==["a"]
def test_aries_import_never_marks_pair_approved():
    raw={"pair_id":"pair-1","paper_id":"paper-1","discipline":"computer science","section":"methods",
      "original_text":"The model use a neural network.","edited_text":"The model uses a neural network.",
      "edit_types":["grammar"],"rationale":"Subject-verb agreement correction.",
      "source_url":"https://example.org/paper","license":"CC-BY-4.0","license_evidence":"https://example.org/license",
      "attribution":"Author et al.","text_mining_permitted":True,"exact_parity":True,"normalized_parity":True,
      "reconstruction_version":"v4"}
    pair=map_record(raw)
    schema=json.loads((ROOT/"knowledge_base/schemas/revision_pair.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(pair))
    assert pair["review_status"]=="pending_review" and pair["meaning_preserved"] is False
    assert pair["aries_metadata"]["exact_parity"] is True



def test_approved_public_pairs_require_https_source_and_license_evidence():
    base = {
        "pair_id": "public-1",
        "discipline": "computer science",
        "section": "methods",
        "original_text": "The model use a neural network.",
        "edited_text": "The model uses a neural network.",
        "edit_types": ["grammar"],
        "rationale": "Subject-verb agreement correction.",
        "meaning_preserved": True,
        "review_status": "human_approved",
        "reviewer_id": "reviewer-1",
        "source": {
            "kind": "public_dataset",
            "reference": "paper-1",
            "license": "CC-BY-4.0",
            "attribution": "Author et al.",
            "url": "https://example.org/paper",
            "license_evidence": "https://example.org/license",
            "text_mining_permitted": True,
        },
    }
    assert len(RevisionCorpus([base]).search("neural network")) == 1

    missing_evidence = {**base, "pair_id": "public-2", "source": {**base["source"], "license_evidence": ""}}
    insecure_source = {**base, "pair_id": "public-3", "source": {**base["source"], "url": "http://example.org/paper"}}
    insecure_evidence = {**base, "pair_id": "public-4", "source": {**base["source"], "license_evidence": "javascript:alert(1)"}}
    assert RevisionCorpus([missing_evidence, insecure_source, insecure_evidence]).search("neural network") == []

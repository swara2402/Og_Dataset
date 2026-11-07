from backend.app.retrieval.bm25 import BM25Index,tokenize
from backend.app.retrieval.corpus import RevisionCorpus

def test_tokenize(): assert tokenize("Neural-network METHODS")==["neural-network","methods"]
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
    assert [x["pair_id"] for x in RevisionCorpus([a,b]).search("measurement",discipline="biology")==["a"]

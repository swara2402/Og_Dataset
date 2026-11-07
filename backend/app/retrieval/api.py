from threading import Lock
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from backend.app.retrieval.corpus import DEFAULT_DATASET, RevisionCorpus
retrieval_router=APIRouter(prefix="/retrieval",tags=["academic retrieval"])
_cache_lock=Lock()
_cached_signature=None
_cached_corpus=None

def _get_corpus():
    global _cached_signature,_cached_corpus
    stat=DEFAULT_DATASET.stat() if DEFAULT_DATASET.exists() else None
    signature=(stat.st_mtime_ns,stat.st_size) if stat else (None,None)
    with _cache_lock:
        if _cached_corpus is None or signature != _cached_signature:
            _cached_corpus=RevisionCorpus.load()
            _cached_signature=signature
        return _cached_corpus

@retrieval_router.get("/examples")
async def retrieve_examples(query: str=Query(...,min_length=2,max_length=1000),
 discipline: str|None=Query(None,min_length=1,max_length=120),
 section: Literal["abstract","introduction","literature_review","methods","results","discussion","conclusion","other"]|None=None,
 edit_type: Literal["grammar","clarity","precision","coherence","concision","terminology","punctuation","formatting"]|None=None,
 limit: int=Query(5,ge=1,le=20)):
    """Retrieve eligible local examples only; never mutates document text."""
    try: examples=_get_corpus().search(query,discipline=discipline,section=section,edit_type=edit_type,limit=limit)
    except (OSError,ValueError) as exc: raise HTTPException(503,"Local academic corpus is invalid or unavailable") from exc
    return {"query":query,"count":len(examples),"examples":examples,"retrieval":"local-bm25","applies_edits":False,
            "eligibility":"human-approved, meaning-preserved, provenance- and licence-eligible pairs only"}

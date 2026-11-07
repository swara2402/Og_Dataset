"""Strict ARIES adapter. Reconstructed pairs are always pending_review, never approved."""
import argparse, hashlib, json, re
from pathlib import Path
from urllib.parse import urlparse
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/"knowledge_base/schemas/revision_pair.schema.json"
LICENSES={"CC-BY-4.0","CC0-1.0","CC-BY-SA-4.0","CC-BY-3.0","CC-BY-SA-3.0"}
SECTIONS={"abstract","introduction","literature_review","methods","results","discussion","conclusion","other"}
TYPES={"grammar","clarity","precision","coherence","concision","terminology","punctuation","formatting"}
def canon(s): return re.sub(r"\s+"," ",s).strip().casefold()
def valid_https(value): return urlparse(value).scheme == "https" and bool(urlparse(value).netloc)
def map_record(r):
    if not isinstance(r, dict):
        raise ValueError("record must be a JSON object")
    required={"pair_id","paper_id","discipline","section","original_text","edited_text","edit_types","rationale","source_url","license","license_evidence","attribution","text_mining_permitted","exact_parity","normalized_parity","reconstruction_version"}
    missing=sorted(required-r.keys())
    if missing: raise ValueError("missing fields: "+", ".join(missing))
    if r["license"] not in LICENSES: raise ValueError("unsupported licence")
    if r["text_mining_permitted"] is not True: raise ValueError("text mining permission must be explicitly true")
    for k in ("pair_id","paper_id","discipline","original_text","edited_text","rationale","source_url","license_evidence","attribution","reconstruction_version"):
        if not isinstance(r[k],str) or not r[k].strip(): raise ValueError(f"{k} must be a non-empty string")
    if not valid_https(r["source_url"]) or not valid_https(r["license_evidence"]): raise ValueError("source and licence evidence URLs must use HTTPS")
    if r["section"] not in SECTIONS: raise ValueError("unsupported section")
    if not isinstance(r["edit_types"],list) or not r["edit_types"] or not set(r["edit_types"]).issubset(TYPES): raise ValueError("invalid edit_types")
    if not isinstance(r["exact_parity"],bool) or not isinstance(r["normalized_parity"],bool): raise ValueError("parity fields must be booleans")
    if canon(r["original_text"])==canon(r["edited_text"]): raise ValueError("no-op pair")
    digest=hashlib.sha256((canon(r["original_text"])+"\0"+canon(r["edited_text"])).encode()).hexdigest()
    safe_id=re.sub(r"[^A-Za-z0-9._-]","_",r["pair_id"])[:100]
    return {"pair_id":"aries_"+safe_id,"discipline":r["discipline"],"section":r["section"],
      "original_text":r["original_text"],"edited_text":r["edited_text"],"edit_types":sorted(set(r["edit_types"])),
      "rationale":r["rationale"],"meaning_preserved":False,"review_status":"pending_review","reviewer_id":None,
      "source":{"kind":"public_dataset","reference":r["paper_id"],"license":r["license"],"attribution":r["attribution"],
                "url":r["source_url"],"license_evidence":r["license_evidence"],"text_mining_permitted":True},
      "aries_metadata":{"paper_id":r["paper_id"],"exact_parity":r["exact_parity"],"normalized_parity":r["normalized_parity"],
        "reconstruction_version":r["reconstruction_version"],"normalized_pair_sha256":digest}}
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--report",type=Path); a=p.parse_args()
    validator=Draft202012Validator(json.loads(SCHEMA.read_text())); rows=[]; ids=set(); fps=set(); rejected=[]
    for n,line in enumerate(a.input.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try:
            row=map_record(json.loads(line)); errors=list(validator.iter_errors(row))
            if errors: raise ValueError(errors[0].message)
            if row["pair_id"] in ids: raise ValueError("duplicate pair_id")
            fp=row["aries_metadata"]["normalized_pair_sha256"]
            if fp in fps: raise ValueError("duplicate normalized pair")
            ids.add(row["pair_id"]); fps.add(fp); rows.append(row)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as e: rejected.append({"line":n,"reason":str(e)})
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8")
    report={"input_records":len(rows)+len(rejected),"imported_pending_review":len(rows),"rejected":len(rejected),"approved":0,
            "note":"Parity is audit metadata, not human approval.","rejections":rejected}
    if a.report: a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="rejections"},indent=2)); return 0 if not rejected else 2
if __name__=="__main__": raise SystemExit(main())

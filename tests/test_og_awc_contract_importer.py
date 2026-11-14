import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from scripts.import_og_awc_records import SCHEMA_PATH, convert_record, import_records

def source_record():
    return {
        "record_id":"pararev-001","source_id":"pararev","paper_id":"paper-001","record_type":"revision_pair",
        "original_text":"The results shows a difference.","revised_text":"The results show a difference.","split":"train",
        "edit_labels":["grammar","academic_register"],
        "provenance":{
            "source_url":"https://example.org/dataset","license_id":"CC-BY-NC-SA-4.0",
            "license_url":"https://creativecommons.org/licenses/by-nc-sa/4.0/","acquisition_date":"2026-11-14",
            "source_record_id":"para-001","source_article_version_id":"source-v1","source_target_id":"target-v2",
            "source_version":"abc123","source_file":"pairs.jsonl","source_row_number":1,
            "source_annotations":{"annot_1":"grammar"},"attribution":"Dataset authors, 2025.","notes":"Source notes."
        }
    }

def test_import_is_pending_and_never_claims_meaning_preserved():
    item=convert_record(source_record())
    assert item["review_status"]=="pending_review" and item["meaning_preserved"] is False
    assert item["reviewer_id"] is None and item["source"]["text_mining_permitted"] is False
    assert item["edit_types"]==["grammar"]
    assert "does not provide a verified edit rationale" in item["rationale"]
    assert item["pararev_metadata"]["paper_id"]=="paper-001"

def test_explicit_permission_is_preserved_but_does_not_approve():
    record=source_record(); record["provenance"]["text_mining_permitted"]=True
    item=convert_record(record)
    assert item["source"]["text_mining_permitted"] is True
    assert item["review_status"]=="pending_review" and item["meaning_preserved"] is False

@pytest.mark.parametrize("url",["http://example.org/data","https://user:pass@example.org/data","not-a-url"])
def test_rejects_unsafe_source_url(url):
    record=source_record(); record["provenance"]["source_url"]=url
    with pytest.raises(ValueError): convert_record(record)

def test_rejects_missing_license_evidence():
    record=source_record(); record["provenance"].pop("license_url")
    with pytest.raises(ValueError): convert_record(record)

def test_rejects_source_only_and_noop_records():
    record=source_record(); record["record_type"]="source_only"
    with pytest.raises(ValueError): convert_record(record)
    record=source_record(); record["revised_text"]=record["original_text"]
    with pytest.raises(ValueError): convert_record(record)

def test_output_matches_canonical_schema():
    item=convert_record(source_record())
    schema=json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(item))

def test_import_report_deduplicates_and_counts_rejections(tmp_path: Path):
    source=tmp_path/"input.jsonl"; output=tmp_path/"pending.jsonl"; report=tmp_path/"report.json"
    rows=[source_record(),source_record(),{"bad":"record"}]
    source.write_text("".join(json.dumps(x)+"\n" for x in rows),encoding="utf-8")
    result=import_records(source,output,report)
    assert result["input_records"]==3 and result["imported_pending_review"]==1
    assert result["rejected"]==2 and result["approved"]==0 and result["retrieval_eligible"]==0
    assert len(output.read_text(encoding="utf-8").splitlines())==1

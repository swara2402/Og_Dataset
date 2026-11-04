"""Build privacy- and licence-conscious aggregate academic writing observations.

No network access, model inference, source-sentence retention, or rule mutation.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_LICENSES = {"CC-BY-4.0", "CC0-1.0", "CC-BY-SA-4.0", "CC-BY-3.0", "CC-BY-SA-3.0"}
SECTIONS = {"abstract", "introduction", "literature_review", "methods", "results", "discussion", "conclusion"}
HEDGES = {"may", "might", "could", "possibly", "potentially", "suggest", "suggests", "suggested", "appears", "indicates"}
BE_AUXILIARY_MARKERS = {"was", "were", "been", "being", "is", "are"}
TRANSITIONS = {
    "contrast": {"however", "although", "whereas", "nevertheless"},
    "addition": {"additionally", "furthermore", "moreover", "also"},
    "cause_effect": {"therefore", "thus", "consequently", "because"},
    "sequence": {"first", "next", "finally", "subsequently"}
}


def sentences(text: str) -> list[str]:
    # Conservative sentence boundary heuristic; abbreviations may require manual cleanup.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text) if len(s.split()) >= 3]


def classify_sentence_opening(words: list[str]) -> str:
    if not words:
        return "empty"
    first = words[0]
    if any(first in terms for terms in TRANSITIONS.values()):
        return "transition_led"
    if first in {"although", "because", "if", "since", "unless", "when", "while", "whereas"}:
        return "subordinate_clause_led"
    if first in {"the", "a", "an", "this", "these", "those"}:
        return "determiner_led"
    if first in {"we", "i", "they", "it", "he", "she", "you", "our", "my", "your", "their"}:
        return "pronoun_led"
    if first in {"in", "on", "at", "by", "for", "from", "with", "within", "across"}:
        return "prepositional_phrase_led"
    return "other"


def load_manifest(path: Path) -> list[dict]:
    records, seen = [], set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Manifest line {line_no}: invalid JSON") from exc
        required = {"source_id", "title", "license", "text_mining_permitted", "discipline", "sections", "local_text"}
        if not required.issubset(item):
            raise ValueError(f"Manifest line {line_no}: missing {sorted(required - item.keys())}")
        sid = item["source_id"]
        if not isinstance(sid, str) or not sid or sid in seen:
            raise ValueError(f"Manifest line {line_no}: source_id must be unique and non-empty")
        seen.add(sid)
        if item["license"] != "SYNTHETIC" and item["license"] not in ALLOWED_LICENSES:
            raise ValueError(f"{sid}: licence is not on the reviewed allowlist")
        if item["text_mining_permitted"] is not True:
            raise ValueError(f"{sid}: text_mining_permitted must be explicitly true")
        if not isinstance(item["sections"], list) or not set(item["sections"]).issubset(SECTIONS):
            raise ValueError(f"{sid}: unsupported section label")
        if not isinstance(item["local_text"], str) or Path(item["local_text"]).name != item["local_text"]:
            raise ValueError(f"{sid}: local_text must be a filename, not a path")
        records.append(item)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "knowledge_base/corpus/sources.jsonl")
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/corpus_raw")
    parser.add_argument("--output", type=Path, default=ROOT / "knowledge_base/corpus/observations.json")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    stats = defaultdict(lambda: {"sentences": 0, "word_counts": [], "hedge_markers": 0,
                                 "be_auxiliary_markers": 0, "transition_markers": Counter(), "opening_patterns": Counter()})
    disciplines, total = Counter(), 0
    for source in manifest:
        source_path = args.input_dir / source["local_text"]
        if not source_path.is_file():
            if source["license"] == "SYNTHETIC":
                continue
            raise FileNotFoundError(f"Missing local text for {source['source_id']}: {source_path}")
        raw = source_path.read_text(encoding="utf-8")
        # Text extracts use explicit [SECTION: section_name] markers.
        current = "abstract"
        buckets = defaultdict(list)
        for line in raw.splitlines():
            marker = re.fullmatch(r"\s*\[SECTION:\s*([a-z_]+)\]\s*", line, re.I)
            if marker:
                current = marker.group(1).lower()
                if current not in SECTIONS:
                    raise ValueError(f"{source['source_id']}: unsupported section {current}")
            else:
                buckets[current].append(line)
        disciplines[source["discipline"]] += 1
        for section, lines in buckets.items():
            if section not in source["sections"]:
                continue
            for sentence in sentences(" ".join(lines)):
                words = re.findall(r"[A-Za-z][A-Za-z'-]*", sentence.lower())
                if not words:
                    continue
                row = stats[f"{source['discipline']}::{section}"]
                row["sentences"] += 1
                row["word_counts"].append(len(words))
                row["hedge_markers"] += sum(w in HEDGES for w in words)
                row["be_auxiliary_markers"] += sum(w in PASSIVE_MARKERS for w in words)
                row["opening_patterns"][classify_sentence_opening(words)] += 1
                for category, terms in TRANSITIONS.items():
                    row["transition_markers"][category] += sum(w in terms for w in words)
                total += 1
    report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_count": sum(disciplines.values()),
        "sentence_count": total,
        "discipline_counts": dict(sorted(disciplines.items())),
        "section_statistics": {
            key: {
                "sentence_count": value["sentences"],
                "mean_words": round(statistics.mean(value["word_counts"]), 2),
                "median_words": statistics.median(value["word_counts"]),
                "hedge_markers_per_100_sentences": round(100 * value["hedge_markers"] / value["sentences"], 2),
                "be_auxiliary_markers_per_100_sentences": round(100 * value["be_auxiliary_markers"] / value["sentences"], 2),
                "transition_markers": dict(value["transition_markers"]),
                "sentence_opening_patterns": dict(value["opening_patterns"])
            } for key, value in sorted(stats.items()) if value["sentences"]
        },
        "notes": [
            "Statistics describe this corpus only; they are not writing-quality targets.",
            "Source sentences and full-text extracts are not copied into this report.",
            "Be-auxiliary counts are coarse lexical observations, not a syntactic passive-voice classifier.",
            "Sentence-opening categories are heuristic corpus summaries, not recommended templates.",
            "Human review is required before any observation informs an editing rule."
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("source_count", "sentence_count", "discipline_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

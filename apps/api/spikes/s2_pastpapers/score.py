"""Scoring the outputs in ``.local/`` against the key. Writes numbers only (no course text)
to ``results/<name>.json`` and prints the comparison table."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from spikes.s2_pastpapers.key import Key, KeyPaper
from spikes.s2_pastpapers.metrics import (
    ClassificationScore,
    Classified,
    Predicted,
    label_found,
    marks_found,
    normalise,
    pct,
    qualify,
    score_classification,
    score_segmentation,
)
from spikes.s2_pastpapers.run import LOCAL, SEGMENTATIONS, read_json, slug, write_json

RESULTS = Path(__file__).resolve().parent / "results"
SEGMENTATION_TARGET = 90.0
TOPIC_TARGET = 80.0
# Run 1 (prompt v1) is kept beside run 2 (v2, ``seg-a`` and ``seg-b``).
# Run 1: transcription v1, segmentation prompt v1. Run 2: transcription v1, prompt v2.
# Run 3 (``seg-a``, ``seg-b``): transcription v2, prompt v2 with the page-boundary rule in B.
SEGMENTATION_RUNS = ("seg-a-v1", "seg-b-v1", "seg-a-v2", "seg-b-v2", *SEGMENTATIONS)
TRANSCRIPTS = {"transcribe-v1": "transcripts-v1", "transcribe": "transcripts"}


def transcription_check(
    key: Key, needed: dict[str, list[int]], folder_name: str = "transcripts"
) -> dict[str, Any]:
    """Pages to transcribe, done and failed; and for the key's parts on those pages, whether
    their label and their marks appear in the page's transcription."""
    out: dict[str, Any] = {"papers": {}}
    totals = {"pages": 0, "done": 0, "failed": 0, "parts": 0, "label": 0, "marks": 0}
    for paper in key.papers:
        pages = needed.get(paper.label, [])
        folder = LOCAL / folder_name / slug(paper.label)
        texts = {p: (folder / f"p{p:02d}.txt") for p in pages}
        done = [p for p, path in texts.items() if path.is_file()]
        parts = [k for k in paper.parts if k.page in done]
        label = sum(label_found(texts[k.page].read_text(encoding="utf-8"), k.number) for k in parts)
        marks = sum(marks_found(texts[k.page].read_text(encoding="utf-8"), k.marks) for k in parts)
        row = {
            "pages": len(pages),
            "done": len(done),
            "failed": len(pages) - len(done),
            "parts": len(parts),
            "label": label,
            "marks": marks,
        }
        out["papers"][paper.label] = row
        for name in totals:
            totals[name] += row[name]
    out["overall"] = totals | {
        "label_pct": pct(totals["label"], totals["parts"]),
        "marks_pct": pct(totals["marks"], totals["parts"]),
    }
    return out


def segmentation_results(key: Key, source: str, *, qualified: bool) -> dict[str, Any]:
    """``qualified``: numbers through ``qualify`` (code) first."""
    papers: dict[str, Any] = {}
    exact = parts = totals_right = totals_printed = 0
    for paper in key.papers:
        seg = read_json(LOCAL / source / f"{slug(paper.label)}.json")
        if seg is None:
            papers[paper.label] = {"failed": True, "parts": len(paper.parts)}
            parts += len(paper.parts)
            totals_printed += paper.printed_total is not None
            continue
        predicted = [
            Predicted(
                qualify(q["number"], q["parent"]) if qualified else q["number"],
                float(q["marks"]),
                q["page"],
            )
            for q in seg["questions"]
        ]
        score = score_segmentation(
            paper.parts,
            predicted,
            printed_total=paper.printed_total,
            predicted_total=seg.get("total_marks"),
        )
        papers[paper.label] = {
            "parts": score.parts,
            "predicted": len(predicted),
            "exact": score.exact,
            "exact_pct": score.exact_pct,
            "marks_wrong": score.number_only,
            "missing": score.missing,
            "extra": score.extra,
            "page_right": score.page_right,
            "total_right": score.total_right,
            "sum_right": score.sum_right,
            "models": seg.get("models") or [seg.get("model")],
            # Part numbers only (no text): what the correction screen would have to fix.
            "mismatches": score.mismatches,
        }
        exact += score.exact
        parts += score.parts
        if score.total_right is not None:
            totals_printed += 1
            totals_right += score.total_right
    return {
        "papers": papers,
        "overall": {
            "parts": parts,
            "exact": exact,
            "exact_pct": pct(exact, parts),
            "totals_right": totals_right,
            "totals_printed": totals_printed,
            "meets_target": (pct(exact, parts) or 0) >= SEGMENTATION_TARGET,
        },
    }


def classified_map(result: dict[str, Any] | None, chapters: set[str]) -> dict[str, Classified]:
    out: dict[str, Classified] = {}
    for q in (result or {}).get("questions", []):
        if not q.get("chapter"):
            continue
        subtopics = tuple(t for t in q["topics"] if t not in chapters)
        out.setdefault(
            normalise(q["number"]), Classified(q["number"], q["chapter"], subtopics, q["type"])
        )
    return out


def classification_results(key: Key, name: str, chapters: set[str]) -> dict[str, Any]:
    papers: dict[str, Any] = {}
    totals = ClassificationScore(0, 0, 0, 0, 0, 0, 0, 0)
    unknown = 0
    for paper in key.papers:
        result = read_json(LOCAL / name / f"{slug(paper.label)}.json")
        unknown += sum(q.get("unknown_codes", 0) for q in (result or {}).get("questions", []))
        score = score_classification(paper.parts, classified_map(result, chapters))
        papers[paper.label] = score.as_dict() | {"failed": result is None}
        for field_name in vars(totals):
            setattr(totals, field_name, getattr(totals, field_name) + getattr(score, field_name))
    overall = totals.as_dict() | {"unknown_codes": unknown}
    overall["meets_target"] = (pct(totals.chapter_agree, totals.answered) or 0) >= TOPIC_TARGET
    return {"papers": papers, "overall": overall}


def score(
    key: Key, name: str, chapters: set[str], needed: dict[str, list[int]], out: TextIO
) -> dict[str, Any]:
    costs: dict[str, Any] = read_json(LOCAL / "costs.json") or {}
    results: dict[str, Any] = {
        "spike": "S2 past-paper parsing",
        "module": key.module,
        "date": datetime.now(UTC).date().isoformat(),
        "key": {
            "papers": len(key.papers),
            "parts": sum(len(p.parts) for p in key.papers),
            "marks": sum(p.marks_sum for p in key.papers),
            "excluded_papers": len(key.excluded_titles),
            "excluded_pages": sum(len(p.excluded_pages) for p in key.papers),
        },
        "transcription": {
            step: transcription_check(key, needed, folder) | {"cost": costs.get(step)}
            for step, folder in TRANSCRIPTS.items()
        },
        "segmentation": {},
        "classification": {},
    }
    for source in SEGMENTATION_RUNS:
        for qualified in (False, True):
            label = f"{source}+qualify" if qualified else source
            results["segmentation"][label] = segmentation_results(
                key, source, qualified=qualified
            ) | {"cost": costs.get(source)}
    for source in SEGMENTATIONS:
        for step in ("c1", "c2"):
            run_name = f"{step}-on-{source}"
            if not (LOCAL / run_name).is_dir():
                results["classification"][run_name] = {"not_run": True}
                continue
            results["classification"][run_name] = classification_results(
                key, run_name, chapters
            ) | {"cost": costs.get(run_name)}
    write_json(RESULTS / f"{name}.json", results)
    print_table(results, key.papers, out)
    return results


def print_table(results: dict[str, Any], papers: Sequence[KeyPaper], out: TextIO) -> None:
    for step, check in results["transcription"].items():
        t = check["overall"]
        print(
            f"{step}: {t['done']}/{t['pages']} pages; labels {t['label_pct']} %, "
            f"marks {t['marks_pct']} % of {t['parts']} parts",
            file=out,
        )
    for source, seg in results["segmentation"].items():
        o = seg["overall"]
        c = seg.get("cost") or {}
        print(
            f"{source}: exact {o['exact']}/{o['parts']} ({o['exact_pct']} %), totals "
            f"{o['totals_right']}/{o['totals_printed']}; calls {c.get('calls')}, "
            f"tokens {c.get('input_tokens')}+{c.get('output_tokens')}, {c.get('seconds')} s, "
            f"failures {c.get('failures')}",
            file=out,
        )
    for run_name, cls in results["classification"].items():
        if cls.get("not_run"):
            print(f"{run_name}: not run", file=out)
            continue
        o = cls["overall"]
        c = cls.get("cost") or {}
        print(
            f"{run_name}: chapter {o['chapter_pct']} %, subtopic {o['subtopic_pct']} %, "
            f"type {o['type_pct']} % of {o['answered']}/{o['parts']}; strong-fit chapter "
            f"{o['strong_chapter_pct']} %; calls {c.get('calls')}, tokens "
            f"{c.get('input_tokens')}+{c.get('output_tokens')}, {c.get('seconds')} s, "
            f"failures {c.get('failures')}",
            file=out,
        )
    for paper in papers:
        cells = [
            f"{s}: {r['papers'][paper.label].get('exact_pct')}"
            for s, r in results["segmentation"].items()
        ]
        print(f"  {paper.label}: " + ", ".join(cells), file=out)

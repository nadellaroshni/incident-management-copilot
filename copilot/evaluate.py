"""Score the copilot against the labeled incidents.

Examples:
  python3 -m copilot.evaluate                       # offline baseline
  python3 -m copilot.evaluate --backend llm --model-id <id> --region <region>

Writes a markdown report to docs/results/ (unless --no-report is set).
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import date
from pathlib import Path

from .agent import BedrockLLM, investigate_llm, investigate_offline
from .retrieval import BM25Index, load_runbooks

REPO = Path(__file__).resolve().parent.parent


def run(incidents_path: Path, runbooks_path: Path, backend: str, llm=None) -> dict:
    index = BM25Index(load_runbooks(runbooks_path))
    rows = []
    with incidents_path.open(encoding="utf-8") as f:
        incidents = [json.loads(line) for line in f]
    for incident in incidents:
        if backend == "llm":
            output, stats = investigate_llm(incident, index, llm)
        else:
            output, stats = investigate_offline(incident, index)
        root = output.get("root_cause", {}).get("label")
        cited = [c.get("runbook_id") for c in output.get("citations", [])]
        rows.append({
            "incident_id": incident["incident_id"],
            "truth": incident["ground_truth_root_cause"],
            "predicted": root,
            "correct": root == incident["ground_truth_root_cause"],
            "citation_correct": bool(cited) and all(r == incident["ground_truth_runbook"] for r in cited),
            "insufficient": bool(output.get("insufficient_evidence")),
            "validation_errors": len(stats.errors),
            "latency_ms": stats.latency_ms,
            "input_tokens": stats.input_tokens,
            "output_tokens": stats.output_tokens,
        })

    n = len(rows)
    summary = {
        "backend": backend,
        "incidents": n,
        "top1_accuracy": round(sum(r["correct"] for r in rows) / n, 3),
        "citation_accuracy": round(sum(r["citation_correct"] for r in rows) / n, 3),
        "insufficient_rate": round(sum(r["insufficient"] for r in rows) / n, 3),
        "validation_failures": sum(1 for r in rows if r["validation_errors"]),
        "median_latency_ms": int(statistics.median(r["latency_ms"] for r in rows)),
        "input_tokens": sum(r["input_tokens"] for r in rows),
        "output_tokens": sum(r["output_tokens"] for r in rows),
    }
    return {"summary": summary, "rows": rows}


def markdown_report(result: dict) -> str:
    s = result["summary"]
    lines = [
        f"# Evaluation: {s['backend']} backend ({date.today().isoformat()})",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Incidents | {s['incidents']} |",
        f"| Top-1 root-cause accuracy | {s['top1_accuracy']:.1%} |",
        f"| Citation accuracy | {s['citation_accuracy']:.1%} |",
        f"| Insufficient-evidence rate | {s['insufficient_rate']:.1%} |",
        f"| Validation failures | {s['validation_failures']} |",
        f"| Median latency (ms) | {s['median_latency_ms']} |",
        f"| Input tokens | {s['input_tokens']} |",
        f"| Output tokens | {s['output_tokens']} |",
        "",
        "## Misses",
        "",
    ]
    misses = [r for r in result["rows"] if not r["correct"]]
    if not misses:
        lines.append("None.")
    for r in misses:
        lines.append(f"- {r['incident_id']}: truth `{r['truth']}`, predicted `{r['predicted']}`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copilot.evaluate")
    parser.add_argument("--incidents", type=Path, default=REPO / "sample-app" / "data" / "incidents.jsonl")
    parser.add_argument("--runbooks", type=Path, default=REPO / "knowledge" / "runbooks")
    parser.add_argument("--backend", choices=["offline", "llm"], default="offline")
    parser.add_argument("--model-id", default="anthropic.claude-3-5-haiku-20241022-v1:0")
    parser.add_argument("--region", default="ap-south-1")
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)

    llm = BedrockLLM(args.model_id, args.region) if args.backend == "llm" else None
    result = run(args.incidents, args.runbooks, args.backend, llm)
    print(json.dumps(result["summary"], indent=2))
    if not args.no_report:
        out = REPO / "docs" / "results" / f"{args.backend}-{date.today().isoformat()}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown_report(result), encoding="utf-8")
        print(f"report: {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

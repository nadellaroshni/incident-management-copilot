"""Command-line entry point.

Examples:
  python3 -m copilot investigate --incident INC-001
  python3 -m copilot investigate --incident INC-001 --backend llm --model-id <id> --region <region>
  python3 -m copilot investigate --incident INC-001 --decision approve --approver you@example.com
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .agent import BedrockLLM, investigate_llm, investigate_offline
from .retrieval import BM25Index, load_runbooks

REPO = Path(__file__).resolve().parent.parent
DEFAULT_INCIDENTS = REPO / "sample-app" / "data" / "incidents.jsonl"
DEFAULT_RUNBOOKS = REPO / "knowledge" / "runbooks"
DEFAULT_AUDIT = REPO / "runs" / "audit.jsonl"


def load_incident(path: Path, incident_id: str) -> dict:
    with path.open(encoding="utf-8") as f:
        for line in f:
            incident = json.loads(line)
            if incident["incident_id"] == incident_id:
                return incident
    raise SystemExit(f"incident {incident_id} not found in {path}")


def audit(entry: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copilot")
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("investigate", help="investigate one incident and record an approval decision")
    inv.add_argument("--incident", required=True)
    inv.add_argument("--incidents", type=Path, default=DEFAULT_INCIDENTS)
    inv.add_argument("--runbooks", type=Path, default=DEFAULT_RUNBOOKS)
    inv.add_argument("--backend", choices=["offline", "llm"], default="offline")
    inv.add_argument("--model-id", default="anthropic.claude-3-5-haiku-20241022-v1:0")
    inv.add_argument("--region", default="ap-south-1")
    inv.add_argument("--decision", choices=["approve", "reject"],
                     help="record a decision without prompting (for scripts)")
    inv.add_argument("--approver", default="local-user")
    inv.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args(argv)

    incident = load_incident(args.incidents, args.incident)
    index = BM25Index(load_runbooks(args.runbooks))
    if args.backend == "llm":
        output, stats = investigate_llm(incident, index, BedrockLLM(args.model_id, args.region))
    else:
        output, stats = investigate_offline(incident, index)

    print(json.dumps(output, indent=2))
    print(f"\nsteps={stats.steps} tokens_in={stats.input_tokens} tokens_out={stats.output_tokens} "
          f"latency_ms={stats.latency_ms}", file=sys.stderr)

    decision = args.decision
    if decision is None and not output.get("insufficient_evidence") and sys.stdin.isatty():
        decision = "approve" if input("\nApprove the proposed remediation (dry run)? [y/N] ").strip().lower() == "y" else "reject"
    if decision is None:
        decision = "pending"
    if output.get("insufficient_evidence") and decision == "approve":
        print("Cannot approve: the investigation had insufficient evidence.", file=sys.stderr)
        return 1

    audit({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "incident_id": incident["incident_id"],
        "backend": args.backend,
        "root_cause": output.get("root_cause", {}).get("label"),
        "decision": decision,
        "approver": args.approver if decision != "pending" else None,
        "dry_run_steps": len(output.get("remediation", [])),
    }, args.audit)
    print(f"decision: {decision} (recorded in {args.audit})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate labeled synthetic incidents for evaluating the copilot.

Each incident is a short window of JSON log lines (mirroring the messages in
app.py) plus one alert and a ground-truth root cause. The copilot is scored
against the ground truth, so the labels must be correct.

Output: sample-app/data/incidents.jsonl  (one incident per line)

Run:  python3 sample-app/generate_incidents.py --count 40 --seed 7
"""

import argparse
import json
import random
from pathlib import Path

ROOT_CAUSES = {
    "db_pool_exhaustion": {
        "runbook": "rb-db-pool",
        "alert": "checkout error rate > 5% for 5m (HTTP 503)",
        "logs": [
            "connection pool timeout after 0.5s; active=5/5",
            "connection pool timeout after 0.5s; active=5/5",
        ],
        "status": 503,
        "summary": "Database connection pool exhausted; connections are not being returned.",
    },
    "disk_full": {
        "runbook": "rb-disk-full",
        "alert": "checkout error rate > 5% for 5m (HTTP 500)",
        "logs": [
            "OSError: [Errno 28] No space left on device while writing order record",
        ],
        "status": 500,
        "summary": "Host disk is full, so order records cannot be written.",
    },
    "bad_deploy": {
        "runbook": "rb-bad-deploy",
        "alert": "checkout error rate 100% since last deploy (HTTP 500)",
        "logs": [
            "missing configuration key PAYMENT_GATEWAY_URL; checkout cannot start",
        ],
        "status": 500,
        "summary": "Latest deploy is missing the PAYMENT_GATEWAY_URL configuration key.",
    },
}

NOISE = [
    "order accepted",
    "order accepted",
    "order accepted",
    "health check ok",
    "cache hit for product catalog",
]


def make_incident(index, rng):
    cause = rng.choice(list(ROOT_CAUSES))
    spec = ROOT_CAUSES[cause]
    minutes = rng.randint(0, 59)
    lines = []
    for _ in range(rng.randint(8, 15)):
        lines.append({
            "ts": f"2026-10-13T10:{minutes:02d}:{rng.randint(0, 59):02d}Z",
            "level": "INFO",
            "service": "checkout",
            "msg": rng.choice(NOISE),
        })
    for msg in spec["logs"] * rng.randint(2, 4):
        lines.append({
            "ts": f"2026-10-13T10:{minutes:02d}:{rng.randint(0, 59):02d}Z",
            "level": "ERROR",
            "service": "checkout",
            "msg": msg,
            "status": spec["status"],
        })
    rng.shuffle(lines)
    return {
        "incident_id": f"INC-{index:03d}",
        "alert": spec["alert"],
        "logs": lines,
        "ground_truth_root_cause": cause,
        "ground_truth_summary": spec["summary"],
        "ground_truth_runbook": spec["runbook"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default=str(Path(__file__).parent / "data" / "incidents.jsonl"))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for i in range(1, args.count + 1):
            f.write(json.dumps(make_incident(i, rng)) + "\n")
    print(f"wrote {args.count} incidents to {out}")


if __name__ == "__main__":
    main()

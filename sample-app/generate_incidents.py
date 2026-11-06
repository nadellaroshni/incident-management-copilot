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

# Paraphrased variant: the same failures described in different words, and noisier
# logs with unrelated warnings that mention similar components. Runbooks are NOT
# changed, so this measures whether retrieval still works on wording it hasn't seen.
PARAPHRASED = {
    "db_pool_exhaustion": [
        "waited 500 ms for a free database session; all 5 sessions are in use",
        "request gave up waiting for a database handle after half a second, none free",
    ],
    "disk_full": [
        "could not persist order: volume has no free blocks left",
        "write failed, storage device reports zero bytes available for order data",
    ],
    "bad_deploy": [
        "startup aborted: PAYMENT_GATEWAY_URL is not set in this environment",
        "service refused to boot, required setting for the payment gateway endpoint is absent",
    ],
}

NOISE_PARAPHRASED = [
    "order accepted",
    "upstream probe responded in 12 ms",
    "catalog cache refreshed",
    "slow query on inventory table: 340 ms",
    "database replica lag 0.2s, within threshold",
    "TLS handshake with metrics agent completed",
    "retrying metrics export after timeout",
]


# Vocabulary-shifted variant: same failures, described without the runbook's own
# keywords (as a different team might write them). This is the hardest set here.
SHIFTED = {
    "db_pool_exhaustion": [
        "could not lease a session from the datastore; 5 of 5 handles in flight",
        "checkout stalled waiting on a backend slot, every slot is held",
    ],
    "disk_full": [
        "order journal flush failed: volume out of capacity, cannot allocate blocks",
        "ENOSPC while flushing order journal to volume",
    ],
    "bad_deploy": [
        "boot halted: environment lacks a required endpoint parameter for payments",
        "config validation failed at startup, the payments endpoint value was never provided",
    ],
}


def make_incident(index, rng, variant="standard"):
    cause = rng.choice(list(ROOT_CAUSES))
    spec = ROOT_CAUSES[cause]
    alert = spec["alert"]
    if variant == "shifted":
        # Generic alert: the real alerts name the cause ("since last deploy"), which leaks the answer.
        error_msgs = SHIFTED[cause]
        noise = NOISE_PARAPHRASED
        alert = "checkout error rate above threshold"
    elif variant == "paraphrased":
        error_msgs = PARAPHRASED[cause]
        noise = NOISE_PARAPHRASED
    else:
        error_msgs = spec["logs"]
        noise = NOISE
    minutes = rng.randint(0, 59)
    lines = []
    for _ in range(rng.randint(8, 15)):
        lines.append({
            "ts": f"2026-10-13T10:{minutes:02d}:{rng.randint(0, 59):02d}Z",
            "level": "INFO",
            "service": "checkout",
            "msg": rng.choice(noise),
        })
    for msg in error_msgs * rng.randint(2, 4):
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
        "alert": alert,
        "logs": lines,
        "ground_truth_root_cause": cause,
        "ground_truth_summary": spec["summary"],
        "ground_truth_runbook": spec["runbook"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--variant", choices=["standard", "paraphrased", "shifted"], default="standard")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    names = {"standard": "incidents.jsonl", "paraphrased": "incidents_paraphrased.jsonl",
             "shifted": "incidents_shifted.jsonl"}
    default_name = names[args.variant]
    out = Path(args.out) if args.out else Path(__file__).parent / "data" / default_name
    rng = random.Random(args.seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for i in range(1, args.count + 1):
            f.write(json.dumps(make_incident(i, rng, args.variant)) + "\n")
    print(f"wrote {args.count} {args.variant} incidents to {out}")


if __name__ == "__main__":
    main()

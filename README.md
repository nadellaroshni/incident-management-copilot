# Incident Management Copilot

An AI-powered copilot that helps engineers investigate production incidents. It analyses logs and alerts, retrieves relevant runbooks with RAG, proposes a likely root cause with citations, and drafts remediation steps. Every action that changes a system waits for human approval.

> **Status:** Phase 1 (foundation) in progress. See [docs/ROADMAP.md](docs/ROADMAP.md).

## Repository layout

```
copilot/               Retrieval, validator, investigation agents, CLI and evaluation
knowledge/runbooks/    Runbooks the copilot cites (one file per failure mode)
sample-app/            Checkout service with injectable faults, plus a labeled incident generator
tests/                 Unit tests (python3 -m unittest)
scripts/               Setup scripts (AWS budget alerts)
docs/                  ARCHITECTURE.md, SETUP.md (step-by-step), ROADMAP.md, results/
```

## Quick start

Full instructions are in [docs/SETUP.md](docs/SETUP.md). The short version:

```bash
python3 -m unittest -v                                  # run the tests
python3 -m copilot investigate --incident INC-001       # investigate and approve (offline)
python3 -m copilot.evaluate                             # score the offline baseline
```

## Run the sample service

Requires Python 3.9 or later. No third-party packages are needed.

```bash
# Run the sample service
python3 sample-app/app.py

# In another terminal: trigger a fault and watch the logs
curl localhost:8080/checkout
curl "localhost:8080/admin/fault?mode=db_pool_exhaustion"
curl localhost:8080/checkout          # now returns 503
curl "localhost:8080/admin/fault?mode=none"

# Regenerate the labeled evaluation incidents
python3 sample-app/generate_incidents.py --count 40 --seed 7
```

Supported fault modes: `none`, `db_pool_exhaustion`, `disk_full`, `bad_deploy`.

## AWS cost guardrails

```bash
export BUDGET_EMAIL=you@example.com
export BUDGET_LIMIT=80        # USD per month
./scripts/setup_budgets.sh
```

This creates a monthly budget with email alerts at 25%, 50% and 80% of actual spend, plus a forecast alert at 100%.

## Evaluation

The copilot will be scored on the labeled incidents in `sample-app/data/incidents.jsonl`:

- Top-1 root-cause accuracy
- Citation accuracy (cited runbook actually supports the claim)
- Time to first summary, compared with a manual baseline

Results will be added here once the agent is built.

## License

MIT. See [LICENSE](LICENSE).

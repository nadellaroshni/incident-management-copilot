# Setup and Run Guide

This guide covers three levels, each building on the one before:

1. **Local (offline):** run the sample service, investigate incidents with the deterministic baseline, record approvals, run tests and evaluation. No AWS account needed.
2. **Local with the LLM agent:** point the same CLI at Amazon Bedrock (Claude) using your own AWS credentials.
3. **AWS deployment:** deploy the sample service and the pipeline with CDK. This part is planned in `docs/ARCHITECTURE.md` and is not built yet.

Status of each part is stated at the end of each section, so you know what has been verified.

---

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.9 or later (3.11+ recommended) | `python3 --version` |
| Git | any recent version | `git --version` |
| curl | any (for the sample service demo) | `curl --version` |

Level 1 needs nothing else. No third-party Python packages are required for the offline path.

## 2. Get the code

```bash
git clone https://github.com/nadellaroshni/incident-management-copilot.git
cd incident-management-copilot
git log --oneline -3     # you should see the Phase 1 and architecture commits
```

## 3. Verify the project (about 1 minute)

Run the test suite from the repository root:

```bash
python3 -m unittest -v
```

Expected: `Ran 16 tests` and `OK`. The tests cover:

- runbook front matter parsing and section chunking,
- BM25 retrieval returning the right runbook for each failure's error message,
- the output validator (rejects fabricated quotes, unretrieved citations, non-dry-run steps, unknown labels),
- the offline agent and the LLM tool loop (tested with a scripted fake model, not a live one),
- the approval record written by the CLI.

## 4. Run the sample service

Open a terminal and start the service. It listens on port 8080 and writes JSON logs to the terminal.

```bash
python3 sample-app/app.py
```

In a second terminal, inject faults and send requests:

```bash
# Healthy
curl localhost:8080/checkout                       # {"status": "ok"}

# Database pool exhaustion
curl "localhost:8080/admin/fault?mode=db_pool_exhaustion"
curl localhost:8080/checkout                       # {"error": "service unavailable"}

# Reset
curl "localhost:8080/admin/fault?mode=none"
```

The other fault modes are `disk_full` and `bad_deploy`. Stop the service with `Ctrl+C`.

Each fault writes a JSON log line such as:

```json
{"ts": "...", "level": "ERROR", "service": "checkout", "msg": "connection pool timeout after 0.5s; active=5/5", "status": 503, "route": "/checkout"}
```

## 5. Investigate an incident (offline)

The labeled incidents live in `sample-app/data/incidents.jsonl`. List their IDs:

```bash
python3 -c "import json; [print(json.loads(l)['incident_id']) for l in open('sample-app/data/incidents.jsonl')]" | head -5
```

Investigate one:

```bash
python3 -m copilot investigate --incident INC-001
```

The output shows:

1. the root cause label and confidence,
2. the evidence lines it relied on,
3. the runbook section it cited,
4. the proposed remediation steps (all dry-run),
5. a prompt asking you to approve or reject. Type `y` to approve, then press Enter.

Each decision is appended to `runs/audit.jsonl` with the incident ID, the root cause, the decision, and the approver.

For scripts, skip the prompt and record the decision directly:

```bash
python3 -m copilot investigate --incident INC-002 --decision approve --approver you@example.com
cat runs/audit.jsonl
```

Insufficient evidence cannot be approved. The CLI refuses and returns a non-zero exit code.

### Add your own runbook

1. Create `knowledge/runbooks/<name>.md` with this front matter:

   ```markdown
   ---
   runbook_id: rb-my-thing
   failure_mode: my_thing
   title: Short description of the failure
   ---

   ## Symptoms
   ...

   ## Remediation
   - First step
   - Second step
   ```

2. Run `python3 -m unittest -v`. The test that checks every runbook has a `Remediation` section will catch a missing one.
3. Re-run an investigation. New runbooks are loaded automatically.

## 6. Run the evaluation (offline)

```bash
python3 -m copilot.evaluate
```

This prints a summary and writes a report to `docs/results/offline-<date>.md`.

**Read the result with care.** The offline baseline scores 100% on every synthetic set. There are three sets, and all three score 100%:

| Set | File | How it differs |
|---|---|---|
| Standard | `sample-app/data/incidents.jsonl` | Log messages copied from the runbook wording |
| Paraphrased | `sample-app/data/incidents_paraphrased.jsonl` | Same failures in different words, with noisier logs |
| Shifted | `sample-app/data/incidents_shifted.jsonl` | Vocabulary avoids the runbook's keywords, and the alert is generic |

Regenerate the harder sets with `python3 sample-app/generate_incidents.py --variant paraphrased --seed 99` and `--variant shifted --seed 123`, then score them with `python3 -m copilot.evaluate --incidents sample-app/data/<file>.jsonl --no-report`.

**Why the synthetic sets are not enough.** Even the shifted set scores 100%. The runbooks and the generated text share too much everyday vocabulary, such as "order", "volume", "environment" and "checkout", so keyword retrieval finds the right runbook regardless of how the failure is worded. The sets were written by the same person who wrote the runbooks, so they cannot show how the copilot does on real incidents. Treat every number on these sets as a pipeline check, not an accuracy result.

**What would give a real number.** Incident descriptions written by someone other than the runbook author, ideally taken from real postmortems or incident reports with the identifying details removed, scored against the root cause a human engineer confirmed. Until that exists, do not quote an accuracy figure for the copilot.

Status: **verified** (tests pass, CLI and evaluation run locally).

## 7. Run the LLM agent with Amazon Bedrock

This level needs an AWS account with Bedrock access. Costs are per token and small for this workload, but check the current pricing in the AWS console before you run the full evaluation.

### 7.1 One-time AWS setup

1. **Pick a region** where your chosen Claude model is available. `ap-south-1` (Mumbai) is the default in the code. Check availability under Amazon Bedrock → Model catalog.
2. **Request model access.** In the Bedrock console, open Model access and enable the Claude model you want (for example, Claude Haiku). Access can take a few minutes.
3. **Create a budget** before running anything paid. Either run the script:

   ```bash
   export BUDGET_EMAIL=you@example.com
   export BUDGET_LIMIT=80
   ./scripts/setup_budgets.sh
   ```

   or create one in the console under Billing → Budgets.
4. **Credentials.** Use AWS SSO (`aws configure sso`) or a short-lived role. Avoid long-lived access keys on disk. If you have ever pasted an access key into a chat or a file, deactivate it in IAM and create a new one.

### 7.2 Local Python setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # installs boto3 only
```

Verify your credentials work:

```bash
aws sts get-caller-identity
```

### 7.3 Run one investigation with the LLM

```bash
python3 -m copilot investigate --incident INC-001 \
  --backend llm \
  --model-id <your-claude-model-id> \
  --region ap-south-1
```

Replace `<your-claude-model-id>` with the model ID shown in the Bedrock console for the model you enabled. The CLI prints the token counts at the end, so you can see what each investigation costs.

### 7.4 Run the full evaluation with the LLM

Run a small subset first to check cost and behaviour:

```bash
python3 -m copilot.evaluate --backend llm --model-id <your-claude-model-id> --region ap-south-1
```

The report is written to `docs/results/llm-<date>.md`. Compare the LLM row with the offline baseline. If the LLM is worse on the synthetic set, the synthetic set is too easy to show a benefit; that is a reason to add the held-out variants before drawing conclusions.

Status: **not yet verified against live Bedrock.** The tool loop is tested with a scripted fake model. The first live run is the test. If it fails, check the error message against the Converse API and the model ID.

## 8. AWS deployment (planned, not built yet)

The sample service and the pipeline are designed to run on AWS (Lambda, API Gateway, Step Functions, S3, DynamoDB, Cognito, CloudFront) with CDK in Python. See `docs/ARCHITECTURE.md` sections 3 and 4 and the phase plan in section 7.

Before that phase starts, we need to decide how deployments reach AWS. The recommended option is GitHub Actions using OpenID Connect, so no long-lived keys are stored anywhere. That needs a one-time IAM setup in your account, described in the architecture document.

## 9. Teardown and cost hygiene

- Stop the local sample service with `Ctrl+C`.
- Delete local run output if you don't need it: `rm -rf runs/`.
- Once AWS resources exist, destroy them after each demo with `cdk destroy --all`, then confirm in the console that nothing is running.

## 10. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `incident INC-xxx not found` | The ID doesn't exist. Use one from `sample-app/data/incidents.jsonl` (INC-001 to INC-040). |
| `ModuleNotFoundError: copilot` | Run commands from the repository root, not from a subfolder. |
| `ModuleNotFoundError: boto3` | Only needed for `--backend llm`. Run `pip install -r requirements.txt` inside the virtual environment. |
| `AccessDenied` or `UnrecognizedClientException` from Bedrock | Your credentials are missing or expired, or the Claude model access request isn't approved yet. Run `aws sts get-caller-identity` and check Model access. |
| `ValidationException: The provided model identifier is invalid` | The model ID is wrong for this region. Copy the ID from the Bedrock console for the region you are using. |
| `Cannot approve: the investigation had insufficient evidence` | The agent did not find enough support. This is intended behaviour. Add or fix the runbook, or review the log lines. |
| Port 8080 already in use | Stop the other process, or change the port in `sample-app/app.py`. |

## What is verified and what is not

| Part | Status |
|---|---|
| Runbook loading, retrieval, validator, offline agent | Verified by tests |
| CLI investigation and approval record | Verified locally |
| Sample service and fault injection | Verified locally with curl |
| Evaluation script (offline) | Verified locally; baseline is too easy to show real accuracy |
| LLM tool loop | Verified with a scripted fake model only |
| Bedrock live calls | **Not yet verified** |
| AWS deployment (CDK, Step Functions, API, UI) | **Not built yet** |

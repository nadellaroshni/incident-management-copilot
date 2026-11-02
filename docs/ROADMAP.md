# Roadmap

Phased plan for the Incident Management Copilot. Each phase ends with a tagged release and a short note on what was measured.

## Budget

- Target: stay under USD 80 for the whole project, with the rest of the credits held in reserve.
- Monthly budget with alerts at 25%, 50%, 80% actual and 100% forecast (`scripts/setup_budgets.sh`).
- Avoid always-on resources: OpenSearch Serverless, NAT gateways and always-on databases. Tear down with infrastructure-as-code after each demo.
- Use Claude Haiku for bulk extraction; reserve larger models for final reasoning.

## Phase 1: Foundation (current)

- [x] Sample checkout service with injectable faults (`sample-app/app.py`)
- [x] Labeled synthetic incident generator with ground truth (`sample-app/generate_incidents.py`)
- [x] Monthly AWS budget with email alerts (`scripts/setup_budgets.sh`)
- [ ] Run the budget script against the AWS account
- [ ] Infrastructure skeleton (CDK or Terraform) with destroy support

## Phase 2: Log pipeline and runbook RAG

- Ship logs to S3 and CloudWatch Logs
- Write runbooks and postmortems in markdown for the sample app
- Chunk by section, embed, and retrieve with citations
- Target: retrieval returns the correct runbook for every labeled incident

## Phase 3: Investigation agent

- Agent tools: query logs, retrieve runbooks, summarise the timeline
- Output: root cause, cited evidence, proposed remediation steps
- All remediation is dry-run only in this project

## Phase 4: Human approval gate and UI

- Step Functions workflow that waits for an approve or reject decision before any action
- Simple UI: timeline, evidence, proposed fix, approve and reject buttons
- Audit trail of every decision

## Phase 5: Evaluation

- Run the agent on all labeled incidents
- Report top-1 root-cause accuracy, citation accuracy, and time to first summary
- Compare with a manual baseline timed by hand

## Phase 6: Polish and demo

- Architecture diagram and README
- Two-minute demo video: inject a fault, watch the investigation, approve the fix
- Cost report showing total spend against the budget

## Out of scope

- Real remediation against production systems
- Real customer or employer data

"""Tests for retrieval, validation, both agent backends and the approval record.

Run from the repository root:  python3 -m unittest -v
No AWS access or third-party packages are needed.
"""

import json
import tempfile
import unittest
from pathlib import Path

from copilot.agent import investigate_llm, investigate_offline
from copilot.retrieval import BM25Index, load_runbooks, parse_front_matter, tokenize
from copilot.validator import validate

REPO = Path(__file__).resolve().parent.parent
RUNBOOKS = REPO / "knowledge" / "runbooks"
INCIDENTS = REPO / "sample-app" / "data" / "incidents.jsonl"


def load_incidents():
    with INCIDENTS.open() as f:
        return [json.loads(line) for line in f]


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.chunks = load_runbooks(RUNBOOKS)
        self.index = BM25Index(self.chunks)

    def test_front_matter_is_parsed(self):
        meta, body = parse_front_matter("---\nrunbook_id: rb-x\nfailure_mode: y\n---\nbody")
        self.assertEqual(meta, {"runbook_id": "rb-x", "failure_mode": "y"})
        self.assertEqual(body, "body")

    def test_every_runbook_has_remediation_section(self):
        for runbook in {c.runbook_id for c in self.chunks}:
            headings = {c.heading for c in self.chunks if c.runbook_id == runbook}
            self.assertIn("Remediation", headings, runbook)

    def test_error_message_retrieves_matching_runbook(self):
        cases = {
            "connection pool timeout after 0.5s; active=5/5": "rb-db-pool",
            "No space left on device while writing order record": "rb-disk-full",
            "missing configuration key PAYMENT_GATEWAY_URL": "rb-bad-deploy",
        }
        for query, expected in cases.items():
            top, score = self.index.search(query, k=1)[0]
            self.assertEqual(top.runbook_id, expected, query)
            self.assertGreater(score, 0)

    def test_tokenizer_drops_stopwords_and_single_letters(self):
        self.assertEqual(tokenize("The pool is at 5 of x"), ["pool", "5"])


class ValidatorTests(unittest.TestCase):
    labels = {"db_pool_exhaustion", "disk_full", "bad_deploy"}
    logs = [{"msg": "connection pool timeout after 0.5s; active=5/5", "level": "ERROR"}]

    def good(self, **overrides):
        output = {
            "root_cause": {"label": "db_pool_exhaustion", "confidence": 0.8, "summary": "s"},
            "evidence": [{"log_ts": "t", "quote": self.logs[0]["msg"], "source": "logs"}],
            "citations": [{"chunk_id": "rb-db-pool#1", "runbook_id": "rb-db-pool", "heading": "Diagnosis"}],
            "remediation": [{"step": "restart", "risk": "low", "dry_run": True}],
            "insufficient_evidence": False,
        }
        output.update(overrides)
        return output

    def test_valid_output_passes(self):
        self.assertEqual(validate(self.good(), self.labels, {"rb-db-pool#1"}, self.logs), [])

    def test_unretrieved_citation_is_rejected(self):
        errors = validate(self.good(), self.labels, set(), self.logs)
        self.assertTrue(any("never retrieved" in e for e in errors))

    def test_fabricated_quote_is_rejected(self):
        output = self.good(evidence=[{"log_ts": "t", "quote": "made up line", "source": "logs"}])
        errors = validate(output, self.labels, {"rb-db-pool#1"}, self.logs)
        self.assertTrue(any("not found in logs" in e for e in errors))

    def test_non_dry_run_remediation_is_rejected(self):
        output = self.good(remediation=[{"step": "delete table", "risk": "high", "dry_run": False}])
        errors = validate(output, self.labels, {"rb-db-pool#1"}, self.logs)
        self.assertTrue(any("dry-run" in e for e in errors))

    def test_unknown_label_is_rejected(self):
        output = self.good(root_cause={"label": "made_up", "confidence": 0.5, "summary": "s"})
        errors = validate(output, self.labels, {"rb-db-pool#1"}, self.logs)
        self.assertTrue(any("not a known failure mode" in e for e in errors))

    def test_honest_insufficient_evidence_always_passes(self):
        output = {"insufficient_evidence": True}
        self.assertEqual(validate(output, self.labels, set(), self.logs), [])


class OfflineAgentTests(unittest.TestCase):
    def test_offline_baseline_scores_all_labeled_incidents(self):
        index = BM25Index(load_runbooks(RUNBOOKS))
        correct = 0
        incidents = load_incidents()
        for incident in incidents:
            output, stats = investigate_offline(incident, index)
            self.assertEqual(stats.errors, [], incident["incident_id"])
            if output.get("root_cause", {}).get("label") == incident["ground_truth_root_cause"]:
                correct += 1
        self.assertEqual(correct, len(incidents))

    def test_offline_output_cites_ground_truth_runbook(self):
        index = BM25Index(load_runbooks(RUNBOOKS))
        incident = load_incidents()[0]
        output, _ = investigate_offline(incident, index)
        self.assertEqual(output["citations"][0]["runbook_id"], incident["ground_truth_runbook"])
        self.assertTrue(all(step["dry_run"] for step in output["remediation"]))


class ScriptedLLM:
    """Stands in for Bedrock: asks for a runbook search, then answers with a citation it retrieved."""

    def __init__(self, index, incident):
        self.index = index
        self.incident = incident
        self.calls = 0

    def converse(self, messages, tools, system):
        self.calls += 1
        usage = {"inputTokens": 100, "outputTokens": 20}
        if self.calls == 1:
            return {"stopReason": "tool_use", "usage": usage, "output": {"message": {
                "role": "assistant", "content": [{"toolUse": {
                    "toolUseId": "t1", "name": "search_runbooks",
                    "input": {"query": self.incident["alert"]}}}]}}}
        chunk, _ = self.index.search(self.incident["alert"], k=1)[0]
        answer = {
            "root_cause": {"label": chunk.failure_mode, "confidence": 0.9, "summary": chunk.title},
            "evidence": [{"log_ts": line["ts"], "quote": line["msg"], "source": "logs"}
                         for line in self.incident["logs"] if line["level"] == "ERROR"][:1],
            "citations": [{"chunk_id": chunk.chunk_id, "runbook_id": chunk.runbook_id, "heading": chunk.heading}],
            "remediation": [{"step": "roll back", "risk": "low", "dry_run": True}],
            "insufficient_evidence": False,
        }
        return {"stopReason": "end_turn", "usage": usage, "output": {"message": {
            "role": "assistant", "content": [{"text": json.dumps(answer)}]}}}


class LLMAgentTests(unittest.TestCase):
    def test_tool_loop_produces_validated_output(self):
        index = BM25Index(load_runbooks(RUNBOOKS))
        incident = load_incidents()[0]
        llm = ScriptedLLM(index, incident)
        output, stats = investigate_llm(incident, index, llm)
        self.assertFalse(output["insufficient_evidence"], stats.errors)
        self.assertEqual(stats.steps, 2)
        self.assertEqual(stats.input_tokens, 200)

    def test_step_limit_returns_insufficient_evidence(self):
        class Looping:
            def converse(self, messages, tools, system):
                return {"stopReason": "tool_use", "usage": {}, "output": {"message": {
                    "role": "assistant", "content": [{"toolUse": {
                        "toolUseId": "x", "name": "get_alert", "input": {}}}]}}}

        index = BM25Index(load_runbooks(RUNBOOKS))
        output, stats = investigate_llm(load_incidents()[0], index, Looping(), max_steps=3)
        self.assertTrue(output["insufficient_evidence"])
        self.assertIn("step limit reached", stats.errors)

    def test_hallucinated_citation_is_caught(self):
        class Hallucinating(ScriptedLLM):
            def converse(self, messages, tools, system):
                if self.calls == 0:
                    self.calls += 1
                    return {"stopReason": "end_turn", "usage": {}, "output": {"message": {
                        "role": "assistant", "content": [{"text": json.dumps({
                            "root_cause": {"label": "disk_full", "confidence": 0.9, "summary": "s"},
                            "evidence": [], "remediation": [], "insufficient_evidence": False,
                            "citations": [{"chunk_id": "rb-fake#9", "runbook_id": "rb-fake", "heading": "x"}],
                        })}]}}}
                return super().converse(messages, tools, system)

        index = BM25Index(load_runbooks(RUNBOOKS))
        incident = load_incidents()[0]
        output, stats = investigate_llm(incident, index, Hallucinating(index, incident))
        self.assertTrue(output["insufficient_evidence"])
        self.assertTrue(any("never retrieved" in e for e in stats.errors))


class CliAuditTests(unittest.TestCase):
    def test_approval_is_recorded_with_approver(self):
        from copilot.__main__ import main

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            code = main(["investigate", "--incident", "INC-001", "--incidents", str(INCIDENTS),
                         "--runbooks", str(RUNBOOKS), "--decision", "approve",
                         "--approver", "tester", "--audit", str(audit_path)])
            self.assertEqual(code, 0)
            entry = json.loads(audit_path.read_text().splitlines()[-1])
            self.assertEqual(entry["decision"], "approve")
            self.assertEqual(entry["approver"], "tester")
            self.assertEqual(entry["incident_id"], "INC-001")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Offline unit tests for the Spacelift provider's normalized read surface."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import unittest
import urllib.error
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "agent-do"
loader = importlib.machinery.SourceFileLoader("spacelift_provider", str(ROOT / "tools/agent-spacelift"))
spec = importlib.util.spec_from_loader(loader.name, loader)
provider = importlib.util.module_from_spec(spec)
loader.exec_module(provider)


class SpaceliftTests(unittest.TestCase):
    @staticmethod
    def args(**values):
        return type("Args", (), values)()

    def test_supplied_jwt_is_preferred_over_an_api_key(self):
        with patch.dict(os.environ, {"SPACELIFT_API_TOKEN": "ready-jwt", "SPACELIFT_API_KEY_ID": "key-id", "SPACELIFT_API_KEY_SECRET": "key-secret"}), patch.object(provider, "exchange_api_key") as exchange:
            self.assertEqual(provider.token(), "ready-jwt")
        exchange.assert_not_called()

    def test_api_key_is_exchanged_only_in_memory(self):
        with patch.object(provider, "post_graphql", return_value={"apiKeyUser": {"jwt": "minted-jwt"}}) as request:
            self.assertEqual(provider.exchange_api_key("key-id", "key-secret"), "minted-jwt")
        request.assert_called_once()
        self.assertIn("apiKeyUser", request.call_args.args[0]["query"])

    def test_incomplete_api_key_fails_without_making_a_request(self):
        with patch.dict(os.environ, {"SPACELIFT_API_TOKEN": "", "SPACELIFT_API_KEY_ID": "key-id", "SPACELIFT_API_KEY_SECRET": ""}):
            with self.assertRaisesRegex(provider.ProviderError, "incomplete"):
                provider.token()

    def test_api_key_exchange_requires_a_jwt(self):
        with patch.object(provider, "post_graphql", return_value={"apiKeyUser": {}}):
            with self.assertRaisesRegex(provider.ProviderError, "no JWT"):
                provider.exchange_api_key("key-id", "key-secret")

    def test_failed_apply_is_distinct_from_policy_failure(self):
        run = provider.normalize_run({"id": "r1", "state": "FAILED", "failureReason": "terraform apply failed"})
        self.assertTrue(run["terraform_apply_failed"])
        self.assertFalse(run["policy_failed"])

    def test_policy_failure_is_distinct(self):
        run = provider.normalize_run({"id": "r1", "state": "FAILED", "policyOutcome": "DENIED"})
        self.assertTrue(run["policy_failed"])
        self.assertFalse(run["terraform_apply_failed"])

    def test_commit_and_pr_metadata_are_preserved_when_present(self):
        run = provider.normalize_run({"id": "r1", "commitSha": "abc123", "pr": {"number": 42}, "createdAt": "start", "finishedAt": "end"})
        self.assertEqual(run["commit_sha"], "abc123")
        self.assertEqual(run["pull_request"], {"number": 42})
        self.assertEqual(run["started_at"], "start")
        self.assertEqual(run["ended_at"], "end")

    def test_run_list_reports_explicit_truncation(self):
        response = {"stackRuns": [{"id": "r1"}, {"id": "r2"}]}
        with patch.object(provider, "scalar_fields", return_value={"id"}), patch.object(provider, "gql", return_value=response):
            result = provider.runs(self.args(stack="s1", limit=1, cursor=None))
        self.assertTrue(result["pagination"]["truncated"])
        self.assertEqual(result["pagination"]["returned"], 1)

    def test_empty_stack_and_run_lists_are_valid(self):
        with patch.object(provider, "scalar_fields", return_value={"id"}), patch.object(provider, "gql", return_value={"stacks": []}):
            self.assertEqual(provider.stack_list(self.args(limit=10))["stacks"], [])
        with patch.object(provider, "scalar_fields", return_value={"id"}), patch.object(provider, "gql", return_value={"stackRuns": []}):
            self.assertEqual(provider.runs(self.args(stack="s1", limit=10, cursor=None))["runs"], [])

    def test_unverified_cursor_fails_explicitly(self):
        with self.assertRaisesRegex(provider.ProviderError, "cursor"):
            provider.runs(self.args(stack="s1", limit=10, cursor="opaque"))

    def test_drift_unknown_does_not_claim_a_check(self):
        with patch.object(provider, "runs", return_value={"runs": []}):
            result = provider.drift(self.args(stack="s1"))
        self.assertEqual(result["state"], "unknown")
        self.assertFalse(result["checked_now"])

    def test_drift_present_and_absent_are_based_on_provider_state(self):
        for detected, expected in ((True, "present"), (False, "absent")):
            with patch.object(provider, "runs", return_value={"runs": [{"drift_detection": True, "drift_detected": detected}]}):
                result = provider.drift(self.args(stack="s1"))
            self.assertEqual(result["state"], expected)

    def test_missing_token_json_is_one_redacted_document(self):
        env = os.environ.copy()
        env.update({"SPACELIFT_API_ENDPOINT": "https://account.app.spacelift.io", "SPACELIFT_API_TOKEN": ""})
        result = subprocess.run([str(CLI), "spacelift", "doctor", "--json"], text=True, capture_output=True, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["ok"], False)
        self.assertNotIn("Bearer", result.stdout + result.stderr)

    def test_invalid_provider_json_is_safe(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return b"not-json"
        with patch.dict(os.environ, {"SPACELIFT_API_ENDPOINT": "https://example.test", "SPACELIFT_API_TOKEN": "secret"}), patch("urllib.request.urlopen", return_value=Response()):
            with self.assertRaisesRegex(provider.ProviderError, "malformed JSON"):
                provider.gql("{ __typename }")

    def test_unauthorized_and_timeout_failures_redact_all_credentials(self):
        env = {"SPACELIFT_API_ENDPOINT": "https://example.test", "SPACELIFT_API_TOKEN": "jwt-secret", "SPACELIFT_API_KEY_ID": "key-id", "SPACELIFT_API_KEY_SECRET": "key-secret"}
        unauthorized = urllib.error.HTTPError("https://example.test/graphql", 401, "jwt-secret", {}, None)
        with patch.dict(os.environ, env), patch("urllib.request.urlopen", side_effect=unauthorized):
            with self.assertRaisesRegex(provider.ProviderError, "rejected") as error:
                provider.gql("{ __typename }")
        self.assertNotIn("jwt-secret", str(error.exception))
        with patch.dict(os.environ, env), patch("urllib.request.urlopen", side_effect=urllib.error.URLError("key-secret")):
            with self.assertRaisesRegex(provider.ProviderError, "timed out") as error:
                provider.gql("{ __typename }")
        self.assertNotIn("key-secret", str(error.exception))

    def test_json_success_is_exactly_one_document(self):
        output = StringIO()
        with patch.object(provider, "gql", return_value={"__typename": "Query"}), patch("sys.argv", ["agent-spacelift", "doctor", "--json"]), redirect_stdout(output):
            self.assertEqual(provider.main(), 0)
        self.assertEqual(json.loads(output.getvalue()), {"api": "authenticated", "credential": "available", "ok": True, "read_only": True})


if __name__ == "__main__": unittest.main()

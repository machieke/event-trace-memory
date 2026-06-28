import subprocess
import unittest

from event_trace_memory.rholang import (
    EVENT_TRACE_INDEX,
    RholangCli,
    build_registry_call_program,
    data_at_name_argument,
    rho_literal,
)


class RholangClientTest(unittest.TestCase):
    def test_rho_literal_renders_supported_values(self):
        self.assertEqual(rho_literal("event:1"), '"event:1"')
        self.assertEqual(rho_literal(True), "true")
        self.assertEqual(rho_literal(None), "Nil")
        self.assertEqual(rho_literal(["/2026", 6]), '["/2026", 6]')
        self.assertEqual(
            rho_literal({"eventId": "event:1", "ok": True, "timePrefixKeys": ["/2026"]}),
            '{"eventId": "event:1", "ok": true, "timePrefixKeys": ["/2026"]}',
        )

    def test_rho_literal_rejects_float_literals(self):
        with self.assertRaises(TypeError):
            rho_literal(0.82)

    def test_registry_call_program_uses_published_uri_name(self):
        program = build_registry_call_program(
            EVENT_TRACE_INDEX,
            "byTimePrefix",
            ["/2026/06/28/13"],
            "event-trace-memory:client-result",
        )

        self.assertIn('for (@uri <- @"event-trace-memory:EventTraceIndexUri")', program)
        self.assertIn('@"event-trace-memory:EventTraceIndexUri"!(uri)', program)
        self.assertIn("lookup!(uri, *lookedUp)", program)
        self.assertIn('@eventTraceIndex!("byTimePrefix", "/2026/06/28/13", *result)', program)
        self.assertIn('@"event-trace-memory:client-result"!(value)', program)

    def test_cli_deploy_and_propose_parse_outputs(self):
        calls = []

        def runner(command, timeout):
            calls.append((list(command), timeout))
            if command[1] == "deploy":
                return subprocess.CompletedProcess(command, 0, "Response: Success!\nDeployId is: abc123\n", "")
            return subprocess.CompletedProcess(
                command,
                0,
                "Response: Success! Block deadbeef created and added.\n",
                "",
            )

        client = RholangCli(node_bin="node", runner=runner)
        deploy = client.deploy(location="/tmp/client.rho", private_key="private")
        propose = client.propose()

        self.assertEqual(deploy.deploy_id, "abc123")
        self.assertEqual(propose.block_hash, "deadbeef")
        self.assertEqual(
            calls[0][0],
            [
                "node",
                "deploy",
                "1000000000",
                "1",
                "0",
                "private",
                "/tmp/event-trace-memory-unused-private-key-path",
                "/tmp/client.rho",
                "root",
            ],
        )
        self.assertEqual(calls[1][0], ["node", "propose", "--print-unmatched-sends"])

    def test_cli_data_at_name_uses_rholang_string_argument(self):
        calls = []

        def runner(command, timeout):
            calls.append((list(command), timeout))
            return subprocess.CompletedProcess(command, 124, 'Initial data size: 1\ncontext canceled\n', "")

        client = RholangCli(node_bin="node", runner=runner)
        result = client.data_at_name("event-trace-memory:EventTraceIndexUri", timeout_seconds=3)

        self.assertEqual(data_at_name_argument("event-trace-memory:EventTraceIndexUri"), '"event-trace-memory:EventTraceIndexUri"')
        self.assertEqual(result.initial_data_size, 1)
        self.assertTrue(result.timed_out)
        self.assertEqual(calls[0][0], ["node", "data-at-name", '"event-trace-memory:EventTraceIndexUri"'])
        self.assertEqual(calls[0][1], 3)


if __name__ == "__main__":
    unittest.main()

import io
import json
import unittest
from pathlib import Path

from event_trace_memory.cli import main
from event_trace_memory.rholang import DeployResult, ProposeResult
from event_trace_memory.rholang_deployment import (
    deploy_rholang_contracts,
    load_rholang_deployment_config,
    rholang_deployment_plan,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "rholang-local-docker.json"


class RholangDeploymentTest(unittest.TestCase):
    def test_deployment_config_builds_redacted_plan(self):
        config = load_rholang_deployment_config(CONFIG)
        plan = rholang_deployment_plan(config)

        self.assertEqual(
            [contract.name for contract in config.contracts],
            ["EventTraceIndex", "EventTraceRSpaceIndex", "DerivedArtifactIndex"],
        )
        self.assertEqual(plan["privateKey"], "<redacted>")
        self.assertNotIn(config.private_key, json.dumps(plan))
        self.assertEqual(plan["contracts"][0]["deployCommand"][1], "deploy")
        self.assertEqual(plan["contracts"][0]["deployCommand"][5], "<redacted-private-key>")
        self.assertEqual(plan["proposeCommand"], [config.node_bin, "propose", "--print-unmatched-sends"])

    def test_deploy_contracts_uses_config_sequence(self):
        config = load_rholang_deployment_config(CONFIG)
        fake = FakeRholangCli()

        result = deploy_rholang_contracts(config, cli=fake)

        self.assertEqual([deploy.deploy_id for deploy in result.deploys], ["deploy-1", "deploy-2", "deploy-3"])
        self.assertEqual(result.propose.block_hash, "block-1")
        self.assertEqual(
            [call["location"] for call in fake.deploy_calls],
            [
                "contracts/EventTraceIndex.rho",
                "contracts/EventTraceRSpaceIndex.rho",
                "contracts/DerivedArtifactIndex.rho",
            ],
        )
        self.assertEqual(fake.deploy_calls[0]["private_key"], config.private_key)
        self.assertEqual(fake.deploy_calls[0]["phlo_limit"], 1000000000)
        self.assertEqual(fake.propose_calls, [{"print_unmatched_sends": True}])

    def test_cli_rholang_plan_outputs_redacted_json(self):
        stdout = io.StringIO()

        exit_code = main(["rholang-plan", "--config", str(CONFIG)], stdout=stdout)

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["privateKey"], "<redacted>")
        self.assertNotIn("event-trace-memory-local-dev-private-key", stdout.getvalue())
        self.assertEqual(len(payload["contracts"]), 3)


class FakeRholangCli:
    def __init__(self):
        self.deploy_calls = []
        self.propose_calls = []

    def deploy(self, **kwargs):
        self.deploy_calls.append(kwargs)
        return DeployResult(f"deploy-{len(self.deploy_calls)}", "Response: Success!")

    def propose(self, **kwargs):
        self.propose_calls.append(kwargs)
        return ProposeResult(f"block-{len(self.propose_calls)}", "Response: Success! Block created and added.")


if __name__ == "__main__":
    unittest.main()

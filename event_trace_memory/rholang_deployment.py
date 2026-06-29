"""Config-driven Rholang deployment helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from event_trace_memory.rholang import DeployResult, ProposeResult, RholangCli


@dataclass(frozen=True)
class RholangDeployTarget:
    name: str
    path: str
    valid_after_block: int = 0


@dataclass(frozen=True)
class RholangDeploymentConfig:
    node_bin: str
    private_key: str
    private_key_path: str
    shard_id: str
    phlo_limit: int
    phlo_price: int
    propose_after_deploys: bool
    print_unmatched_sends: bool
    contracts: list[RholangDeployTarget]


@dataclass(frozen=True)
class RholangDeploymentResult:
    deploys: list[DeployResult]
    propose: Optional[ProposeResult]


def load_rholang_deployment_config(path: Any) -> RholangDeploymentConfig:
    return rholang_deployment_config_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def rholang_deployment_config_from_dict(value: dict[str, Any]) -> RholangDeploymentConfig:
    contracts = [
        RholangDeployTarget(
            name=item["name"],
            path=item["path"],
            valid_after_block=item.get("validAfterBlock", value.get("validAfterBlock", 0)),
        )
        for item in value["contracts"]
    ]
    return RholangDeploymentConfig(
        node_bin=value.get("nodeBin", "/opt/docker/bin/node"),
        private_key=value["privateKey"],
        private_key_path=value.get("privateKeyPath", "/tmp/event-trace-memory-unused-private-key-path"),
        shard_id=value.get("shardId", "root"),
        phlo_limit=value.get("phloLimit", 1000000000),
        phlo_price=value.get("phloPrice", 1),
        propose_after_deploys=value.get("proposeAfterDeploys", True),
        print_unmatched_sends=value.get("printUnmatchedSends", True),
        contracts=contracts,
    )


def rholang_deployment_plan(config: RholangDeploymentConfig) -> dict[str, Any]:
    return {
        "nodeBin": config.node_bin,
        "shardId": config.shard_id,
        "phloLimit": config.phlo_limit,
        "phloPrice": config.phlo_price,
        "privateKey": "<redacted>",
        "privateKeyPath": config.private_key_path,
        "proposeAfterDeploys": config.propose_after_deploys,
        "printUnmatchedSends": config.print_unmatched_sends,
        "contracts": [
            {
                "name": contract.name,
                "path": contract.path,
                "validAfterBlock": contract.valid_after_block,
                "deployCommand": [
                    config.node_bin,
                    "deploy",
                    str(config.phlo_limit),
                    str(config.phlo_price),
                    str(contract.valid_after_block),
                    "<redacted-private-key>",
                    config.private_key_path,
                    contract.path,
                    config.shard_id,
                ],
            }
            for contract in config.contracts
        ],
        "proposeCommand": _propose_command(config) if config.propose_after_deploys else None,
    }


def deploy_rholang_contracts(config: RholangDeploymentConfig, cli: Optional[RholangCli] = None) -> RholangDeploymentResult:
    cli = cli or RholangCli(node_bin=config.node_bin)
    deploys = [
        cli.deploy(
            location=contract.path,
            private_key=config.private_key,
            private_key_path=config.private_key_path,
            phlo_limit=config.phlo_limit,
            phlo_price=config.phlo_price,
            valid_after_block=contract.valid_after_block,
            shard_id=config.shard_id,
        )
        for contract in config.contracts
    ]
    propose = None
    if config.propose_after_deploys:
        propose = cli.propose(print_unmatched_sends=config.print_unmatched_sends)
    return RholangDeploymentResult(deploys=deploys, propose=propose)


def _propose_command(config: RholangDeploymentConfig) -> list[str]:
    if config.print_unmatched_sends:
        return [config.node_bin, "propose", "--print-unmatched-sends"]
    return [config.node_bin, "propose"]

"""Rholang deploy/call client helpers."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence


EVENT_TRACE_INDEX_URI_NAME = "event-trace-memory:EventTraceIndexUri"
EVENT_TRACE_RSPACE_INDEX_URI_NAME = "event-trace-memory:EventTraceRSpaceIndexUri"
DERIVED_ARTIFACT_INDEX_URI_NAME = "event-trace-memory:DerivedArtifactIndexUri"


class RholangClientError(RuntimeError):
    """Raised when the F1R3FLY node CLI returns an unusable result."""


@dataclass(frozen=True)
class RholangContractBinding:
    uri_name: str
    contract_name: str


EVENT_TRACE_INDEX = RholangContractBinding(EVENT_TRACE_INDEX_URI_NAME, "eventTraceIndex")
EVENT_TRACE_RSPACE_INDEX = RholangContractBinding(EVENT_TRACE_RSPACE_INDEX_URI_NAME, "eventTraceRSpaceIndex")
DERIVED_ARTIFACT_INDEX = RholangContractBinding(DERIVED_ARTIFACT_INDEX_URI_NAME, "derivedArtifactIndex")


@dataclass(frozen=True)
class DeployResult:
    deploy_id: str
    output: str


@dataclass(frozen=True)
class ProposeResult:
    block_hash: str
    output: str


@dataclass(frozen=True)
class DataAtNameResult:
    name: str
    initial_data_size: int | None
    output: str
    timed_out: bool = False


Runner = Callable[[Sequence[str], Optional[int]], subprocess.CompletedProcess]


def rho_literal(value: Any) -> str:
    """Render a Python value as a Rholang literal accepted by the target runtime."""

    if value is None:
        return "Nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        raise TypeError("F1R3FLY Rholang validation does not accept float literals; pass an integer-scaled value")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(rho_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        parts: list[str] = []
        for key in sorted(value):
            if not isinstance(key, str):
                raise TypeError("Rholang map literal keys must be strings")
            parts.append(f"{rho_literal(key)}: {rho_literal(value[key])}")
        return "{" + ", ".join(parts) + "}"
    raise TypeError(f"Unsupported Rholang literal type: {type(value).__name__}")


def rho_public_name(name: str) -> str:
    return "@" + rho_literal(name)


def data_at_name_argument(name: str) -> str:
    return rho_literal(name)


def build_registry_call_program(
    binding: RholangContractBinding,
    method: str,
    args: Sequence[Any],
    result_name: str,
) -> str:
    rendered_args = [rho_literal(method)] + [rho_literal(arg) for arg in args]
    rendered_call_args = ", ".join(rendered_args + ["*result"])
    uri_name = rho_public_name(binding.uri_name)
    result_public_name = rho_public_name(result_name)

    return f"""new lookup(`rho:registry:lookup`), lookedUp, result in {{
  for (@uri <- {uri_name}) {{
    {uri_name}!(uri)
    |
    lookup!(uri, *lookedUp)
    |
    for (@{binding.contract_name} <- lookedUp) {{
      @{binding.contract_name}!({rendered_call_args})
    }}
    |
    for (@value <- result) {{
      {result_public_name}!(value)
    }}
  }}
}}
"""


def build_registry_marker_program(
    binding: RholangContractBinding,
    method: str,
    args: Sequence[Any],
    success_name: str,
    result_expression: str,
) -> str:
    rendered_args = [rho_literal(method)] + [rho_literal(arg) for arg in args]
    rendered_call_args = ", ".join(rendered_args + ["*result"])
    uri_name = rho_public_name(binding.uri_name)
    success_public_name = rho_public_name(success_name)

    return f"""new lookup(`rho:registry:lookup`), lookedUp, result in {{
  for (@uri <- {uri_name}) {{
    {uri_name}!(uri)
    |
    lookup!(uri, *lookedUp)
    |
    for (@{binding.contract_name} <- lookedUp) {{
      @{binding.contract_name}!({rendered_call_args})
    }}
    |
    for (@value <- result) {{
      if ({result_expression}) {{
        {success_public_name}!(true)
      }}
    }}
  }}
}}
"""


class RholangCli:
    def __init__(
        self,
        *,
        node_bin: str = "/opt/docker/bin/node",
        runner: Runner | None = None,
    ) -> None:
        self.node_bin = node_bin
        self.runner = runner or self._subprocess_runner

    def deploy(
        self,
        *,
        location: str | Path,
        private_key: str,
        private_key_path: str = "/tmp/event-trace-memory-unused-private-key-path",
        phlo_limit: int = 1000000000,
        phlo_price: int = 1,
        valid_after_block: int = 0,
        shard_id: str = "root",
    ) -> DeployResult:
        command = [
            self.node_bin,
            "deploy",
            str(phlo_limit),
            str(phlo_price),
            str(valid_after_block),
            private_key,
            private_key_path,
            str(location),
            shard_id,
        ]
        completed = self._run(command)
        output = _combined_output(completed)
        if completed.returncode != 0 or "Response: Success!" not in output:
            raise RholangClientError(output)
        match = re.search(r"^DeployId is: (?P<deploy_id>\S+)$", output, re.MULTILINE)
        if not match:
            raise RholangClientError(f"Deploy succeeded without a deploy id:\n{output}")
        return DeployResult(match.group("deploy_id"), output)

    def propose(self, *, print_unmatched_sends: bool = True) -> ProposeResult:
        command = [self.node_bin, "propose"]
        if print_unmatched_sends:
            command.append("--print-unmatched-sends")
        completed = self._run(command)
        output = _combined_output(completed)
        if completed.returncode != 0 or "Response: Success! Block" not in output:
            raise RholangClientError(output)
        match = re.search(r"Response: Success! Block (?P<block_hash>[0-9a-f]+) created and added\.", output)
        if not match:
            raise RholangClientError(f"Propose succeeded without a block hash:\n{output}")
        return ProposeResult(match.group("block_hash"), output)

    def data_at_name(self, name: str, *, timeout_seconds: int = 10) -> DataAtNameResult:
        command = [self.node_bin, "data-at-name", data_at_name_argument(name)]
        try:
            completed = self._run(command, timeout_seconds)
            output = _combined_output(completed)
            timed_out = completed.returncode == 124
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            output = stdout + stderr
            timed_out = True

        match = re.search(r"Initial data size: (?P<size>\d+)", output)
        size = int(match.group("size")) if match else None
        return DataAtNameResult(name, size, output, timed_out)

    def _run(self, command: Sequence[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        return self.runner(command, timeout)

    @staticmethod
    def _subprocess_runner(command: Sequence[str], timeout: int | None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )


def _combined_output(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stdout or "") + (completed.stderr or "")

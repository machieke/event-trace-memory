#!/usr/bin/env python3
"""Benchmark RSpace batch-anchor deploy inclusion/finality on a local shard."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRIVATE_KEY = os.environ.get(
    "RHOLANG_VALIDATOR_PRIVATE_KEY",
    "5f668a7ee96d944a4494cc947e4005e172d7ab3461ee5538f1f2a45a835e9657",
)
PRIVATE_KEY_PATH = "/tmp/event-trace-memory-unused-private-key-path"
SHARD_ID = "root"
PHLO_LIMIT = 1_000_000_000
PHLO_PRICE = 1

DEFAULT_BASELINE = Path("docs/performance/artifacts/rspace-batch-anchor-recovery-aware-20260713T111154Z.json")
DEFAULT_BASELINE_100X50 = Path("docs/performance/artifacts/rspace-batch-anchor-100x50-20260713T124204Z.json")


@dataclass(frozen=True)
class Workload:
    deploys: int
    batch_size: int

    @property
    def label(self) -> str:
        return f"{self.deploys}x{self.batch_size}"

    @property
    def events(self) -> int:
        return self.deploys * self.batch_size


def run(command: list[str], *, timeout: int | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=timeout)
    if check and completed.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(command)
            + "\nstdout:\n"
            + completed.stdout
            + "\nstderr:\n"
            + completed.stderr
        )
    return completed


def docker_exec(container: str, args: list[str], *, timeout: int | None = None, check: bool = True) -> str:
    completed = run(["docker", "exec", container, *args], timeout=timeout, check=check)
    return (completed.stdout or "") + (completed.stderr or "")


def docker_cp(src: Path, container: str, dst: str) -> None:
    run(["docker", "cp", str(src), f"{container}:{dst}"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_workload(value: str) -> Workload:
    match = re.fullmatch(r"(\d+)x(\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError(f"invalid workload {value!r}; expected NxM, for example 10x50")
    return Workload(deploys=int(match.group(1)), batch_size=int(match.group(2)))


def parse_latest_block_number(show_blocks_output: str) -> int:
    matches = [int(value) for value in re.findall(r"block_number:\s*(\d+)", show_blocks_output)]
    if not matches:
        raise RuntimeError(f"could not parse block_number from show-blocks output:\n{show_blocks_output}")
    return max(matches)


def parse_latest_block_hash(show_blocks_output: str) -> str:
    match = re.search(r'block_hash:\s*"([0-9a-f]+)"', show_blocks_output)
    if not match:
        raise RuntimeError(f"could not parse block_hash from show-blocks output:\n{show_blocks_output}")
    return match.group(1)


def latest_block(container: str) -> dict[str, Any]:
    output = docker_exec(container, ["/opt/docker/bin/node", "show-blocks", "1"])
    return {
        "number": parse_latest_block_number(output),
        "hash": parse_latest_block_hash(output),
        "raw": output,
    }


def last_finalized_block(container: str) -> dict[str, Any]:
    output = docker_exec(container, ["/opt/docker/bin/node", "last-finalized-block"])
    return {
        "number": parse_latest_block_number(output),
        "hash": parse_latest_block_hash(output),
        "raw": output,
    }


def write_scoped_contract(root: Path, tmp_dir: Path, uri_name: str) -> Path:
    source = (root / "contracts" / "EventTraceRSpaceIndex.rho").read_text(encoding="utf-8")
    scoped = source.replace(
        '"event-trace-memory:EventTraceRSpaceIndexUri"',
        json.dumps(uri_name),
    )
    path = tmp_dir / "EventTraceRSpaceIndex.scoped.rho"
    path.write_text(scoped, encoding="utf-8")
    return path


def deploy_file(container: str, local_path: Path, remote_name: str, valid_after: int) -> dict[str, Any]:
    remote_path = f"/tmp/{remote_name}"
    docker_cp(local_path, container, remote_path)
    start = utc_now()
    output = docker_exec(
        container,
        [
            "/opt/docker/bin/node",
            "deploy",
            str(PHLO_LIMIT),
            str(PHLO_PRICE),
            str(valid_after),
            PRIVATE_KEY,
            PRIVATE_KEY_PATH,
            remote_path,
            SHARD_ID,
        ],
        timeout=120,
    )
    end = utc_now()
    if "Response: Success!" not in output:
        raise RuntimeError(f"deploy failed for {local_path}:\n{output}")
    match = re.search(r"^DeployId is:\s*(\S+)$", output, re.MULTILINE)
    if not match:
        raise RuntimeError(f"deploy succeeded without deploy id:\n{output}")
    return {
        "deploy_id": match.group(1),
        "start_iso": start.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "end_iso": end.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "elapsed_s": (end - start).total_seconds(),
        "output": output,
    }


def data_at_name_size(container: str, name: str) -> int | None:
    completed = run(
        ["docker", "exec", container, "/opt/docker/bin/node", "data-at-name", json.dumps(name)],
        timeout=20,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    match = re.search(r"Initial data size:\s*(\d+)", output)
    return int(match.group(1)) if match else None


def wait_for_data_at_name(container: str, name: str, *, timeout_s: int) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if data_at_name_size(container, name):
            return time.monotonic() - start
        time.sleep(2)
    raise TimeoutError(f"timed out waiting for data at public name {name!r}")


def light_blocks(container: str, depth: int) -> list[dict[str, Any]]:
    output = docker_exec(container, ["/opt/docker/bin/node", "show-blocks", str(depth)], timeout=120)
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("block_hash:"):
            match = re.search(r'"([0-9a-f]+)"', line)
            if match:
                current = {"hash": match.group(1)}
        elif line.startswith("block_number:") and current:
            match = re.search(r"(\d+)", line)
            if match:
                current["number"] = int(match.group(1))
        elif line.startswith("block_size:") and current:
            match = re.search(r'"(\d+)"', line)
            if match:
                current["block_size"] = int(match.group(1))
        elif line.startswith("deploy_count:") and current:
            match = re.search(r"(\d+)", line)
            if match:
                current["deploy_count"] = int(match.group(1))
        elif line.startswith("is_finalized:") and current:
            current["finalized"] = "true" in line
            if "hash" in current and "number" in current:
                blocks.append(current)
            current = {}
    return blocks


def scan_blocks_for_text(container: str, needle: str, *, depth: int = 250) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for light in light_blocks(container, depth):
        if light["hash"] in seen_hashes or int(light.get("deploy_count") or 0) == 0:
            continue
        seen_hashes.add(light["hash"])
        output = show_block(container, light["hash"])
        if needle not in output:
            continue
        summary = block_summary_from_output(light["hash"], output)
        summary["number"] = light.get("number", summary.get("number"))
        summary["finalized"] = light.get("finalized")
        summary["deploy_count"] = light.get("deploy_count", summary.get("deploy_count"))
        hits.append(summary)
    return sorted(hits, key=lambda item: item.get("number") or 0)


def wait_for_finalized_contract(container: str, uri_name: str, *, timeout_s: int, depth: int) -> dict[str, Any]:
    start = utc_now()
    while (utc_now() - start).total_seconds() < timeout_s:
        hits = scan_blocks_for_text(container, uri_name, depth=depth)
        finalized_hits = [hit for hit in hits if hit.get("finalized")]
        if finalized_hits:
            hit = finalized_hits[-1]
            hit["elapsed_s"] = (utc_now() - start).total_seconds()
            return hit
        print(
            f"contract binding scan: hits={len(hits)} finalized={len(finalized_hits)}",
            flush=True,
        )
        time.sleep(5)
    raise TimeoutError(f"timed out waiting for finalized contract deploy containing {uri_name!r}")


def rho_literal(value: Any) -> str:
    if value is None:
        return "Nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, list):
        return "[" + ", ".join(rho_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        parts = [f"{rho_literal(key)}: {rho_literal(value[key])}" for key in sorted(value)]
        return "{" + ", ".join(parts) + "}"
    raise TypeError(f"unsupported literal type: {type(value).__name__}")


def event_pointer(run_id: str, batch: int, offset: int) -> dict[str, Any]:
    event_id = f"event:{run_id}:batch-{batch:02d}:event-{offset:04d}"
    root_id = f"event:{run_id}:batch-{batch:02d}:event-0000"
    return {
        "actorPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/user", f"/irc/libera/user/user-{offset % 20:02d}"],
        "channelPrefixKeys": [
            "/irc",
            "/irc/libera",
            "/irc/libera/channel",
            f"/irc/libera/channel/%23rspace-{offset % 10:02d}",
        ],
        "eventCid": f"cid:{run_id}:event:{batch:02d}:{offset:04d}",
        "eventId": event_id,
        "kind": "event-pointer",
        "parentEventIds": [] if offset == 0 else [f"event:{run_id}:batch-{batch:02d}:event-{offset - 1:04d}"],
        "payloadCid": f"cid:{run_id}:payload:{batch:02d}:{offset:04d}",
        "rootEventId": root_id,
        "schema": "event-pointer-v0.1",
        "timePrefixKeys": ["/2026", "/2026/07", "/2026/07/13", f"/2026/07/13/{13 + (offset % 4):02d}"],
        "valueKind": "memory-query" if offset % 3 == 0 else "message",
    }


def batch_anchor(run_id: str, batch: int, batch_size: int) -> dict[str, Any]:
    return {
        "batchId": f"batch:{run_id}:{batch:02d}",
        "eventCount": batch_size,
        "eventManifestCid": f"cid:{run_id}:event-manifest:{batch:02d}",
        "kind": "event-trace-batch-anchor",
        "maxObservedAt": "2026-07-13T13:59:59Z",
        "merkleRoot": f"merkle:{run_id}:{batch:02d}",
        "minObservedAt": "2026-07-13T13:00:00Z",
        "postingsManifestCid": f"cid:{run_id}:postings:{batch:02d}",
        "schema": "event-trace-batch-anchor-v0.1",
        "shardPath": "/2026/07/13/13",
    }


def write_batch_deploy(tmp_dir: Path, uri_name: str, run_id: str, batch: int, batch_size: int) -> Path:
    anchor = batch_anchor(run_id, batch, batch_size)
    events = [event_pointer(run_id, batch, offset) for offset in range(batch_size)]
    marker_name = f"event-trace-memory:RSpaceScaleOk:{run_id}:batch-{batch:02d}"
    path = tmp_dir / f"{run_id}-batch-{batch:02d}.rho"
    path.write_text(
        f"""new lookup(`rho:registry:lookup`), lookedUp, putAck in {{
  for (@uri <- @{rho_literal(uri_name)}) {{
    @{rho_literal(uri_name)}!(uri)
    |
    lookup!(uri, *lookedUp)
    |
    for (@eventTraceRSpaceIndex <- lookedUp) {{
      @eventTraceRSpaceIndex!("putBatchEvents", {rho_literal(anchor)}, {rho_literal(events)}, *putAck)
    }}
    |
    for (@result <- putAck) {{
      if (result.get("ok")) {{
        @{rho_literal(marker_name)}!(result)
      }}
    }}
  }}
}}
""",
        encoding="utf-8",
    )
    return path


def parse_find_deploy(output: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for match in re.finditer(r"BlockInfo\s*\{(?P<body>.*?)(?=\nBlockInfo\s*\{|\Z)", output, flags=re.DOTALL):
        body = match.group("body")
        hash_match = re.search(r'block_hash:\s*"([0-9a-f]+)"', body)
        number_match = re.search(r"block_number:\s*(\d+)", body)
        finalized_match = re.search(r"is_finalized:\s*(true|false)", body)
        deploy_count_match = re.search(r"deploy_count:\s*(\d+)", body)
        if hash_match and number_match:
            hits.append(
                {
                    "hash": hash_match.group(1),
                    "number": int(number_match.group(1)),
                    "finalized": finalized_match.group(1) == "true" if finalized_match else None,
                    "deploy_count": int(deploy_count_match.group(1)) if deploy_count_match else None,
                }
            )
    return hits


def find_deploy(container: str, deploy_id: str) -> list[dict[str, Any]]:
    output = docker_exec(container, ["/opt/docker/bin/node", "find-deploy", deploy_id], timeout=60, check=False)
    return parse_find_deploy(output)


def is_finalized(container: str, block_hash: str) -> bool:
    output = docker_exec(container, ["/opt/docker/bin/node", "is-finalized", block_hash], timeout=30, check=False)
    return "true" in output.lower()


def show_block(container: str, block_hash: str) -> str:
    return docker_exec(container, ["/opt/docker/bin/node", "show-block", block_hash], timeout=120)


def block_summary(container: str, block_hash: str) -> dict[str, Any]:
    output = show_block(container, block_hash)
    return block_summary_from_output(block_hash, output)


def block_summary_from_output(block_hash: str, output: str) -> dict[str, Any]:
    number_match = re.search(r"block_number:\s*(\d+)", output)
    size_match = re.search(r'block_size:\s*"(\d+)"', output)
    deploy_count_match = re.search(r"deploy_count:\s*(\d+)", output)
    cost_values = [int(value) for value in re.findall(r"cost:\s*(\d+)", output)]
    return {
        "hash": block_hash,
        "number": int(number_match.group(1)) if number_match else None,
        "block_size": int(size_match.group(1)) if size_match else None,
        "deploy_count": int(deploy_count_match.group(1)) if deploy_count_match else None,
        "cost_sum": sum(cost_values),
        "cost_values": cost_values,
        "errors": len(re.findall(r"errored:\s*true", output)),
    }


def load_baselines(root: Path) -> dict[str, Any]:
    baselines: dict[str, Any] = {}
    recovery_path = root / DEFAULT_BASELINE
    if recovery_path.exists():
        recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
        for label, item in recovery.get("results", {}).items():
            baselines[label] = item
    large_path = root / DEFAULT_BASELINE_100X50
    if large_path.exists():
        large = json.loads(large_path.read_text(encoding="utf-8"))
        result = large.get("result", {})
        if result:
            baselines[result.get("label", "100x50")] = result
    return baselines


def compare_to_baseline(result: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any] | None:
    if not baseline:
        return None

    def baseline_value(*names: str) -> float | int | None:
        for name in names:
            value = baseline.get(name)
            if value is not None:
                return value
        return None

    comparisons: dict[str, Any] = {}
    fields = [
        ("canonical_added_s", "first_deploy_to_canonical_added_s"),
        ("finality_s", "first_deploy_to_finality_s"),
        ("first_inclusion_s", "first_deploy_to_first_added_s"),
        ("total_cost_sum", "total_cost_sum"),
        ("cost_per_event", "cost_per_event"),
        ("canonical_block_count", "canonical_block_count"),
    ]
    for current_name, baseline_name in fields:
        current = result.get(current_name)
        previous = baseline_value(baseline_name)
        if current is None or previous in (None, 0):
            continue
        comparisons[current_name] = {
            "previous": previous,
            "current": current,
            "delta": current - previous,
            "ratio": current / previous,
        }
    return comparisons


def poll_workload(
    container: str,
    workload: Workload,
    run_id: str,
    first_submit: datetime,
    *,
    poll_s: float,
    timeout_s: int,
) -> dict[str, Any]:
    start_monotonic = time.monotonic()
    first_inclusion: dict[str, Any] | None = None
    first_all_included: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] = []
    expected_batches = set(range(workload.deploys))

    while time.monotonic() - start_monotonic < timeout_s:
        now = utc_now()
        hits = scan_blocks_for_text(container, run_id, depth=300)
        for hit in hits:
            hit["batch_ids"] = sorted(batch_ids_from_block_output(run_id, show_block(container, hit["hash"])))
            hit["batch_count"] = len(hit["batch_ids"])

        included_batches: set[int] = set()
        finalized_batches: set[int] = set()
        for hit in hits:
            included_batches.update(hit["batch_ids"])
            if hit.get("finalized"):
                finalized_batches.update(hit["batch_ids"])

        if included_batches and first_inclusion is None:
            first_hit = sorted(hits, key=lambda item: item.get("number") or 0)[0]
            first_inclusion = {
                **first_hit,
                "observed_iso": now.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "elapsed_s": (now - first_submit).total_seconds(),
            }
        if included_batches >= expected_batches and first_all_included is None:
            first_all_included = {
                "observed_iso": now.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "elapsed_s": (now - first_submit).total_seconds(),
                "block_count": len(hits),
            }

        timeline.append(
            {
                "observed_iso": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "included_batches": len(included_batches),
                "finalized_batches": len(finalized_batches),
                "hit_block_count": len(hits),
                "finalized_block_count": len([hit for hit in hits if hit.get("finalized")]),
            }
        )

        print(
            f"{workload.label}: included={len(included_batches)}/{workload.deploys} "
            f"finalized={len(finalized_batches)}/{workload.deploys} "
            f"hit_blocks={len(hits)} finalized_blocks={len([hit for hit in hits if hit.get('finalized')])}",
            flush=True,
        )
        if finalized_batches >= expected_batches:
            finality_observed = now
            canonical_blocks = [
                hit for hit in hits if hit.get("finalized") and set(hit["batch_ids"]) & expected_batches
            ]
            cost_sum = sum(block["cost_sum"] for block in canonical_blocks)
            total_size = sum(block["block_size"] or 0 for block in canonical_blocks)
            finality_s = (finality_observed - first_submit).total_seconds()
            canonical_added_s = finality_s
            if first_all_included:
                canonical_added_s = first_all_included["elapsed_s"]
            return {
                "label": workload.label,
                "events": workload.events,
                "deploys_submitted": workload.deploys,
                "batch_size": workload.batch_size,
                "first_inclusion_s": first_inclusion["elapsed_s"] if first_inclusion else None,
                "all_included_s": first_all_included["elapsed_s"] if first_all_included else None,
                "canonical_added_s": canonical_added_s,
                "finality_s": finality_s,
                "canonical_added_to_finality_s": finality_s - canonical_added_s,
                "events_per_s_to_canonical_added": workload.events / canonical_added_s if canonical_added_s else None,
                "events_per_s_to_finality": workload.events / finality_s if finality_s else None,
                "total_cost_sum": cost_sum,
                "cost_avg": cost_sum / workload.deploys if workload.deploys else None,
                "cost_per_event": cost_sum / workload.events if workload.events else None,
                "total_block_size": total_size,
                "canonical_block_count": len(canonical_blocks),
                "canonical_blocks": canonical_blocks,
                "first_inclusion": first_inclusion,
                "first_all_included": first_all_included,
                "timeline": timeline,
                "all_hits": hits,
                "errored_true_count": sum(block["errors"] for block in canonical_blocks),
            }

        time.sleep(poll_s)

    raise TimeoutError(f"timed out waiting for {workload.label} finality")


def batch_ids_from_block_output(run_id: str, output: str) -> set[int]:
    ids: set[int] = set()
    escaped = re.escape(run_id)
    for match in re.finditer(rf"batch:{escaped}:(\d+)", output):
        ids.add(int(match.group(1)))
    for match in re.finditer(rf"{escaped}:batch-(\d+)", output):
        ids.add(int(match.group(1)))
    return ids


def run_workload(
    root: Path,
    container: str,
    tmp_dir: Path,
    uri_name: str,
    workload: Workload,
    run_prefix: str,
    baseline: dict[str, Any] | None,
    *,
    poll_s: float,
    timeout_s: int,
) -> dict[str, Any]:
    valid_after = last_finalized_block(container)["number"]
    run_id = f"rspace-leadership-{workload.label}-{run_prefix}"
    deploy_results: list[dict[str, Any]] = []
    print(f"Submitting {workload.label} as {run_id} with validAfter={valid_after}", flush=True)
    first_submit: datetime | None = None
    for batch in range(workload.deploys):
        path = write_batch_deploy(tmp_dir, uri_name, run_id, batch, workload.batch_size)
        deploy_result = deploy_file(container, path, path.name, valid_after)
        deploy_result["batch"] = batch
        deploy_result["term_bytes"] = path.stat().st_size
        if first_submit is None:
            first_submit = datetime.fromisoformat(deploy_result["start_iso"].replace("Z", "+00:00"))
        deploy_results.append(deploy_result)
        if (batch + 1) % 10 == 0 or batch + 1 == workload.deploys:
            elapsed = (utc_now() - first_submit).total_seconds()
            print(f"{workload.label}: submitted {batch + 1}/{workload.deploys} in {elapsed:.3f}s", flush=True)

    assert first_submit is not None
    result = poll_workload(
        container,
        workload,
        run_id,
        first_submit,
        poll_s=poll_s,
        timeout_s=timeout_s,
    )
    result["submit_span_s"] = (
        datetime.fromisoformat(deploy_results[-1]["end_iso"].replace("Z", "+00:00")) - first_submit
    ).total_seconds()
    result.update(
        {
            "run_id": run_id,
            "valid_after": valid_after,
            "uri_name": uri_name,
            "deploys": deploy_results,
            "total_term_bytes": sum(item["term_bytes"] for item in deploy_results),
        }
    )
    result["comparison"] = compare_to_baseline(result, baseline)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="rnode.validator3")
    parser.add_argument("--workload", action="append", type=parse_workload, default=[])
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument(
        "--existing-uri",
        help="Use an already-finalized EventTraceRSpaceIndex registry URI instead of deploying a new scoped contract.",
    )
    parser.add_argument(
        "--contract-scan-depth",
        type=int,
        default=250,
        help="Recent block depth to scan when confirming the scoped contract binding.",
    )
    parser.add_argument(
        "--skip-contract-check",
        action="store_true",
        help="Skip block scanning for an existing contract URI that was already verified externally.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    workloads = args.workload or [Workload(10, 10), Workload(10, 25), Workload(10, 50), Workload(100, 50)]
    run_prefix = utc_now().strftime("%Y%m%dT%H%M%SZ")
    uri_name = args.existing_uri or f"event-trace-memory:EventTraceRSpaceIndexUri:leadership-{run_prefix}"
    output = args.output or Path(f"/tmp/event-trace-memory-leadership-benchmark-{run_prefix}.json")
    baselines = load_baselines(root)

    with tempfile.TemporaryDirectory(prefix="etm-rspace-leadership-") as tmp:
        tmp_dir = Path(tmp)
        if args.existing_uri:
            contract_deploy = None
            print(f"Using existing scoped EventTraceRSpaceIndex URI {uri_name}", flush=True)
        else:
            contract = write_scoped_contract(root, tmp_dir, uri_name)
            contract_valid_after = last_finalized_block(args.container)["number"]
            print(f"Deploying scoped EventTraceRSpaceIndex as {uri_name} validAfter={contract_valid_after}", flush=True)
            contract_deploy = deploy_file(args.container, contract, contract.name, contract_valid_after)
            print(f"Scoped contract deploy id: {contract_deploy['deploy_id']}", flush=True)

        if args.skip_contract_check:
            contract_block = None
            binding_wait_s = 0.0
            print("Skipped scoped contract block scan", flush=True)
        else:
            contract_block = wait_for_finalized_contract(
                args.container,
                uri_name,
                timeout_s=600,
                depth=args.contract_scan_depth,
            )
            binding_wait_s = contract_block["elapsed_s"]
            print(
                f"Scoped contract available in finalized block {contract_block.get('number')} after {binding_wait_s:.3f}s",
                flush=True,
            )

        results = []
        for workload in workloads:
            results.append(
                run_workload(
                    root,
                    args.container,
                    tmp_dir,
                    uri_name,
                    workload,
                    run_prefix,
                    baselines.get(workload.label),
                    poll_s=args.poll_seconds,
                    timeout_s=args.timeout_seconds,
                )
            )

    artifact = {
        "created_at": iso_now(),
        "container": args.container,
        "node_status": docker_exec(args.container, ["/opt/docker/bin/node", "status"], check=False),
        "latest_block_after": latest_block(args.container),
        "last_finalized_after": last_finalized_block(args.container),
        "uri_name": uri_name,
        "contract_deploy": contract_deploy,
        "contract_block": contract_block,
        "contract_binding_wait_s": binding_wait_s,
        "results": {item["label"]: item for item in results},
    }
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {output}", flush=True)
    print(json.dumps({label: summarize_result(item) for label, item in artifact["results"].items()}, indent=2), flush=True)
    return 0


def summarize_result(item: dict[str, Any]) -> dict[str, Any]:
    comparison = item.get("comparison") or {}
    return {
        "run_id": item.get("run_id"),
        "events": item.get("events"),
        "deploys": item.get("deploys_submitted"),
        "canonical_blocks": item.get("canonical_block_count"),
        "cost_sum": item.get("total_cost_sum"),
        "cost_per_event": item.get("cost_per_event"),
        "first_inclusion_s": item.get("first_inclusion_s"),
        "canonical_added_s": item.get("canonical_added_s"),
        "finality_s": item.get("finality_s"),
        "events_per_s_to_finality": item.get("events_per_s_to_finality"),
        "comparison": comparison,
    }


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Deploy stored percept-memory event pointers through the RSpace batch-anchor path."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shlex
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_rspace_batch_anchor as bench  # noqa: E402


DEFAULT_POINTER_CONTAINER = "percept-memory"
DEFAULT_POINTER_LOG = "/data/pointers.jsonl"


@dataclass(frozen=True)
class StoredEventWorkload:
    deploys: int
    batch_size: int
    events: int

    @property
    def label(self) -> str:
        return f"stored-{self.events}-events-{self.deploys}x{self.batch_size}"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def merkle_root_hex(leaves: list[bytes]) -> str:
    if not leaves:
        return hashlib.sha256(b"").hexdigest()
    level = [hashlib.sha256(leaf).digest() for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()


def parse_hour_start(pointer: dict[str, Any]) -> datetime | None:
    time_path = pointer.get("timePath")
    if not isinstance(time_path, list) or len(time_path) < 4:
        return None
    try:
        return datetime(
            int(time_path[0]),
            int(time_path[1]),
            int(time_path[2]),
            int(time_path[3]),
            tzinfo=timezone.utc,
        )
    except (TypeError, ValueError):
        return None


def iso_hour_range(events: list[dict[str, Any]]) -> tuple[str, str]:
    hours = [parsed for event in events if (parsed := parse_hour_start(event))]
    if not hours:
        return "unknown", "unknown"
    min_hour = min(hours)
    max_hour = max(hours).replace(minute=59, second=59)
    return (
        min_hour.isoformat(timespec="seconds").replace("+00:00", "Z"),
        max_hour.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )


def common_time_shard(events: list[dict[str, Any]]) -> str:
    paths = [event.get("timePrefixKeys") for event in events if isinstance(event.get("timePrefixKeys"), list)]
    if not paths:
        return "/stored-events"
    common = list(paths[0])
    for path in paths[1:]:
        next_common: list[str] = []
        for left, right in zip(common, path):
            if left != right:
                break
            next_common.append(left)
        common = next_common
        if not common:
            break
    return str(common[-1]) if common else "/stored-events"


def postings_fingerprint(events: list[dict[str, Any]]) -> dict[str, Any]:
    indexes: dict[str, collections.defaultdict[str, list[str]]] = {
        "kind": collections.defaultdict(list),
        "root": collections.defaultdict(list),
        "time": collections.defaultdict(list),
        "actor": collections.defaultdict(list),
        "channel": collections.defaultdict(list),
        "parent": collections.defaultdict(list),
    }
    for event in events:
        event_id = str(event.get("eventId"))
        indexes["kind"][str(event.get("valueKind"))].append(event_id)
        indexes["root"][str(event.get("rootEventId", event_id))].append(event_id)
        for key in event.get("timePrefixKeys") or []:
            indexes["time"][str(key)].append(event_id)
        for key in event.get("actorPrefixKeys") or []:
            indexes["actor"][str(key)].append(event_id)
        for key in event.get("channelPrefixKeys") or []:
            indexes["channel"][str(key)].append(event_id)
        for key in event.get("parentEventIds") or []:
            indexes["parent"][str(key)].append(event_id)
    return {
        name: {key: values for key, values in sorted(index.items())}
        for name, index in sorted(indexes.items())
    }


def source_pointer_log(container: str, pointer_log: str, *, timeout_s: int) -> tuple[str, str]:
    completed = bench.run(
        ["docker", "exec", container, "sh", "-lc", f"cat {shlex.quote(pointer_log)}"],
        timeout=timeout_s,
    )
    text = completed.stdout
    return text, sha256_hex(text.encode("utf-8"))


def load_unique_pointers(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates = 0
    bad_json = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            pointer = json.loads(line)
        except json.JSONDecodeError:
            bad_json += 1
            continue
        event_id = pointer.get("eventId")
        if not isinstance(event_id, str):
            raise ValueError(f"pointer log line {line_no} has no string eventId")
        if event_id in seen:
            duplicates += 1
            continue
        seen.add(event_id)
        events.append(pointer)
    return events, {
        "line_count": len(text.splitlines()),
        "unique_event_count": len(events),
        "duplicate_event_ids": duplicates,
        "bad_json_lines": bad_json,
    }


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    kinds: collections.Counter[str] = collections.Counter()
    roots: set[str] = set()
    sessions: collections.Counter[str] = collections.Counter()
    hours: collections.Counter[str] = collections.Counter()
    actors: collections.Counter[str] = collections.Counter()
    for event in events:
        kinds[str(event.get("valueKind", ""))] += 1
        roots.add(str(event.get("rootEventId", "")))
        channel_path = event.get("channelPath") or []
        if len(channel_path) > 1:
            sessions[str(channel_path[1])] += 1
        time_prefixes = event.get("timePrefixKeys") or []
        if time_prefixes:
            hours[str(time_prefixes[-1])] += 1
        actor_prefixes = event.get("actorPrefixKeys") or []
        if actor_prefixes:
            actors[str(actor_prefixes[-1])] += 1
    return {
        "value_kind_top": kinds.most_common(20),
        "root_event_count": len(roots),
        "session_top": sessions.most_common(20),
        "hour_top": hours.most_common(20),
        "actor_top": actors.most_common(20),
    }


def build_batch_anchor(
    run_id: str,
    batch_index: int,
    events: list[dict[str, Any]],
    *,
    source_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    batch_id = f"batch:{run_id}:{batch_index:04d}"
    min_observed_at, max_observed_at = iso_hour_range(events)
    event_manifest = {
        "schema": "percept-event-pointer-batch-manifest-v0.1",
        "batchId": batch_id,
        "sourcePointerLogSha256": source_sha256,
        "eventIds": [event["eventId"] for event in events],
        "eventCids": [event["eventCid"] for event in events],
    }
    postings_manifest = {
        "schema": "percept-event-postings-manifest-v0.1",
        "batchId": batch_id,
        "sourcePointerLogSha256": source_sha256,
        "postings": postings_fingerprint(events),
    }
    event_manifest_hash = sha256_hex(canonical_json_bytes(event_manifest))
    postings_manifest_hash = sha256_hex(canonical_json_bytes(postings_manifest))
    merkle_root = merkle_root_hex([canonical_json_bytes(event) for event in events])
    anchor = {
        "batchId": batch_id,
        "eventCount": len(events),
        "eventManifestCid": f"cidv0-local-sha256:{event_manifest_hash}",
        "kind": "event-trace-batch-anchor",
        "maxObservedAt": max_observed_at,
        "merkleRoot": f"sha256-merkle:{merkle_root}",
        "minObservedAt": min_observed_at,
        "postingsManifestCid": f"cidv0-local-sha256:{postings_manifest_hash}",
        "schema": "event-trace-batch-anchor-v0.1",
        "shardPath": common_time_shard(events),
    }
    summary = {
        "batch": batch_index,
        "batchId": batch_id,
        "eventCount": len(events),
        "firstEventId": events[0]["eventId"],
        "lastEventId": events[-1]["eventId"],
        "eventManifestSha256": event_manifest_hash,
        "postingsManifestSha256": postings_manifest_hash,
        "merkleRootSha256": merkle_root,
        "minObservedAt": min_observed_at,
        "maxObservedAt": max_observed_at,
        "shardPath": anchor["shardPath"],
    }
    return anchor, summary


def write_stored_batch_deploy(
    tmp_dir: Path,
    uri_name: str,
    run_id: str,
    batch_index: int,
    events: list[dict[str, Any]],
    *,
    source_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    anchor, summary = build_batch_anchor(run_id, batch_index, events, source_sha256=source_sha256)
    marker_name = f"event-trace-memory:RSpaceStoredOk:{run_id}:batch-{batch_index:04d}"
    path = tmp_dir / f"{run_id}-batch-{batch_index:04d}.rho"
    path.write_text(
        f"""new lookup(`rho:registry:lookup`), lookedUp, putAck in {{
  for (@uri <- @{bench.rho_literal(uri_name)}) {{
    @{bench.rho_literal(uri_name)}!(uri)
    |
    lookup!(uri, *lookedUp)
    |
    for (@eventTraceRSpaceIndex <- lookedUp) {{
      @eventTraceRSpaceIndex!("putBatchEvents", {bench.rho_literal(anchor)}, {bench.rho_literal(events)}, *putAck)
    }}
    |
    for (@result <- putAck) {{
      if (result.get("ok")) {{
        @{bench.rho_literal(marker_name)}!(result)
      }}
    }}
  }}
}}
""",
        encoding="utf-8",
    )
    return path, summary


def run_stored_workload(
    *,
    root: Path,
    container: str,
    tmp_dir: Path,
    uri_name: str,
    run_id: str,
    events: list[dict[str, Any]],
    batch_size: int,
    source_sha256: str,
    poll_s: float,
    timeout_s: int,
) -> dict[str, Any]:
    batches = [events[index : index + batch_size] for index in range(0, len(events), batch_size)]
    workload = StoredEventWorkload(deploys=len(batches), batch_size=batch_size, events=len(events))
    valid_after = bench.last_finalized_block(container)["number"]
    deploy_results: list[dict[str, Any]] = []
    batch_summaries: list[dict[str, Any]] = []
    print(
        f"Submitting {len(events)} stored events as {len(batches)} deploys "
        f"({batch_size} max events/deploy) with validAfter={valid_after}",
        flush=True,
    )
    first_submit: datetime | None = None
    for batch_index, batch_events in enumerate(batches):
        path, batch_summary = write_stored_batch_deploy(
            tmp_dir,
            uri_name,
            run_id,
            batch_index,
            batch_events,
            source_sha256=source_sha256,
        )
        deploy_result = bench.deploy_file(container, path, path.name, valid_after)
        deploy_result["batch"] = batch_index
        deploy_result["event_count"] = len(batch_events)
        deploy_result["term_bytes"] = path.stat().st_size
        if first_submit is None:
            first_submit = datetime.fromisoformat(deploy_result["start_iso"].replace("Z", "+00:00"))
        deploy_results.append(deploy_result)
        batch_summaries.append(batch_summary)
        if (batch_index + 1) % 10 == 0 or batch_index + 1 == len(batches):
            elapsed = (bench.utc_now() - first_submit).total_seconds()
            print(
                f"stored events: submitted {batch_index + 1}/{len(batches)} deploys "
                f"({sum(item['event_count'] for item in deploy_results)}/{len(events)} events) in {elapsed:.3f}s",
                flush=True,
            )

    if first_submit is None:
        raise RuntimeError("no stored events were submitted")

    result = bench.poll_workload(
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
            "batch_summaries": batch_summaries,
            "root": str(root),
        }
    )
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="rnode.validator3")
    parser.add_argument("--pointer-container", default=DEFAULT_POINTER_CONTAINER)
    parser.add_argument("--pointer-log", default=DEFAULT_POINTER_LOG)
    parser.add_argument("--pointer-log-timeout-seconds", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument(
        "--existing-uri",
        help="Use an already-finalized EventTraceRSpaceIndex registry URI instead of deploying a new scoped contract.",
    )
    parser.add_argument("--contract-scan-depth", type=int, default=250)
    parser.add_argument("--skip-contract-check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")

    root = Path(__file__).resolve().parents[1]
    run_prefix = bench.utc_now().strftime("%Y%m%dT%H%M%SZ")
    run_id = f"rspace-stored-events-batch-anchor-{run_prefix}"
    uri_name = args.existing_uri or f"event-trace-memory:EventTraceRSpaceIndexUri:stored-events-{run_prefix}"
    output = args.output or Path(f"/tmp/event-trace-memory-stored-events-{run_prefix}.json")

    print(f"Reading {args.pointer_container}:{args.pointer_log}", flush=True)
    pointer_log_text, source_sha256 = source_pointer_log(
        args.pointer_container,
        args.pointer_log,
        timeout_s=args.pointer_log_timeout_seconds,
    )
    events, source_counts = load_unique_pointers(pointer_log_text)
    if not events:
        raise RuntimeError("pointer log contained no deployable events")
    event_summary = summarize_events(events)
    print(
        f"Loaded {source_counts['unique_event_count']} unique events "
        f"from {source_counts['line_count']} pointer-log lines, sha256={source_sha256}",
        flush=True,
    )

    with tempfile.TemporaryDirectory(prefix="etm-rspace-stored-events-") as tmp:
        tmp_dir = Path(tmp)
        if args.existing_uri:
            contract_deploy = None
            print(f"Using existing scoped EventTraceRSpaceIndex URI {uri_name}", flush=True)
        else:
            contract = bench.write_scoped_contract(root, tmp_dir, uri_name)
            contract_valid_after = bench.last_finalized_block(args.container)["number"]
            print(f"Deploying scoped EventTraceRSpaceIndex as {uri_name} validAfter={contract_valid_after}", flush=True)
            contract_deploy = bench.deploy_file(args.container, contract, contract.name, contract_valid_after)
            print(f"Scoped contract deploy id: {contract_deploy['deploy_id']}", flush=True)

        if args.skip_contract_check:
            contract_block = None
            binding_wait_s = 0.0
            print("Skipped scoped contract block scan", flush=True)
        else:
            contract_block = bench.wait_for_finalized_contract(
                args.container,
                uri_name,
                timeout_s=600,
                depth=args.contract_scan_depth,
            )
            binding_wait_s = contract_block["elapsed_s"]
            print(
                f"Scoped contract available in finalized block {contract_block.get('number')} "
                f"after {binding_wait_s:.3f}s",
                flush=True,
            )

        result = run_stored_workload(
            root=root,
            container=args.container,
            tmp_dir=tmp_dir,
            uri_name=uri_name,
            run_id=run_id,
            events=events,
            batch_size=args.batch_size,
            source_sha256=source_sha256,
            poll_s=args.poll_seconds,
            timeout_s=args.timeout_seconds,
        )

    artifact = {
        "created_at": bench.iso_now(),
        "container": args.container,
        "pointer_source": {
            "container": args.pointer_container,
            "pointer_log": args.pointer_log,
            "pointer_log_sha256": source_sha256,
            **source_counts,
        },
        "event_summary": event_summary,
        "node_status": bench.docker_exec(args.container, ["/opt/docker/bin/node", "status"], check=False),
        "latest_block_after": bench.latest_block(args.container),
        "last_finalized_after": bench.last_finalized_block(args.container),
        "uri_name": uri_name,
        "contract_deploy": contract_deploy,
        "contract_block": contract_block,
        "contract_binding_wait_s": binding_wait_s,
        "result": result,
        "summary": bench.summarize_result(result),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {output}", flush=True)
    print(json.dumps(artifact["summary"], indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

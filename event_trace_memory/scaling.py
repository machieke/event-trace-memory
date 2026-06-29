"""Scaling metrics, sharding recommendations, and posting compression."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from event_trace_memory.indexes import EventTraceIndex
from event_trace_memory.snapshots import SnapshotView


@dataclass(frozen=True)
class EventIndexScaleMetrics:
    events: int
    time_keys: int
    actor_keys: int
    channel_keys: int
    root_keys: int
    total_index_entries: int


@dataclass(frozen=True)
class SnapshotScaleMetrics:
    shard_path: str
    events: int
    posting_keys: int
    posting_entries: int
    max_posting_length: int


@dataclass(frozen=True)
class ScalingThresholds:
    max_events_per_contract: int = 100000
    max_index_entries_per_contract: int = 1000000
    max_posting_entries_per_snapshot: int = 1000000


@dataclass(frozen=True)
class ShardingRecommendation:
    recommended: bool
    reasons: list[str]


def measure_event_index(index: EventTraceIndex) -> EventIndexScaleMetrics:
    return EventIndexScaleMetrics(
        events=len(index.events),
        time_keys=len(index.time_index),
        actor_keys=len(index.actor_index),
        channel_keys=len(index.channel_index),
        root_keys=len(index.root_index),
        total_index_entries=sum(
            _posting_entries(postings)
            for postings in [
                index.time_index,
                index.actor_index,
                index.channel_index,
                index.kind_index,
                index.parent_index,
                index.root_index,
                index.payload_index,
            ]
        ),
    )


def measure_snapshot(snapshot: SnapshotView) -> SnapshotScaleMetrics:
    posting_lengths = [len(values) for values in snapshot.postings.values()]
    return SnapshotScaleMetrics(
        shard_path=snapshot.manifest["shardPath"],
        events=len(snapshot.event_dictionary["eventIdToLocalId"]),
        posting_keys=len(snapshot.postings),
        posting_entries=sum(posting_lengths),
        max_posting_length=max(posting_lengths) if posting_lengths else 0,
    )


def recommend_sharding(
    event_metrics: EventIndexScaleMetrics,
    snapshot_metrics: SnapshotScaleMetrics,
    thresholds: ScalingThresholds = ScalingThresholds(),
) -> ShardingRecommendation:
    reasons: list[str] = []
    if event_metrics.events > thresholds.max_events_per_contract:
        reasons.append("event-count")
    if event_metrics.total_index_entries > thresholds.max_index_entries_per_contract:
        reasons.append("index-entry-count")
    if snapshot_metrics.posting_entries > thresholds.max_posting_entries_per_snapshot:
        reasons.append("snapshot-posting-entry-count")
    return ShardingRecommendation(recommended=bool(reasons), reasons=reasons)


def compress_postings(postings: dict[str, list[int]]) -> dict[str, Any]:
    return {
        "kind": "compressed-postings",
        "schema": "delta-postings-v0.1",
        "encoding": "sorted-delta-v1",
        "postings": {token: _delta_encode(values) for token, values in sorted(postings.items())},
    }


def decompress_postings(compressed: dict[str, Any]) -> dict[str, list[int]]:
    if compressed.get("encoding") != "sorted-delta-v1":
        raise ValueError(f"unsupported postings encoding: {compressed.get('encoding')}")
    return {token: _delta_decode(values) for token, values in compressed.get("postings", {}).items()}


def compact_snapshot_postings(snapshot: SnapshotView) -> dict[str, Any]:
    compressed = compress_postings(snapshot.postings)
    compressed["sourceSnapshotCid"] = snapshot.cid
    compressed["shardPath"] = snapshot.manifest["shardPath"]
    return compressed


def _posting_entries(index: dict[str, list[str]]) -> int:
    return sum(len(values) for values in index.values())


def _delta_encode(values: list[int]) -> list[int]:
    encoded: list[int] = []
    previous = 0
    for value in sorted(set(values)):
        encoded.append(value - previous)
        previous = value
    return encoded


def _delta_decode(values: list[int]) -> list[int]:
    decoded: list[int] = []
    current = 0
    for delta in values:
        current += delta
        decoded.append(current)
    return decoded


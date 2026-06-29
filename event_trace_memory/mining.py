"""Pattern mining over materialized snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from event_trace_memory.artifacts import ArtifactWriter, StoredArtifact
from event_trace_memory.ingestion import EventIngestor, IngestedEvent
from event_trace_memory.snapshots import SnapshotView


@dataclass(frozen=True)
class SupportResult:
    strategy: str
    tokens: list[str]
    local_ids: list[int]
    event_ids: list[str]
    support: int


@dataclass(frozen=True)
class MinedPattern:
    pattern: StoredArtifact
    occurrences: list[StoredArtifact]
    support_vector: dict[str, int]


class PatternMiner:
    def __init__(self, writer: ArtifactWriter) -> None:
        self.writer = writer

    def support_for_tokens(self, snapshot: SnapshotView, tokens: list[str]) -> SupportResult:
        posting_sets = [set(snapshot.postings.get(token, [])) for token in tokens]
        if not posting_sets:
            local_ids: list[int] = []
        else:
            local_ids = sorted(set.intersection(*posting_sets))
        event_ids = [snapshot.event_dictionary["localIdToEventId"][str(local_id)] for local_id in local_ids]
        return SupportResult(
            strategy="set-intersection",
            tokens=tokens,
            local_ids=local_ids,
            event_ids=event_ids,
            support=len(local_ids),
        )

    def mine_sequence(
        self,
        *,
        snapshot: SnapshotView,
        sequence: list[str],
        mining_run_id: str,
        miner_key: str,
        min_support: int = 1,
        max_window_seconds: int = 30,
    ) -> MinedPattern | None:
        matches: list[tuple[str, list[str]]] = []
        for root_event_id, event_ids in snapshot.event_columns["eventsByRoot"].items():
            matched = self._match_sequence(snapshot, event_ids, sequence)
            if matched:
                matches.append((root_event_id, matched))

        if len(matches) < min_support:
            return None

        support_vector = self._support_vector(snapshot, [event_id for _, event_ids in matches for event_id in event_ids])
        support_vector["rootTraceSupport"] = len({root_event_id for root_event_id, _ in matches})
        support_vector["occurrenceSupport"] = len(matches)

        pattern_core = {
            "kind": "pattern",
            "schema": "pattern-core-v0.1",
            "patternType": "sequence",
            "body": [{"eventKind": event_kind} for event_kind in sequence],
            "constraints": {
                "sameRootTrace": True,
                "maxWindowSeconds": max_window_seconds,
            },
        }
        pattern = self.writer.put_pattern(
            pattern_core=pattern_core,
            input_snapshot_cids=[snapshot.cid],
            mining_run_id=mining_run_id,
            miner_key=miner_key,
            support_vector=support_vector,
        )

        occurrences: list[StoredArtifact] = []
        for root_event_id, participating_event_ids in matches:
            claim_occurrence_ids: list[str] = []
            for event_id in participating_event_ids:
                claim_occurrence_ids.extend(snapshot.claim_occurrences.get(event_id, []))
            occurrences.append(
                self.writer.put_pattern_occurrence(
                    pattern_id=pattern.artifact_id,
                    root_event_id=root_event_id,
                    participating_event_ids=participating_event_ids,
                    participating_claim_occurrence_ids=claim_occurrence_ids,
                    mined_by=mining_run_id,
                )
            )
        return MinedPattern(pattern=pattern, occurrences=occurrences, support_vector=support_vector)

    def mine_itemset(
        self,
        *,
        snapshot: SnapshotView,
        tokens: list[str],
        mining_run_id: str,
        miner_key: str,
        min_support: int = 1,
    ) -> MinedPattern | None:
        support = self.support_for_tokens(snapshot, tokens)
        if support.support < min_support:
            return None

        support_vector = self._support_vector(snapshot, support.event_ids)
        support_vector["itemsetSupport"] = support.support
        support_vector["occurrenceSupport"] = support.support
        support_vector["rootTraceSupport"] = len(
            {snapshot.event_columns["events"][event_id]["rootEventId"] for event_id in support.event_ids}
        )

        pattern_core = {
            "kind": "pattern",
            "schema": "pattern-core-v0.1",
            "patternType": "itemset",
            "body": [{"postingToken": token} for token in tokens],
            "constraints": {
                "supportStrategy": support.strategy,
            },
        }
        pattern = self.writer.put_pattern(
            pattern_core=pattern_core,
            input_snapshot_cids=[snapshot.cid],
            mining_run_id=mining_run_id,
            miner_key=miner_key,
            support_vector=support_vector,
        )

        by_root: dict[str, list[str]] = {}
        for event_id in support.event_ids:
            root_event_id = snapshot.event_columns["events"][event_id]["rootEventId"]
            by_root.setdefault(root_event_id, []).append(event_id)

        occurrences: list[StoredArtifact] = []
        for root_event_id, participating_event_ids in by_root.items():
            occurrences.append(
                self.writer.put_pattern_occurrence(
                    pattern_id=pattern.artifact_id,
                    root_event_id=root_event_id,
                    participating_event_ids=participating_event_ids,
                    participating_claim_occurrence_ids=self._claim_occurrences_for_events(
                        snapshot,
                        participating_event_ids,
                    ),
                    mined_by=mining_run_id,
                )
            )
        return MinedPattern(pattern=pattern, occurrences=occurrences, support_vector=support_vector)

    def mine_parent_child_motif(
        self,
        *,
        snapshot: SnapshotView,
        parent_kind: str,
        child_kind: str,
        mining_run_id: str,
        miner_key: str,
        min_support: int = 1,
    ) -> MinedPattern | None:
        matches: list[tuple[str, str]] = []
        for edge in snapshot.provenance_edges["parentEdges"]:
            parent_event_id = edge["parentEventId"]
            child_event_id = edge["childEventId"]
            parent = snapshot.event_columns["events"].get(parent_event_id)
            child = snapshot.event_columns["events"].get(child_event_id)
            if not parent or not child:
                continue
            if parent["eventKind"] == parent_kind and child["eventKind"] == child_kind:
                matches.append((parent_event_id, child_event_id))

        if len(matches) < min_support:
            return None

        matched_event_ids = [event_id for match in matches for event_id in match]
        support_vector = self._support_vector(snapshot, matched_event_ids)
        support_vector["edgeSupport"] = len(matches)
        support_vector["occurrenceSupport"] = len(matches)
        support_vector["rootTraceSupport"] = len(
            {
                snapshot.event_columns["events"][parent_event_id]["rootEventId"]
                for parent_event_id, _ in matches
            }
        )

        pattern_core = {
            "kind": "pattern",
            "schema": "pattern-core-v0.1",
            "patternType": "graph-motif",
            "body": [
                {
                    "edge": "parent-child",
                    "parentEventKind": parent_kind,
                    "childEventKind": child_kind,
                }
            ],
            "constraints": {
                "edgeType": "parentEventId",
            },
        }
        pattern = self.writer.put_pattern(
            pattern_core=pattern_core,
            input_snapshot_cids=[snapshot.cid],
            mining_run_id=mining_run_id,
            miner_key=miner_key,
            support_vector=support_vector,
        )

        occurrences: list[StoredArtifact] = []
        for parent_event_id, child_event_id in matches:
            participating_event_ids = [parent_event_id, child_event_id]
            root_event_id = snapshot.event_columns["events"][parent_event_id]["rootEventId"]
            occurrences.append(
                self.writer.put_pattern_occurrence(
                    pattern_id=pattern.artifact_id,
                    root_event_id=root_event_id,
                    participating_event_ids=participating_event_ids,
                    participating_claim_occurrence_ids=self._claim_occurrences_for_events(
                        snapshot,
                        participating_event_ids,
                    ),
                    mined_by=mining_run_id,
                )
            )
        return MinedPattern(pattern=pattern, occurrences=occurrences, support_vector=support_vector)

    def log_pattern_discovery_event(
        self,
        *,
        ingestor: EventIngestor,
        mining_run: StoredArtifact,
        mined_pattern: MinedPattern,
        observed_at: str,
        parent_event_ids: list[str],
    ) -> IngestedEvent:
        return ingestor.log_child_event(
            raw_payload={
                "kind": "pattern-discovery",
                "runId": mining_run.artifact_id,
                "runCid": mining_run.cid,
                "patternId": mined_pattern.pattern.artifact_id,
                "patternCid": mined_pattern.pattern.cid,
                "occurrenceIds": [occurrence.artifact_id for occurrence in mined_pattern.occurrences],
                "supportVector": mined_pattern.support_vector,
                "observedAt": observed_at,
            },
            observed_at=observed_at,
            actor_path=["agent", "omega-claw", "pattern-miner", "sequence-v0"],
            channel_path=["system", "pattern-mining", "sequence"],
            value_kind="pattern-discovery",
            parent_event_ids=parent_event_ids,
            input_event_ids=parent_event_ids,
            output_artifact_ids=[mined_pattern.pattern.artifact_id]
            + [occurrence.artifact_id for occurrence in mined_pattern.occurrences],
        )

    @staticmethod
    def _match_sequence(snapshot: SnapshotView, event_ids: list[str], sequence: list[str]) -> list[str]:
        matched: list[str] = []
        search_index = 0
        for event_id in event_ids:
            if search_index >= len(sequence):
                break
            event_kind = snapshot.event_columns["events"][event_id]["eventKind"]
            if event_kind == sequence[search_index]:
                matched.append(event_id)
                search_index += 1
        return matched if search_index == len(sequence) else []

    @staticmethod
    def _claim_occurrences_for_events(snapshot: SnapshotView, event_ids: list[str]) -> list[str]:
        occurrence_ids: list[str] = []
        for event_id in event_ids:
            occurrence_ids.extend(snapshot.claim_occurrences.get(event_id, []))
        return occurrence_ids

    @staticmethod
    def _support_vector(snapshot: SnapshotView, event_ids: list[str]) -> dict[str, int]:
        events = [snapshot.event_columns["events"][event_id] for event_id in event_ids]
        return {
            "eventSupport": len(set(event_ids)),
            "actorSupport": len({event["actorKey"] for event in events}),
            "channelSupport": len({event["channelKey"] for event in events}),
            "daySupport": len({"-".join(str(part) for part in event["timePath"][:3]) for event in events}),
            "sourceSupport": 1,
            "extractorRunSupport": 0,
        }

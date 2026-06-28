"""Shard snapshot builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from event_trace_memory.da import FileDA
from event_trace_memory.indexes import DerivedArtifactIndex, EventTraceIndex


@dataclass(frozen=True)
class SnapshotView:
    cid: str
    manifest: dict[str, Any]
    event_dictionary: dict[str, Any]
    event_columns: dict[str, Any]
    postings: dict[str, list[int]]
    provenance_edges: dict[str, Any]
    claim_occurrences: dict[str, list[str]]
    feature_occurrences: dict[str, list[str]]


class SnapshotBuilder:
    def __init__(self, da: FileDA, event_index: EventTraceIndex, derived_index: DerivedArtifactIndex) -> None:
        self.da = da
        self.event_index = event_index
        self.derived_index = derived_index

    @staticmethod
    def affected_shard_paths(event_pointer: dict[str, Any]) -> list[str]:
        time_prefixes = event_pointer.get("timePrefixKeys", [])
        return [time_prefixes[-1]] if time_prefixes else []

    def build_hour_snapshot(self, shard_path: str) -> SnapshotView:
        event_ids = self.event_index.by_time_prefix(shard_path)["eventIds"]
        event_id_to_local_id = {event_id: index + 1 for index, event_id in enumerate(event_ids)}
        local_id_to_event_id = {str(local_id): event_id for event_id, local_id in event_id_to_local_id.items()}

        columns: dict[str, Any] = {
            "eventIds": event_ids,
            "events": {},
            "eventsByRoot": {},
        }
        postings: dict[str, list[int]] = {}
        parent_edges: list[dict[str, str]] = []
        claim_occurrences_by_event: dict[str, list[str]] = {}
        feature_occurrences_by_event: dict[str, list[str]] = {}

        for event_id in event_ids:
            event_response = self.event_index.get_event(event_id)
            if not event_response["ok"]:
                continue
            pointer = event_response["event"]
            local_id = event_id_to_local_id[event_id]
            actor_key = pointer.get("actorPrefixKeys", [""])[-1]
            channel_key = pointer.get("channelPrefixKeys", [""])[-1]
            root_event_id = pointer.get("rootEventId", event_id)
            event_record = {
                "localId": local_id,
                "eventId": event_id,
                "eventCid": pointer["eventCid"],
                "payloadCid": pointer["payloadCid"],
                "eventKind": pointer["valueKind"],
                "actorKey": actor_key,
                "channelKey": channel_key,
                "rootEventId": root_event_id,
                "timePath": pointer.get("timePath", []),
                "inputEventIds": pointer.get("inputEventIds", []),
                "outputArtifactIds": pointer.get("outputArtifactIds", []),
            }
            columns["events"][event_id] = event_record
            columns["eventsByRoot"].setdefault(root_event_id, []).append(event_id)

            self._add_posting(postings, f"event.kind:{pointer['valueKind']}", local_id)
            self._add_posting(postings, f"actor:{actor_key}", local_id)
            self._add_posting(postings, f"channel:{channel_key}", local_id)
            self._add_posting(postings, f"root:{root_event_id}", local_id)

            for parent_event_id in pointer.get("parentEventIds", []):
                parent_edges.append({"parentEventId": parent_event_id, "childEventId": event_id})

            derived = self.derived_index.by_source_event(event_id)
            claim_occurrences_by_event[event_id] = derived["claimOccurrenceIds"]
            feature_occurrences_by_event[event_id] = derived["featureOccurrenceIds"]
            for occurrence_id in derived["claimOccurrenceIds"]:
                occurrence = self.derived_index.claim_occurrences[occurrence_id]
                self._add_posting(postings, f"claim:{occurrence['claimId']}", local_id)
                self._add_posting(postings, "artifact.kind:claim-occurrence", local_id)
            for occurrence_id in derived["featureOccurrenceIds"]:
                occurrence = self.derived_index.feature_occurrences[occurrence_id]
                self._add_posting(postings, f"feature:{occurrence['featureId']}", local_id)
                feature = self.derived_index.features[occurrence["featureId"]]
                self._add_posting(postings, f"feature.type:{feature['featureType']}", local_id)

        event_dictionary = {
            "kind": "event-dictionary",
            "schema": "event-dictionary-v0.1",
            "eventIdToLocalId": event_id_to_local_id,
            "localIdToEventId": local_id_to_event_id,
        }
        provenance_edges = {
            "kind": "provenance-edges",
            "schema": "provenance-edges-v0.1",
            "parentEdges": parent_edges,
        }
        event_dictionary_cid = self.da.put_json(event_dictionary)
        event_columns_cid = self.da.put_json(columns)
        postings_cid = self.da.put_json(postings)
        provenance_edges_cid = self.da.put_json(provenance_edges)
        claim_occurrences_cid = self.da.put_json(claim_occurrences_by_event)
        feature_occurrences_cid = self.da.put_json(feature_occurrences_by_event)
        manifest = {
            "kind": "mining-snapshot",
            "schema": "mining-snapshot-v0.1",
            "shardPath": shard_path,
            "eventDictionaryCid": event_dictionary_cid,
            "eventColumnsCid": event_columns_cid,
            "postingsCid": postings_cid,
            "provenanceEdgesCid": provenance_edges_cid,
            "claimOccurrencesCid": claim_occurrences_cid,
            "featureOccurrencesCid": feature_occurrences_cid,
            "sourceContract": "reference-event-trace-index",
            "sourceQuery": {"type": "timePrefix", "prefixKey": shard_path},
            "rawPayloadsScanned": False,
        }
        snapshot_cid = self.da.put_json(manifest)
        return SnapshotView(
            cid=snapshot_cid,
            manifest=manifest,
            event_dictionary=event_dictionary,
            event_columns=columns,
            postings=postings,
            provenance_edges=provenance_edges,
            claim_occurrences=claim_occurrences_by_event,
            feature_occurrences=feature_occurrences_by_event,
        )

    def load_snapshot(self, snapshot_cid: str) -> SnapshotView:
        manifest = self.da.get_json(snapshot_cid)
        return SnapshotView(
            cid=snapshot_cid,
            manifest=manifest,
            event_dictionary=self.da.get_json(manifest["eventDictionaryCid"]),
            event_columns=self.da.get_json(manifest["eventColumnsCid"]),
            postings=self.da.get_json(manifest["postingsCid"]),
            provenance_edges=self.da.get_json(manifest["provenanceEdgesCid"]),
            claim_occurrences=self.da.get_json(manifest["claimOccurrencesCid"]),
            feature_occurrences=self.da.get_json(manifest["featureOccurrencesCid"]),
        )

    @staticmethod
    def _add_posting(postings: dict[str, list[int]], token: str, local_id: int) -> None:
        bucket = postings.setdefault(token, [])
        if local_id not in bucket:
            bucket.append(local_id)

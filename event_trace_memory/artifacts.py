"""Derived artifact writers for the reference implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from event_trace_memory.canonical import content_id
from event_trace_memory.da import FileDA
from event_trace_memory.indexes import DerivedArtifactIndex, EventTraceIndex


@dataclass(frozen=True)
class StoredArtifact:
    artifact_id: str
    cid: str
    body: dict[str, Any]
    pointer: dict[str, Any]
    ack: dict[str, Any]


class ArtifactWriter:
    def __init__(self, da: FileDA, event_index: EventTraceIndex, derived_index: DerivedArtifactIndex) -> None:
        self.da = da
        self.event_index = event_index
        self.derived_index = derived_index

    def record_run(
        self,
        *,
        run_type: str,
        input_event_ids: list[str],
        actor_key: str,
        tool: dict[str, Any],
        config: dict[str, Any],
        started_at: str,
        completed_at: str,
        status: str = "success",
        output_artifact_ids: list[str] | None = None,
        input_snapshot_cids: list[str] | None = None,
    ) -> StoredArtifact:
        body = {
            "kind": "run",
            "schema": "run-v0.1",
            "runType": run_type,
            "inputEventIds": input_event_ids,
            "inputSnapshotCids": input_snapshot_cids or [],
            "tool": tool,
            "config": config,
            "startedAt": started_at,
            "completedAt": completed_at,
            "status": status,
            "outputArtifactIds": output_artifact_ids or [],
        }
        cid = self.da.put_json(body)
        run_id = content_id("run", body)
        pointer = {
            "kind": "run-pointer",
            "schema": "run-pointer-v0.1",
            "runId": run_id,
            "runCid": cid,
            "runType": run_type,
            "inputEventIds": input_event_ids,
            "inputSnapshotCids": input_snapshot_cids or [],
            "outputArtifactIds": output_artifact_ids or [],
            "extractorKey": actor_key,
            "minerKey": actor_key,
            "reasonerKey": actor_key,
            "tool": tool,
            "config": config,
            "status": status,
        }
        ack = self.derived_index.put_run(pointer)
        return StoredArtifact(run_id, cid, body, pointer, ack)

    def put_claim(self, claim_core: dict[str, Any]) -> StoredArtifact:
        cid = self.da.put_json(claim_core)
        claim_id = content_id("claim", claim_core)
        pointer = {
            "kind": "claim-pointer",
            "schema": "claim-pointer-v0.1",
            "claimId": claim_id,
            "claimCid": cid,
            "subjectKey": DerivedArtifactIndex.stable_key("subject", claim_core.get("subject")),
            "predicateKey": DerivedArtifactIndex.stable_key("predicate", claim_core.get("predicate")),
            "objectKey": DerivedArtifactIndex.stable_key("object", claim_core.get("object")),
        }
        ack = self.derived_index.put_claim(pointer)
        return StoredArtifact(claim_id, cid, claim_core, pointer, ack)

    def put_claim_occurrence(
        self,
        *,
        claim_core: dict[str, Any],
        source_event_id: str,
        extraction_run_id: str,
        evidence: dict[str, Any],
        polarity: str = "asserted",
        confidence: float = 1.0,
        provenance: dict[str, Any] | None = None,
    ) -> StoredArtifact:
        claim = self.put_claim(claim_core)
        source_event = self.event_index.get_event(source_event_id)
        if not source_event["ok"]:
            raise KeyError(source_event_id)
        source_pointer = source_event["event"]
        body = {
            "kind": "claim-occurrence",
            "schema": "claim-occurrence-v0.1",
            "claimId": claim.artifact_id,
            "claimCid": claim.cid,
            "sourceEventId": source_event_id,
            "sourceEventCid": source_pointer["eventCid"],
            "sourcePayloadCid": source_pointer["payloadCid"],
            "extractionRunId": extraction_run_id,
            "evidence": evidence,
            "polarity": polarity,
            "confidence": confidence,
            "provenance": provenance or {},
        }
        cid = self.da.put_json(body)
        occurrence_id = content_id("claim-occ", body)
        pointer = {
            "kind": "claim-occurrence-pointer",
            "schema": "claim-occurrence-pointer-v0.1",
            "occurrenceId": occurrence_id,
            "occurrenceCid": cid,
            "claimId": claim.artifact_id,
            "claimCid": claim.cid,
            "sourceEventId": source_event_id,
            "sourceEventCid": source_pointer["eventCid"],
            "sourcePayloadCid": source_pointer["payloadCid"],
            "extractionRunId": extraction_run_id,
            "polarity": polarity,
            "confidence": confidence,
        }
        ack = self.derived_index.put_claim_occurrence(pointer)
        return StoredArtifact(occurrence_id, cid, body, pointer, ack)

    def put_claim_cluster(
        self,
        *,
        relation: str,
        members: list[str],
        method: dict[str, Any],
        confidence: float,
    ) -> StoredArtifact:
        body = {
            "kind": "claim-cluster",
            "schema": "claim-cluster-v0.1",
            "relation": relation,
            "members": members,
            "method": method,
            "confidence": confidence,
        }
        cid = self.da.put_json(body)
        cluster_id = content_id("claim-cluster", body)
        pointer = {
            "kind": "claim-cluster-pointer",
            "schema": "claim-cluster-pointer-v0.1",
            "clusterId": cluster_id,
            "clusterCid": cid,
            "relation": relation,
            "members": members,
            "method": method,
            "confidence": confidence,
        }
        ack = self.derived_index.put_claim_cluster(pointer)
        return StoredArtifact(cluster_id, cid, body, pointer, ack)

    def put_feature(self, feature_core: dict[str, Any]) -> StoredArtifact:
        cid = self.da.put_json(feature_core)
        feature_id = content_id("feature", feature_core)
        pointer = {
            "kind": "feature-pointer",
            "schema": "feature-pointer-v0.1",
            "featureId": feature_id,
            "featureCid": cid,
            "featureType": feature_core["featureType"],
        }
        ack = self.derived_index.put_feature(pointer)
        return StoredArtifact(feature_id, cid, feature_core, pointer, ack)

    def put_feature_occurrence(
        self,
        *,
        feature_core: dict[str, Any],
        source_event_id: str,
        extraction_run_id: str,
        confidence: float,
        evidence: dict[str, Any],
    ) -> StoredArtifact:
        feature = self.put_feature(feature_core)
        body = {
            "kind": "feature-occurrence",
            "schema": "feature-occurrence-v0.1",
            "featureId": feature.artifact_id,
            "featureCid": feature.cid,
            "sourceEventId": source_event_id,
            "extractionRunId": extraction_run_id,
            "confidence": confidence,
            "evidence": evidence,
        }
        cid = self.da.put_json(body)
        occurrence_id = content_id("feature-occ", body)
        pointer = {
            "kind": "feature-occurrence-pointer",
            "schema": "feature-occurrence-pointer-v0.1",
            "occurrenceId": occurrence_id,
            "occurrenceCid": cid,
            "featureId": feature.artifact_id,
            "featureCid": feature.cid,
            "sourceEventId": source_event_id,
            "extractionRunId": extraction_run_id,
            "confidence": confidence,
        }
        ack = self.derived_index.put_feature_occurrence(pointer)
        return StoredArtifact(occurrence_id, cid, body, pointer, ack)

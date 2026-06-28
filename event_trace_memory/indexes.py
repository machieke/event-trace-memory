"""Reference contract indexes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from event_trace_memory.canonical import digest_json


def _append_unique(index: dict[str, list[str]], key: str, value: str) -> None:
    bucket = index.setdefault(key, [])
    if value not in bucket:
        bucket.append(value)


class EventTraceIndex:
    """In-process stand-in for the EventTraceIndex contract."""

    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.time_index: dict[str, list[str]] = {}
        self.actor_index: dict[str, list[str]] = {}
        self.channel_index: dict[str, list[str]] = {}
        self.kind_index: dict[str, list[str]] = {}
        self.parent_index: dict[str, list[str]] = {}
        self.root_index: dict[str, list[str]] = {}
        self.payload_index: dict[str, list[str]] = {}
        self.event_cid_index: dict[str, str] = {}

    def put_event(self, event_pointer: dict[str, Any]) -> dict[str, Any]:
        event_id = event_pointer["eventId"]
        event_cid = event_pointer["eventCid"]
        payload_cid = event_pointer["payloadCid"]
        root_event_id = event_pointer.get("rootEventId") or event_id

        if event_id in self.events:
            return {"ok": False, "error": "duplicate-event-id", "eventId": event_id}

        pointer = deepcopy(event_pointer)
        pointer["rootEventId"] = root_event_id
        self.events[event_id] = pointer

        for prefix_key in pointer.get("timePrefixKeys", []):
            _append_unique(self.time_index, prefix_key, event_id)
        for prefix_key in pointer.get("actorPrefixKeys", []):
            _append_unique(self.actor_index, prefix_key, event_id)
        for prefix_key in pointer.get("channelPrefixKeys", []):
            _append_unique(self.channel_index, prefix_key, event_id)
        for parent_event_id in pointer.get("parentEventIds", []):
            _append_unique(self.parent_index, parent_event_id, event_id)

        _append_unique(self.kind_index, pointer.get("valueKind", ""), event_id)
        _append_unique(self.root_index, root_event_id, event_id)
        _append_unique(self.payload_index, payload_cid, event_id)
        self.event_cid_index[event_cid] = event_id

        return {
            "ok": True,
            "eventId": event_id,
            "eventCid": event_cid,
            "payloadCid": payload_cid,
        }

    def get_event(self, event_id: str) -> dict[str, Any]:
        if event_id not in self.events:
            return {"ok": False, "error": "not-found", "eventId": event_id}
        return {"ok": True, "event": deepcopy(self.events[event_id])}

    def by_time_prefix(self, prefix_key: str) -> dict[str, Any]:
        return {"ok": True, "prefixKey": prefix_key, "eventIds": list(self.time_index.get(prefix_key, []))}

    def by_actor_prefix(self, prefix_key: str) -> dict[str, Any]:
        return {"ok": True, "prefixKey": prefix_key, "eventIds": list(self.actor_index.get(prefix_key, []))}

    def by_channel_prefix(self, prefix_key: str) -> dict[str, Any]:
        return {"ok": True, "prefixKey": prefix_key, "eventIds": list(self.channel_index.get(prefix_key, []))}

    def by_kind(self, value_kind: str) -> dict[str, Any]:
        return {"ok": True, "valueKind": value_kind, "eventIds": list(self.kind_index.get(value_kind, []))}

    def by_parent(self, parent_event_id: str) -> dict[str, Any]:
        return {"ok": True, "parentEventId": parent_event_id, "eventIds": list(self.parent_index.get(parent_event_id, []))}

    def by_root(self, root_event_id: str) -> dict[str, Any]:
        return {"ok": True, "rootEventId": root_event_id, "eventIds": list(self.root_index.get(root_event_id, []))}

    def by_payload_cid(self, payload_cid: str) -> dict[str, Any]:
        return {"ok": True, "payloadCid": payload_cid, "eventIds": list(self.payload_index.get(payload_cid, []))}

    def state_stats(self) -> dict[str, int]:
        return {
            "events": len(self.events),
            "timeKeys": len(self.time_index),
            "actorKeys": len(self.actor_index),
            "channelKeys": len(self.channel_index),
            "rootKeys": len(self.root_index),
        }


def _stable_key(label: str, value: Any) -> str:
    return f"{label}:{digest_json(value)}"


class DerivedArtifactIndex:
    """In-process stand-in for the DerivedArtifactIndex contract."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.claims: dict[str, dict[str, Any]] = {}
        self.claim_occurrences: dict[str, dict[str, Any]] = {}
        self.claim_clusters: dict[str, dict[str, Any]] = {}
        self.features: dict[str, dict[str, Any]] = {}
        self.feature_occurrences: dict[str, dict[str, Any]] = {}
        self.patterns: dict[str, dict[str, Any]] = {}
        self.pattern_occurrences: dict[str, dict[str, Any]] = {}
        self.reasoning_inputs: dict[str, dict[str, Any]] = {}
        self.reasoning_outputs: dict[str, dict[str, Any]] = {}

        self.occurrences_by_claim: dict[str, list[str]] = {}
        self.occurrences_by_source_event: dict[str, list[str]] = {}
        self.claims_by_subject: dict[str, list[str]] = {}
        self.claims_by_predicate: dict[str, list[str]] = {}
        self.claims_by_object: dict[str, list[str]] = {}
        self.clusters_by_claim: dict[str, list[str]] = {}

        self.feature_occurrences_by_feature: dict[str, list[str]] = {}
        self.feature_occurrences_by_source_event: dict[str, list[str]] = {}
        self.features_by_type: dict[str, list[str]] = {}

        self.runs_by_input_event: dict[str, list[str]] = {}
        self.runs_by_output_artifact: dict[str, list[str]] = {}
        self.runs_by_extractor: dict[str, list[str]] = {}
        self.outputs_by_run: dict[str, list[str]] = {}

        self.occurrences_by_pattern: dict[str, list[str]] = {}
        self.patterns_by_type: dict[str, list[str]] = {}
        self.patterns_by_input_snapshot: dict[str, list[str]] = {}
        self.patterns_by_miner: dict[str, list[str]] = {}
        self.pattern_occurrences_by_root: dict[str, list[str]] = {}

        self.reasoning_outputs_by_claim: dict[str, list[str]] = {}
        self.reasoning_outputs_by_input: dict[str, list[str]] = {}
        self.reasoning_outputs_by_run: dict[str, list[str]] = {}

    def put_run(self, run_pointer: dict[str, Any]) -> dict[str, Any]:
        run_id = run_pointer["runId"]
        if run_id in self.runs:
            return {"ok": True, "duplicate": True, "runId": run_id}

        pointer = deepcopy(run_pointer)
        self.runs[run_id] = pointer
        for event_id in pointer.get("inputEventIds", []):
            _append_unique(self.runs_by_input_event, event_id, run_id)
        for artifact_id in pointer.get("outputArtifactIds", []):
            _append_unique(self.runs_by_output_artifact, artifact_id, run_id)
            _append_unique(self.outputs_by_run, run_id, artifact_id)
        extractor_key = pointer.get("extractorKey")
        if extractor_key:
            _append_unique(self.runs_by_extractor, extractor_key, run_id)
        return {"ok": True, "runId": run_id}

    def put_claim(self, claim_pointer: dict[str, Any]) -> dict[str, Any]:
        claim_id = claim_pointer["claimId"]
        if claim_id in self.claims:
            return {"ok": True, "duplicate": True, "claimId": claim_id}

        pointer = deepcopy(claim_pointer)
        self.claims[claim_id] = pointer
        _append_unique(self.claims_by_subject, pointer["subjectKey"], claim_id)
        _append_unique(self.claims_by_predicate, pointer["predicateKey"], claim_id)
        _append_unique(self.claims_by_object, pointer["objectKey"], claim_id)
        return {"ok": True, "claimId": claim_id}

    def put_claim_occurrence(self, occurrence_pointer: dict[str, Any]) -> dict[str, Any]:
        occurrence_id = occurrence_pointer["occurrenceId"]
        if occurrence_id in self.claim_occurrences:
            return {"ok": True, "duplicate": True, "occurrenceId": occurrence_id}

        pointer = deepcopy(occurrence_pointer)
        self.claim_occurrences[occurrence_id] = pointer
        _append_unique(self.occurrences_by_claim, pointer["claimId"], occurrence_id)
        _append_unique(self.occurrences_by_source_event, pointer["sourceEventId"], occurrence_id)
        run_id = pointer["extractionRunId"]
        _append_unique(self.outputs_by_run, run_id, occurrence_id)
        _append_unique(self.runs_by_output_artifact, occurrence_id, run_id)
        return {"ok": True, "occurrenceId": occurrence_id}

    def put_claim_cluster(self, cluster_pointer: dict[str, Any]) -> dict[str, Any]:
        cluster_id = cluster_pointer["clusterId"]
        if cluster_id in self.claim_clusters:
            return {"ok": True, "duplicate": True, "clusterId": cluster_id}

        pointer = deepcopy(cluster_pointer)
        self.claim_clusters[cluster_id] = pointer
        for claim_id in pointer.get("members", []):
            _append_unique(self.clusters_by_claim, claim_id, cluster_id)
        return {"ok": True, "clusterId": cluster_id}

    def put_feature(self, feature_pointer: dict[str, Any]) -> dict[str, Any]:
        feature_id = feature_pointer["featureId"]
        if feature_id in self.features:
            return {"ok": True, "duplicate": True, "featureId": feature_id}

        pointer = deepcopy(feature_pointer)
        self.features[feature_id] = pointer
        _append_unique(self.features_by_type, pointer["featureType"], feature_id)
        return {"ok": True, "featureId": feature_id}

    def put_feature_occurrence(self, occurrence_pointer: dict[str, Any]) -> dict[str, Any]:
        occurrence_id = occurrence_pointer["occurrenceId"]
        if occurrence_id in self.feature_occurrences:
            return {"ok": True, "duplicate": True, "occurrenceId": occurrence_id}

        pointer = deepcopy(occurrence_pointer)
        self.feature_occurrences[occurrence_id] = pointer
        _append_unique(self.feature_occurrences_by_feature, pointer["featureId"], occurrence_id)
        _append_unique(self.feature_occurrences_by_source_event, pointer["sourceEventId"], occurrence_id)
        run_id = pointer["extractionRunId"]
        _append_unique(self.outputs_by_run, run_id, occurrence_id)
        _append_unique(self.runs_by_output_artifact, occurrence_id, run_id)
        return {"ok": True, "occurrenceId": occurrence_id}

    def put_pattern(self, pattern_pointer: dict[str, Any]) -> dict[str, Any]:
        pattern_id = pattern_pointer["patternId"]
        if pattern_id in self.patterns:
            return {"ok": True, "duplicate": True, "patternId": pattern_id}

        pointer = deepcopy(pattern_pointer)
        self.patterns[pattern_id] = pointer
        _append_unique(self.patterns_by_type, pointer["patternType"], pattern_id)
        for snapshot_cid in pointer.get("inputSnapshotCids", []):
            _append_unique(self.patterns_by_input_snapshot, snapshot_cid, pattern_id)
        miner_key = pointer.get("minerKey")
        if miner_key:
            _append_unique(self.patterns_by_miner, miner_key, pattern_id)
        return {"ok": True, "patternId": pattern_id}

    def put_pattern_occurrence(self, occurrence_pointer: dict[str, Any]) -> dict[str, Any]:
        occurrence_id = occurrence_pointer["occurrenceId"]
        if occurrence_id in self.pattern_occurrences:
            return {"ok": True, "duplicate": True, "occurrenceId": occurrence_id}

        pointer = deepcopy(occurrence_pointer)
        self.pattern_occurrences[occurrence_id] = pointer
        _append_unique(self.occurrences_by_pattern, pointer["patternId"], occurrence_id)
        _append_unique(self.pattern_occurrences_by_root, pointer["rootEventId"], occurrence_id)
        run_id = pointer["minedBy"]
        _append_unique(self.outputs_by_run, run_id, occurrence_id)
        _append_unique(self.runs_by_output_artifact, occurrence_id, run_id)
        return {"ok": True, "occurrenceId": occurrence_id}

    def put_reasoning_input(self, input_pointer: dict[str, Any]) -> dict[str, Any]:
        input_id = input_pointer["inputId"]
        if input_id in self.reasoning_inputs:
            return {"ok": True, "duplicate": True, "inputId": input_id}
        self.reasoning_inputs[input_id] = deepcopy(input_pointer)
        return {"ok": True, "inputId": input_id}

    def put_reasoning_output(self, output_pointer: dict[str, Any]) -> dict[str, Any]:
        output_id = output_pointer["outputId"]
        if output_id in self.reasoning_outputs:
            return {"ok": True, "duplicate": True, "outputId": output_id}

        pointer = deepcopy(output_pointer)
        self.reasoning_outputs[output_id] = pointer
        _append_unique(self.reasoning_outputs_by_claim, pointer["claimId"], output_id)
        _append_unique(self.reasoning_outputs_by_input, pointer["inputId"], output_id)
        _append_unique(self.reasoning_outputs_by_run, pointer["reasoningRunId"], output_id)
        _append_unique(self.outputs_by_run, pointer["reasoningRunId"], output_id)
        _append_unique(self.runs_by_output_artifact, output_id, pointer["reasoningRunId"])
        return {"ok": True, "outputId": output_id}

    def by_source_event(self, event_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "eventId": event_id,
            "claimOccurrenceIds": list(self.occurrences_by_source_event.get(event_id, [])),
            "featureOccurrenceIds": list(self.feature_occurrences_by_source_event.get(event_id, [])),
        }

    def by_claim(self, claim_id: str) -> dict[str, Any]:
        return {"ok": True, "claimId": claim_id, "occurrenceIds": list(self.occurrences_by_claim.get(claim_id, []))}

    def by_feature(self, feature_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "featureId": feature_id,
            "occurrenceIds": list(self.feature_occurrences_by_feature.get(feature_id, [])),
        }

    def by_run(self, run_id: str) -> dict[str, Any]:
        return {"ok": True, "runId": run_id, "artifactIds": list(self.outputs_by_run.get(run_id, []))}

    def by_extractor(self, extractor_key: str) -> dict[str, Any]:
        return {"ok": True, "extractorKey": extractor_key, "runIds": list(self.runs_by_extractor.get(extractor_key, []))}

    def by_pattern(self, pattern_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "patternId": pattern_id,
            "occurrenceIds": list(self.occurrences_by_pattern.get(pattern_id, [])),
        }

    def clusters_for_claim(self, claim_id: str) -> dict[str, Any]:
        return {"ok": True, "claimId": claim_id, "clusterIds": list(self.clusters_by_claim.get(claim_id, []))}

    @staticmethod
    def stable_key(label: str, value: Any) -> str:
        return _stable_key(label, value)

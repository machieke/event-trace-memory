"""Evidence-backed NAL/PLR adapter."""

from __future__ import annotations

from event_trace_memory.artifacts import StoredArtifact
from event_trace_memory.canonical import content_id
from event_trace_memory.da import FileDA
from event_trace_memory.indexes import DerivedArtifactIndex, EventTraceIndex
from event_trace_memory.ingestion import EventIngestor, IngestedEvent


class ReasoningAdapter:
    def __init__(self, da: FileDA, event_index: EventTraceIndex, derived_index: DerivedArtifactIndex) -> None:
        self.da = da
        self.event_index = event_index
        self.derived_index = derived_index

    def build_input(
        self,
        *,
        claim_id: str,
        statement_text: str,
        derived_from_patterns: list[str] | None = None,
    ) -> StoredArtifact:
        if claim_id not in self.derived_index.claims:
            raise KeyError(claim_id)

        claim_pointer = self.derived_index.claims[claim_id]
        positive_occurrences: list[str] = []
        negative_occurrences: list[str] = []
        for occurrence_id in self.derived_index.occurrences_by_claim.get(claim_id, []):
            occurrence = self.derived_index.claim_occurrences[occurrence_id]
            if occurrence.get("polarity") in {"denied", "negated", "negative"}:
                negative_occurrences.append(occurrence_id)
            else:
                positive_occurrences.append(occurrence_id)

        support_vector = self._support_vector(positive_occurrences + negative_occurrences)
        body = {
            "kind": "reasoning-input",
            "schema": "nal-plr-input-v0.1",
            "claimId": claim_id,
            "claimCid": claim_pointer["claimCid"],
            "statement": {
                "format": "nal-like",
                "text": statement_text,
            },
            "evidence": {
                "positiveOccurrences": positive_occurrences,
                "negativeOccurrences": negative_occurrences,
                "supportVector": support_vector,
            },
            "derivedFromPatterns": derived_from_patterns or [],
        }
        cid = self.da.put_json(body)
        input_id = content_id("reasoning-input", body)
        pointer = {
            "kind": "reasoning-input-pointer",
            "schema": "reasoning-input-pointer-v0.1",
            "inputId": input_id,
            "inputCid": cid,
            "claimId": claim_id,
            "claimCid": claim_pointer["claimCid"],
            "evidenceOccurrenceIds": positive_occurrences + negative_occurrences,
            "supportVector": support_vector,
            "derivedFromPatterns": derived_from_patterns or [],
        }
        ack = self.derived_index.put_reasoning_input(pointer)
        return StoredArtifact(input_id, cid, body, pointer, ack)

    def record_output(
        self,
        *,
        reasoning_input: StoredArtifact,
        reasoning_run_id: str,
        truth_value: dict[str, float],
        revision_policy: str,
    ) -> StoredArtifact:
        claim_id = reasoning_input.pointer["claimId"]
        evidence_occurrence_ids = reasoning_input.pointer["evidenceOccurrenceIds"]
        belief_state_core = {
            "kind": "belief-state",
            "schema": "belief-state-v0.1",
            "claimId": claim_id,
            "truthValue": truth_value,
            "revisionPolicy": revision_policy,
            "evidenceOccurrenceIds": evidence_occurrence_ids,
        }
        belief_state_id = content_id("belief-state", belief_state_core)
        body = {
            "kind": "reasoning-output",
            "schema": "reasoning-output-v0.1",
            "inputId": reasoning_input.artifact_id,
            "inputCid": reasoning_input.cid,
            "claimId": claim_id,
            "reasoningRunId": reasoning_run_id,
            "beliefStateId": belief_state_id,
            "truthValue": truth_value,
            "revisionPolicy": revision_policy,
            "evidenceOccurrenceIds": evidence_occurrence_ids,
        }
        cid = self.da.put_json(body)
        output_id = content_id("reasoning-output", body)
        pointer = {
            "kind": "reasoning-output-pointer",
            "schema": "reasoning-output-pointer-v0.1",
            "outputId": output_id,
            "outputCid": cid,
            "inputId": reasoning_input.artifact_id,
            "inputCid": reasoning_input.cid,
            "claimId": claim_id,
            "reasoningRunId": reasoning_run_id,
            "beliefStateId": belief_state_id,
            "evidenceOccurrenceIds": evidence_occurrence_ids,
        }
        ack = self.derived_index.put_reasoning_output(pointer)
        return StoredArtifact(output_id, cid, body, pointer, ack)

    def log_reasoning_event(
        self,
        *,
        ingestor: EventIngestor,
        reasoning_run: StoredArtifact,
        reasoning_output: StoredArtifact,
        observed_at: str,
        parent_event_ids: list[str],
    ) -> IngestedEvent:
        return ingestor.log_child_event(
            raw_payload={
                "kind": "reasoning-run",
                "runId": reasoning_run.artifact_id,
                "runCid": reasoning_run.cid,
                "outputId": reasoning_output.artifact_id,
                "outputCid": reasoning_output.cid,
                "observedAt": observed_at,
            },
            observed_at=observed_at,
            actor_path=["agent", "omega-claw", "reasoner", "plr-adapter-v0.1"],
            channel_path=["system", "reasoning", "plr"],
            value_kind="reasoning-run",
            parent_event_ids=parent_event_ids,
            input_event_ids=parent_event_ids,
            output_artifact_ids=[reasoning_output.artifact_id],
        )

    def _support_vector(self, occurrence_ids: list[str]) -> dict[str, int]:
        event_ids: set[str] = set()
        actor_keys: set[str] = set()
        channel_keys: set[str] = set()
        day_keys: set[str] = set()
        source_payload_cids: set[str] = set()
        extraction_run_ids: set[str] = set()

        for occurrence_id in occurrence_ids:
            occurrence = self.derived_index.claim_occurrences[occurrence_id]
            event_ids.add(occurrence["sourceEventId"])
            source_payload_cids.add(occurrence["sourcePayloadCid"])
            extraction_run_ids.add(occurrence["extractionRunId"])
            event = self.event_index.get_event(occurrence["sourceEventId"])
            if event["ok"]:
                pointer = event["event"]
                actor_keys.add(pointer.get("actorPrefixKeys", [""])[-1])
                channel_keys.add(pointer.get("channelPrefixKeys", [""])[-1])
                time_path = pointer.get("timePath", [])
                day_keys.add("/".join(str(part) for part in time_path[:3]))

        return {
            "occurrenceSupport": len(occurrence_ids),
            "eventSupport": len(event_ids),
            "actorSupport": len(actor_keys),
            "channelSupport": len(channel_keys),
            "daySupport": len(day_keys),
            "sourceSupport": len(source_payload_cids),
            "extractorRunSupport": len(extraction_run_ids),
        }

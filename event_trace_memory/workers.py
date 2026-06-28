"""Worker-facing adapters built on the reference APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from event_trace_memory.artifacts import ArtifactWriter, StoredArtifact
from event_trace_memory.ingestion import EventIngestor, IngestedEvent


@dataclass(frozen=True)
class MemoryQueryTrace:
    query_event: IngestedEvent
    result_event: IngestedEvent


@dataclass(frozen=True)
class ShellActionTrace:
    start_event: IngestedEvent
    result_event: IngestedEvent
    stdout_cid: str
    stderr_cid: str


@dataclass(frozen=True)
class ExtractionWorkerResult:
    run: StoredArtifact
    claim_occurrences: list[StoredArtifact]
    feature_occurrences: list[StoredArtifact]
    event: IngestedEvent


class IrcSourceWorker:
    """Thin adapter for source integrations that produce IRC message records."""

    def __init__(self, ingestor: EventIngestor) -> None:
        self.ingestor = ingestor

    def ingest_message(
        self,
        *,
        server: str,
        room: str,
        nick: str,
        message: str,
        raw: str,
        observed_at: str,
    ) -> IngestedEvent:
        return self.ingestor.ingest_irc_message(
            server=server,
            room=room,
            nick=nick,
            message=message,
            raw=raw,
            observed_at=observed_at,
        )


class MemoryQueryWorker:
    """Log memory-query worker start/result events without hiding provenance."""

    def __init__(self, ingestor: EventIngestor) -> None:
        self.ingestor = ingestor

    def record_query_result(
        self,
        *,
        query: str,
        matches: list[dict[str, Any]],
        observed_at: str,
        completed_at: str,
        parent_event_ids: list[str],
        worker_key: str = "omega-claw-memory-worker:0.1.0",
    ) -> MemoryQueryTrace:
        query_event = self.ingestor.log_child_event(
            raw_payload={
                "kind": "memory-query",
                "query": query,
                "workerKey": worker_key,
                "observedAt": observed_at,
            },
            observed_at=observed_at,
            actor_path=["agent", "omega-claw", "memory-worker", worker_key],
            channel_path=["system", "memory", "long-term", "query"],
            value_kind="memory-query-start",
            parent_event_ids=parent_event_ids,
            provenance={"source": "worker", "workerKey": worker_key, "observedBy": "omega-claw"},
        )
        result_event = self.ingestor.log_child_event(
            raw_payload={
                "kind": "memory-query-result",
                "queryEventId": query_event.event_id,
                "matches": matches,
                "workerKey": worker_key,
                "observedAt": completed_at,
            },
            observed_at=completed_at,
            actor_path=["agent", "omega-claw", "memory-worker", worker_key],
            channel_path=["system", "memory", "long-term", "result"],
            value_kind="memory-query-result",
            parent_event_ids=[query_event.event_id],
            provenance={"source": "worker", "workerKey": worker_key, "observedBy": "omega-claw"},
        )
        return MemoryQueryTrace(query_event=query_event, result_event=result_event)


class ShellActionWorker:
    """Record explicitly permissioned shell action traces.

    This adapter does not execute commands. Callers provide the observed command
    result, and the adapter stores stdout/stderr in DA before logging pointers.
    """

    def __init__(self, ingestor: EventIngestor) -> None:
        self.ingestor = ingestor

    def record_action_result(
        self,
        *,
        command: list[str],
        cwd: str,
        allowlist_policy: str,
        exit_code: int,
        stdout: Any,
        stderr: Any,
        started_at: str,
        completed_at: str,
        parent_event_ids: list[str],
        worker_key: str = "omega-claw-shell-worker:0.1.0",
    ) -> ShellActionTrace:
        start_event = self.ingestor.log_child_event(
            raw_payload={
                "kind": "shell-action",
                "command": command,
                "cwd": cwd,
                "allowlistPolicy": allowlist_policy,
                "workerKey": worker_key,
                "observedAt": started_at,
            },
            observed_at=started_at,
            actor_path=["agent", "omega-claw", "shell-worker", worker_key],
            channel_path=["system", "shell", "action", "start"],
            value_kind="shell-action-start",
            parent_event_ids=parent_event_ids,
            provenance={"source": "worker", "workerKey": worker_key, "observedBy": "omega-claw"},
        )
        stdout_cid = self.ingestor.da.put_bytes(_as_bytes(stdout), codec="text/plain")
        stderr_cid = self.ingestor.da.put_bytes(_as_bytes(stderr), codec="text/plain")
        result_event = self.ingestor.log_child_event(
            raw_payload={
                "kind": "shell-action-result",
                "startEventId": start_event.event_id,
                "command": command,
                "cwd": cwd,
                "allowlistPolicy": allowlist_policy,
                "exitCode": exit_code,
                "stdoutCid": stdout_cid,
                "stderrCid": stderr_cid,
                "workerKey": worker_key,
                "observedAt": completed_at,
            },
            observed_at=completed_at,
            actor_path=["agent", "omega-claw", "shell-worker", worker_key],
            channel_path=["system", "shell", "action", "result"],
            value_kind="shell-action-result",
            parent_event_ids=[start_event.event_id],
            output_artifact_ids=[stdout_cid, stderr_cid],
            provenance={"source": "worker", "workerKey": worker_key, "observedBy": "omega-claw"},
        )
        return ShellActionTrace(start_event=start_event, result_event=result_event, stdout_cid=stdout_cid, stderr_cid=stderr_cid)


class ClaimFeatureExtractionWorker:
    """Record claim/feature extraction runs and their provenance edges."""

    def __init__(self, ingestor: EventIngestor, writer: ArtifactWriter) -> None:
        self.ingestor = ingestor
        self.writer = writer

    def record_extraction(
        self,
        *,
        input_event_ids: list[str],
        claim_specs: list[dict[str, Any]],
        feature_specs: list[dict[str, Any]],
        actor_key: str,
        tool: dict[str, Any],
        config: dict[str, Any],
        started_at: str,
        completed_at: str,
        parent_event_ids: list[str],
    ) -> ExtractionWorkerResult:
        run = self.writer.record_run(
            run_type="claim-feature-extraction",
            input_event_ids=input_event_ids,
            actor_key=actor_key,
            tool=tool,
            config=config,
            started_at=started_at,
            completed_at=completed_at,
        )
        claim_occurrences = [
            self.writer.put_claim_occurrence(
                claim_core=spec["claimCore"],
                source_event_id=spec["sourceEventId"],
                extraction_run_id=run.artifact_id,
                evidence=spec.get("evidence", {"kind": "whole-event"}),
                polarity=spec.get("polarity", "asserted"),
                confidence=spec.get("confidence", 1.0),
                provenance=spec.get("provenance", {"extractor": actor_key}),
            )
            for spec in claim_specs
        ]
        feature_occurrences = [
            self.writer.put_feature_occurrence(
                feature_core=spec["featureCore"],
                source_event_id=spec["sourceEventId"],
                extraction_run_id=run.artifact_id,
                evidence=spec.get("evidence", {"kind": "whole-event"}),
                confidence=spec.get("confidence", 1.0),
            )
            for spec in feature_specs
        ]
        output_artifact_ids = [artifact.artifact_id for artifact in claim_occurrences + feature_occurrences]
        event = self.ingestor.log_child_event(
            raw_payload={
                "kind": "extraction-run",
                "runId": run.artifact_id,
                "runCid": run.cid,
                "workerKey": actor_key,
                "claimOccurrenceIds": [artifact.artifact_id for artifact in claim_occurrences],
                "featureOccurrenceIds": [artifact.artifact_id for artifact in feature_occurrences],
                "observedAt": completed_at,
            },
            observed_at=completed_at,
            actor_path=["agent", "omega-claw", "extractor", actor_key],
            channel_path=["system", "extraction", "claims-features"],
            value_kind="extraction-run",
            parent_event_ids=parent_event_ids,
            input_event_ids=input_event_ids,
            output_artifact_ids=output_artifact_ids,
            provenance={"source": "worker", "workerKey": actor_key, "observedBy": "omega-claw"},
        )
        return ExtractionWorkerResult(
            run=run,
            claim_occurrences=claim_occurrences,
            feature_occurrences=feature_occurrences,
            event=event,
        )


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


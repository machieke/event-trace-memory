"""Event ingestion worker helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from event_trace_memory.canonical import canonical_json_bytes, content_id, sha256_hex
from event_trace_memory.da import DAStore
from event_trace_memory.indexes import EventTraceIndex
from event_trace_memory.paths import parse_utc_time, prefix_keys, time_prefix_keys


@dataclass(frozen=True)
class IngestedEvent:
    event_id: str
    event_cid: str
    payload_cid: str
    envelope: dict[str, Any]
    pointer: dict[str, Any]
    ack: dict[str, Any]


class EventIngestor:
    def __init__(self, da: DAStore, index: EventTraceIndex) -> None:
        self.da = da
        self.index = index

    def ingest_irc_message(
        self,
        *,
        server: str,
        room: str,
        nick: str,
        message: str,
        raw: str,
        observed_at: str,
    ) -> IngestedEvent:
        raw_payload = {
            "kind": "raw-payload",
            "schema": "raw-irc-v0.1",
            "transport": "irc",
            "server": server,
            "room": room,
            "nick": nick,
            "message": message,
            "raw": raw,
            "observedAt": observed_at,
        }
        return self.ingest_event(
            raw_payload=raw_payload,
            observed_at=observed_at,
            actor_path=["irc", server, "user", nick],
            channel_path=["irc", server, "channel", room],
            value_kind="message",
            content_type="application/json",
            preview=message[:160],
            provenance={
                "source": "irc",
                "observedBy": "omega-claw",
                "ingestionPipeline": "event-trace-v0",
            },
        )

    def log_child_event(
        self,
        *,
        raw_payload: dict[str, Any],
        observed_at: str,
        actor_path: list[str],
        channel_path: list[str],
        value_kind: str,
        parent_event_ids: list[str],
        root_event_id: str | None = None,
        input_event_ids: list[str] | None = None,
        output_artifact_ids: list[str] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> IngestedEvent:
        if root_event_id is None and parent_event_ids:
            parent = self.index.get_event(parent_event_ids[0])
            if parent["ok"]:
                root_event_id = parent["event"].get("rootEventId")
        return self.ingest_event(
            raw_payload=raw_payload,
            observed_at=observed_at,
            actor_path=actor_path,
            channel_path=channel_path,
            value_kind=value_kind,
            parent_event_ids=parent_event_ids,
            root_event_id=root_event_id,
            input_event_ids=input_event_ids or [],
            output_artifact_ids=output_artifact_ids or [],
            provenance=provenance
            or {
                "source": "worker",
                "observedBy": "omega-claw",
                "ingestionPipeline": "event-trace-v0",
            },
        )

    def ingest_event(
        self,
        *,
        raw_payload: dict[str, Any],
        observed_at: str,
        actor_path: list[str],
        channel_path: list[str],
        value_kind: str,
        content_type: str = "application/json",
        preview: str | None = None,
        provenance: dict[str, Any] | None = None,
        parent_event_ids: list[str] | None = None,
        root_event_id: str | None = None,
        input_event_ids: list[str] | None = None,
        output_artifact_ids: list[str] | None = None,
    ) -> IngestedEvent:
        parent_event_ids = parent_event_ids or []
        input_event_ids = input_event_ids or []
        output_artifact_ids = output_artifact_ids or []

        payload_cid = self.da.put_json(raw_payload)
        time = parse_utc_time(observed_at)
        envelope = {
            "kind": "event-trace",
            "schema": "event-trace-v0.1",
            "time": time,
            "actorPath": actor_path,
            "channelPath": channel_path,
            "value": {
                "kind": value_kind,
                "contentType": content_type,
                "payloadCid": payload_cid,
            },
            "provenance": provenance
            or {
                "source": "unknown",
                "observedBy": "omega-claw",
                "ingestionPipeline": "event-trace-v0",
            },
            "causal": {
                "parentEventIds": parent_event_ids,
                "rootEventId": root_event_id,
                "inputEventIds": input_event_ids,
                "outputArtifactIds": output_artifact_ids,
            },
        }
        if preview is not None:
            envelope["value"]["preview"] = preview

        event_bytes = canonical_json_bytes(envelope)
        event_cid = self.da.put_bytes(event_bytes, codec="dag-json")
        event_id = f"event:{sha256_hex(event_bytes)}"
        pointer_root_event_id = root_event_id or event_id
        pointer = {
            "kind": "event-pointer",
            "schema": "event-pointer-v0.1",
            "eventId": event_id,
            "eventCid": event_cid,
            "payloadCid": payload_cid,
            "timePath": [time["year"], time["month"], time["day"], time["hour"]],
            "timePrefixKeys": time_prefix_keys(time),
            "actorPath": actor_path,
            "actorPrefixKeys": prefix_keys(actor_path),
            "channelPath": channel_path,
            "channelPrefixKeys": prefix_keys(channel_path),
            "valueKind": value_kind,
            "parentEventIds": parent_event_ids,
            "rootEventId": pointer_root_event_id,
            "inputEventIds": input_event_ids,
            "outputArtifactIds": output_artifact_ids,
        }
        ack = self.index.put_event(pointer)
        return IngestedEvent(event_id, event_cid, payload_cid, envelope, pointer, ack)


def artifact_id(kind: str, artifact: dict[str, Any]) -> str:
    return content_id(kind, artifact)

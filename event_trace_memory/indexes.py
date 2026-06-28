"""Reference contract indexes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


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

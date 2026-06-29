"""Privacy and public-index policy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from event_trace_memory.canonical import sha256_hex
from event_trace_memory.ingestion import EventIngestor, IngestedEvent


class PrivacyPolicyError(ValueError):
    """Raised when an event is not allowed in the selected public index path."""


@dataclass(frozen=True)
class PrivacyDecision:
    public_index_allowed: bool
    privacy_level: str
    reason: str


@dataclass(frozen=True)
class PublicIndexPolicy:
    public_levels: tuple[str, ...] = ("public",)
    private_levels: tuple[str, ...] = ("private", "confidential", "secret")
    hash_salt: str = "event-trace-memory-public-index-v0"

    def classify(self, raw_payload: dict[str, Any]) -> PrivacyDecision:
        privacy_level = str(raw_payload.get("privacy", "public"))
        if privacy_level in self.public_levels:
            return PrivacyDecision(True, privacy_level, "public-level")
        if privacy_level in self.private_levels:
            return PrivacyDecision(False, privacy_level, "private-level")
        return PrivacyDecision(False, privacy_level, "unknown-level")

    def assert_public_index_allowed(self, raw_payload: dict[str, Any]) -> PrivacyDecision:
        decision = self.classify(raw_payload)
        if not decision.public_index_allowed:
            raise PrivacyPolicyError(
                f"privacy level {decision.privacy_level!r} is not allowed in the public event index"
            )
        return decision

    def hash_path(self, path: list[str]) -> list[str]:
        return [hash_path_segment(segment, salt=self.hash_salt) for segment in path]


class PrivacyAwareIngestor:
    """Policy wrapper that protects public event indexes."""

    def __init__(self, ingestor: EventIngestor, policy: PublicIndexPolicy | None = None) -> None:
        self.ingestor = ingestor
        self.policy = policy or PublicIndexPolicy()

    def ingest_public_event(
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
    ) -> IngestedEvent:
        decision = self.policy.assert_public_index_allowed(raw_payload)
        return self.ingestor.ingest_event(
            raw_payload=raw_payload,
            observed_at=observed_at,
            actor_path=actor_path,
            channel_path=channel_path,
            value_kind=value_kind,
            content_type=content_type,
            preview=preview,
            provenance=_with_privacy_decision(provenance, decision),
        )

    def ingest_hashed_path_event(
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
    ) -> IngestedEvent:
        decision = self.policy.classify(raw_payload)
        return self.ingestor.ingest_event(
            raw_payload=raw_payload,
            observed_at=observed_at,
            actor_path=self.policy.hash_path(actor_path),
            channel_path=self.policy.hash_path(channel_path),
            value_kind=value_kind,
            content_type=content_type,
            preview=preview,
            provenance=_with_privacy_decision(provenance, decision, path_mode="hashed"),
        )


def hash_path_segment(segment: object, *, salt: str) -> str:
    digest = sha256_hex(f"{salt}\0{segment}".encode("utf-8"))
    return f"hash-sha256:{digest}"


def _with_privacy_decision(
    provenance: dict[str, Any] | None,
    decision: PrivacyDecision,
    *,
    path_mode: str = "clear",
) -> dict[str, Any]:
    result = dict(provenance or {"source": "privacy-aware-ingestor", "observedBy": "omega-claw"})
    result["privacy"] = {
        "level": decision.privacy_level,
        "publicIndexAllowed": decision.public_index_allowed,
        "reason": decision.reason,
        "pathMode": path_mode,
    }
    return result


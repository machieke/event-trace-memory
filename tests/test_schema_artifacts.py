from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from event_trace_memory import (
    ArtifactWriter,
    DerivedArtifactIndex,
    EventIngestor,
    EventTraceIndex,
    FileDA,
    PatternMiner,
    ReasoningAdapter,
    SnapshotBuilder,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


class SchemaArtifactTest(unittest.TestCase):
    def test_schema_files_are_parseable_ascii_json(self):
        schema_files = sorted(SCHEMAS.glob("*.schema.json"))
        self.assertGreater(len(schema_files), 0)

        for path in schema_files:
            with self.subTest(schema=path.name):
                source = path.read_text(encoding="utf-8")
                source.encode("ascii")
                schema = json.loads(source)
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(schema["type"], "object")
                self.assertIn("required", schema)
                self.assertIn("properties", schema)

    def test_schemas_validate_reference_artifacts(self):
        samples = build_reference_samples()
        schema_names = {path.name for path in SCHEMAS.glob("*.schema.json")}

        self.assertEqual(set(samples), schema_names)

        for name, sample in sorted(samples.items()):
            with self.subTest(schema=name):
                schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
                validate_schema_fragment(schema, sample)


def validate_schema_fragment(schema: dict[str, Any], value: Any, path: str = "$") -> None:
    if "const" in schema:
        if value != schema["const"]:
            raise AssertionError(f"{path} expected const {schema['const']!r}, got {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        raise AssertionError(f"{path} expected one of {schema['enum']!r}, got {value!r}")

    expected_type = schema.get("type")
    if expected_type is not None and not matches_json_type(value, expected_type):
        raise AssertionError(f"{path} expected type {expected_type!r}, got {type(value).__name__}")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise AssertionError(f"{path} missing required key {key!r}")
        properties = schema.get("properties", {})
        for key, child_schema in properties.items():
            if key in value:
                validate_schema_fragment(child_schema, value[key], f"{path}.{key}")
        additional_schema = schema.get("additionalProperties")
        if isinstance(additional_schema, dict):
            for key, item in value.items():
                if key not in properties:
                    validate_schema_fragment(additional_schema, item, f"{path}.{key}")

    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            validate_schema_fragment(schema["items"], item, f"{path}[{index}]")


def matches_json_type(value: Any, expected_type: Any) -> bool:
    if isinstance(expected_type, list):
        return any(matches_json_type(value, item) for item in expected_type)

    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    raise AssertionError(f"Unsupported schema type {expected_type!r}")


def build_reference_samples() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        da = FileDA(f"{temp_dir}/da")
        event_index = EventTraceIndex()
        derived_index = DerivedArtifactIndex()
        ingestor = EventIngestor(da, event_index)
        writer = ArtifactWriter(da, event_index, derived_index)
        miner = PatternMiner(writer)
        adapter = ReasoningAdapter(da, event_index, derived_index)

        root = ingestor.ingest_irc_message(
            server="libera",
            room="#chat",
            nick="alice",
            message="The event trace store should index by time, actor, and channel.",
            raw=":alice!user@host PRIVMSG #chat :The event trace store should index by time, actor, and channel.",
            observed_at="2026-06-27T14:35:00Z",
        )
        memory_query = ingestor.log_child_event(
            raw_payload={"kind": "memory-query", "query": "event trace", "observedAt": "2026-06-27T14:35:01Z"},
            observed_at="2026-06-27T14:35:01Z",
            actor_path=["agent", "omega-claw", "memory-worker"],
            channel_path=["system", "memory", "long-term", "query"],
            value_kind="memory-query-start",
            parent_event_ids=[root.event_id],
        )
        shell_action = ingestor.log_child_event(
            raw_payload={"kind": "shell-action", "action": "read", "observedAt": "2026-06-27T14:35:02Z"},
            observed_at="2026-06-27T14:35:02Z",
            actor_path=["agent", "omega-claw", "shell-worker"],
            channel_path=["system", "shell", "filesystem", "read"],
            value_kind="shell-action-start",
            parent_event_ids=[root.event_id],
        )

        extraction_run = writer.record_run(
            run_type="claim-extraction",
            input_event_ids=[root.event_id, memory_query.event_id, shell_action.event_id],
            actor_key="omega-claw-claim-extractor:0.1.0",
            tool={"name": "omega-claw-claim-extractor", "version": "0.1.0", "codeCid": "cidv0-local-sha256:" + "1" * 64},
            config={"claimSchema": "claim-core-v0.1"},
            started_at="2026-06-27T14:35:03Z",
            completed_at="2026-06-27T14:35:04Z",
        )
        claim_core = {
            "kind": "claim",
            "schema": "claim-core-v0.1",
            "subject": {"id": "event-trace-store"},
            "predicate": {"id": "indexable-by"},
            "object": {"items": ["time", "actor", "channel"]},
            "modality": "normative",
            "context": {"domain": "episodic-memory-architecture"},
        }
        claim = writer.put_claim(claim_core)
        claim_occurrence = writer.put_claim_occurrence(
            claim_core=claim_core,
            source_event_id=root.event_id,
            extraction_run_id=extraction_run.artifact_id,
            evidence={"kind": "text-span", "span": {"start": 0, "end": 68}},
            confidence=0.84,
            provenance={"extractor": "omega-claw-claim-extractor", "extractorVersion": "0.1.0"},
        )
        claim_cluster = writer.put_claim_cluster(
            relation="semantic-near-duplicate",
            members=[claim.artifact_id],
            method={"name": "exact-first", "version": "0.1.0"},
            confidence=1.0,
        )

        feature_core = {
            "kind": "feature",
            "schema": "feature-core-v0.1",
            "featureType": "topic",
            "value": {"id": "event-trace-indexing", "label": "event trace indexing"},
        }
        feature = writer.put_feature(feature_core)
        feature_occurrence = writer.put_feature_occurrence(
            feature_core=feature_core,
            source_event_id=root.event_id,
            extraction_run_id=extraction_run.artifact_id,
            confidence=0.91,
            evidence={"kind": "whole-event"},
        )

        extraction_event = ingestor.log_child_event(
            raw_payload={
                "kind": "extraction-run",
                "runId": extraction_run.artifact_id,
                "runCid": extraction_run.cid,
                "observedAt": "2026-06-27T14:35:05Z",
            },
            observed_at="2026-06-27T14:35:05Z",
            actor_path=["agent", "omega-claw", "extractor", "claim-extractor-v0.1"],
            channel_path=["system", "extraction", "claims"],
            value_kind="extraction-run",
            parent_event_ids=[root.event_id],
            input_event_ids=[root.event_id, memory_query.event_id, shell_action.event_id],
            output_artifact_ids=[claim_occurrence.artifact_id, feature_occurrence.artifact_id],
        )

        snapshot = SnapshotBuilder(da, event_index, derived_index).build_hour_snapshot("/2026/06/27/14")
        mining_run = writer.record_run(
            run_type="pattern-mining",
            input_event_ids=[],
            input_snapshot_cids=[snapshot.cid],
            actor_key="omega-sequence-miner:0.1.0",
            tool={"name": "omega-sequence-miner", "version": "0.1.0", "codeCid": "cidv0-local-sha256:" + "2" * 64},
            config={"minSupport": 1, "maxWindowSeconds": 30, "supportUnit": "root-trace"},
            started_at="2026-06-27T15:00:00Z",
            completed_at="2026-06-27T15:00:07Z",
        )
        mined = miner.mine_sequence(
            snapshot=snapshot,
            sequence=["message", "memory-query-start", "shell-action-start", "extraction-run"],
            mining_run_id=mining_run.artifact_id,
            miner_key="omega-sequence-miner:0.1.0",
        )
        assert mined is not None

        reasoning_input = adapter.build_input(
            claim_id=claim.artifact_id,
            statement_text="<event-trace-store --> indexable-by-time-actor-channel>",
            derived_from_patterns=[mined.pattern.artifact_id],
        )
        reasoning_run = writer.record_run(
            run_type="reasoning",
            input_event_ids=[root.event_id],
            actor_key="plr-adapter:0.1.0",
            tool={"name": "plr-adapter", "version": "0.1.0", "codeCid": "cidv0-local-sha256:" + "3" * 64},
            config={"revisionPolicy": "evidence-weighted"},
            started_at="2026-06-27T15:01:00Z",
            completed_at="2026-06-27T15:01:01Z",
        )
        reasoning_output = adapter.record_output(
            reasoning_input=reasoning_input,
            reasoning_run_id=reasoning_run.artifact_id,
            truth_value={"frequency": 1.0, "confidence": 0.84},
            revision_policy="evidence-weighted",
        )

        return {
            "raw-irc-v0.1.schema.json": da.get_json(root.payload_cid),
            "event-trace-v0.1.schema.json": root.envelope,
            "event-pointer-v0.1.schema.json": root.pointer,
            "run-v0.1.schema.json": extraction_run.body,
            "run-pointer-v0.1.schema.json": extraction_run.pointer,
            "claim-core-v0.1.schema.json": claim.body,
            "claim-pointer-v0.1.schema.json": claim.pointer,
            "claim-occurrence-v0.1.schema.json": claim_occurrence.body,
            "claim-occurrence-pointer-v0.1.schema.json": claim_occurrence.pointer,
            "claim-cluster-v0.1.schema.json": claim_cluster.body,
            "claim-cluster-pointer-v0.1.schema.json": claim_cluster.pointer,
            "feature-core-v0.1.schema.json": feature.body,
            "feature-pointer-v0.1.schema.json": feature.pointer,
            "feature-occurrence-v0.1.schema.json": feature_occurrence.body,
            "feature-occurrence-pointer-v0.1.schema.json": feature_occurrence.pointer,
            "mining-snapshot-v0.1.schema.json": snapshot.manifest,
            "event-dictionary-v0.1.schema.json": snapshot.event_dictionary,
            "event-columns-v0.1.schema.json": snapshot.event_columns,
            "postings-v0.1.schema.json": snapshot.postings,
            "provenance-edges-v0.1.schema.json": snapshot.provenance_edges,
            "claim-occurrences-by-event-v0.1.schema.json": snapshot.claim_occurrences,
            "feature-occurrences-by-event-v0.1.schema.json": snapshot.feature_occurrences,
            "pattern-core-v0.1.schema.json": mined.pattern.body,
            "pattern-pointer-v0.1.schema.json": mined.pattern.pointer,
            "pattern-occurrence-v0.1.schema.json": mined.occurrences[0].body,
            "pattern-occurrence-pointer-v0.1.schema.json": mined.occurrences[0].pointer,
            "nal-plr-input-v0.1.schema.json": reasoning_input.body,
            "reasoning-input-pointer-v0.1.schema.json": reasoning_input.pointer,
            "reasoning-output-v0.1.schema.json": reasoning_output.body,
            "reasoning-output-pointer-v0.1.schema.json": reasoning_output.pointer,
        }


if __name__ == "__main__":
    unittest.main()

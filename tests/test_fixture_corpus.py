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
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "minimum-corpus-v0.1.json"

EXPECTED_COVERAGE = [
    "single IRC message",
    "duplicate IRC message",
    "same payload under different schema version",
    "two messages same claim",
    "one event with memory query and shell action",
    "one extraction run with two claims",
    "one hour snapshot with postings",
    "one sequence pattern discovery",
    "one NAL/PLR input generation",
]


class FixtureCorpusTest(unittest.TestCase):
    def test_minimum_fixture_corpus_covers_plan_items(self):
        corpus = load_fixture_corpus()

        self.assertEqual(corpus["kind"], "event-trace-memory-fixture-corpus")
        self.assertEqual(corpus["schema"], "fixture-corpus-v0.1")
        self.assertEqual(corpus["covers"], EXPECTED_COVERAGE)

    def test_minimum_fixture_corpus_executes_reference_flow(self):
        corpus = load_fixture_corpus()

        with tempfile.TemporaryDirectory() as temp_dir:
            da = FileDA(f"{temp_dir}/da")
            event_index = EventTraceIndex()
            derived_index = DerivedArtifactIndex()
            ingestor = EventIngestor(da, event_index)
            writer = ArtifactWriter(da, event_index, derived_index)

            root = ingest_irc_fixture(ingestor, corpus["ircMessages"]["single"])
            duplicate = ingest_irc_fixture(ingestor, corpus["ircMessages"]["duplicate"])

            self.assertTrue(root.ack["ok"])
            self.assertTrue(da.has(root.payload_cid))
            self.assertEqual(duplicate.payload_cid, root.payload_cid)
            self.assertFalse(duplicate.ack["ok"])

            interpreted_one, interpreted_two = ingest_alternate_interpretations(
                ingestor,
                corpus["samePayloadDifferentSchemaVersion"],
            )
            self.assertEqual(interpreted_one.payload_cid, interpreted_two.payload_cid)
            self.assertNotEqual(interpreted_one.event_cid, interpreted_two.event_cid)
            self.assertNotEqual(interpreted_one.event_id, interpreted_two.event_id)

            memory_query = log_child_fixture(ingestor, corpus["childEvents"]["memoryQuery"], root.event_id)
            shell_action = log_child_fixture(ingestor, corpus["childEvents"]["shellAction"], root.event_id)
            self.assertEqual(
                event_index.by_parent(root.event_id)["eventIds"],
                [memory_query.event_id, shell_action.event_id],
            )

            same_claim_alice = ingest_irc_fixture(ingestor, corpus["ircMessages"]["sameClaimAlice"])
            same_claim_bob = ingest_irc_fixture(ingestor, corpus["ircMessages"]["sameClaimBob"])

            extraction_run = record_run_fixture(
                writer,
                corpus["extractionRun"],
                input_event_ids=[root.event_id, memory_query.event_id, shell_action.event_id],
            )
            claim_one = corpus["claimCores"][0]["body"]
            claim_two = corpus["claimCores"][1]["body"]
            occurrence_one = writer.put_claim_occurrence(
                claim_core=claim_one,
                source_event_id=same_claim_alice.event_id,
                extraction_run_id=extraction_run.artifact_id,
                evidence={"kind": "text-span", "quote": same_claim_alice.envelope["value"]["preview"]},
                confidence=0.82,
            )
            occurrence_two = writer.put_claim_occurrence(
                claim_core=claim_one,
                source_event_id=same_claim_bob.event_id,
                extraction_run_id=extraction_run.artifact_id,
                evidence={"kind": "text-span", "quote": same_claim_bob.envelope["value"]["preview"]},
                confidence=0.79,
            )
            occurrence_three = writer.put_claim_occurrence(
                claim_core=claim_two,
                source_event_id=root.event_id,
                extraction_run_id=extraction_run.artifact_id,
                evidence={"kind": "whole-event"},
                confidence=0.84,
            )
            feature_occurrence = writer.put_feature_occurrence(
                feature_core=corpus["featureCore"],
                source_event_id=root.event_id,
                extraction_run_id=extraction_run.artifact_id,
                confidence=0.91,
                evidence={"kind": "whole-event"},
            )

            self.assertEqual(
                derived_index.by_claim(occurrence_one.pointer["claimId"])["occurrenceIds"],
                [occurrence_one.artifact_id, occurrence_two.artifact_id],
            )
            self.assertEqual(len(derived_index.claims), 2)
            self.assertEqual(
                derived_index.by_run(extraction_run.artifact_id)["artifactIds"],
                [
                    occurrence_one.artifact_id,
                    occurrence_two.artifact_id,
                    occurrence_three.artifact_id,
                    feature_occurrence.artifact_id,
                ],
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
                output_artifact_ids=[
                    occurrence_one.artifact_id,
                    occurrence_two.artifact_id,
                    occurrence_three.artifact_id,
                    feature_occurrence.artifact_id,
                ],
            )

            snapshot = SnapshotBuilder(da, event_index, derived_index).build_hour_snapshot(corpus["snapshot"]["shardPath"])
            self.assertIn(root.event_id, snapshot.event_dictionary["eventIdToLocalId"])
            self.assertIn("event.kind:message", snapshot.postings)
            self.assertIn(occurrence_three.artifact_id, snapshot.claim_occurrences[root.event_id])

            mining_run = record_run_fixture(
                writer,
                corpus["patternMiningRun"],
                input_event_ids=[],
                input_snapshot_cids=[snapshot.cid],
            )
            miner = PatternMiner(writer)
            mined = miner.mine_sequence(
                snapshot=snapshot,
                sequence=corpus["pattern"]["sequence"],
                mining_run_id=mining_run.artifact_id,
                miner_key=corpus["pattern"]["minerKey"],
                min_support=corpus["pattern"]["minSupport"],
                max_window_seconds=corpus["pattern"]["maxWindowSeconds"],
            )
            self.assertIsNotNone(mined)
            assert mined is not None
            self.assertEqual(
                derived_index.pattern_occurrences[mined.occurrences[0].artifact_id]["participatingEventIds"],
                [root.event_id, memory_query.event_id, shell_action.event_id, extraction_event.event_id],
            )

            discovery_event = miner.log_pattern_discovery_event(
                ingestor=ingestor,
                mining_run=mining_run,
                mined_pattern=mined,
                observed_at="2026-06-27T15:00:08Z",
                parent_event_ids=[root.event_id],
            )
            self.assertEqual(event_index.by_kind("pattern-discovery")["eventIds"], [discovery_event.event_id])

            adapter = ReasoningAdapter(da, event_index, derived_index)
            reasoning_input = adapter.build_input(
                claim_id=occurrence_one.pointer["claimId"],
                statement_text=corpus["reasoning"]["statementText"],
                derived_from_patterns=[mined.pattern.artifact_id],
            )
            self.assertEqual(
                reasoning_input.body["evidence"]["positiveOccurrences"],
                [occurrence_one.artifact_id, occurrence_two.artifact_id],
            )
            self.assertEqual(reasoning_input.body["derivedFromPatterns"], [mined.pattern.artifact_id])

            reasoning_run = record_run_fixture(
                writer,
                corpus["reasoning"]["run"],
                input_event_ids=[root.event_id],
            )
            reasoning_output = adapter.record_output(
                reasoning_input=reasoning_input,
                reasoning_run_id=reasoning_run.artifact_id,
                truth_value=corpus["reasoning"]["truthValue"],
                revision_policy=corpus["reasoning"]["revisionPolicy"],
            )
            self.assertEqual(
                derived_index.reasoning_outputs_by_input[reasoning_input.artifact_id],
                [reasoning_output.artifact_id],
            )


def load_fixture_corpus() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def ingest_irc_fixture(ingestor: EventIngestor, fixture: dict[str, Any]):
    return ingestor.ingest_irc_message(
        server=fixture["server"],
        room=fixture["room"],
        nick=fixture["nick"],
        message=fixture["message"],
        raw=fixture["raw"],
        observed_at=fixture["observedAt"],
    )


def ingest_alternate_interpretations(ingestor: EventIngestor, fixture: dict[str, Any]):
    raw_payload = fixture["rawPayload"]
    first = fixture["firstInterpretation"]
    second = fixture["secondInterpretation"]
    return (
        ingestor.ingest_event(
            raw_payload=raw_payload,
            observed_at=first["observedAt"],
            actor_path=first["actorPath"],
            channel_path=first["channelPath"],
            value_kind=first["valueKind"],
            provenance=first["provenance"],
        ),
        ingestor.ingest_event(
            raw_payload=raw_payload,
            observed_at=second["observedAt"],
            actor_path=second["actorPath"],
            channel_path=second["channelPath"],
            value_kind=second["valueKind"],
            provenance=second["provenance"],
        ),
    )


def log_child_fixture(ingestor: EventIngestor, fixture: dict[str, Any], root_event_id: str):
    return ingestor.log_child_event(
        raw_payload=fixture["rawPayload"],
        observed_at=fixture["observedAt"],
        actor_path=fixture["actorPath"],
        channel_path=fixture["channelPath"],
        value_kind=fixture["valueKind"],
        parent_event_ids=[root_event_id],
    )


def record_run_fixture(
    writer: ArtifactWriter,
    fixture: dict[str, Any],
    *,
    input_event_ids: list[str],
    input_snapshot_cids=None,
):
    return writer.record_run(
        run_type=fixture["runType"],
        input_event_ids=input_event_ids,
        input_snapshot_cids=input_snapshot_cids,
        actor_key=fixture["actorKey"],
        tool=fixture["tool"],
        config=fixture["config"],
        started_at=fixture["startedAt"],
        completed_at=fixture["completedAt"],
    )


if __name__ == "__main__":
    unittest.main()

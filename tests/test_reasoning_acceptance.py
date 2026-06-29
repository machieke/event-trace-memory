import tempfile
import unittest

from event_trace_memory import (
    ArtifactWriter,
    DerivedArtifactIndex,
    EventIngestor,
    EventTraceIndex,
    FileDA,
    ReasoningAdapter,
)


class ReasoningAcceptanceTest(unittest.TestCase):
    def test_reasoning_acceptance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            da = FileDA(f"{temp_dir}/da")
            event_index = EventTraceIndex()
            derived_index = DerivedArtifactIndex()
            ingestor = EventIngestor(da, event_index)
            writer = ArtifactWriter(da, event_index, derived_index)
            adapter = ReasoningAdapter(da, event_index, derived_index)

            source = ingestor.ingest_irc_message(
                server="libera",
                room="#chat",
                nick="alice",
                message="The event trace store should index by time, actor, and channel.",
                raw=":alice!user@host PRIVMSG #chat :The event trace store should index by time, actor, and channel.",
                observed_at="2026-06-27T14:35:00Z",
            )
            extraction_run = writer.record_run(
                run_type="claim-extraction",
                input_event_ids=[source.event_id],
                actor_key="omega-claw-claim-extractor:0.1.0",
                tool={"name": "omega-claw-claim-extractor", "version": "0.1.0", "codeCid": "cidv0-local-sha256:" + "7" * 64},
                config={"claimSchema": "claim-core-v0.1"},
                started_at="2026-06-27T14:35:01Z",
                completed_at="2026-06-27T14:35:02Z",
            )
            occurrence = writer.put_claim_occurrence(
                claim_core={
                    "kind": "claim",
                    "schema": "claim-core-v0.1",
                    "subject": {"id": "event-trace-store"},
                    "predicate": {"id": "indexable-by"},
                    "object": {"items": ["time", "actor", "channel"]},
                },
                source_event_id=source.event_id,
                extraction_run_id=extraction_run.artifact_id,
                evidence={"kind": "text-span", "span": {"start": 0, "end": 68}},
                confidence=0.84,
            )
            claim_id = occurrence.pointer["claimId"]

            reasoning_input = adapter.build_input(
                claim_id=claim_id,
                statement_text="<event-trace-store --> indexable-by-time-actor-channel>",
                derived_from_patterns=["pattern:example"],
            )

            self.assertEqual(reasoning_input.body["claimId"], claim_id)
            self.assertEqual(reasoning_input.body["evidence"]["positiveOccurrences"], [occurrence.artifact_id])
            self.assertEqual(reasoning_input.body["evidence"]["supportVector"]["eventSupport"], 1)
            self.assertNotIn("truthValue", reasoning_input.body)
            self.assertEqual(derived_index.reasoning_inputs[reasoning_input.artifact_id]["supportVector"]["occurrenceSupport"], 1)

            reasoning_run = writer.record_run(
                run_type="reasoning",
                input_event_ids=[source.event_id],
                actor_key="plr-adapter:0.1.0",
                tool={"name": "plr-adapter", "version": "0.1.0", "codeCid": "cidv0-local-sha256:" + "8" * 64},
                config={
                    "revisionPolicy": "evidence-weighted",
                    "decayPolicy": "time-decay-v0",
                    "sourceReliabilityPolicy": "support-vector-v0",
                },
                started_at="2026-06-27T14:35:03Z",
                completed_at="2026-06-27T14:35:04Z",
            )
            reasoning_output = adapter.record_output(
                reasoning_input=reasoning_input,
                reasoning_run_id=reasoning_run.artifact_id,
                truth_value={"frequency": 1.0, "confidence": 0.84},
                revision_policy="evidence-weighted",
            )

            self.assertEqual(reasoning_output.pointer["inputId"], reasoning_input.artifact_id)
            self.assertEqual(reasoning_output.pointer["evidenceOccurrenceIds"], [occurrence.artifact_id])
            self.assertNotEqual(reasoning_output.pointer["beliefStateId"], claim_id)
            self.assertNotIn("truthValue", derived_index.claims[claim_id])
            self.assertEqual(derived_index.reasoning_outputs_by_input[reasoning_input.artifact_id], [reasoning_output.artifact_id])
            self.assertEqual(
                derived_index.reasoning_outputs_for_input(reasoning_input.artifact_id)["outputIds"],
                [reasoning_output.artifact_id],
            )
            self.assertEqual(reasoning_run.pointer["extractorKey"], "")
            self.assertEqual(reasoning_run.pointer["minerKey"], "")
            self.assertEqual(reasoning_run.pointer["reasonerKey"], "plr-adapter:0.1.0")
            self.assertEqual(derived_index.by_run(reasoning_run.artifact_id)["artifactIds"], [reasoning_output.artifact_id])
            self.assertEqual(derived_index.by_reasoner("plr-adapter:0.1.0")["runIds"], [reasoning_run.artifact_id])

            reasoning_event = adapter.log_reasoning_event(
                ingestor=ingestor,
                reasoning_run=reasoning_run,
                reasoning_output=reasoning_output,
                observed_at="2026-06-27T14:35:05Z",
                parent_event_ids=[source.event_id],
            )

            self.assertIn(reasoning_event.event_id, event_index.by_kind("reasoning-run")["eventIds"])
            self.assertEqual(event_index.get_event(reasoning_event.event_id)["event"]["outputArtifactIds"], [reasoning_output.artifact_id])


if __name__ == "__main__":
    unittest.main()

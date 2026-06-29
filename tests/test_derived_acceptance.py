import tempfile
import unittest

from event_trace_memory import ArtifactWriter, DerivedArtifactIndex, EventIngestor, EventTraceIndex, FileDA


def claim_core(object_items):
    return {
        "kind": "claim",
        "schema": "claim-core-v0.1",
        "subject": {"type": "system-component", "id": "event-trace-store"},
        "predicate": {"id": "should-index-by"},
        "object": {"type": "index-set", "items": object_items},
        "modality": "normative",
        "context": {"domain": "episodic-memory-architecture"},
    }


class DerivedAcceptanceTest(unittest.TestCase):
    def test_provenance_and_dedup_acceptance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            da = FileDA(f"{temp_dir}/da")
            event_index = EventTraceIndex()
            derived_index = DerivedArtifactIndex()
            ingestor = EventIngestor(da, event_index)
            writer = ArtifactWriter(da, event_index, derived_index)

            event_one = ingestor.ingest_irc_message(
                server="libera",
                room="#chat",
                nick="alice",
                message="We should index event traces by time, actor, and channel.",
                raw=":alice!user@host PRIVMSG #chat :We should index event traces by time, actor, and channel.",
                observed_at="2026-06-27T14:35:00Z",
            )
            event_two = ingestor.ingest_irc_message(
                server="libera",
                room="#chat",
                nick="bob",
                message="Event traces should be indexed by time, actor, and channel.",
                raw=":bob!user@host PRIVMSG #chat :Event traces should be indexed by time, actor, and channel.",
                observed_at="2026-06-27T14:36:00Z",
            )
            duplicate_event = ingestor.ingest_irc_message(
                server="libera",
                room="#chat",
                nick="alice",
                message="We should index event traces by time, actor, and channel.",
                raw=":alice!user@host PRIVMSG #chat :We should index event traces by time, actor, and channel.",
                observed_at="2026-06-27T14:35:00Z",
            )

            self.assertEqual(duplicate_event.payload_cid, event_one.payload_cid)
            self.assertFalse(duplicate_event.ack["ok"])

            run = writer.record_run(
                run_type="claim-extraction",
                input_event_ids=[event_one.event_id, event_two.event_id],
                actor_key="omega-claw-claim-extractor:0.1.0",
                tool={
                    "name": "omega-claw-claim-extractor",
                    "version": "0.1.0",
                    "codeCid": "cidv0-local-sha256:" + "1" * 64,
                    "promptCid": "cidv0-local-sha256:" + "2" * 64,
                    "model": {
                        "name": "local-llm-x",
                        "version": "2026-06-01",
                        "weightsCid": "cidv0-local-sha256:" + "3" * 64,
                    },
                },
                config={"claimSchema": "claim-core-v0.1", "includeEvidenceSpans": True, "minConfidence": 0.3},
                started_at="2026-06-27T14:36:01Z",
                completed_at="2026-06-27T14:36:05Z",
            )

            core = claim_core(["time", "actor", "channel"])
            occurrence_one = writer.put_claim_occurrence(
                claim_core=core,
                source_event_id=event_one.event_id,
                extraction_run_id=run.artifact_id,
                evidence={"kind": "text-span", "span": {"start": 0, "end": 62}, "quote": event_one.envelope["value"]["preview"]},
                polarity="asserted",
                confidence=0.82,
                provenance={"extractor": "omega-claw-claim-extractor", "extractorVersion": "0.1.0"},
            )
            occurrence_two = writer.put_claim_occurrence(
                claim_core=core,
                source_event_id=event_two.event_id,
                extraction_run_id=run.artifact_id,
                evidence={"kind": "text-span", "span": {"start": 0, "end": 62}, "quote": event_two.envelope["value"]["preview"]},
                polarity="asserted",
                confidence=0.79,
                provenance={"extractor": "omega-claw-claim-extractor", "extractorVersion": "0.1.0"},
            )

            self.assertEqual(len(derived_index.claims), 1)
            self.assertNotEqual(occurrence_one.artifact_id, occurrence_two.artifact_id)
            self.assertEqual(
                derived_index.by_claim(occurrence_one.pointer["claimId"])["occurrenceIds"],
                [occurrence_one.artifact_id, occurrence_two.artifact_id],
            )
            self.assertEqual(
                derived_index.by_source_event(event_one.event_id)["claimOccurrenceIds"],
                [occurrence_one.artifact_id],
            )
            self.assertEqual(occurrence_one.pointer["sourceEventId"], event_one.event_id)
            self.assertEqual(occurrence_one.pointer["extractionRunId"], run.artifact_id)

            stored_run = derived_index.runs[run.artifact_id]
            self.assertEqual(stored_run["tool"]["codeCid"], "cidv0-local-sha256:" + "1" * 64)
            self.assertEqual(stored_run["tool"]["promptCid"], "cidv0-local-sha256:" + "2" * 64)
            self.assertEqual(stored_run["tool"]["model"]["weightsCid"], "cidv0-local-sha256:" + "3" * 64)
            self.assertEqual(stored_run["config"]["claimSchema"], "claim-core-v0.1")
            self.assertEqual(derived_index.get_run(run.artifact_id)["run"], run.pointer)
            self.assertEqual(derived_index.get_run("run:missing"), {"ok": False, "error": "not-found", "runId": "run:missing"})
            self.assertEqual(
                derived_index.get_claim(occurrence_one.pointer["claimId"])["claim"],
                derived_index.claims[occurrence_one.pointer["claimId"]],
            )
            self.assertEqual(derived_index.get_claim_occurrence(occurrence_one.artifact_id)["claimOccurrence"], occurrence_one.pointer)
            self.assertEqual(
                derived_index.by_extractor("omega-claw-claim-extractor:0.1.0")["runIds"],
                [run.artifact_id],
            )
            self.assertEqual(derived_index.by_miner("omega-claw-claim-extractor:0.1.0")["runIds"], [])
            self.assertEqual(derived_index.by_reasoner("omega-claw-claim-extractor:0.1.0")["runIds"], [])
            self.assertEqual(
                derived_index.by_run(run.artifact_id)["artifactIds"],
                [occurrence_one.artifact_id, occurrence_two.artifact_id],
            )

            feature_run = writer.record_run(
                run_type="feature-extraction",
                input_event_ids=[event_one.event_id],
                actor_key="omega-feature-extractor:0.1.0",
                tool={"name": "omega-feature-extractor", "version": "0.1.0", "codeCid": "cidv0-local-sha256:" + "4" * 64},
                config={"featureSchema": "feature-core-v0.1"},
                started_at="2026-06-27T14:36:06Z",
                completed_at="2026-06-27T14:36:07Z",
            )
            feature_occurrence = writer.put_feature_occurrence(
                feature_core={
                    "kind": "feature",
                    "schema": "feature-core-v0.1",
                    "featureType": "topic",
                    "value": {"id": "event-trace-indexing", "label": "event trace indexing"},
                },
                source_event_id=event_one.event_id,
                extraction_run_id=feature_run.artifact_id,
                confidence=0.91,
                evidence={"kind": "whole-event"},
            )

            self.assertEqual(
                derived_index.by_source_event(event_one.event_id)["featureOccurrenceIds"],
                [feature_occurrence.artifact_id],
            )
            self.assertEqual(
                derived_index.by_feature(feature_occurrence.pointer["featureId"])["occurrenceIds"],
                [feature_occurrence.artifact_id],
            )
            self.assertEqual(derived_index.get_feature(feature_occurrence.pointer["featureId"])["feature"], derived_index.features[feature_occurrence.pointer["featureId"]])
            self.assertEqual(derived_index.get_feature_occurrence(feature_occurrence.artifact_id)["featureOccurrence"], feature_occurrence.pointer)

            near_duplicate = writer.put_claim(claim_core(["actor", "channel", "time"]))
            cluster = writer.put_claim_cluster(
                relation="semantic-near-duplicate",
                members=[occurrence_one.pointer["claimId"], near_duplicate.artifact_id],
                method={"name": "embedding-llm-human-review", "version": "0.1.0"},
                confidence=0.88,
            )

            self.assertEqual(len(derived_index.claims), 2)
            self.assertIn(occurrence_one.pointer["claimId"], derived_index.claims)
            self.assertIn(near_duplicate.artifact_id, derived_index.claims)
            self.assertEqual(
                derived_index.clusters_for_claim(near_duplicate.artifact_id)["clusterIds"],
                [cluster.artifact_id],
            )
            self.assertEqual(derived_index.get_claim_cluster(cluster.artifact_id)["claimCluster"], cluster.pointer)


if __name__ == "__main__":
    unittest.main()

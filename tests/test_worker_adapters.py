import tempfile
import unittest

from event_trace_memory import (
    ArtifactWriter,
    ClaimFeatureExtractionWorker,
    DerivedArtifactIndex,
    EventTraceIndex,
    FileDA,
    IrcSourceWorker,
    MemoryQueryWorker,
    ShellActionWorker,
)
from event_trace_memory.ingestion import EventIngestor


class WorkerAdapterTest(unittest.TestCase):
    def test_worker_adapters_log_provenance_and_da_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            da = FileDA(f"{temp_dir}/da")
            event_index = EventTraceIndex()
            derived_index = DerivedArtifactIndex()
            ingestor = EventIngestor(da, event_index)
            writer = ArtifactWriter(da, event_index, derived_index)

            source = IrcSourceWorker(ingestor).ingest_message(
                server="libera",
                room="#chat",
                nick="alice",
                message="Workers should log explicit provenance.",
                raw=":alice!user@host PRIVMSG #chat :Workers should log explicit provenance.",
                observed_at="2026-06-27T14:35:00Z",
            )

            memory = MemoryQueryWorker(ingestor).record_query_result(
                query="explicit provenance",
                matches=[{"eventId": source.event_id, "score": 1}],
                observed_at="2026-06-27T14:35:01Z",
                completed_at="2026-06-27T14:35:02Z",
                parent_event_ids=[source.event_id],
            )
            self.assertEqual(event_index.by_parent(source.event_id)["eventIds"], [memory.query_event.event_id])
            self.assertEqual(event_index.by_parent(memory.query_event.event_id)["eventIds"], [memory.result_event.event_id])

            shell = ShellActionWorker(ingestor).record_action_result(
                command=["python3", "-V"],
                cwd="/workspace",
                allowlist_policy="read-only-diagnostics",
                exit_code=0,
                stdout="Python 3.11.0\n",
                stderr="",
                started_at="2026-06-27T14:35:03Z",
                completed_at="2026-06-27T14:35:04Z",
                parent_event_ids=[source.event_id],
            )
            self.assertEqual(da.get_bytes(shell.stdout_cid), b"Python 3.11.0\n")
            self.assertEqual(da.get_bytes(shell.stderr_cid), b"")
            shell_result_payload = da.get_json(shell.result_event.payload_cid)
            self.assertEqual(shell_result_payload["stdoutCid"], shell.stdout_cid)
            self.assertEqual(shell_result_payload["stderrCid"], shell.stderr_cid)
            self.assertNotIn("Python 3.11.0", str(event_index.get_event(shell.result_event.event_id)["event"]))

            extraction = ClaimFeatureExtractionWorker(ingestor, writer).record_extraction(
                input_event_ids=[source.event_id, memory.result_event.event_id, shell.result_event.event_id],
                parent_event_ids=[source.event_id],
                actor_key="omega-claw-claim-feature-extractor:0.1.0",
                tool={
                    "name": "omega-claw-claim-feature-extractor",
                    "version": "0.1.0",
                    "codeCid": "cidv0-local-sha256:" + "9" * 64,
                    "promptCid": "cidv0-local-sha256:" + "8" * 64,
                },
                config={"claimSchema": "claim-core-v0.1", "featureSchema": "feature-core-v0.1"},
                started_at="2026-06-27T14:35:05Z",
                completed_at="2026-06-27T14:35:06Z",
                claim_specs=[
                    {
                        "claimCore": {
                            "kind": "claim",
                            "schema": "claim-core-v0.1",
                            "subject": {"id": "worker-adapters"},
                            "predicate": {"id": "should-log"},
                            "object": {"items": ["provenance", "da-boundaries"]},
                        },
                        "sourceEventId": source.event_id,
                        "evidence": {"kind": "whole-event"},
                        "confidence": 0.9,
                    }
                ],
                feature_specs=[
                    {
                        "featureCore": {
                            "kind": "feature",
                            "schema": "feature-core-v0.1",
                            "featureType": "topic",
                            "value": {"id": "worker-provenance"},
                        },
                        "sourceEventId": source.event_id,
                        "evidence": {"kind": "whole-event"},
                        "confidence": 0.88,
                    }
                ],
            )

            claim_occurrence = extraction.claim_occurrences[0]
            feature_occurrence = extraction.feature_occurrences[0]
            self.assertEqual(derived_index.by_source_event(source.event_id)["claimOccurrenceIds"], [claim_occurrence.artifact_id])
            self.assertEqual(derived_index.by_source_event(source.event_id)["featureOccurrenceIds"], [feature_occurrence.artifact_id])
            self.assertEqual(
                derived_index.by_run(extraction.run.artifact_id)["artifactIds"],
                [claim_occurrence.artifact_id, feature_occurrence.artifact_id],
            )
            self.assertEqual(
                event_index.get_event(extraction.event.event_id)["event"]["outputArtifactIds"],
                [claim_occurrence.artifact_id, feature_occurrence.artifact_id],
            )
            self.assertEqual(extraction.run.pointer["tool"]["codeCid"], "cidv0-local-sha256:" + "9" * 64)
            self.assertEqual(extraction.run.pointer["tool"]["promptCid"], "cidv0-local-sha256:" + "8" * 64)


if __name__ == "__main__":
    unittest.main()

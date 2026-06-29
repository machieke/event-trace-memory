import tempfile
import unittest

from event_trace_memory import ArtifactWriter, DerivedArtifactIndex, EventIngestor, EventTraceIndex, FileDA, MemoryDA
from event_trace_memory.canonical import digest_from_cid


class DABackendTest(unittest.TestCase):
    def test_file_and_memory_da_share_cids_manifests_and_verification(self):
        value = {"kind": "example", "schema": "example-v0.1", "items": ["a", "b"]}

        with tempfile.TemporaryDirectory() as temp_dir:
            file_da = FileDA(f"{temp_dir}/da")
            memory_da = MemoryDA()

            file_cid = file_da.put_json(value)
            memory_cid = memory_da.put_json(value)

            self.assertEqual(file_cid, memory_cid)
            self.assertEqual(file_da.get_json(file_cid), value)
            self.assertEqual(memory_da.get_json(memory_cid), value)
            self.assertEqual(file_da.stat(file_cid), memory_da.stat(memory_cid))
            self.assertTrue(file_da.verify(file_cid)["ok"])
            self.assertTrue(memory_da.verify(memory_cid)["ok"])

    def test_file_da_verification_reports_corruption(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            da = FileDA(f"{temp_dir}/da")
            cid = da.put_bytes(b"original bytes", codec="text/plain")
            object_path = da.objects_dir / digest_from_cid(cid)
            object_path.write_bytes(b"corrupt bytes")

            verification = da.verify(cid)

            self.assertFalse(verification["ok"])
            self.assertIn("digest mismatch", verification["error"])
            with self.assertRaises(ValueError):
                da.get_bytes(cid)

    def test_reference_apis_accept_memory_da_backend(self):
        da = MemoryDA()
        event_index = EventTraceIndex()
        derived_index = DerivedArtifactIndex()
        ingestor = EventIngestor(da, event_index)
        writer = ArtifactWriter(da, event_index, derived_index)

        event = ingestor.ingest_irc_message(
            server="libera",
            room="#chat",
            nick="alice",
            message="memory da backend",
            raw=":alice!user@host PRIVMSG #chat :memory da backend",
            observed_at="2026-06-27T14:35:00Z",
        )
        run = writer.record_run(
            run_type="claim-extraction",
            input_event_ids=[event.event_id],
            actor_key="omega-claw-claim-extractor:0.1.0",
            tool={"name": "omega-claw-claim-extractor", "version": "0.1.0"},
            config={"claimSchema": "claim-core-v0.1"},
            started_at="2026-06-27T14:35:01Z",
            completed_at="2026-06-27T14:35:02Z",
        )
        occurrence = writer.put_claim_occurrence(
            claim_core={
                "kind": "claim",
                "schema": "claim-core-v0.1",
                "subject": {"id": "da-backend"},
                "predicate": {"id": "supports"},
                "object": {"items": ["memory", "file"]},
            },
            source_event_id=event.event_id,
            extraction_run_id=run.artifact_id,
            evidence={"kind": "whole-event"},
        )

        self.assertTrue(da.verify(event.payload_cid)["ok"])
        self.assertTrue(da.verify(event.event_cid)["ok"])
        self.assertTrue(da.verify(occurrence.cid)["ok"])
        self.assertEqual(derived_index.by_run(run.artifact_id)["artifactIds"], [occurrence.artifact_id])


if __name__ == "__main__":
    unittest.main()

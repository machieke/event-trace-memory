import tempfile
import unittest

from event_trace_memory import (
    ArtifactWriter,
    DerivedArtifactIndex,
    EventIngestor,
    EventTraceIndex,
    FileDA,
    PatternMiner,
    SnapshotBuilder,
)


class MiningAcceptanceTest(unittest.TestCase):
    def test_snapshot_and_pattern_mining_acceptance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            da = FileDA(f"{temp_dir}/da")
            event_index = EventTraceIndex()
            derived_index = DerivedArtifactIndex()
            ingestor = EventIngestor(da, event_index)
            writer = ArtifactWriter(da, event_index, derived_index)

            root = ingestor.ingest_irc_message(
                server="libera",
                room="#chat",
                nick="alice",
                message="index the event trace",
                raw=":alice!user@host PRIVMSG #chat :index the event trace",
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
                tool={"name": "omega-claw-claim-extractor", "version": "0.1.0", "codeCid": "cidv0-local-sha256:" + "5" * 64},
                config={"claimSchema": "claim-core-v0.1"},
                started_at="2026-06-27T14:35:03Z",
                completed_at="2026-06-27T14:35:04Z",
            )
            claim_occurrence = writer.put_claim_occurrence(
                claim_core={
                    "kind": "claim",
                    "schema": "claim-core-v0.1",
                    "subject": {"id": "event-trace-store"},
                    "predicate": {"id": "should-index-by"},
                    "object": {"items": ["time", "actor", "channel"]},
                },
                source_event_id=root.event_id,
                extraction_run_id=extraction_run.artifact_id,
                evidence={"kind": "whole-event"},
                confidence=0.8,
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
                output_artifact_ids=[claim_occurrence.artifact_id],
            )

            builder = SnapshotBuilder(da, event_index, derived_index)
            snapshot = builder.build_hour_snapshot("/2026/06/27/14")

            self.assertTrue(da.has(snapshot.cid))
            self.assertEqual(snapshot.manifest["sourceQuery"], {"type": "timePrefix", "prefixKey": "/2026/06/27/14"})
            self.assertFalse(snapshot.manifest["rawPayloadsScanned"])
            self.assertIn(root.event_id, snapshot.event_dictionary["eventIdToLocalId"])
            self.assertIn(claim_occurrence.artifact_id, snapshot.claim_occurrences[root.event_id])

            miner = PatternMiner(writer)
            support = miner.support_for_tokens(
                snapshot,
                ["event.kind:message", "channel:/irc/libera/channel/%23chat"],
            )
            self.assertEqual(support.strategy, "set-intersection")
            self.assertEqual(support.event_ids, [root.event_id])

            mining_run = writer.record_run(
                run_type="pattern-mining",
                input_event_ids=[],
                input_snapshot_cids=[snapshot.cid],
                actor_key="omega-sequence-miner:0.1.0",
                tool={"name": "omega-sequence-miner", "version": "0.1.0", "codeCid": "cidv0-local-sha256:" + "6" * 64},
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

            self.assertIsNotNone(mined)
            assert mined is not None
            self.assertEqual(mined.support_vector["rootTraceSupport"], 1)
            self.assertEqual(mined.support_vector["eventSupport"], 4)
            self.assertEqual(mining_run.pointer["extractorKey"], "")
            self.assertEqual(mining_run.pointer["minerKey"], "omega-sequence-miner:0.1.0")
            self.assertEqual(mining_run.pointer["reasonerKey"], "")
            self.assertEqual(derived_index.patterns[mined.pattern.artifact_id]["inputSnapshotCids"], [snapshot.cid])
            self.assertEqual(derived_index.patterns[mined.pattern.artifact_id]["minedBy"], mining_run.artifact_id)
            self.assertEqual(derived_index.by_miner("omega-sequence-miner:0.1.0")["runIds"], [mining_run.artifact_id])
            self.assertEqual(derived_index.get_pattern(mined.pattern.artifact_id)["pattern"], mined.pattern.pointer)
            self.assertEqual(derived_index.by_pattern_type("sequence")["patternIds"], [mined.pattern.artifact_id])
            self.assertEqual(derived_index.by_pattern_input_snapshot(snapshot.cid)["patternIds"], [mined.pattern.artifact_id])
            self.assertEqual(derived_index.by_pattern_miner("omega-sequence-miner:0.1.0")["patternIds"], [mined.pattern.artifact_id])
            self.assertEqual(derived_index.by_pattern_miner("")["patternIds"], [])
            self.assertEqual(derived_index.by_pattern(mined.pattern.artifact_id)["occurrenceIds"], [mined.occurrences[0].artifact_id])
            self.assertEqual(
                derived_index.get_pattern_occurrence(mined.occurrences[0].artifact_id)["patternOccurrence"],
                mined.occurrences[0].pointer,
            )
            self.assertEqual(derived_index.by_pattern_root(root.event_id)["occurrenceIds"], [mined.occurrences[0].artifact_id])
            self.assertEqual(
                derived_index.pattern_occurrences[mined.occurrences[0].artifact_id]["participatingEventIds"],
                [root.event_id, memory_query.event_id, shell_action.event_id, extraction_event.event_id],
            )
            self.assertIn(
                claim_occurrence.artifact_id,
                derived_index.pattern_occurrences[mined.occurrences[0].artifact_id]["participatingClaimOccurrenceIds"],
            )

            discovery_event = miner.log_pattern_discovery_event(
                ingestor=ingestor,
                mining_run=mining_run,
                mined_pattern=mined,
                observed_at="2026-06-27T15:00:08Z",
                parent_event_ids=[root.event_id],
            )
            self.assertIn(discovery_event.event_id, event_index.by_kind("pattern-discovery")["eventIds"])
            self.assertEqual(
                event_index.get_event(discovery_event.event_id)["event"]["outputArtifactIds"],
                [mined.pattern.artifact_id, mined.occurrences[0].artifact_id],
            )

            later = ingestor.ingest_irc_message(
                server="libera",
                room="#chat",
                nick="alice",
                message="new hour",
                raw=":alice!user@host PRIVMSG #chat :new hour",
                observed_at="2026-06-27T15:00:00Z",
            )
            self.assertEqual(SnapshotBuilder.affected_shard_paths(later.pointer), ["/2026/06/27/15"])
            rebuilt_snapshot = builder.build_hour_snapshot("/2026/06/27/14")
            self.assertNotIn(later.event_id, rebuilt_snapshot.event_dictionary["eventIdToLocalId"])


if __name__ == "__main__":
    unittest.main()

import unittest

from event_trace_memory import (
    ArtifactWriter,
    DerivedArtifactIndex,
    EventIngestor,
    EventTraceIndex,
    MemoryDA,
    PatternMiner,
    ReasoningAdapter,
    SnapshotBuilder,
)


class AdvancedMiningReasoningTest(unittest.TestCase):
    def test_itemset_and_parent_child_motif_mining(self):
        da = MemoryDA()
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
        ingestor.log_child_event(
            raw_payload={"kind": "shell-action", "action": "read", "observedAt": "2026-06-27T14:35:02Z"},
            observed_at="2026-06-27T14:35:02Z",
            actor_path=["agent", "omega-claw", "shell-worker"],
            channel_path=["system", "shell", "filesystem", "read"],
            value_kind="shell-action-start",
            parent_event_ids=[root.event_id],
        )
        extraction_run = writer.record_run(
            run_type="claim-extraction",
            input_event_ids=[root.event_id],
            actor_key="omega-claw-claim-extractor:0.1.0",
            tool={
                "name": "omega-claw-claim-extractor",
                "version": "0.1.0",
                "codeCid": "cidv0-local-sha256:" + "a" * 64,
            },
            config={"claimSchema": "claim-core-v0.1"},
            started_at="2026-06-27T14:35:03Z",
            completed_at="2026-06-27T14:35:04Z",
        )
        claim_occurrence = writer.put_claim_occurrence(
            claim_core={
                "kind": "claim",
                "schema": "claim-core-v0.1",
                "subject": {"id": "event-trace-store"},
                "predicate": {"id": "indexable-by"},
                "object": {"items": ["time", "actor", "channel"]},
            },
            source_event_id=root.event_id,
            extraction_run_id=extraction_run.artifact_id,
            evidence={"kind": "whole-event"},
            confidence=0.8,
        )

        snapshot = SnapshotBuilder(da, event_index, derived_index).build_hour_snapshot("/2026/06/27/14")
        mining_run = writer.record_run(
            run_type="pattern-mining",
            input_event_ids=[],
            input_snapshot_cids=[snapshot.cid],
            actor_key="omega-advanced-miner:0.1.0",
            tool={
                "name": "omega-advanced-miner",
                "version": "0.1.0",
                "codeCid": "cidv0-local-sha256:" + "b" * 64,
            },
            config={"minSupport": 1, "supportUnit": "event-or-edge"},
            started_at="2026-06-27T15:00:00Z",
            completed_at="2026-06-27T15:00:07Z",
        )

        miner = PatternMiner(writer)
        itemset = miner.mine_itemset(
            snapshot=snapshot,
            tokens=["event.kind:message", "channel:/irc/libera/channel/%23chat"],
            mining_run_id=mining_run.artifact_id,
            miner_key="omega-advanced-miner:0.1.0",
        )

        self.assertIsNotNone(itemset)
        assert itemset is not None
        self.assertEqual(itemset.pattern.body["patternType"], "itemset")
        self.assertEqual(itemset.support_vector["itemsetSupport"], 1)
        self.assertEqual(itemset.support_vector["rootTraceSupport"], 1)
        self.assertEqual(
            derived_index.by_pattern(itemset.pattern.artifact_id)["occurrenceIds"],
            [itemset.occurrences[0].artifact_id],
        )
        self.assertEqual(itemset.occurrences[0].pointer["participatingEventIds"], [root.event_id])
        self.assertEqual(
            itemset.occurrences[0].pointer["participatingClaimOccurrenceIds"],
            [claim_occurrence.artifact_id],
        )

        motif = miner.mine_parent_child_motif(
            snapshot=snapshot,
            parent_kind="message",
            child_kind="memory-query-start",
            mining_run_id=mining_run.artifact_id,
            miner_key="omega-advanced-miner:0.1.0",
        )

        self.assertIsNotNone(motif)
        assert motif is not None
        self.assertEqual(motif.pattern.body["patternType"], "graph-motif")
        self.assertEqual(motif.support_vector["edgeSupport"], 1)
        self.assertEqual(motif.support_vector["rootTraceSupport"], 1)
        self.assertEqual(
            motif.occurrences[0].pointer["participatingEventIds"],
            [root.event_id, memory_query.event_id],
        )
        self.assertEqual(derived_index.patterns_by_type["itemset"], [itemset.pattern.artifact_id])
        self.assertEqual(derived_index.patterns_by_type["graph-motif"], [motif.pattern.artifact_id])

    def test_belief_revision_history_records_ordered_reasoning_states(self):
        da = MemoryDA()
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
            tool={
                "name": "omega-claw-claim-extractor",
                "version": "0.1.0",
                "codeCid": "cidv0-local-sha256:" + "c" * 64,
            },
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
            evidence={"kind": "whole-event"},
            confidence=0.84,
        )
        claim_id = occurrence.pointer["claimId"]
        reasoning_input = adapter.build_input(
            claim_id=claim_id,
            statement_text="<event-trace-store --> indexable-by-time-actor-channel>",
            derived_from_patterns=[],
        )
        first_run = writer.record_run(
            run_type="reasoning",
            input_event_ids=[source.event_id],
            actor_key="plr-adapter:0.1.0",
            tool={
                "name": "plr-adapter",
                "version": "0.1.0",
                "codeCid": "cidv0-local-sha256:" + "d" * 64,
            },
            config={"revisionPolicy": "evidence-weighted"},
            started_at="2026-06-27T14:35:03Z",
            completed_at="2026-06-27T14:35:04Z",
        )
        second_run = writer.record_run(
            run_type="reasoning",
            input_event_ids=[source.event_id],
            actor_key="plr-adapter:0.1.0",
            tool={
                "name": "plr-adapter",
                "version": "0.1.0",
                "codeCid": "cidv0-local-sha256:" + "e" * 64,
            },
            config={"revisionPolicy": "evidence-weighted"},
            started_at="2026-06-27T14:36:03Z",
            completed_at="2026-06-27T14:36:04Z",
        )
        first_output = adapter.record_output(
            reasoning_input=reasoning_input,
            reasoning_run_id=first_run.artifact_id,
            truth_value={"frequency": 1.0, "confidence": 0.7},
            revision_policy="evidence-weighted",
        )
        second_output = adapter.record_output(
            reasoning_input=reasoning_input,
            reasoning_run_id=second_run.artifact_id,
            truth_value={"frequency": 1.0, "confidence": 0.9},
            revision_policy="evidence-weighted",
        )

        history = adapter.record_revision_history(
            claim_id=claim_id,
            reasoning_outputs=[first_output, second_output],
            revision_policy="evidence-weighted",
        )

        self.assertEqual(history.body["kind"], "belief-revision-history")
        self.assertEqual(history.body["schema"], "belief-revision-history-v0.1")
        self.assertEqual(
            [state["outputId"] for state in history.body["states"]],
            [first_output.artifact_id, second_output.artifact_id],
        )
        self.assertEqual(history.body["states"][1]["truthValue"]["confidence"], 0.9)
        self.assertEqual(history.pointer["outputIds"], [first_output.artifact_id, second_output.artifact_id])
        self.assertEqual(da.get_json(history.cid), history.body)
        self.assertEqual(
            derived_index.belief_histories_by_claim(claim_id)["historyIds"],
            [history.artifact_id],
        )
        self.assertEqual(
            derived_index.belief_histories_by_output(second_output.artifact_id)["historyIds"],
            [history.artifact_id],
        )
        self.assertEqual(
            derived_index.put_belief_revision_history(history.pointer),
            {"ok": True, "duplicate": True, "historyId": history.artifact_id},
        )

        other_claim_output = dict(second_output.body)
        other_claim_output["claimId"] = "claim:other"
        conflicting_output = second_output.__class__(
            second_output.artifact_id,
            second_output.cid,
            other_claim_output,
            second_output.pointer,
            second_output.ack,
        )
        with self.assertRaises(ValueError):
            adapter.record_revision_history(
                claim_id=claim_id,
                reasoning_outputs=[first_output, conflicting_output],
                revision_policy="evidence-weighted",
            )


if __name__ == "__main__":
    unittest.main()

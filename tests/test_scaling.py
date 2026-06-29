import unittest

from event_trace_memory import (
    DerivedArtifactIndex,
    EventIngestor,
    EventTraceIndex,
    MemoryDA,
    ScalingThresholds,
    SnapshotBuilder,
    compact_snapshot_postings,
    compress_postings,
    decompress_postings,
    measure_event_index,
    measure_snapshot,
    recommend_sharding,
)


class ScalingTest(unittest.TestCase):
    def test_scale_metrics_and_sharding_recommendations(self):
        da = MemoryDA()
        event_index = EventTraceIndex()
        derived_index = DerivedArtifactIndex()
        ingestor = EventIngestor(da, event_index)

        first = ingestor.ingest_irc_message(
            server="libera",
            room="#chat",
            nick="alice",
            message="first",
            raw=":alice!user@host PRIVMSG #chat :first",
            observed_at="2026-06-27T14:35:00Z",
        )
        second = ingestor.log_child_event(
            raw_payload={"kind": "memory-query", "query": "first"},
            observed_at="2026-06-27T14:35:01Z",
            actor_path=["agent", "omega-claw", "memory-worker"],
            channel_path=["system", "memory", "long-term", "query"],
            value_kind="memory-query-start",
            parent_event_ids=[first.event_id],
        )
        snapshot = SnapshotBuilder(da, event_index, derived_index).build_hour_snapshot("/2026/06/27/14")

        event_metrics = measure_event_index(event_index)
        snapshot_metrics = measure_snapshot(snapshot)

        self.assertEqual(event_metrics.events, 2)
        self.assertGreater(event_metrics.total_index_entries, 0)
        self.assertEqual(snapshot_metrics.events, 2)
        self.assertGreater(snapshot_metrics.posting_entries, 0)

        default_recommendation = recommend_sharding(event_metrics, snapshot_metrics)
        forced_recommendation = recommend_sharding(
            event_metrics,
            snapshot_metrics,
            ScalingThresholds(
                max_events_per_contract=1,
                max_index_entries_per_contract=1,
                max_posting_entries_per_snapshot=1,
            ),
        )

        self.assertFalse(default_recommendation.recommended)
        self.assertTrue(forced_recommendation.recommended)
        self.assertEqual(
            forced_recommendation.reasons,
            ["event-count", "index-entry-count", "snapshot-posting-entry-count"],
        )

        compacted = compact_snapshot_postings(snapshot)
        self.assertEqual(compacted["sourceSnapshotCid"], snapshot.cid)
        self.assertEqual(decompress_postings(compacted), {key: sorted(values) for key, values in snapshot.postings.items()})
        self.assertEqual(second.pointer["rootEventId"], first.event_id)

    def test_posting_compression_sorts_deduplicates_and_round_trips(self):
        postings = {
            "event.kind:message": [3, 1, 1, 2],
            "actor:/irc/libera/user/alice": [10, 7],
        }

        compressed = compress_postings(postings)

        self.assertEqual(compressed["schema"], "delta-postings-v0.1")
        self.assertEqual(compressed["postings"]["event.kind:message"], [1, 1, 1])
        self.assertEqual(decompress_postings(compressed), {
            "actor:/irc/libera/user/alice": [7, 10],
            "event.kind:message": [1, 2, 3],
        })

    def test_unknown_posting_encoding_is_rejected(self):
        with self.assertRaises(ValueError):
            decompress_postings({"encoding": "unknown", "postings": {}})


if __name__ == "__main__":
    unittest.main()

import unittest

from event_trace_memory import (
    EventIngestor,
    EventTraceIndex,
    MemoryDA,
    PrivacyAwareIngestor,
    PrivacyPolicyError,
    PublicIndexPolicy,
)


class PrivacyPolicyTest(unittest.TestCase):
    def test_private_event_is_rejected_from_public_index(self):
        da = MemoryDA()
        index = EventTraceIndex()
        ingestor = PrivacyAwareIngestor(EventIngestor(da, index))

        with self.assertRaises(PrivacyPolicyError):
            ingestor.ingest_public_event(
                raw_payload={
                    "kind": "raw-payload",
                    "schema": "raw-irc-v0.1",
                    "privacy": "private",
                    "message": "do not index this publicly",
                },
                observed_at="2026-06-27T14:35:00Z",
                actor_path=["irc", "libera", "user", "alice"],
                channel_path=["irc", "libera", "channel", "#private"],
                value_kind="message",
            )

        self.assertEqual(index.state_stats()["events"], 0)
        self.assertEqual(da.objects, {})

    def test_public_event_is_accepted_with_privacy_provenance(self):
        da = MemoryDA()
        index = EventTraceIndex()
        ingestor = PrivacyAwareIngestor(EventIngestor(da, index))

        event = ingestor.ingest_public_event(
            raw_payload={
                "kind": "raw-payload",
                "schema": "raw-irc-v0.1",
                "privacy": "public",
                "message": "index this publicly",
            },
            observed_at="2026-06-27T14:35:00Z",
            actor_path=["irc", "libera", "user", "alice"],
            channel_path=["irc", "libera", "channel", "#chat"],
            value_kind="message",
        )

        self.assertTrue(event.ack["ok"])
        self.assertEqual(index.by_actor_prefix("/irc/libera/user/alice")["eventIds"], [event.event_id])
        self.assertTrue(event.envelope["provenance"]["privacy"]["publicIndexAllowed"])

    def test_hashed_path_event_does_not_leak_clear_segments_in_public_index(self):
        da = MemoryDA()
        index = EventTraceIndex()
        policy = PublicIndexPolicy(hash_salt="test-salt")
        ingestor = PrivacyAwareIngestor(EventIngestor(da, index), policy)

        event = ingestor.ingest_hashed_path_event(
            raw_payload={
                "kind": "encrypted-payload",
                "schema": "encrypted-payload-v0.1",
                "privacy": "private",
                "ciphertextCid": "cidv0-local-sha256:" + "1" * 64,
            },
            observed_at="2026-06-27T14:35:00Z",
            actor_path=["irc", "libera", "user", "alice"],
            channel_path=["irc", "libera", "channel", "#private"],
            value_kind="encrypted-message",
        )
        pointer = index.get_event(event.event_id)["event"]
        hashed_actor_path = policy.hash_path(["irc", "libera", "user", "alice"])

        self.assertTrue(event.ack["ok"])
        self.assertEqual(pointer["actorPath"], hashed_actor_path)
        self.assertTrue(all(segment.startswith("hash-sha256:") for segment in pointer["actorPath"]))
        self.assertNotIn("alice", str(pointer))
        self.assertNotIn("#private", str(pointer))
        self.assertEqual(index.by_actor_prefix("/irc/libera/user/alice")["eventIds"], [])
        self.assertEqual(index.by_actor_prefix(pointer["actorPrefixKeys"][-1])["eventIds"], [event.event_id])
        self.assertEqual(event.envelope["provenance"]["privacy"]["pathMode"], "hashed")


if __name__ == "__main__":
    unittest.main()

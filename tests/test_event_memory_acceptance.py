import tempfile
import unittest

from event_trace_memory import EventIngestor, EventTraceIndex, FileDA


class EventMemoryAcceptanceTest(unittest.TestCase):
    def test_event_index_postings_are_unique_for_repeated_pointer_keys(self):
        index = EventTraceIndex()
        pointer = {
            "kind": "event-pointer",
            "schema": "event-pointer-v0.1",
            "eventId": "event:repeated-keys",
            "eventCid": "cid:event-repeated-keys",
            "payloadCid": "cid:payload-repeated-keys",
            "timePrefixKeys": ["/2026", "/2026", "/2026/06"],
            "actorPrefixKeys": ["/irc", "/irc", "/irc/libera"],
            "channelPrefixKeys": ["/irc", "/irc", "/irc/libera"],
            "valueKind": "message",
            "parentEventIds": ["event:root", "event:root"],
            "rootEventId": "event:root",
        }

        self.assertEqual(
            index.put_event(pointer),
            {
                "ok": True,
                "eventId": "event:repeated-keys",
                "eventCid": "cid:event-repeated-keys",
                "payloadCid": "cid:payload-repeated-keys",
            },
        )
        self.assertEqual(index.by_time_prefix("/2026")["eventIds"], ["event:repeated-keys"])
        self.assertEqual(index.by_actor_prefix("/irc")["eventIds"], ["event:repeated-keys"])
        self.assertEqual(index.by_channel_prefix("/irc")["eventIds"], ["event:repeated-keys"])
        self.assertEqual(index.by_parent("event:root")["eventIds"], ["event:repeated-keys"])

    def test_event_memory_acceptance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            da = FileDA(f"{temp_dir}/da")
            index = EventTraceIndex()
            ingestor = EventIngestor(da, index)

            root = ingestor.ingest_irc_message(
                server="libera",
                room="#chat",
                nick="alice",
                message="hello world",
                raw=":alice!user@host PRIVMSG #chat :hello world",
                observed_at="2026-06-27T14:35:00Z",
            )

            self.assertTrue(root.ack["ok"])
            self.assertTrue(da.has(root.payload_cid))
            self.assertTrue(da.has(root.event_cid))
            self.assertEqual(da.get_json(root.payload_cid)["message"], "hello world")
            self.assertEqual(da.get_json(root.event_cid)["value"]["payloadCid"], root.payload_cid)

            stored = index.get_event(root.event_id)
            self.assertTrue(stored["ok"])
            self.assertEqual(stored["event"]["eventCid"], root.event_cid)
            self.assertNotIn("hello world", str(stored["event"]))

            duplicate = index.put_event(root.pointer)
            self.assertEqual(
                duplicate,
                {
                    "ok": False,
                    "error": "duplicate-event-id",
                    "eventId": root.event_id,
                },
            )
            duplicate_cid_pointer = dict(root.pointer)
            duplicate_cid_pointer["eventId"] = "event:duplicate-cid"
            self.assertEqual(
                index.put_event(duplicate_cid_pointer),
                {
                    "ok": False,
                    "error": "duplicate-event-cid",
                    "eventCid": root.event_cid,
                    "eventId": root.event_id,
                },
            )
            self.assertEqual(
                index.state_stats(),
                {
                    "events": 1,
                    "timeKeys": 4,
                    "actorKeys": 4,
                    "channelKeys": 4,
                    "kindKeys": 1,
                    "parentKeys": 0,
                    "rootKeys": 1,
                    "payloadKeys": 1,
                    "eventCidKeys": 1,
                },
            )

            self.assertEqual(index.by_time_prefix("/2026/06/27/14")["eventIds"], [root.event_id])
            self.assertEqual(index.by_actor_prefix("/irc/libera/user/alice")["eventIds"], [root.event_id])
            self.assertEqual(index.by_channel_prefix("/irc/libera/channel/%23chat")["eventIds"], [root.event_id])
            self.assertEqual(index.by_payload_cid(root.payload_cid)["eventIds"], [root.event_id])
            self.assertEqual(
                index.by_event_cid(root.event_cid),
                {"ok": True, "eventCid": root.event_cid, "eventId": root.event_id},
            )
            self.assertEqual(
                index.by_event_cid("cidv0-local-sha256:" + "0" * 64),
                {"ok": False, "error": "not-found", "eventCid": "cidv0-local-sha256:" + "0" * 64},
            )

            memory_query = ingestor.log_child_event(
                raw_payload={
                    "kind": "memory-query",
                    "query": "hello world",
                    "observedAt": "2026-06-27T14:35:01Z",
                },
                observed_at="2026-06-27T14:35:01Z",
                actor_path=["agent", "omega-claw", "memory-query-worker"],
                channel_path=["system", "memory", "long-term", "query"],
                value_kind="memory-query-start",
                parent_event_ids=[root.event_id],
            )
            shell_action = ingestor.log_child_event(
                raw_payload={
                    "kind": "shell-action",
                    "action": "read",
                    "path": "event-trace-memory-full-implementation-plan.md",
                    "observedAt": "2026-06-27T14:35:02Z",
                },
                observed_at="2026-06-27T14:35:02Z",
                actor_path=["agent", "omega-claw", "shell-worker"],
                channel_path=["system", "shell", "filesystem", "read"],
                value_kind="shell-action-start",
                parent_event_ids=[root.event_id],
            )
            memory_result = ingestor.log_child_event(
                raw_payload={
                    "kind": "memory-query-result",
                    "matches": [],
                    "observedAt": "2026-06-27T14:35:03Z",
                },
                observed_at="2026-06-27T14:35:03Z",
                actor_path=["agent", "omega-claw", "memory-query-worker"],
                channel_path=["system", "memory", "long-term", "result"],
                value_kind="memory-query-result",
                parent_event_ids=[memory_query.event_id],
            )

            self.assertEqual(index.by_parent(root.event_id)["eventIds"], [memory_query.event_id, shell_action.event_id])
            self.assertEqual(index.by_parent(memory_query.event_id)["eventIds"], [memory_result.event_id])
            self.assertEqual(
                index.by_root(root.event_id)["eventIds"],
                [
                    root.event_id,
                    memory_query.event_id,
                    shell_action.event_id,
                    memory_result.event_id,
                ],
            )


if __name__ == "__main__":
    unittest.main()

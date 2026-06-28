import tempfile
import unittest
from pathlib import Path

from event_trace_memory.fixture_flow import EXPECTED_COVERAGE, load_fixture_corpus, run_fixture_corpus


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "minimum-corpus-v0.1.json"


class FixtureCorpusTest(unittest.TestCase):
    def test_minimum_fixture_corpus_covers_plan_items(self):
        corpus = load_fixture_corpus(FIXTURE_PATH)

        self.assertEqual(corpus["kind"], "event-trace-memory-fixture-corpus")
        self.assertEqual(corpus["schema"], "fixture-corpus-v0.1")
        self.assertEqual(corpus["covers"], EXPECTED_COVERAGE)

    def test_minimum_fixture_corpus_executes_reference_flow(self):
        corpus = load_fixture_corpus(FIXTURE_PATH)

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = run_fixture_corpus(corpus, f"{temp_dir}/da")

        self.assertTrue(summary["ok"])
        self.assertTrue(all(summary["checks"].values()), summary["checks"])
        self.assertFalse(summary["events"]["duplicateAccepted"])
        self.assertEqual(summary["derivedArtifacts"]["claimCount"], 2)
        self.assertEqual(summary["snapshot"]["shardPath"], "/2026/06/27/14")
        self.assertEqual(summary["pattern"]["supportVector"]["rootTraceSupport"], 1)
        self.assertEqual(len(summary["reasoning"]["positiveOccurrences"]), 2)


if __name__ == "__main__":
    unittest.main()

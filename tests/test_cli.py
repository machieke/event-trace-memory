import io
import json
import tempfile
import unittest
from pathlib import Path

from event_trace_memory.cli import main


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "minimum-corpus-v0.1.json"


class CliTest(unittest.TestCase):
    def test_fixture_summary_outputs_coverage_json(self):
        stdout = io.StringIO()
        exit_code = main(
            ["fixture-summary", "--fixture", str(FIXTURE_PATH)],
            stdout=stdout,
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["coverageComplete"])
        self.assertEqual(payload["kind"], "event-trace-memory-fixture-corpus")

    def test_run_fixture_outputs_end_to_end_summary(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code = main(
                [
                    "run-fixture",
                    "--fixture",
                    str(FIXTURE_PATH),
                    "--da-root",
                    f"{temp_dir}/da",
                ],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["ephemeralDaRoot"])
        self.assertTrue(all(payload["checks"].values()), payload["checks"])
        self.assertIn("patternId", payload["pattern"])
        self.assertIn("outputId", payload["reasoning"])


if __name__ == "__main__":
    unittest.main()

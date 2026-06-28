import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "event-trace-memory-full-implementation-plan.md"
ADR = ROOT / "docs" / "decisions" / "0001-mvp-operational-policies.md"


class DesignDecisionTest(unittest.TestCase):
    def test_plan_section_23_records_resolved_mvp_decisions(self):
        section = section_between(
            PLAN.read_text(encoding="utf-8"),
            "## 23. Resolved MVP design decisions",
            "## 24. Relationship to Rholang/RSpace execution",
        )

        self.assertNotIn("Decide whether", section)
        self.assertNotIn("MVP recommendation", section)
        self.assertIn("docs/decisions/0001-mvp-operational-policies.md", section)

        for heading in [
            "### 23.1 On-chain prefix expansion",
            "### 23.2 Contract sharding",
            "### 23.3 Private events",
            "### 23.4 Semantic dedup policy",
        ]:
            with self.subTest(heading=heading):
                subsection = section_from_heading(section, heading)
                self.assertIn("Decision:", subsection)

    def test_mvp_operational_policy_adr_is_accepted(self):
        source = ADR.read_text(encoding="utf-8")

        self.assertIn("Status: Accepted", source)
        self.assertIn("Prefix keys are computed off-chain", source)
        self.assertIn("one `EventTraceIndex` contract and one `DerivedArtifactIndex`", source)
        self.assertIn("not indexed in public contracts", source)
        self.assertIn("Semantic near-duplicates are represented by reversible cluster", source)


def section_between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def section_from_heading(source: str, heading: str) -> str:
    tail = source.split(heading, 1)[1]
    marker = "\n### "
    if marker in tail:
        return tail.split(marker, 1)[0]
    return tail


if __name__ == "__main__":
    unittest.main()

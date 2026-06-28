import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


class RholangContractsTest(unittest.TestCase):
    def test_event_trace_index_contract_api(self):
        source = (CONTRACTS / "EventTraceIndex.rho").read_text(encoding="utf-8")

        for method in [
            "putEvent",
            "getEvent",
            "byTimePrefix",
            "byActorPrefix",
            "byChannelPrefix",
            "byKind",
            "byParent",
            "byRoot",
            "byPayloadCid",
            "byEventCid",
            "getStateStats",
        ]:
            self.assertRegex(source, rf'contract\s+eventTraceIndex\(@"{method}"')

        for state_key in [
            "events",
            "timeIndex",
            "actorIndex",
            "channelIndex",
            "kindIndex",
            "parentIndex",
            "rootIndex",
            "payloadIndex",
            "eventCidIndex",
        ]:
            self.assertIn(f'"{state_key}"', source)

        self.assertIn("duplicate-event-id", source)
        self.assertIn("insertArbitrary!(bundle+{*eventTraceIndex}", source)

    def test_derived_artifact_index_contract_api(self):
        source = (CONTRACTS / "DerivedArtifactIndex.rho").read_text(encoding="utf-8")

        for method in [
            "putRun",
            "putClaim",
            "putClaimOccurrence",
            "putClaimCluster",
            "putFeature",
            "putFeatureOccurrence",
            "putPattern",
            "putPatternOccurrence",
            "putReasoningInput",
            "putReasoningOutput",
            "bySourceEvent",
            "byClaim",
            "byFeature",
            "byRun",
            "byExtractor",
            "byMiner",
            "byReasoner",
            "byPattern",
            "byPatternRoot",
            "clustersForClaim",
            "reasoningOutputsByInput",
            "getStateStats",
        ]:
            self.assertRegex(source, rf'contract\s+derivedArtifactIndex\(@"{method}"')

        for state_key in [
            "runs",
            "claims",
            "claimOccurrences",
            "claimClusters",
            "features",
            "featureOccurrences",
            "patterns",
            "patternOccurrences",
            "reasoningInputs",
            "reasoningOutputs",
            "occurrencesByClaim",
            "occurrencesBySourceEvent",
            "patternsByInputSnapshot",
            "reasoningOutputsByInput",
        ]:
            self.assertIn(f'"{state_key}"', source)

        self.assertIn("insertArbitrary!(bundle+{*derivedArtifactIndex}", source)

    def test_contracts_are_not_plan_placeholders(self):
        for path in sorted(CONTRACTS.glob("*.rho")):
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, re.compile(r"\bTODO\b|pseudocode|appendAll", re.IGNORECASE))
            self.assertIn("stateCh!", source)
            self.assertIn("return!", source)
            source.encode("ascii")

    def test_runtime_validation_script_exists(self):
        script = ROOT / "scripts" / "validate_rholang_contracts.sh"
        source = script.read_text(encoding="utf-8")
        self.assertIn("f1r3flyindustries/f1r3fly-rust-node:latest", source)
        self.assertIn("EventTraceIndex.rho", source)
        self.assertIn("DerivedArtifactIndex.rho", source)
        self.assertIn("/opt/docker/bin/node eval", source)


if __name__ == "__main__":
    unittest.main()

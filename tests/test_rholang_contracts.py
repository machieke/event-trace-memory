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
        self.assertIn('@"event-trace-memory:EventTraceIndexUri"!(uri)', source)

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
            "putBeliefRevisionHistory",
            "getRun",
            "getClaim",
            "getClaimOccurrence",
            "getClaimCluster",
            "getFeature",
            "getFeatureOccurrence",
            "getPattern",
            "getPatternOccurrence",
            "getReasoningInput",
            "getReasoningOutput",
            "getBeliefRevisionHistory",
            "bySourceEvent",
            "runsByInputEvent",
            "runsByOutputArtifact",
            "byClaim",
            "claimsBySubject",
            "claimsByPredicate",
            "claimsByObject",
            "byFeature",
            "featuresByType",
            "byRun",
            "byExtractor",
            "byMiner",
            "byReasoner",
            "byPattern",
            "byPatternRoot",
            "patternsByType",
            "patternsByInputSnapshot",
            "patternsByMiner",
            "clustersForClaim",
            "reasoningOutputsByInput",
            "reasoningOutputsByClaim",
            "reasoningOutputsByRun",
            "beliefHistoriesByClaim",
            "beliefHistoriesByOutput",
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
            "beliefRevisionHistories",
            "occurrencesByClaim",
            "occurrencesBySourceEvent",
            "claimsBySubject",
            "claimsByPredicate",
            "claimsByObject",
            "featuresByType",
            "runsByInputEvent",
            "runsByOutputArtifact",
            "patternsByInputSnapshot",
            "patternsByType",
            "patternsByMiner",
            "reasoningOutputsByInput",
            "reasoningOutputsByClaim",
            "reasoningOutputsByRun",
            "beliefRevisionHistoriesByClaim",
            "beliefRevisionHistoriesByOutput",
        ]:
            self.assertIn(f'"{state_key}"', source)

        self.assertIn("insertArbitrary!(bundle+{*derivedArtifactIndex}", source)
        self.assertIn("appendOptionalOne", source)
        self.assertIn('if (key == "")', source)
        self.assertIn('@"event-trace-memory:DerivedArtifactIndexUri"!(uri)', source)

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
        self.assertIn("/opt/docker/bin/node eval --print-unmatched-sends-only", source)
        self.assertIn("EventTraceIndexSmoke.rho", source)
        self.assertIn("DerivedArtifactIndexSmoke.rho", source)
        self.assertIn("claim-occ:smoke-1", source)
        self.assertIn("--validator-private-key", source)
        self.assertIn("/opt/docker/bin/node deploy", source)
        self.assertIn("/opt/docker/bin/node propose --print-unmatched-sends", source)
        self.assertIn("/opt/docker/bin/node data-at-name", source)
        self.assertIn("EventTraceIndexDeploySmoke.rho", source)
        self.assertIn("DerivedArtifactIndexDeploySmoke.rho", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:event:deploy-smoke-1", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:getEvent", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:byActorPrefix", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:byChannelPrefix", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:byKind", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:byParent", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:byRoot", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:byPayloadCid", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:byEventCid", source)
        self.assertIn("EventTraceIndexDeploySmokeOk:getStateStats", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:claim-occ:deploy-smoke-1", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getRun", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getClaim", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getClaimOccurrence", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getClaimCluster", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getFeature", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getFeatureOccurrence", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getPattern", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getPatternOccurrence", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getReasoningInput", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getReasoningOutput", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getBeliefRevisionHistory", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:bySourceEvent", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:runsByInputEvent", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:runsByOutputArtifact", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:claimsBySubject", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:claimsByPredicate", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:claimsByObject", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:byFeature", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:featuresByType", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:byRun", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:byExtractor", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:byMiner", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:byReasoner", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:byPattern", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:byPatternRoot", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:patternsByType", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:patternsByInputSnapshot", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:patternsByMiner", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:clustersForClaim", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:reasoningOutputsByInput", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:reasoningOutputsByClaim", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:reasoningOutputsByRun", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:beliefHistoriesByClaim", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:beliefHistoriesByOutput", source)
        self.assertIn("DerivedArtifactIndexDeploySmokeOk:getStateStats", source)


if __name__ == "__main__":
    unittest.main()

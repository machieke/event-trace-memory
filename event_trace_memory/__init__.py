"""Reference implementation for event trace memory."""

from event_trace_memory.canonical import canonical_json_bytes, cid_for_bytes, content_id
from event_trace_memory.artifacts import ArtifactWriter
from event_trace_memory.da import DAStore, FileDA, MemoryDA
from event_trace_memory.fixture_flow import load_fixture_corpus, run_fixture_corpus
from event_trace_memory.indexes import DerivedArtifactIndex, EventTraceIndex
from event_trace_memory.ingestion import EventIngestor
from event_trace_memory.mining import PatternMiner
from event_trace_memory.privacy import (
    PrivacyAwareIngestor,
    PrivacyPolicyError,
    PublicIndexPolicy,
    hash_path_segment,
)
from event_trace_memory.reasoning import ReasoningAdapter
from event_trace_memory.rholang import (
    EVENT_TRACE_RSPACE_INDEX,
    EVENT_TRACE_RSPACE_INDEX_URI_NAME,
    RholangCli,
    build_registry_call_program,
    rho_literal,
)
from event_trace_memory.rholang_deployment import (
    RholangDeployTarget,
    RholangDeploymentConfig,
    RholangDeploymentResult,
    deploy_rholang_contracts,
    load_rholang_deployment_config,
    rholang_deployment_plan,
)
from event_trace_memory.scaling import (
    ScalingThresholds,
    compact_snapshot_postings,
    compress_postings,
    decompress_postings,
    measure_event_index,
    measure_snapshot,
    recommend_sharding,
)
from event_trace_memory.snapshots import SnapshotBuilder
from event_trace_memory.workers import (
    ClaimFeatureExtractionWorker,
    IrcSourceWorker,
    MemoryQueryWorker,
    ShellActionWorker,
)

__all__ = [
    "ArtifactWriter",
    "ClaimFeatureExtractionWorker",
    "DAStore",
    "DerivedArtifactIndex",
    "EventIngestor",
    "EventTraceIndex",
    "EVENT_TRACE_RSPACE_INDEX",
    "EVENT_TRACE_RSPACE_INDEX_URI_NAME",
    "FileDA",
    "IrcSourceWorker",
    "load_fixture_corpus",
    "MemoryQueryWorker",
    "MemoryDA",
    "PatternMiner",
    "PrivacyAwareIngestor",
    "PrivacyPolicyError",
    "PublicIndexPolicy",
    "ReasoningAdapter",
    "RholangCli",
    "RholangDeployTarget",
    "RholangDeploymentConfig",
    "RholangDeploymentResult",
    "ScalingThresholds",
    "SnapshotBuilder",
    "build_registry_call_program",
    "canonical_json_bytes",
    "cid_for_bytes",
    "compact_snapshot_postings",
    "compress_postings",
    "content_id",
    "decompress_postings",
    "deploy_rholang_contracts",
    "hash_path_segment",
    "load_rholang_deployment_config",
    "measure_event_index",
    "measure_snapshot",
    "recommend_sharding",
    "rho_literal",
    "rholang_deployment_plan",
    "run_fixture_corpus",
    "ShellActionWorker",
]

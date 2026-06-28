# 0001. MVP Operational Policies

Status: Accepted

Date: 2026-06-28

## Context

The reference implementation now has executable coverage for ingestion, derived
artifacts, snapshots, pattern mining, reasoning, Rholang contracts, schemas, and
fixtures. The implementation plan still had open prompts for prefix handling,
contract sharding, private events, and semantic deduplication. Those choices
need to be explicit so the next phases do not build against different
assumptions.

## Decision

Prefix keys are computed off-chain by trusted ingestion and snapshot workers for
the MVP. Workers submit prefix keys in compact event pointers; the canonical
event envelope remains in the DA layer.

The MVP uses one `EventTraceIndex` contract and one `DerivedArtifactIndex`
contract. Snapshot shard paths are materialized off-chain and referenced by CID.
Contract-per-shard layouts are deferred until measured index size, deploy cost,
or query cost requires them.

The public MVP store accepts only non-sensitive fixture and demo data. Private
events are not indexed in public contracts until a capability-gated private
store is implemented.

Exact content identity is canonical for claims, features, patterns, runs, and
occurrences. Semantic near-duplicates are represented by reversible cluster
nodes, not destructive merges.

## Consequences

The Rholang contracts stay small: they validate duplicate IDs, store compact
pointers, and update indexes from submitted key lists.

Workers remain responsible for canonicalization, path expansion, privacy
classification, and snapshot materialization.

Future hardening can add signed prefix manifests, public ingest authorities,
private encrypted DA payloads, hashed path segments, and contract shards without
changing the existing object identity rules.


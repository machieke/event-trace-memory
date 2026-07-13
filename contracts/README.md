# Rholang Contracts

This directory contains the Rholang contract implementation for the event trace
memory indexes.

## Contracts

- `EventTraceIndex.rho` stores event pointers and query indexes by time, actor,
  channel, kind, parent/root trace, payload CID, and event CID.
- `EventTraceRSpaceIndex.rho` is the performance-oriented RSpace-native event
  anchor. Its hot path stores immutable batch anchors and DA manifest pointers
  at deterministic public names, avoiding a shared `stateCh`, list membership
  scans, and list append/copy updates. Detailed event/posting facts remain
  available through explicit materialization calls for small batches, debugging,
  or selected lookup acceleration. Duplicate detection and rich query planning
  are handled off-chain through batch manifests, Merkle roots, and DA snapshots.
- `DerivedArtifactIndex.rho` stores derived artifact pointers and provenance
  indexes for runs, claims, features, patterns, reasoning inputs, reasoning
  outputs, and belief revision histories.

## Storage Boundary

The reference contracts store compact pointers only. Raw payloads, canonical
envelopes, large artifacts, vectors, snapshots, extraction outputs, mining
outputs, and reasoning outputs remain in the DA layer and are referenced by CIDs.
Belief revision history bodies also remain in DA; the contract stores compact
history pointers and lookup indexes by claim/output.

The RSpace-native event contract pushes this boundary further for production
ingestion. The batch-first path anchors manifests:

```text
event-trace-memory:RSpaceBatch:<batchId>
event-trace-memory:RSpaceBatchByShard:<shardPath>
event-trace-memory:RSpaceBatchByEventManifest:<eventManifestCid>
event-trace-memory:RSpaceBatchByPostingsManifest:<postingsManifestCid>
event-trace-memory:RSpaceBatchByMerkleRoot:<merkleRoot>
```

When a caller explicitly materializes detail with `putEventFact` or
`putBatchEventFacts`, the contract also emits:

```text
event-trace-memory:RSpaceEvent:<eventId>
event-trace-memory:RSpaceEventCid:<eventCid>
event-trace-memory:RSpacePosting:<index>:<key>
```

Those names are read with `data-at-name` or by off-chain materializers. The
default `putBatchEvents` path accepts inline events for compatibility but stores
only the batch anchor and manifest indexes; consumers read detailed event and
posting data from DA manifests unless detail facts have been materialized.

## Validation

The repository includes static contract coverage tests:

```bash
python3 -m unittest discover -s tests
```

Runtime validation against the F1R3FLY Docker image:

```bash
bash scripts/validate_rholang_contracts.sh
```

The script starts a bonded standalone F1R3FLY node in Docker, evaluates all
`.rho` contracts with `/opt/docker/bin/node eval`, generates smoke-call Rholang
programs that exercise `putEvent`/`byTimePrefix`, RSpace-native
`putBatchEvents` plus explicit `putEventFact` detail materialization, and
`putRun`/`putClaim`/`putClaimOccurrence`/`byClaim`, then deploys the contracts
through `deploy`/`propose`. Deployed contract registry URIs are published at
`"event-trace-memory:EventTraceIndexUri"`,
`"event-trace-memory:EventTraceRSpaceIndexUri"`, and
`"event-trace-memory:DerivedArtifactIndexUri"` so follow-up client deploys can
look up and call the contracts. The deployed smoke clients cover every public
EventTraceIndex query, the RSpace-native batch-first path, explicit detailed
event/posting facts, and every DerivedArtifactIndex artifact/query family.

The Python helper module `event_trace_memory.rholang` renders Rholang literals,
builds registry lookup/call programs for those URI names, and wraps the
F1R3FLY `node deploy`, `propose`, and `data-at-name` client commands.

Notes from local validation:

- The Docker image path validates the contracts successfully.
- Building `rholang-cli` from the upstream workspace required `clang` to avoid
  an `aws-lc-sys` GCC rejection, then failed because the system `protoc`
  version was `libprotoc 3.6.1`, which rejects proto3 `optional` fields.
  Docker runtime validation is the reproducible Phase 1 path for this repo.

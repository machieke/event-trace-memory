# Rholang Contracts

This directory contains the Rholang contract implementation for the event trace
memory indexes.

## Contracts

- `EventTraceIndex.rho` stores event pointers and query indexes by time, actor,
  channel, kind, parent/root trace, payload CID, and event CID.
- `EventTraceRSpaceIndex.rho` is the performance-oriented RSpace-native event
  anchor. It stores immutable batch anchors and append-only event/posting facts
  at deterministic public names, avoiding a shared `stateCh`, list membership
  scans, and list append/copy updates. Duplicate detection and rich query
  planning are handled off-chain through batch manifests, Merkle roots, and DA
  snapshots.
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
ingestion. It anchors batch manifests and emits immutable facts:

```text
event-trace-memory:RSpaceBatch:<batchId>
event-trace-memory:RSpaceEvent:<eventId>
event-trace-memory:RSpaceEventCid:<eventCid>
event-trace-memory:RSpacePosting:<index>:<key>
```

Those names are read with `data-at-name` or by off-chain materializers. The
contract does not attempt to return complete posting lists through a mutable
state map.

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
`putBatchEvents`, and `putRun`/`putClaim`/`putClaimOccurrence`/`byClaim`, then
deploys the contracts through `deploy`/`propose`. Deployed contract registry URIs
are published at `"event-trace-memory:EventTraceIndexUri"`,
`"event-trace-memory:EventTraceRSpaceIndexUri"`, and
`"event-trace-memory:DerivedArtifactIndexUri"` so follow-up client deploys can
look up and call the contracts. The deployed smoke clients cover every public
EventTraceIndex query, the RSpace-native batch/event/posting fact path, and every
DerivedArtifactIndex artifact/query family.

The Python helper module `event_trace_memory.rholang` renders Rholang literals,
builds registry lookup/call programs for those URI names, and wraps the
F1R3FLY `node deploy`, `propose`, and `data-at-name` client commands.

Notes from local validation:

- The Docker image path validates the contracts successfully.
- Building `rholang-cli` from the upstream workspace required `clang` to avoid
  an `aws-lc-sys` GCC rejection, then failed because the system `protoc`
  version was `libprotoc 3.6.1`, which rejects proto3 `optional` fields.
  Docker runtime validation is the reproducible Phase 1 path for this repo.

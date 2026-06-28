# Rholang Contracts

This directory contains the Rholang contract implementation for the event trace
memory indexes.

## Contracts

- `EventTraceIndex.rho` stores event pointers and query indexes by time, actor,
  channel, kind, parent/root trace, payload CID, and event CID.
- `DerivedArtifactIndex.rho` stores derived artifact pointers and provenance
  indexes for runs, claims, features, patterns, reasoning inputs, and reasoning
  outputs.

## Storage Boundary

The contracts store compact pointers only. Raw payloads, canonical envelopes,
large artifacts, vectors, snapshots, extraction outputs, mining outputs, and
reasoning outputs remain in the DA layer and are referenced by CIDs.

## Validation

The repository includes static contract coverage tests:

```bash
python3 -m unittest discover -s tests
```

Runtime validation against the F1R3FLY Docker image:

```bash
bash scripts/validate_rholang_contracts.sh
```

The script starts a bonded standalone F1R3FLY node in Docker, evaluates both
`.rho` contracts with `/opt/docker/bin/node eval`, generates smoke-call
Rholang programs that exercise `putEvent`/`byTimePrefix` and
`putRun`/`putClaim`/`putClaimOccurrence`/`byClaim`, then deploys the contracts
through `deploy`/`propose`. Deployed contract registry URIs are published at
`"event-trace-memory:EventTraceIndexUri"` and
`"event-trace-memory:DerivedArtifactIndexUri"` so follow-up client deploys can
look up and call the contracts.

The Python helper module `event_trace_memory.rholang` renders Rholang literals,
builds registry lookup/call programs for those URI names, and wraps the
F1R3FLY `node deploy`, `propose`, and `data-at-name` client commands.

Notes from local validation:

- The Docker image path validates the contracts successfully.
- Building `rholang-cli` from the upstream workspace required `clang` to avoid
  an `aws-lc-sys` GCC rejection, then failed because the system `protoc`
  version was `libprotoc 3.6.1`, which rejects proto3 `optional` fields.
  Docker runtime validation is the reproducible Phase 1 path for this repo.

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

If a Rholang/F1R3FLY runtime is available, these files should also be compiled
and exercised against the same fixtures as the Python reference implementation.

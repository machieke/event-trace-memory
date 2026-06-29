# Event Trace Memory

Reference implementation for content-addressed event trace memory, derived
artifact provenance, snapshot-backed pattern mining, reasoning inputs, and
Rholang index contracts.

## Quickstart

Run the acceptance suite:

```bash
python3 -m unittest discover -s tests
```

Inspect the minimum fixture corpus:

```bash
python3 -m event_trace_memory.cli fixture-summary \
  --fixture tests/fixtures/minimum-corpus-v0.1.json \
  --pretty
```

Execute the end-to-end reference flow:

```bash
python3 -m event_trace_memory.cli run-fixture \
  --fixture tests/fixtures/minimum-corpus-v0.1.json \
  --da-root /tmp/event-trace-memory-da \
  --pretty
```

The fixture runner ingests IRC events, logs memory and shell child events,
records derived claims/features, builds an hour snapshot, mines a sequence
pattern, and generates reasoning input/output artifacts. The JSON summary
contains IDs, CIDs, support vectors, and checks for the expected acceptance
properties.

After package installation, the same commands are available through the console
script:

```bash
event-trace-memory run-fixture \
  --fixture tests/fixtures/minimum-corpus-v0.1.json \
  --da-root /tmp/event-trace-memory-da \
  --pretty
```

## Worker Adapters

`event_trace_memory.workers` provides adapters for integration code that wants
to log real worker activity without bypassing provenance:

- `IrcSourceWorker` ingests IRC-style source messages.
- `MemoryQueryWorker` logs query and result events.
- `ShellActionWorker` records explicitly permissioned shell action results and
  stores stdout/stderr bytes in DA.
- `ClaimFeatureExtractionWorker` records extractor run identity and writes
  claim/feature occurrences linked to source events.

## Data Availability Backends

The DA layer is pluggable through the `DAStore` protocol:

- `FileDA` stores content-addressed objects and manifests on disk.
- `MemoryDA` provides the same CID and manifest behavior in memory for tests and
  embedded flows.

Both backends support `verify(cid)`, which checks object digest, manifest CID,
and manifest size metadata. `get_bytes(cid)` also verifies the content digest
before returning bytes.

## Privacy Policy

`PrivacyAwareIngestor` wraps `EventIngestor` for public-index safety:

- `ingest_public_event` rejects payloads marked `private`, `confidential`, or
  `secret` before they reach DA or contract indexes.
- `ingest_hashed_path_event` indexes hashed actor/channel path segments for
  payloads that should not expose clear path labels publicly.

This does not encrypt payloads by itself. Private payload bytes should be
encrypted or stored outside the public DA path before publishing a public pointer.

## Scaling Helpers

`event_trace_memory.scaling` provides measurement and compaction helpers for
when indexes or snapshots get large:

- `measure_event_index` and `measure_snapshot` produce sizing metrics.
- `recommend_sharding` compares metrics against explicit thresholds.
- `compress_postings` stores sorted posting lists as delta-encoded integers.

## Rholang Validation

Static and reference tests:

```bash
python3 -m unittest discover -s tests
```

Docker-backed Rholang runtime validation:

```bash
bash scripts/validate_rholang_contracts.sh
```

Print a redacted deployment plan from config:

```bash
python3 -m event_trace_memory.cli rholang-plan \
  --config configs/rholang-local-docker.json \
  --pretty
```

Deploy from the same config when pointed at a live node environment:

```bash
python3 -m event_trace_memory.cli rholang-deploy \
  --config configs/rholang-local-docker.json \
  --pretty
```

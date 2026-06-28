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

## Rholang Validation

Static and reference tests:

```bash
python3 -m unittest discover -s tests
```

Docker-backed Rholang runtime validation:

```bash
bash scripts/validate_rholang_contracts.sh
```


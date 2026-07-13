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

## RSpace-Native Batch-Anchor Usage

`EventTraceRSpaceIndex.rho` treats RSpace itself as the index. The production
write path does not mutate a shared state map and does not append to on-chain
posting lists. It publishes immutable facts at deterministic public names, then
lets clients resolve detail through DA manifests.

The hot path is:

1. Write event rows, posting snapshots, and any dictionaries to DA.
2. Build a compact batch anchor with the DA manifest CIDs and Merkle root.
3. Call `putBatchAnchor` or compatibility method `putBatchEvents`.
4. Query the anchor public names, then read detail from DA.

### Batch Anchor Shape

The batch anchor is intentionally small:

```rholang
{
  "kind": "event-trace-batch-anchor",
  "schema": "event-trace-batch-anchor-v0.1",
  "batchId": "batch:irc:2026-07-13T13:00Z:0001",
  "eventCount": 500,
  "shardPath": "/2026/07/13/13",
  "minObservedAt": "2026-07-13T13:00:00Z",
  "maxObservedAt": "2026-07-13T13:59:59Z",
  "eventManifestCid": "bafy...events",
  "postingsManifestCid": "bafy...postings",
  "merkleRoot": "merkle:7b6f..."
}
```

`eventManifestCid` points to the event-pointer manifest in DA. The postings
manifest contains query indexes such as time, actor, channel, kind, root,
parent, payload CID, and event CID. The Merkle root lets consumers verify that a
detail record returned from DA belongs to the anchored batch.

### Ingestion

Preferred production ingestion calls `putBatchAnchor` directly:

```rholang
new lookup(`rho:registry:lookup`), lookedUp, ack in {
  for (@uri <- @"event-trace-memory:EventTraceRSpaceIndexUri") {
    @"event-trace-memory:EventTraceRSpaceIndexUri"!(uri)
    |
    lookup!(uri, *lookedUp)
    |
    for (@eventTraceRSpaceIndex <- lookedUp) {
      @eventTraceRSpaceIndex!(
        "putBatchAnchor",
        {
          "kind": "event-trace-batch-anchor",
          "schema": "event-trace-batch-anchor-v0.1",
          "batchId": "batch:irc:2026-07-13T13:00Z:0001",
          "eventCount": 500,
          "shardPath": "/2026/07/13/13",
          "minObservedAt": "2026-07-13T13:00:00Z",
          "maxObservedAt": "2026-07-13T13:59:59Z",
          "eventManifestCid": "bafy...events",
          "postingsManifestCid": "bafy...postings",
          "merkleRoot": "merkle:7b6f..."
        },
        *ack
      )
    }
    |
    for (@result <- ack) {
      @"event-trace-memory:IngestOk:batch:irc:2026-07-13T13:00Z:0001"!(result)
    }
  }
}
```

Compatibility callers can keep using `putBatchEvents`, but the event list is not
part of the on-chain storage model:

```rholang
@eventTraceRSpaceIndex!("putBatchEvents", batchAnchor, eventPointers, *ack)
```

The result has `"storage": "batch-anchor-and-da-manifests"` and
`"onChainEventFacts": false`. The contract stores the anchor and manifest lookup
facts only; detailed events remain in DA.

### Query

On-chain query starts by reading public names. Depending on the node build, the
CLI command may be `data-at-name` or `cont-at-name`; both target the same public
name.

Direct batch lookup:

```bash
node data-at-name '"event-trace-memory:RSpaceBatch:batch:irc:2026-07-13T13:00Z:0001"'
```

Shard lookup:

```bash
node data-at-name '"event-trace-memory:RSpaceBatchByShard:/2026/07/13/13"'
```

Manifest and root lookups:

```bash
node data-at-name '"event-trace-memory:RSpaceBatchByEventManifest:bafy...events"'
node data-at-name '"event-trace-memory:RSpaceBatchByPostingsManifest:bafy...postings"'
node data-at-name '"event-trace-memory:RSpaceBatchByMerkleRoot:merkle:7b6f..."'
```

A typical off-chain query flow is:

1. Read `RSpaceBatchByShard:<shardPath>` to discover candidate batch ids.
2. Read `RSpaceBatch:<batchId>` for each candidate.
3. Fetch `postingsManifestCid` from DA.
4. Resolve the posting list inside the DA manifest, for example
   `channel:/irc/libera/channel/%23rspace`.
5. Fetch matching event pointers from `eventManifestCid`.
6. Verify each event pointer against the anchored Merkle root.

The contract also exposes `getNameHints` for clients that need to discover
public-name conventions from the deployed contract:

```rholang
@eventTraceRSpaceIndex!(
  "getNameHints",
  "batch:irc:2026-07-13T13:00Z:0001",
  "event:irc:2026-07-13T13:05Z:42",
  *hints
)
```

### Optional Detailed Lookup

Detailed on-chain lookup is opt-in. Use it for small batches, debugging, or
selected hot records that need direct public-name lookup.

Materialize one event:

```rholang
@eventTraceRSpaceIndex!(
  "putEventFact",
  {
    "kind": "event-pointer",
    "schema": "event-pointer-v0.1",
    "eventId": "event:irc:2026-07-13T13:05Z:42",
    "eventCid": "bafy...event",
    "payloadCid": "bafy...payload",
    "valueKind": "message",
    "timePrefixKeys": ["/2026", "/2026/07", "/2026/07/13", "/2026/07/13/13"],
    "actorPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/user/alice"],
    "channelPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/channel/%23rspace"],
    "parentEventIds": [],
    "rootEventId": "event:irc:2026-07-13T13:05Z:42"
  },
  *ack
)
```

That creates names such as:

```text
event-trace-memory:RSpaceEvent:event:irc:2026-07-13T13:05Z:42
event-trace-memory:RSpaceEventCid:bafy...event
event-trace-memory:RSpacePosting:channel:/irc/libera/channel/%23rspace
```

Materialize an anchored batch plus detail facts:

```rholang
@eventTraceRSpaceIndex!("putBatchEventFacts", batchAnchor, eventPointers, *ack)
```

That path returns `"storage": "batch-anchor-and-detailed-rspace-facts"` and
`"onChainEventFacts": true`. It is intentionally not the production hot path,
because every materialized event creates multiple additional public facts.

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

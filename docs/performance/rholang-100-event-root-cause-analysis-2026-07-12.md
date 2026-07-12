# Rholang 100 Event Root Cause Analysis - 2026-07-12

## Executive Summary

The 100-event integration run was slow for two independent reasons:

1. **Contract execution cost grew with shared posting-list size.**
   The event ingestion contract stores global list-valued indexes and updates
   them by recursively scanning lists and appending with list copy. Common
   prefixes such as `/2026`, `/2026/07`, `/2026/07/06`, `/perception`, and
   `/device` accumulated nearly every event. Every later event paid to scan and
   copy those growing lists.

2. **The shard stopped making timely progress after inclusion.**
   After the verifier block, validators repeatedly logged that the newest latest
   message was more than 60 seconds old. Finality advanced only when validators
   resumed proposing around `20:41:30Z`. That accounts for the `47m 11.687s`
   wait after the last event block was added.

The first issue is a repository/contract design problem. The second is shard
health/liveness behavior in the local F1R3 node run.

## Evidence

### Stable Payload Size, Exploding Cost

Each deploy carried a 10-event batch. The Rholang term and JSON event payload
sizes were roughly constant across batches:

| Batch | Term chars | Event JSON chars | Deploy cost |
| --- | ---: | ---: | ---: |
| `batch-00` | `17,395` | `10,641` | `9,127,224` |
| `batch-01` | `17,406` | `10,654` | `23,714,765` |
| `batch-02` | `17,489` | `10,732` | `39,209,857` |
| `batch-03` | `17,477` | `10,725` | `53,455,281` |
| `batch-04` | `17,429` | `10,675` | `70,473,028` |
| `batch-05` | `17,280` | `10,530` | `86,945,670` |
| `batch-06` | `17,432` | `10,681` | `107,560,177` |
| `batch-07` | `17,537` | `10,784` | `130,125,823` |
| `batch-08` | `17,605` | `10,852` | `154,666,645` |
| `batch-09` | `17,484` | `10,732` | `178,711,203` |

Ratios from first to last batch:

- Term size: `1.005x`
- Event JSON size: `1.009x`
- Deploy cost: `19.58x`

This rules out payload size as the main cause.

### Posting-List Work Tracks Cost

A simple model of list work was computed from the actual event pointers:

- Deduplicated index append: scan existing list length `L`, then append/copy
  length `L`, modeled as `2L`.
- Direct append indexes: append/copy existing list length `L`, modeled as `L`.

This is intentionally approximate, but it tracks the shape of the contract:
`containsValue` recursively scans lists, and `++ [eventId]` copies list content.

| Batch | Modeled linear list cells | Deploy cost |
| --- | ---: | ---: |
| `batch-00` | `1,051` | `9,127,224` |
| `batch-01` | `3,326` | `23,714,765` |
| `batch-02` | `5,334` | `39,209,857` |
| `batch-03` | `5,521` | `53,455,281` |
| `batch-04` | `7,557` | `70,473,028` |
| `batch-05` | `8,118` | `86,945,670` |
| `batch-06` | `10,701` | `107,560,177` |
| `batch-07` | `13,531` | `130,125,823` |
| `batch-08` | `16,182` | `154,666,645` |
| `batch-09` | `18,021` | `178,711,203` |

Correlation between modeled list work and deploy cost: `0.995`.

The model grew `17.15x` from first to last batch. The measured cost grew
`19.58x`. The remaining difference is consistent with broader state growth,
RSpace term/state serialization, validation checks, and fixed execution overhead.

### Hot Posting Keys

After 100 events, the largest posting lists were:

| Index | Key | Posting length |
| --- | --- | ---: |
| `time` | `/2026` | `100` |
| `time` | `/2026/07` | `100` |
| `time` | `/2026/07/06` | `100` |
| `channel` | `/perception` | `100` |
| `actor` | `/device` | `98` |
| `actor` | `/device/moto-g84-5g` | `98` |
| `actor` | `/device/moto-g84-5g/camera` | `75` |
| `actor` | `/device/moto-g84-5g/camera/0` | `75` |
| `time` | `/2026/07/06/11` | `70` |
| `kind` | `track-segment` | `61` |
| `root` | first session root | `48` |
| `parent` | first session root parent | `47` |

The contract stores prefix indexes as flat posting lists. Low-cardinality global
prefixes are therefore written by nearly every event and become progressively
more expensive.

## Contract-Level Root Causes

### 1. Single Shared State Channel Serializes All Writes

`EventTraceIndex.rho` keeps all event and index maps behind one `stateCh`.
Every `putEvent` consumes this state and later writes back a replacement state:

- `contracts/EventTraceIndex.rho:16-26`
- `contracts/EventTraceIndex.rho:82-177`

Effect:

- All ingestion writes contend on one channel.
- A block with multiple deploys cannot get useful parallelism for event writes.
- A 10-event batch deploy also serializes its own events because the generated
  `ingestAll` helper waits for each `putEvent` acknowledgement before calling
  the next one.

### 2. Deduplication Is Linear In Posting Length

The contract deduplicates some index entries with `containsValue`:

- `contracts/EventTraceIndex.rho:30-43`
- `contracts/EventTraceIndex.rho:66-75`

`containsValue` is recursive over a list:

```rholang
match items {
  [hd, ...tl] => {
    if (hd == value) {
      return!(true)
    } else {
      containsValue!(tl, value, *return)
    }
  }
  _ => { return!(false) }
}
```

For a new event id, the scan normally traverses the whole existing posting list.

### 3. Appending Copies Existing Lists

The same append path uses:

```rholang
indexMap.set(key, indexMap.getOrElse(key, []) ++ [value])
```

That makes appending to a hot key proportional to current posting length. The
deduplicated indexes pay both the scan and the append/copy cost.

Direct list appends for `kindIndex`, `rootIndex`, and `payloadIndex` also use
`++ [eventId]`:

- `contracts/EventTraceIndex.rho:147-162`

`payloadIndex` stayed cheap because payload CIDs were unique. `kindIndex` and
`rootIndex` did not.

### 4. Global Prefix Indexing Creates Hot Keys

Each event writes all prefix keys:

- Time prefixes: typically `/2026`, `/2026/07`, `/2026/07/06`, `/hour`.
- Actor prefixes: typically `/device`, `/device/moto-g84-5g`, component path.
- Channel prefixes: typically `/perception`, session path, stream path.
- Parent ids: common roots and scene markers.

This gives good prefix query semantics, but on-chain it creates low-cardinality
hot postings. With list-backed postings, total work trends toward quadratic for
events sharing common prefixes.

### 5. Test Harness Added Query Work To Each Ingestion Deploy

Each 10-event batch deploy was not pure ingestion. The generated Rholang program
also performed correctness checks:

- 10 runtime `putEvent` calls through the recursive `ingestAll` helper.
- 9 query calls after ingestion.
- 8 client-side `containsValue` scans over query result lists.

That validation is useful for correctness, but it should not be part of a
production ingestion benchmark. It amplifies the same posting-list cost because
queries over hot indexes return growing event-id lists.

## Block-Level Effects

The 10 deploys were submitted in about `2.052s`, but the proposer started block
`508` while the burst was still arriving:

- Block `508`: selected 6 event deploys, `batch-00` through `batch-05`.
- Block `509`: selected the remaining 4 event deploys, `batch-06` through
  `batch-09`, after block `508` finished.

This split matters because block `509` executed from a larger contract state.
It contained fewer events than block `508`, but took much longer:

| Block | Events | Cost | Compute time | Compute throughput |
| --- | ---: | ---: | ---: | ---: |
| `508` | 60 | `282,925,825` | `17m 26.380s` | `3.44 events/min` |
| `509` | 40 | `571,063,848` | `40m 49.961s` | `0.98 events/min` |

Block `509` had `67%` as many events but about `202%` of the deploy cost and
about `234%` of the compute time.

## Finality-Level Root Cause

The finality delay after inclusion was not caused by additional Rholang event
execution. The event blocks were already added by `19:54:27.469108Z`.

Observed sequence on `rnode.validator3`:

- `19:55:32.603520Z`: verifier block `512` added.
- `19:55:34.180553Z`: empty block `513` added.
- From `19:56:38Z` through `20:41:18Z`: repeated log line:
  `Requesting tips update as newest latest message is more than 60s old. Might be network is faulty.`
- `20:41:37.610308Z`: heartbeat proposed again because new parents were
  observed with `lag=9`.
- `20:41:39Z`: finalizer sweep finalized the event blocks.

Other validators showed the same stale-latest pattern, with validator1 resuming
around `20:41:30Z` and producing block `514`.

Root cause for the finality component:

- The local shard did not make normal cross-validator progress for roughly
  46 minutes after the verifier.
- Once validator proposals resumed, finalization of the event blocks happened
  immediately in the next finalizer sweep.

This is a local shard health/liveness issue, not an event-contract compute
issue. It still matters operationally because end-to-end ingestion-to-finality
depends on both contract execution and validator liveness.

## Causal Chain

1. Ten large correctness deploys were submitted in one burst.
2. The first event block started before the burst fully arrived and selected only
   six event deploys.
3. Those six deploys executed 60 sequential event inserts against one shared
   contract state channel.
4. Each event updated many global prefix posting lists.
5. Hot prefix posting lists grew with every event.
6. Later inserts scanned and copied longer lists.
7. The remaining four deploys executed in the next block against the larger
   state, making each event much more expensive.
8. The verifier confirmed state, then shard progress stalled for about
   46 minutes.
9. When validators resumed proposing, the already-included event blocks
   finalized.

## What This Means

The current `EventTraceIndex.putEvent` contract is a correctness/reference path,
not a production ingestion path.

It is especially unsuitable for:

- Dense time prefixes.
- Dense actor/device prefixes.
- Dense session/root traces.
- Query workloads that return full event-id lists.
- Large batches that include validation queries in the same deploy.

## Fix Direction

### Production Data Plane

Move production ingestion to batch anchoring:

- Store event pointers and query indexes in DA snapshots.
- Compute Merkle roots over event batches and posting files.
- Submit one compact Rholang batch anchor with:
  - batch id
  - shard path
  - event count
  - min/max event time
  - event manifest CID
  - postings manifest CID
  - Merkle root
- Verify individual events by inclusion proof instead of on-chain insertion.

### If On-Chain Queryable Indexes Are Still Needed

Use a different Rholang shape:

- Contract-per-shard or channel-per-index-key, not one global state map.
- Avoid low-cardinality global prefixes as mutable on-chain posting keys.
- Store compact local integer ids rather than full event ids in postings.
- Use append-only DA postings for hot keys and anchor their root on-chain.
- Replace list dedup scans with membership maps/sets, or enforce uniqueness at
  the batch level and remove on-chain dedup from hot postings.
- Do not run ingestion correctness queries in the same production deploy.

### Operational Finality Controls

Add shard-health instrumentation around integration tests:

- Capture `last_finalized_block_number` at deploy, inclusion, verifier, and
  finality.
- Record per-validator stale latest-message warnings.
- Fail or annotate benchmarks when validators log stale latest messages for more
  than a small threshold.
- Track time from block added to next block by a different validator.
- Keep proposing support blocks after heavy deploys, or restart/reconnect
  validators when the stale-latest condition persists.

## Next Experiments

To isolate remaining uncertainty, run these benchmarks against a healthy shard:

1. 10 batches of 10 events, ingestion only, no validation queries.
2. Same payloads with indexes disabled, storing only `events` and `eventCid`.
3. Same payloads with no `containsValue`, append-only postings.
4. Same payloads anchored as one batch manifest, no per-event insertion.
5. Vary cardinality:
   - all events share `/2026` and `/perception`
   - events distributed across many time/session shards
6. Keep validator liveness fixed and report:
   - deploy accept time
   - inclusion time
   - proposal `compute-state`
   - block added time
   - finality time
   - stale-latest warnings

These experiments should make the remaining bottlenecks directly attributable
instead of blended together.

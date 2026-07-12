# Rholang 100 Event Finality Trace - 2026-07-12

## Scope

Run id: `ten-deploys-of-ten-20260712T185157Z`

Workload:

- 10 deploys submitted in one burst.
- Each deploy ingested a batch of 10 event traces.
- Total event traces: 100.
- All deploys used `validAfterBlockNumber: 505`.
- All event deploys completed with `errored: false`.

Source data:

- `docker exec rnode.validator3 /opt/docker/bin/node show-block ...`
- `docker logs rnode.validator3` filtered around `2026-07-12T18:51Z` to
  `2026-07-12T20:45Z`.

The 100 event traces landed in two blocks:

| Block | Hash prefix | Event deploys | Events | Added | Finalized |
| --- | --- | ---: | ---: | --- | --- |
| `508` | `ef559a637a...` | 6 | 60 | `2026-07-12T19:13:31.701594Z` | `2026-07-12T20:41:39.083238Z` |
| `509` | `c7511eef0f...` | 4 | 40 | `2026-07-12T19:54:27.469108Z` | `2026-07-12T20:41:39.156453Z` |

## End-To-End Breakdown

Measured from the first deploy timestamp to finalization of the last event block:
`1h 45m 37.481s`.

| Phase | Start | End | Duration | Share |
| --- | --- | --- | ---: | ---: |
| First deploy timestamp to first event proposal start | `18:56:01.675Z` | `18:56:02.937822Z` | `1.263s` | `0.02%` |
| Block `508` proposal | `18:56:02.937822Z` | `19:13:31.701594Z` | `17m 28.764s` | `16.55%` |
| Gap between event block proposals | `19:13:31.701594Z` | `19:13:31.804263Z` | `0.103s` | `0.00%` |
| Block `509` proposal | `19:13:31.804263Z` | `19:54:27.469108Z` | `40m 55.665s` | `38.75%` |
| Wait from last event block added to event finality | `19:54:27.469108Z` | `20:41:39.156453Z` | `47m 11.687s` | `44.68%` |

Summary:

- Proposal execution for event blocks: `58m 24.429s`, about `55.30%`.
- `compute-state` inside those proposals: `58m 16.341s`, about `55.17%`.
- Consensus finality after the last event block was added: `47m 11.687s`,
  about `44.68%`.
- End-to-end throughput to finality: `0.947 events/min`.
- Rholang event-block compute throughput before finality wait:
  `1.716 events/min`.

## Deploy Submission And Block Selection

Deploy timestamps from block metadata:

| Batch | Block | Deploy timestamp | Cost | Errored |
| --- | ---: | --- | ---: | --- |
| `batch-00` | `508` | `2026-07-12T18:56:01.675Z` | `9,127,224` | `false` |
| `batch-01` | `508` | `2026-07-12T18:56:01.880Z` | `23,714,765` | `false` |
| `batch-02` | `508` | `2026-07-12T18:56:02.065Z` | `39,209,857` | `false` |
| `batch-03` | `508` | `2026-07-12T18:56:02.252Z` | `53,455,281` | `false` |
| `batch-04` | `508` | `2026-07-12T18:56:02.455Z` | `70,473,028` | `false` |
| `batch-05` | `508` | `2026-07-12T18:56:02.632Z` | `86,945,670` | `false` |
| `batch-06` | `509` | `2026-07-12T18:56:02.800Z` | `107,560,177` | `false` |
| `batch-07` | `509` | `2026-07-12T18:56:03.287Z` | `130,125,823` | `false` |
| `batch-08` | `509` | `2026-07-12T18:56:03.507Z` | `154,666,645` | `false` |
| `batch-09` | `509` | `2026-07-12T18:56:03.727Z` | `178,711,203` | `false` |

The deploy timestamp span was `2.052s`. The node did not put all 10 event
deploys into one block:

- Block `508` selection at `18:56:03.111822Z`:
  `pool=7`, `valid=7`, `alreadyInScope=1`, `selected=6`.
- Block `509` selection at `19:13:32.919109Z`:
  `pool=11`, `valid=11`, `alreadyInScope=7`, `selected=4`.

So the proposer started block `508` while the burst was still arriving. The
remaining 4 event deploys waited until block `508` finished before they could be
selected into block `509`.

## Event Block Proposal Trace

### Block 508

Selected deploys: `batch-00` through `batch-05`.

Total event traces: 60.

Block metadata:

- Hash: `ef559a637a0de1e7b427861c6dfb5583b83c236b45421cdbcbd778d367326aae`
- Header timestamp: `2026-07-12T18:56:03.097Z`
- Added: `2026-07-12T19:13:31.701594Z`
- Deploy count: 6
- Block size: `5,376,743`
- Total deploy cost: `282,925,825`
- Finalized: `true`

Proposal log trace:

| Step | Timestamp | Detail |
| --- | --- | --- |
| Proposal started | `18:56:02.937822Z` | `Propose started` |
| Snapshot ready | `18:56:03.097126Z` | `getCasperSnapshot [159ms]` |
| Block creation | `18:56:03.097700Z` | `Creating block #508` |
| Deploy selection | `18:56:03.111822Z` | `selected=6` |
| Compute started | `18:56:03.133665Z` | `compute-state-started` |
| Rholang play started | `18:56:03.133730Z` | `play-deploys-started` |
| Compute finished | `19:13:29.513501Z` | `compute-state-finished` |
| Validation started | `19:13:30.278837Z` | `Validating self-created block #508` |
| Validation finished | `19:13:30.437554Z` | `Valid`, `158.694ms` |
| Internal finalizer run | `19:13:31.516733Z` to `19:13:31.518741Z` | `2.008ms` |
| Propose timing | `19:13:31.531538Z` | `snapshot_ms=159`, `propose_core_ms=1048419`, `total_ms=1048593` |
| Block added | `19:13:31.701594Z` | `created and added` |

Derived timings:

- Observed proposal start to block added: `17m 28.764s`.
- Node-reported proposal total: `17m 28.593s`.
- `compute-state` duration: `17m 26.380s`.
- `compute-state` share of observed proposal time: about `99.77%`.
- Compute throughput: about `3.44 events/min`.
- Added to finalization: `1h 28m 07.382s`.

### Block 509

Selected deploys: `batch-06` through `batch-09`.

Total event traces: 40.

Block metadata:

- Hash: `c7511eef0f17af180fe33590dc23199ec636639e4b44e5d28707d737a21428cc`
- Header timestamp: `2026-07-12T19:13:32.442Z`
- Added: `2026-07-12T19:54:27.469108Z`
- Deploy count: 4
- Block size: `7,831,100`
- Total deploy cost: `571,063,848`
- Finalized: `true`

Proposal log trace:

| Step | Timestamp | Detail |
| --- | --- | --- |
| Proposal started | `19:13:31.804263Z` | `Propose started` |
| Snapshot ready | `19:13:32.441828Z` | `getCasperSnapshot [637ms]` |
| Block creation | `19:13:32.442306Z` | `Creating block #509` |
| Deploy selection | `19:13:32.919109Z` | `selected=4` |
| Compute started | `19:13:33.045172Z` | `compute-state-started` |
| Rholang play started | `19:13:33.045254Z` | `play-deploys-started` |
| Compute finished | `19:54:23.006107Z` | `compute-state-finished` |
| Validation started | `19:54:24.092104Z` | `Validating self-created block #509` |
| Validation finished | `19:54:24.633642Z` | `Valid`, `541.514ms` |
| Internal finalizer run | `19:54:26.588483Z` to `19:54:26.624063Z` | `35.580ms` |
| Propose timing | `19:54:26.615895Z` | `snapshot_ms=637`, `propose_core_ms=2454146`, `total_ms=2454811` |
| Block added | `19:54:27.469108Z` | `created and added` |

Derived timings:

- Observed proposal start to block added: `40m 55.665s`.
- Node-reported proposal total: `40m 54.811s`.
- `compute-state` duration: `40m 49.961s`.
- `compute-state` share of observed proposal time: about `99.77%`.
- Compute throughput: about `0.98 events/min`.
- Added to finalization: `47m 11.687s`.

## Verifier Block

Block `512` was not one of the event-containing blocks. It ran the verifier
deploy that checked the final on-chain state.

| Step | Timestamp | Detail |
| --- | --- | --- |
| Proposal started | `19:55:11.883952Z` | `Propose started` |
| Deploy selection | `19:55:12.581605Z` | `selected=1` |
| Compute started | `19:55:12.597770Z` | `compute-state-started` |
| Compute finished | `19:55:32.002004Z` | `compute-state-finished` |
| Propose timing | `19:55:32.590214Z` | `snapshot_ms=237`, `propose_core_ms=20466`, `total_ms=20706` |
| Block added | `19:55:32.603520Z` | `created and added` |

The verifier took about `20.706s` total and confirmed the 100-event state. The
event blocks were finalized `46m 06.553s` after this verifier block was added.

## Finalization Trace

Finalizer sweep:

| Timestamp | Detail |
| --- | --- |
| `20:41:38.619000Z` | `finalizer-run-started` |
| `20:41:39.083238Z` | Observed 6 deploys while finalizing a set including `ef559a637a...` and `c7511eef0f...` |
| `20:41:39.156453Z` | Observed 4 deploys while finalizing the same set |
| `20:41:39.205206Z` | `finalizer-run-finished` |

The finalizer work itself took less than a second. The long part was the wait
from block inclusion to the finalizer sweep:

- Block `508`: `1h 28m 07.382s` from added to finalized.
- Block `509`: `47m 11.687s` from added to finalized.

## Cost Growth

The per-deploy Rholang cost grew sharply as the contract state grew:

| Batch | Events in batch | Cost | Cost per event |
| --- | ---: | ---: | ---: |
| `batch-00` | 10 | `9,127,224` | `912,722` |
| `batch-01` | 10 | `23,714,765` | `2,371,477` |
| `batch-02` | 10 | `39,209,857` | `3,920,986` |
| `batch-03` | 10 | `53,455,281` | `5,345,528` |
| `batch-04` | 10 | `70,473,028` | `7,047,303` |
| `batch-05` | 10 | `86,945,670` | `8,694,567` |
| `batch-06` | 10 | `107,560,177` | `10,756,018` |
| `batch-07` | 10 | `130,125,823` | `13,012,582` |
| `batch-08` | 10 | `154,666,645` | `15,466,665` |
| `batch-09` | 10 | `178,711,203` | `17,871,120` |

The last 10-event batch cost about `19.6x` the first 10-event batch.

## Diagnosis

The time was spent in two places:

1. Rholang execution during block proposal.
   Almost all proposal time was `compute-state` / `play-deploys`. Validation,
   snapshot creation, and finalizer bookkeeping were small by comparison.

2. Consensus finality after inclusion.
   The event blocks were already added by `19:54:27Z`, but were not finalized
   until `20:41:39Z`.

The Rholang execution path does not scale because each `putEvent` mutates a
single shared state map and maintains list-valued indexes. The contract uses
recursive `containsValue` checks and list append/copy operations such as
`existingList ++ [eventId]`. As the indexes grow, each later insert becomes more
expensive. The test deploys also did more than ingestion: each batch deploy
included correctness marker sends and query checks after inserting events.

This trace supports a design change:

- Keep `EventTraceIndex.putEvent` as a correctness/reference path.
- Do not use per-event Rholang insertion as the production data plane.
- Store event batches and query indexes in DA snapshots.
- Put compact batch anchors on-chain: batch id, shard path, event count,
  manifest CID, and Merkle root.
- Benchmark finality per anchored batch rather than per event.

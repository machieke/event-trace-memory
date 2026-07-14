# RSpace Batch Anchor Benchmark History - 2026-07-13

## Scope

This document consolidates the batch-ingestion performance runs executed while
moving event-trace ingestion from detailed per-event Rholang indexing to the
RSpace-native batch-anchor path.

The runs are not all the same contract behavior:

- The 2026-07-12 100-event run used the older detailed on-chain event index.
  It wrote event facts and list-backed posting indexes directly in Rholang.
- The 2026-07-13 batch-anchor runs used `EventTraceRSpaceIndex.putBatchEvents`.
  That compatibility method accepts inline event pointers but stores only the
  batch anchor and DA manifest pointers on-chain. Detailed event facts require
  explicit opt-in calls such as `putEventFact` or `putBatchEventFacts`.

For batch-anchor runs, `cost per event` means total phlo cost divided by the
declared event count. It is a throughput normalization, not evidence that each
event was individually indexed on-chain.

## Sources

Primary sources:

- `docker exec rnode.validator3 /opt/docker/bin/node show-blocks ...`
- `docker exec rnode.validator3 /opt/docker/bin/node show-block ...`
- `docker logs rnode.validator3` JSON logs around each run
- Raw benchmark artifacts:
  - `docs/performance/artifacts/rspace-batch-anchor-recovery-aware-20260713T111154Z.json`
  - `docs/performance/artifacts/rspace-batch-anchor-100x50-20260713T124204Z.json`
  - `docs/performance/artifacts/rspace-batch-anchor-leadership-10x-20260713T142407Z.json`
  - `docs/performance/artifacts/rspace-batch-anchor-leadership-100x50-20260713T143346Z.json`
  - `docs/performance/artifacts/rspace-batch-anchor-leadership-100x75-partial-20260713T182238Z.json`
  - `docs/performance/artifacts/rspace-batch-anchor-leadership-150x50-partial-20260713T193527Z.json`
  - `docs/performance/artifacts/rspace-batch-anchor-leadership-150x50-retest-20260714T080823Z.json`
  - `docs/performance/artifacts/rspace-batch-anchor-leadership-150x50-retest-failed-20260714T092913Z.json`
  - `docs/performance/artifacts/rspace-batch-anchor-leadership-150x50-retest-failed-20260714T113330Z.json`
  - `docs/performance/artifacts/rspace-batch-anchor-parent-aware-150x50-retest-recovery-20260714T124211Z.json`

Related earlier analysis:

- `docs/performance/rholang-100-event-finality-trace-2026-07-12.md`
- `docs/performance/rholang-100-event-root-cause-analysis-2026-07-12.md`
- `docs/performance/rspace-batch-anchor-150x50-root-cause-analysis-2026-07-13.md`
- `docs/performance/rspace-batch-anchor-150x50-root-cause-analysis-2026-07-14.md`

## Terms

| Term | Meaning |
| --- | --- |
| First inclusion | First block observed with some or all run deploys, regardless of finality. |
| Canonical inclusion | Finalized block set that covers all batches for the run. |
| Finality latency | First deploy timestamp to finalizer observation of the final canonical block. |
| Recovery-aware measurement | Treat non-final duplicate branches as transient and measure the finalized coverage set. |
| Batch id coverage | The set of logical batch ids found in block deploy terms. |

The local shard repeatedly created non-final branches and later recovered deploys
into finalized blocks. For that reason, the restart-era measurements use
recovery-aware coverage instead of trusting first inclusion.

## Executive Summary

| Run | Contract path | Events | Canonical blocks | Finalized | Cost | Cost/event | Canonical add latency | Finality latency | Finality throughput |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| `10x10` detailed, 2026-07-12 | Detailed event facts and postings | 100 | 2 | yes | `853,989,673` | `8,539,897` | `3,505.692s` | `6,337.481s` | `0.0158 events/s` |
| `10x10` batch-anchor, pre-restart | Batch anchor | 100 | 0 | no | n/a | n/a | n/a | n/a | n/a |
| `10x25` batch-anchor, pre-restart | Batch anchor | 250 | 1 | yes | `17,380,500` | `69,522` | `33.684s` | `156.766s` | `1.595 events/s` |
| `10x50` batch-anchor, pre-restart | Batch anchor | 500 | 1 | no | `50,265,175` | `100,530` | `82.242s` | `>6,720s` | `<0.0744 events/s` |
| `10x10` batch-anchor, restarted shard | Batch anchor | 100 | 1 | yes | `836,850` | `8,369` | `33.158s` | `52.748s` | `1.896 events/s` |
| `10x25` batch-anchor, restarted shard | Batch anchor | 250 | 1 | yes | `1,370,550` | `5,482` | `52.826s` | `68.318s` | `3.659 events/s` |
| `10x50` batch-anchor, restarted shard | Batch anchor | 500 | 2 | yes | `2,259,850` | `4,520` | `11.445s` | `49.190s` | `10.165 events/s` |
| `100x50` batch-anchor, restarted shard | Batch anchor | 5,000 | 4 | yes | `22,815,500` | `4,563` | `552.458s` | `594.821s` | `8.406 events/s` |
| `10x10` batch-anchor, deploy-inclusion leadership | Batch anchor | 100 | 2 | yes | `824,700` | `8,247` | `88.669s` | `334.446s` | `0.299 events/s` |
| `10x25` batch-anchor, deploy-inclusion leadership | Batch anchor | 250 | 1 | yes | `1,333,420` | `5,334` | `20.592s` | `104.799s` | `2.386 events/s` |
| `10x50` batch-anchor, deploy-inclusion leadership | Batch anchor | 500 | 1 | yes | `2,181,020` | `4,362` | `17.984s` | `72.796s` | `6.869 events/s` |
| `100x50` batch-anchor, deploy-inclusion leadership | Batch anchor | 5,000 | 4 | yes | `21,918,700` | `4,384` | `183.729s` | `208.419s` | `23.990 events/s` |
| `100x75` batch-anchor, leadership probe | Batch anchor | 7,500 | 0 finalized, 8 non-final hits | no | n/a | n/a | non-final only | `>2,075s` | `<3.615 events/s` |
| `150x50` batch-anchor, degraded-shard probe | Batch anchor | 7,500 | 0 hit blocks | no | n/a | n/a | no inclusion `>593s` | `>593s` | `<12.648 events/s` |
| `150x50` batch-anchor, post-fix retest | Batch anchor | 7,500 | 5 finalized, 15 total hits | yes | `32,933,050` | `4,391` | `1,035.536s` | `1,468.320s` | `5.108 events/s` |
| `150x50` batch-anchor, 2026-07-14 failed retest | Batch anchor | 7,500 | 0 finalized, non-final scope only | no | n/a | n/a | non-final only | stalled at LFB `81` | `0 events/s` |
| `150x50` batch-anchor, 2026-07-14 post-fix retest | Batch anchor | 7,500 | 0 finalized, 4 non-final hits | no | n/a | n/a | non-final only | LFB reached `127` | `0 events/s` |
| `150x50` batch-anchor, deploy-aware parent support | Batch anchor | 7,500 | 14 | yes | `32,933,200` | `4,391` | `612.679s` | `666.679s` | `11.250 events/s` |

The batch-anchor design changed the cost profile by two to three orders of
magnitude compared with the detailed per-event path. The remaining bottleneck in
the restarted-shard runs is not per-event Rholang indexing. It is deploy
selection, branch recovery, and finality behavior under large pending deploy
sets.

## Detailed Per-Event Baseline

Run id: `ten-deploys-of-ten-20260712T185157Z`

Workload:

- 10 deploys in one burst.
- 10 event traces per deploy.
- 100 total event traces.
- Detailed on-chain event facts and query indexes.
- All event deploys completed with `errored: false`.

The event deploys landed in two finalized blocks:

| Block | Hash prefix | Deploys | Events | Block size | Cost | Compute | Propose total | Added to finality |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `508` | `ef559a637a...` | 6 | 60 | `5,376,743` | `282,925,825` | `1,046.380s` | `1,048.593s` | `5,287.382s` |
| `509` | `c7511eef0f...` | 4 | 40 | `7,831,100` | `571,063,848` | `2,449.961s` | `2,454.811s` | `2,831.687s` |

Aggregates:

| Metric | Value |
| --- | ---: |
| Total cost | `853,989,673` |
| Cost per event | `8,539,896.73` |
| Event-block compute sum | `3,496.341s` |
| Event-block propose sum | `3,504.429s` |
| First deploy to finality | `6,337.481s` |
| Finality throughput | `0.947 events/min` |

This run exposed the anti-pattern: per-event writes to global list-backed
posting indexes made later batches much more expensive than earlier ones. The
last 10-event batch cost `178,711,203`, about `19.6x` the first 10-event batch.

## Batch-Anchor Pre-Restart Runs

These runs used the batch-anchor-first `putBatchEvents` path, but the shard was
still showing poor recovery/finality behavior. The results are therefore useful
for cost comparison, but not as a stable finality baseline.

### 10x10 Pre-Restart

Run shape:

- 10 deploys.
- 10 event traces per deploy.
- 100 declared event traces.

Outcome:

- Deploys were submitted and repeatedly executed on `validator3`.
- Candidate blocks failed with `Invalid(NeglectedInvalidBlock)`.
- No finalized canonical event block was available for cost/finality
  comparison.
- Observed compute per failed proposal was about `2.6s` to `3.6s`.
- Observed proposal total was about `8.0s` to `8.7s`.

### 10x25 Pre-Restart

Run id: `rspace-scale-10x25-20260713T061049Z`

| Metric | Value |
| --- | ---: |
| Events | `250` |
| Deploys | `10` |
| Canonical block | `4328` |
| Hash | `daa06ad2897fd79cd207073753ab81d1b5c8d150bd67e28cb041044a0e4ac4d1` |
| Submit span | `1.260s` |
| First deploy to block added | `33.684s` |
| Compute | `25.234399s` |
| Propose total | `32.212s` |
| Cost sum | `17,380,500` |
| Average cost per deploy | `1,738,050` |
| Cost per event | `69,522` |
| Block size | `2,990,167` |
| First deploy to finality | `156.766s` |
| Added to finality | `123.082s` |

### 10x50 Pre-Restart

Run id: `rspace-scale-10x50-20260713T061337Z`

| Metric | Value |
| --- | ---: |
| Events | `500` |
| Deploys | `10` |
| Included block | `4332` |
| Hash | `b97181bc891084b6ae526457678be6f6748d9c76d755b157310fbee8c28f7d1f` |
| Submit span | `1.541s` |
| First deploy to block added | `82.242s` |
| Compute | `63.742042s` |
| Propose total | `80.484s` |
| Cost sum | `50,265,175` |
| Average cost per deploy | `5,026,517.5` |
| Cost per event | `100,530.35` |
| Block size | `4,951,413` |
| Finalized | no, not after more than `112m` |

The cost increase from `10x25` to `10x50` was too large for the intended
batch-anchor path. After the shard restart and recovery improvements, the same
logical workload became much cheaper and finalized reliably.

## Batch-Anchor Restarted-Shard Runs

The restarted-shard tests used the scoped registry name:

```text
event-trace-memory:EventTraceRSpaceIndexUri:restart-20260713T105845Z
```

The benchmark contract binding was finalized before the workload runs. Each
workload used `putBatchEvents`, so the contract stored batch anchors and DA
manifest pointers rather than detailed event facts.

### Restarted 10x10

Run id: `rspace-scale-10x10-20260713T110421Z`

| Metric | Value |
| --- | ---: |
| Events | `100` |
| Deploys | `10` |
| Submit span | `1.911s` |
| First inclusion | block `192`, non-final |
| First deploy to first inclusion added | `7.594541s` |
| Canonical block | block `195`, hash `5e491df6ff20...` |
| Canonical deploys | `10` |
| Canonical block size | `1,107,453` |
| Cost sum | `836,850` |
| Average cost per deploy | `83,685` |
| Cost per event | `8,368.5` |
| Compute | `5.098314s` |
| Propose total | `5.826s` |
| First deploy to canonical added | `33.158491s` |
| First deploy to finality | `52.747672s` |
| Added to finality | `19.589181s` |

Observed block history:

| Block | Hash prefix | Finalized | Batches | Cost | Size |
| ---: | --- | --- | ---: | ---: | ---: |
| `192` | `57292e93930d...` | no | 10 | `836,850` | `1,107,084` |
| `195` | `5e491df6ff20...` | yes | 10 | `836,850` | `1,107,453` |

### Restarted 10x25

Run id: `rspace-scale-10x25-20260713T110944Z`

| Metric | Value |
| --- | ---: |
| Events | `250` |
| Deploys | `10` |
| Submit span | `1.614389s` |
| First inclusion | block `243`, non-final |
| First deploy to first inclusion added | `8.172475s` |
| Canonical block | block `250`, hash `c67b188dbc11...` |
| Canonical deploys | `10` |
| Canonical block size | `1,276,066` |
| Cost sum | `1,370,550` |
| Average cost per deploy | `137,055` |
| Cost per event | `5,482.2` |
| Compute | `6.144702s` |
| Propose total | `6.944s` |
| First deploy to canonical added | `52.825635s` |
| First deploy to finality | `68.318159s` |
| Added to finality | `15.492524s` |

Observed block history:

| Block | Hash prefix | Finalized | Batches | Cost | Size |
| ---: | --- | --- | ---: | ---: | ---: |
| `243` | `4c6132aada14...` | no | 10 | `1,370,550` | `1,228,342` |
| `247` | `3755be7e2052...` | no | 10 | `1,370,550` | `1,228,045` |
| `250` | `c67b188dbc11...` | yes | 10 | `1,370,550` | `1,276,066` |

### Restarted 10x50

Run id: `rspace-scale-10x50-20260713T111104Z`

| Metric | Value |
| --- | ---: |
| Events | `500` |
| Deploys | `10` |
| Submit span | `3.889698s` |
| First inclusion | block `255`, finalized |
| First deploy to first inclusion added | `2.059186s` |
| Canonical blocks | `2` |
| Canonical block size sum | `1,444,314` |
| Cost sum | `2,259,850` |
| Average cost per deploy | `225,985` |
| Cost per event | `4,519.7` |
| Compute sum | `7.706084s` |
| Propose total sum | `9.079s` |
| First deploy to canonical added | `11.445296s` |
| First deploy to finality | `49.189927s` |
| Added to finality | `37.744631s` |

Canonical blocks:

| Block | Hash prefix | Batches | Cost | Size | Compute | Propose total |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| `255` | `8d451d77b924...` | 1 | `225,985` | `156,365` | `0.994566s` | `1.461s` |
| `256` | `0437f2fb7eed...` | 9 | `2,033,865` | `1,287,949` | `6.711518s` | `7.618s` |

Non-final duplicate:

| Block | Hash prefix | Batches | Cost | Size |
| ---: | --- | ---: | ---: | ---: |
| `258` | `2d3f3401b23e...` | 9 | `2,033,865` | `1,287,358` |

## 100x50 Restarted-Shard Run

Run id: `rspace-scale-100x50-20260713T123148Z`

Workload:

- 100 deploys submitted in one burst.
- 50 event traces per deploy.
- 5,000 declared event traces.
- Total Rholang term bytes: `4,169,300`.
- `validAfter`: `1056`.

### Summary

| Metric | Value |
| --- | ---: |
| Events | `5,000` |
| Deploys | `100` |
| Submit span | `33.631506s` |
| First inclusion | block `1057`, non-final, 10 batches |
| First deploy to first inclusion added | `11.614080s` |
| Canonical blocks | `4` |
| Canonical batch coverage | `100 / 100` |
| Canonical block size sum | `14,248,064` |
| Cost sum | `22,815,500` |
| Average cost per deploy | `228,155` |
| Cost per event | `4,563.1` |
| Compute sum | `105.777042s` |
| Propose total sum | `120.869s` |
| First deploy to canonical added | `552.458423s` |
| First deploy to finality | `594.820663s` |
| Added to finality | `42.362240s` |
| Throughput to canonical added | `9.050 events/s` |
| Throughput to finality | `8.406 events/s` |
| Errors | `0` |

### Submission Progress

The client submitted all 100 deploys successfully:

| Submitted | Elapsed |
| ---: | ---: |
| 10 | `2.023s` |
| 20 | `5.018s` |
| 30 | `7.568s` |
| 40 | `10.591s` |
| 50 | `14.901s` |
| 60 | `21.595s` |
| 70 | `25.204s` |
| 80 | `28.118s` |
| 90 | `30.882s` |
| 100 | `33.650s` |

### Canonical Blocks

The finalized coverage split into `32 + 32 + 32 + 4` deploys:

| Block | Hash prefix | Batches | Batch ids | Cost | Size | Compute | Propose total | Finality log |
| ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| `1083` | `5d1e365bb2f1...` | 32 | `0-30, 99` | `7,300,960` | `4,555,194` | `32.112527s` | `34.694s` | `12:41:32.162799Z` |
| `1084` | `3ebd15cca2c1...` | 32 | `31-61, 98` | `7,300,960` | `4,555,267` | `30.807812s` | `34.867s` | `12:41:32.162799Z` |
| `1085` | `8372b81da763...` | 32 | `62-92, 97` | `7,300,960` | `4,554,971` | `37.818269s` | `43.470s` | `12:41:32.162799Z` |
| `1086` | `8dd0b4587a97...` | 4 | `93-96` | `912,620` | `582,632` | `5.038434s` | `7.838s` | `12:41:43.672663Z` |

The ordering is not contiguous. The first three canonical blocks each included
31 contiguous batches plus one tail batch. The final 4-deploy block filled the
gap with batches `93`, `94`, `95`, and `96`.

### Coverage Timeline

Observed by recovery-aware scanner:

| Time | Hit blocks | Seen batches | Finalized batches |
| --- | ---: | ---: | ---: |
| `12:32:38Z` | 2 | 32 | 0 |
| `12:33:17Z` | 3 | 33 | 0 |
| `12:33:59Z` | 4 | 33 | 0 |
| `12:34:50Z` | 5 | 33 | 0 |
| `12:35:26Z` | 6 | 33 | 0 |
| `12:36:03Z` | 7 | 64 | 0 |
| `12:37:33Z` | 9 | 64 | 0 |
| `12:38:16Z` | 10 | 96 | 0 |
| `12:39:01Z` | 11 | 96 | 0 |
| `12:40:29Z` | 13 | 96 | 0 |
| `12:41:15Z` | 15 | 100 | 0 |
| `12:42:03Z` | 15 | 100 | 100 |

The shard had included all 100 batches before they were all finalized. Finality
arrived in a later sweep after the final 4-deploy recovery block.

### Support Proposals

Manual support proposals were issued while waiting for recovery/finality. The
benchmark artifact preserves the initial manual propose; the later support
proposals below are from the contemporaneous operator notes and node logs for
the same run.

| Purpose | Duration | Block prefix |
| --- | ---: | --- |
| Initial propose after submission | `12.893s` | `c207da872683...` |
| Recovery support | `18.865s` | `1efdca16402f...` |
| Recovery support | `48.927s` | `0ceaebf3ae8d...` |
| Recovery support | `61.093s` | `3ebd15cca2c1...` |
| Recovery support | `2.648s` | `057e978cf24d...` |

The long support proposals happened while a large pending/recovery set was in
scope. That time is part of the practical throughput limit for this local shard.

## Deploy-Inclusion Leadership Retest

The shard was retested after the f1r3fly-rust deploy-inclusion leadership
change. In this build, non-leader validators defer ordinary user-deploy
packaging and spend their proposals on finality support while the selected
deploy-inclusion leader packages user deploys.

The run reused the finalized scoped registry name:

```text
event-trace-memory:EventTraceRSpaceIndexUri:leadership-20260713T140641Z
```

The test submitted the same `10x10`, `10x25`, `10x50`, and `100x50`
batch-anchor workloads against the running shard. Each workload completed with
`errored: false` for the finalized canonical blocks.

### Leadership Retest Summary

| Run | Events | Submit span | Hit blocks | Finalized hit blocks | Canonical blocks | Cost/event | Canonical added | Finality | Finality throughput |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `10x10` | 100 | `5.046s` | 5 | 2 | 2 | `8,247` | `88.669s` | `334.446s` | `0.299 events/s` |
| `10x25` | 250 | `2.287s` | 6 | 1 | 1 | `5,334` | `20.592s` | `104.799s` | `2.386 events/s` |
| `10x50` | 500 | `2.055s` | 3 | 1 | 1 | `4,362` | `17.984s` | `72.796s` | `6.869 events/s` |
| `100x50` | 5,000 | `33.823s` | 5 | 4 | 4 | `4,384` | `183.729s` | `208.419s` | `23.990 events/s` |

### Leadership Versus Restarted Baseline

| Run | Baseline finality | Leadership finality | Finality ratio | Baseline canonical added | Leadership canonical added | Cost/event change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `10x10` | `52.748s` | `334.446s` | `6.34x slower` | `33.158s` | `88.669s` | `-1.45%` |
| `10x25` | `68.318s` | `104.799s` | `1.53x slower` | `52.826s` | `20.592s` | `-2.71%` |
| `10x50` | `49.190s` | `72.796s` | `1.48x slower` | `11.445s` | `17.984s` | `-3.49%` |
| `100x50` | `594.821s` | `208.419s` | `0.35x` | `552.458s` | `183.729s` | `-3.93%` |

The leadership change helped the large 100-deploy burst substantially:

- finality dropped from `594.821s` to `208.419s`,
- canonical coverage dropped from `552.458s` to `183.729s`,
- finality throughput improved from `8.406 events/s` to `23.990 events/s`,
- canonical block count stayed at 4, but the shard needed only 5 hit blocks
  instead of 15 observed hit blocks in the earlier recovery-aware run.

The 10-deploy runs did not show the same end-to-end improvement. They packaged
cleanly enough, and cost fell slightly, but finality remained dominated by
branch/recovery behavior. The `10x10` leadership run was especially poor: it
needed 5 hit blocks and finalized as 2 deploy-carrying blocks, which stretched
first deploy to finality to `334.446s`.

The conclusion is therefore workload-dependent. Deploy-inclusion leadership
reduces large-burst canonicalization time, but it does not eliminate finality
variance or non-final duplicate candidates on this local shard.

### 100x75 Leadership Probe

Run id: `rspace-leadership-100x75-20260713T182238Z`

This probe increased only the batch size: 100 deploys with 75 event pointers
per deploy, for 7,500 declared events. It did not complete as a finalized
benchmark.

| Metric | Value |
| --- | ---: |
| Events | `7,500` |
| Deploys | `100` |
| Submit span | `81.494s` |
| First selection | block `631`, `100` valid deploys |
| Selection cap | `32` deploys per block |
| Non-final hit blocks | `8` |
| Included batches | `100 / 100` |
| Finalized batches by `18:57:13Z` | `0 / 100` |
| First submit to last no-finality observation | `>2,075s` |
| Finality throughput upper bound | `<3.615 events/s` |

Observed non-final deploy blocks:

| Block | Hash prefix | Deploys | Batches | Cost | Finalized |
| ---: | --- | ---: | ---: | ---: | --- |
| `631` | `a39e23086140...` | 32 | 32 | `9,742,784` | no |
| `632` | `e8e1359baeb7...` | 32 | 32 | `9,742,784` | no |
| `634` | `0b0bb5b0a9ee...` | 32 | 32 | `9,742,784` | no |
| `635` | `19e9624e9280...` | 9 | 9 | `2,740,158` | no |
| `638` | `cda6504cde22...` | 32 | 32 | `9,742,784` | no |
| `639` | `3cf89c5e6bcd...` | 32 | 32 | `9,742,784` | no |
| `640` | `613225a91eab...` | 31 | 31 | `9,438,322` | no |
| `643` | `13fef763e382...` | 5 | 5 | `1,522,310` | no |

The first 32-deploy candidate illustrates the new bottleneck. Validator3
selected all 100 deploys at `18:24:39Z`, capped the block to 32 deploys, then
spent about `83.5s` in Rholang compute for that candidate
(`18:26:31Z` to `18:27:55Z`). The later 32-deploy candidates were similarly
expensive. Full logical inclusion arrived, but no deploy-carrying hit block was
finalized by the time polling stopped.

Validator3 restarted at `18:47:52Z` while the benchmark runner was polling, so
there is no normal finalized benchmark artifact for this run. A read-only scan
from validator1, validator2, and the restarted validator3 all showed the same
state: 8 non-final hit blocks, 100/100 included batches, and 0/100 finalized
batches.

Compared with `100x50`, `100x75` is a regression on this local shard:

- client submit span increased from `33.823s` to `81.494s`,
- canonical finality did not complete, versus `208.419s` for `100x50`,
- the finality-throughput upper bound fell below `3.615 events/s`, versus
  `23.990 events/s` for `100x50`,
- branch churn increased from 5 hit blocks to at least 8 non-final hit blocks.

The candidate phlo cost itself did not explode: a 32-deploy, 75-event candidate
cost `9,742,784`, or about `304,462` phlo per deploy and `4,059` phlo per
declared event. The problem was operational: larger deploy terms made each
selected block expensive enough that inclusion and recovery/finality became
unstable.

### 150x50 Degraded-Shard Probe

Run id: `rspace-leadership-150x50-20260713T193527Z`

This probe kept the total declared event count equal to `100x75` but split it
into more deploys: 150 deploys with 50 event pointers each, for 7,500 declared
events. It was run after the `100x75` branch had already left the shard with LFB
stuck at block `633` and multiple non-final deploy-carrying branches.

The first attempt against `rnode.validator3` submitted nothing because
validator3 restarted before `last-finalized-block` could be read. The measured
attempt used `rnode.validator1`, which was stable and connected to the shard.
The runner was stopped after a no-inclusion lower bound. Validator1 restarted
near the end of the observation window, so the conservative lower bound below
uses the time before that restart.

| Metric | Value |
| --- | ---: |
| Events | `7,500` |
| Deploys | `150` |
| Batch size | `50` |
| Valid after | `633` |
| Submit span | `47.082s` |
| DeployData entries received by validator1 | `150` |
| First inclusion before validator1 restart at `19:45:20Z` | none |
| Hit blocks before validator1 restart | `0` |
| Included batches before validator1 restart | `0 / 150` |
| Finalized batches before validator1 restart | `0 / 150` |
| First submit to last pre-restart zero-inclusion observation | `>593s` |
| Finality throughput upper bound | `<12.648 events/s` |

This is not a clean `150x50` throughput benchmark. It is a degraded-shard
failure probe. The useful result is where the path failed:

- client submission was fast: `150` deploys in `47.082s`, or `3.186 deploys/s`;
- validator1 logs confirmed `150` received deploy payloads for the run id;
- the benchmark scanner found no block containing the `150x50` run id;
- block proposal logs repeatedly showed finality-support-only proposals with
  `pool=0`, `valid=0`, and `selected=0` after ordinary deploy selection was
  deferred to the deploy-inclusion leader;
- LFB remained at block `633`, while new visible blocks above it were empty and
  non-final.

Representative log evidence:

| Time | Evidence |
| --- | --- |
| `19:36:14Z` | Runner reported `150/150` deploys submitted in `47.082s`. |
| `19:40:49Z` | Block `#641` proposal: `pool=0`, `valid=0`, `selected=0` after deploy selection was deferred. |
| `19:42:18Z` | Block `#647` proposal: `pool=0`, `valid=0`, `selected=0`; still finality support only. |
| `19:43:27Z` | A separate recovery proposal selected 5 recovered deploys, but the scanner still found 0 blocks for the `150x50` run id. |
| `19:45:20Z` | Validator1 restarted; no `150x50` hit block had been observed before restart. |
| `19:47:21Z` | Validator1 restarted again after the run was stopped; both observed exits were clean (`exit=0`, `oom=false`). |

Compared with `100x75`, `150x50` had a better client submit span but a worse
chain outcome:

| Metric | `100x75` | `150x50` |
| --- | ---: | ---: |
| Declared events | `7,500` | `7,500` |
| Deploys | `100` | `150` |
| Submit span | `81.494s` | `47.082s` |
| Included batches | `100 / 100` non-final | `0 / 150` |
| Finalized batches | `0 / 100` | `0 / 150` |
| Observation lower bound | `>2,075s` no finality | `>593s` no inclusion before restart |

So the `150x50` comparison does not show that smaller deploy terms fixed the
`100x75` problem. On the contrary, under the current shard state, the bottleneck
moved earlier: deploys were accepted by the node but did not enter any observed
deploy-carrying block for that run before the measurement was stopped.

### 150x50 Post-Fix Retest

Run id: `rspace-leadership-150x50-20260714T080824Z`

This run retested the same 150-deploy, 7,500-event workload after the shard was
restarted with deploy-inclusion leadership changes intended to let non-leaders
support finality instead of competing with leader-proposed user-deploy packaging.

The fresh scoped contract deployment was included before the workload run, but
the initial benchmark attempt timed out waiting for its finalized binding after
`600s`. The contract block finalized shortly afterward. The completed workload
run reused that existing URI:

```text
event-trace-memory:EventTraceRSpaceIndexUri:leadership-20260714T075701Z
```

The resumed benchmark found the contract binding in finalized block `217` in
`1.314s`, then submitted the workload.

| Metric | Value |
| --- | ---: |
| Events | `7,500` |
| Deploys | `150` |
| Batch size | `50` |
| Submit span | `105.702s` |
| First inclusion | `208.940s` |
| First all included | `1,035.536s` |
| Finality | `1,468.320s` |
| Inclusion to finality gap | `432.784s` |
| Finality throughput | `5.108 events/s` |
| Canonical deploy blocks | `5` |
| Total hit blocks observed | `15` |
| Total cost | `32,933,050` |
| Cost per deploy | `219,553.667` |
| Cost per event | `4,391.073` |

Canonical finalized coverage used five deploy-carrying blocks:

| Block | Hash prefix | Deploys | Cost | Size |
| ---: | --- | ---: | ---: | ---: |
| `227` | `ddc56b4227f2...` | `45` | `9,864,725` | `6,299,025` |
| `228` | `848dc70916c4...` | `32` | `7,015,229` | `4,484,726` |
| `231` | `27c7d4a800da...` | `32` | `7,021,739` | `4,487,807` |
| `254` | `eb0bbbf3a857...` | `32` | `7,048,864` | `4,493,052` |
| `255` | `984eb004d5bf...` | `9` | `1,982,493` | `1,273,972` |

The improvement over the degraded-shard `150x50` run is large but incomplete:

| Metric | Degraded `150x50` | Post-fix retest |
| --- | ---: | ---: |
| Submitted deploys | `150` | `150` |
| Submit span | `47.082s` | `105.702s` |
| First inclusion | none before `>593s` | `208.940s` |
| All included | never observed | `1,035.536s` |
| Finality | never observed | `1,468.320s` |
| Finalized batches | `0 / 150` | `150 / 150` |
| Finalized throughput | n/a | `5.108 events/s` |

The root bottleneck shifted. The earlier run failed before any observed
inclusion. The retest selected and finalized all work, but it still required
many branch attempts:

- workload selection appeared in proposer logs in chunks such as `32`, `45`,
  `47`, and `9`;
- total hit blocks were `15`, while only `5` were canonical finalized blocks;
- unique inclusion stalled at `109 / 150` for several minutes while duplicate
  non-final hit blocks accumulated;
- the final `41` deploys were repeatedly selected on competing branches before
  finalized blocks `254` and `255` completed coverage.

So the shard fix restored liveness for this workload, but it did not yet make
the `150x50` path fast enough for a high-throughput ingestion target. The
remaining problem is duplicate branch packaging plus finality lag, not Rholang
contract execution cost.

### 150x50 Current-Shard Retest Failure

Run id: `leadership-20260714T092913Z`

Artifact:
`docs/performance/artifacts/rspace-batch-anchor-leadership-150x50-retest-failed-20260714T092913Z.json`

This run was started after another shard restart and additional deploy-inclusion
changes. It did not produce a valid finalized throughput number.

Useful early signals:

- the scoped contract binding finalized in block `70` after `44.240s`;
- all `150` workload deploys were submitted in `56.290s`;
- proposer selection packed the workload as `15 + 49 + 86` selected deploys in
  observed blocks `77`, `81`, and `83`;
- validator1's benchmark output reached `150 / 150` included before a transient
  `show-blocks 100` failure aborted artifact writing.

The clean result failed after that point:

| Metric | Value |
| --- | ---: |
| Events | `7,500` |
| Deploys | `150` |
| Finalized deploys | `0 / 150` |
| LFB during health watch | pinned at block `81` |
| Health watch window | `2026-07-14T09:40:15Z` to `2026-07-14T09:45:54Z` |
| Validator1 restarts by `09:45:54Z` | `13` |
| Validator2 restarts by `09:45:54Z` | `11` |
| Observed hard-kill exit code | `137` |
| Observed high RSS | validator1 `27.36GiB`, validator2 `28.04GiB` |

The important behavioral failure is canonical reinclusion suppression. The DAG
contained user-deploy blocks such as:

| Block | Hash prefix | Deploys | Size | Finalized |
| ---: | --- | ---: | ---: | --- |
| `81` | `c3e5af67fb5d` | `49` | `6,858,798` | no |
| `83` | `225bd723fae2` | `86` | `12,038,226` | no |

The finalized branch's LFB hash was `4648a5ead8941dd2`, while the user-deploy
blocks above were not finalized. Subsequent block `84` proposals logged
`pool=150`, `valid=150`, `alreadyInScope=150`, `selected=0`. In other words,
the deploys were present in DAG scope but absent from canonical finalized
coverage, and the duplicate-scope filter prevented a leader from repackaging
them onto the branch that could finalize.

The retest therefore regressed from "slow but finalized" to "non-final
inclusion plus validator memory blow-up." It should not be compared as a
throughput improvement. The next shard fix should make deploy scope
canonical-aware, or otherwise allow deploys from non-final/losing branches to
be repackaged until finalized coverage exists. It should also cap or stream
DAG/scope processing; the alternating validator1/validator2 `27-28GiB` RSS
spikes and exit `137` restarts make large-run finality unrecoverable.

### 150x50 Retest After Additional Fixes

Run id: `rspace-leadership-150x50-20260714T113330Z`

Artifact:
`docs/performance/artifacts/rspace-batch-anchor-leadership-150x50-retest-failed-20260714T113330Z.json`

This retest was cleaner than the earlier `09:29Z` failed run, but it still did
not produce finalized workload coverage.

Positive changes:

- all shard containers started together at `2026-07-14T11:21:45Z` with `0`
  restarts before the run;
- the scoped contract binding finalized in block `70` after `32.264s`;
- all `150` workload deploys were submitted in `54.545s`;
- validator2 and validator3 stayed at `0` restarts through the final snapshot;
- sampled validator RSS stayed below `1GiB`, not the earlier `27-34GiB` range;
- the workload reached `150 / 150` logical batch inclusion in non-final blocks.

Failure state:

| Metric | Value |
| --- | ---: |
| Events | `7,500` |
| Deploys | `150` |
| Finalized deploys | `0 / 150` |
| Non-final hit blocks | `4` |
| Final LFB snapshot | block `127` |
| Validator1 restarts by `11:51:08Z` | `7` |
| Validator2 / validator3 restarts | `0 / 0` |
| Observed validator1 hard-kill exit code | `137` |

The hit blocks were visible from both validator2 and validator3:

| Block | Hash prefix | Deploys | Batch ids seen | Size | Cost | Finalized |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| `75` | `79ca799d3136` | `18` | `18` | `2,528,922` | `3,945,438` | no |
| `78` | `1fc5cf2ddcc8` | `64` | `64` | `8,954,085` | `14,028,224` | no |
| `79` | `eae5366fb280` | `86` | `86` | `12,037,202` | `18,904,676` | no |
| `84` | `ec357e5d3ede` | `128` | `128` | `17,898,997` | `28,086,828` | no |

The new cap behavior appeared in proposer logs:

- block `83`: `pool=150`, `valid=150`, `alreadyInScope=0`, `selected=128`,
  `deferred=22`, `cap=128`, `strategy=oldest-plus-newest`;
- block `84`: the same `selected=128`, `deferred=22` shape.

That is a real improvement over the prior `alreadyInScope=150`, `selected=0`
stall. But canonical finality still did not include the workload. Later block
`130` proposals showed the deploy lifetime problem:

- `pool=150`, `blockExpired=22`, `valid=0`, `selected=0`;
- later, `pool=128`, `blockExpired=0`, `valid=0`, `selected=0`.

So the remaining bottleneck shifted again. The shard can admit the full
`150x50` burst into non-final blocks without global memory blow-up, but it does
not get those deploys finalized before they expire or become non-selectable.
The next fix should either extend deploy lifetime for recovery, explicitly
recover deploys from non-final branches, or accelerate finality support for
deploy-carrying branches before the expiration window is crossed.

### 150x50 Deploy-Aware Parent Support Retest

Run id: `rspace-leadership-150x50-20260714T124211Z`

Artifact:
`docs/performance/artifacts/rspace-batch-anchor-parent-aware-150x50-retest-recovery-20260714T124211Z.json`

This retest ran after two shard-side fixes:

- deploy-aware parent support in `snapshot.rs`, which promotes the non-final
  parent branch with the most unfinalized deploy signatures after GHOST sorting;
- expiry cleanup in `block_creator.rs`, so block-expired deploys are no longer
  hidden from cleanup just because they are already in unresolved DAG scope.

The initial benchmark harness submitted the workload successfully but aborted
when one `is-finalized` RPC against validator3 timed out. The run was then
continued with a recovery monitor that used `show-blocks` finalization flags
across validator1, validator2, and validator3.

Outcome:

| Metric | Value |
| --- | ---: |
| Events | `7,500` |
| Deploys | `150` |
| Contract binding finality | block `46`, `27.750s` |
| Workload submit span | `51.368s` from deploy timestamps (`51.540s` harness observation) |
| First workload deploy timestamp | `2026-07-14T12:42:39.321Z` |
| All-included observation | `2026-07-14T12:52:52Z` |
| Finality observation | `2026-07-14T12:53:46Z` |
| All-included latency | `612.679s` |
| Finality latency | `666.679s` |
| Added-to-finality after all-included observation | `54.000s` |
| Finality throughput | `11.250 events/s` |
| Canonical blocks | `14` |
| Canonical cost | `32,933,200` |
| Cost/event | `4,391.09` |
| Canonical errored deploys | `0` |

Canonical block shape:

| Block | Hash prefix | Batches | Size | Cost |
| ---: | --- | ---: | ---: | ---: |
| `50` | `b0347f904f47` | `4` | `621,708` | `876,772` |
| `51` | `df1f48875ea0` | `14` | `1,970,465` | `3,068,702` |
| `52` | `f5fe7b3a43e7` | `45` | `6,300,127` | `9,863,685` |
| `53` | `8904dc9eac54` | `8` | `1,132,208` | `1,753,544` |
| `54` | `5ab48039212b` | `8` | `1,132,133` | `1,753,544` |
| `55` | `8be357a88b24` | `8` | `1,132,205` | `1,753,544` |
| `56` | `c99d45b7dcc1` | `8` | `1,132,505` | `1,753,544` |
| `57` | `27a51a6ef814` | `8` | `1,133,265` | `1,756,799` |
| `58` | `7cebedf5a198` | `8` | `1,134,758` | `1,762,224` |
| `59` | `ac7dd9377ae8` | `8` | `1,134,241` | `1,762,224` |
| `60` | `ba1b516e4175` | `8` | `1,182,037` | `1,762,224` |
| `61` | `1cbe76a30fc4` | `8` | `1,133,868` | `1,762,224` |
| `62` | `d8836569869e` | `8` | `1,134,460` | `1,762,224` |
| `63` | `92ee0241f0b2` | `7` | `994,298` | `1,541,946` |

The recovery monitor observed this finalized coverage progression:

| Time UTC | Included | Finalized | LFB |
| --- | ---: | ---: | ---: |
| `12:49:26` | `95 / 150` | `63 / 150` | `52` |
| `12:50:18` | `111 / 150` | `71 / 150` | `53` |
| `12:51:08` | `103 / 150` | `79 / 150` | `54` |
| `12:51:59` | `119 / 150` | `103 / 150` | `57` |
| `12:52:52` | `150 / 150` | `119 / 150` | `60` |
| `12:53:46` | `150 / 150` | `150 / 150` | `65` |

This fixes the previous `0 / 150` finalized-coverage failure. It does not make
the path single-block: the shard intentionally fell back to smaller deploy
chunks under backpressure. Logs showed cap `8` once recovery/backpressure was
active, with examples such as:

```text
block #55: pool=132, valid=132, alreadyInScope=61, selected=8
block #56: pool=132, valid=132, alreadyInScope=69, selected=8
block #62: pool=55, valid=55, alreadyInScope=40, selected=8
block #63: pool=31, valid=31, alreadyInScope=24, selected=7
```

The old expiry dead-end signature did not recur. During this run there was no
workload state matching `pool>0`, `valid=0`, `blockExpired=0`, `selected=0`.
After finality caught up, pending workload deploys drained to `pool=0`.

Compared with the prior successful `150x50` retest, finality latency improved
from `1,468.320s` to `666.679s` (`2.20x` faster), and finality throughput
improved from `5.108` to `11.250 events/s`. The tradeoff is more canonical
blocks: `14` instead of `5`.

## Cross-Run Analysis

### Cost Shape

| Run | Events | Deploys | Cost | Cost/deploy | Cost/event |
| --- | ---: | ---: | ---: | ---: | ---: |
| Detailed `10x10` | 100 | 10 | `853,989,673` | `85,398,967` | `8,539,897` |
| Restarted `10x10` | 100 | 10 | `836,850` | `83,685` | `8,369` |
| Restarted `10x25` | 250 | 10 | `1,370,550` | `137,055` | `5,482` |
| Restarted `10x50` | 500 | 10 | `2,259,850` | `225,985` | `4,520` |
| Restarted `100x50` | 5,000 | 100 | `22,815,500` | `228,155` | `4,563` |
| Post-fix `150x50` | 7,500 | 150 | `32,933,050` | `219,554` | `4,391` |
| Deploy-aware parent `150x50` | 7,500 | 150 | `32,933,200` | `219,555` | `4,391` |

The batch-anchor path makes deploy cost roughly proportional to batch anchor
term size, not to accumulated on-chain posting-list size. Cost per event falls
as batch size grows from 10 to 50 because the fixed per-deploy overhead is
amortized. The `10x50` and `100x50` cost per 50-trace deploy is nearly the same:

```text
10x50:   225,985 phlo/deploy
100x50:  228,155 phlo/deploy
```

That is the expected behavior for an anchor-first path.

### Latency Shape

| Run | Events | Submit span | First inclusion | Canonical added | Finality | Finality throughput |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Detailed `10x10` | 100 | `2.052s` | n/a | `3,505.692s` | `6,337.481s` | `0.0158 events/s` |
| Restarted `10x10` | 100 | `1.911s` | `7.595s` | `33.158s` | `52.748s` | `1.896 events/s` |
| Restarted `10x25` | 250 | `1.614s` | `8.172s` | `52.826s` | `68.318s` | `3.659 events/s` |
| Restarted `10x50` | 500 | `3.890s` | `2.059s` | `11.445s` | `49.190s` | `10.165 events/s` |
| Restarted `100x50` | 5,000 | `33.632s` | `11.614s` | `552.458s` | `594.821s` | `8.406 events/s` |
| Post-fix `150x50` | 7,500 | `105.702s` | `208.940s` | `1,035.536s` | `1,468.320s` | `5.108 events/s` |
| Failed 2026-07-14 `150x50` retest | 7,500 | `56.290s` | non-final only | none | stalled at LFB `81` | `0 events/s` |
| Failed 2026-07-14 post-fix `150x50` retest | 7,500 | `54.545s` | non-final only | none | LFB reached `127` with `0 / 150` finalized | `0 events/s` |
| Deploy-aware parent `150x50` retest | 7,500 | `51.368s` | n/a | `612.679s` | `666.679s` | `11.250 events/s` |

The `100x50` run had strong cost scaling but weaker latency scaling:

- It carried `10x` the events of `10x50`.
- Cost increased by `10.10x`, as expected.
- Finality time increased by `12.09x`.
- Finality throughput dropped from `10.165 events/s` to `8.406 events/s`.

The drop is not caused by Rholang posting-list growth. It is caused by deploy
selection/recovery/finality behavior. The 100-deploy workload did not finalize
as one block; it required four canonical blocks and several non-final duplicate
branches.

### Pre-Restart Versus Restarted Shard

| Run | Pre-restart | Restarted | Change |
| --- | ---: | ---: | ---: |
| `10x10` | failed / no finalized block | finalized in `52.748s` | fixed |
| `10x25` cost | `17,380,500` | `1,370,550` | `0.0789x` |
| `10x25` compute | `25.234s` | `6.145s` | `0.244x` |
| `10x25` finality | `156.766s` | `68.318s` | `0.436x` |
| `10x50` cost | `50,265,175` | `2,259,850` | `0.0450x` |
| `10x50` canonical added | `82.242s` | `11.445s` | `0.139x` |
| `10x50` finality | not finalized after `>112m` | finalized in `49.190s` | fixed |

The restart changed the operational profile dramatically. The same
batch-anchor contract path became cheaper and finalized reliably, but the
larger `100x50` workload still exposed deploy recovery as a scaling limit.

## Query-Latency Coverage

These batch runs measured ingestion, inclusion, and finality. They did not
measure end-to-end detailed event-trace lookup latency.

That distinction matters because the optimized path intentionally changed what
is stored on-chain:

- `putBatchEvents` writes batch anchors and DA manifest pointers.
- Detailed event facts are not indexed unless a caller explicitly uses
  `putEventFact` or `putBatchEventFacts`.
- A detailed lookup in the production-shaped path must resolve the on-chain
  batch anchor, fetch or read the DA manifest, and then inspect the event trace
  payload outside the global Rholang posting lists.

The legacy detailed path supported direct on-chain event indexing, but its
100-event ingestion cost was already prohibitive. Future lookup benchmarks
should therefore report two separate numbers:

1. Anchor lookup latency from finalized RSpace state.
2. Detailed event lookup latency through the DA manifest path.

## Findings

1. The detailed per-event on-chain index is not viable for production ingestion.
   The 100-event detailed run spent `3,496s` in Rholang compute and cost
   `853,989,673` phlo because global list-backed postings grew with every event.

2. Batch-anchor-first is the correct on-chain shape for bulk ingestion.
   The restarted `10x50` and `100x50` runs both cost about `226k` to `228k`
   phlo per 50-trace deploy, with no accumulated posting-list explosion.

3. Larger batch size improves cost per declared event.
   Restarted runs moved from `8,369` phlo/event at `10x10` to about `4,520`
   phlo/event at `10x50` and `4,563` phlo/event at `100x50`.

4. The local shard usually selects around 32 deploys per useful deploy-carrying
   block for this workload, with occasional larger chunks.
   The `100x50` run finalized as `32 + 32 + 32 + 4` deploys; the post-fix
   `150x50` run finalized as `45 + 32 + 32 + 32 + 9`.

5. Recovery/finality, not contract execution, dominates large-run latency.
   In `100x50`, canonical Rholang compute summed to `105.777s`, but finality
   took `594.821s`. The gap was deploy recovery, branch churn, support
   proposals, and finality wait.

6. First inclusion is not a reliable success metric on this shard.
   Multiple runs first appeared in non-final blocks and later reappeared in
   finalized blocks. All future benchmark reports should distinguish first
   inclusion from canonical finalized coverage.

7. Deploy-inclusion leadership materially improved the large burst but did not
   make small bursts uniformly faster. The `100x50` finality latency improved
   from `594.821s` to `208.419s`, while `10x10`, `10x25`, and `10x50` all had
   slower finality than the restarted baseline.

8. The 2026-07-14 failed `150x50` retest exposed a worse canonicality bug:
   non-final deploy branches can suppress canonical reinclusion. All `150`
   deploys were filtered as `alreadyInScope` in later proposals, while
   finalized coverage remained `0 / 150` and validator1/validator2 entered
   exit-`137` restart loops with roughly `27-28GiB` RSS spikes.

9. The later 2026-07-14 retest fixed part of that failure but not finality.
   It avoided the global memory blow-up and admitted all `150` logical batches
   into non-final blocks, but finalized coverage stayed `0 / 150` after LFB
   reached `127`. Later proposals selected zero valid deploys after expiration
   or non-selectability, so deploy lifetime/recovery now gates canonical
   inclusion.

10. Deploy-aware parent support plus in-scope expiry cleanup fixed the
    `150x50` canonical inclusion failure in the next retest. The same 7,500
    event workload finalized all `150` batches in `666.679s`, with no deploy
    errors and no recurrence of the `pool>0 valid=0 blockExpired=0 selected=0`
    expiry dead end.

## Recommendations

1. Keep production ingestion on `putBatchAnchor` or compatibility
   `putBatchEvents`, with detailed event facts in DA manifests.

2. Treat `putBatchEventFacts` and `putEventFact` as opt-in debugging or small
   materialization paths, not as the bulk data plane.

3. Benchmark with recovery-aware accounting:
   - track batch ids across all hit blocks,
   - report first inclusion separately,
   - report only finalized canonical coverage as completion.

4. Add benchmark guardrails:
   - fail or flag when canonical coverage requires duplicate non-final branches,
   - record proposer selected deploy count,
   - record pending-deploy recovery logs,
   - record LFB at submit, first inclusion, canonical inclusion, and finality.

5. If the target workload is thousands of traces per minute, reduce deploy
   count before increasing batch count:
   - prefer fewer larger anchors,
   - aggregate 50-trace manifests into larger DA manifests when possible,
   - avoid client bursts of 100 independent deploys if the shard selects about
     32 deploys per canonical block.

6. For the next benchmark, test larger anchor batches with fewer deploys, for
   example `10x100`, `10x250`, and `10x500`, to separate per-deploy shard
   overhead from per-byte Rholang term overhead.

7. Keep the deploy-aware parent support and in-scope expiry cleanup regression
   tests in the shard. They are now directly tied to an observed production
   benchmark improvement: `0 / 150` finalized before the fix, `150 / 150`
   finalized after it.

8. Add a specific recovery test for deploy lifetime: submit `150x50` with the
   current selection cap, then assert that deploys first seen in non-final
   blocks are either finalized or reselected before `validAfterBlockNumber`
   crosses the expiry threshold.

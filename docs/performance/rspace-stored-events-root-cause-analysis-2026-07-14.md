# RSpace Stored Events Root Cause Analysis - 2026-07-14

## Incident

The stored-event snapshot probe deployed the live `percept-memory` pointer log
through the RSpace batch-anchor path:

```text
rspace-stored-events-batch-anchor-20260714T181331Z
```

The client submitted all stored events successfully:

| Metric | Value |
| --- | ---: |
| Stored event pointers | `54,543` |
| Batch size | `100` events/deploy |
| Deploys submitted | `546` |
| Submit span | `469.636s` |
| Submit acceptance throughput | `116.139 events/s` |
| Workload `validAfterBlockNumber` | `206` |

Full canonical ingestion failed. As of `2026-07-14T18:51:08Z`, every checked
node still reported LFB `223` and latest block `226`. That was `1,940.557s`
after the last observed deploy-carrying block, block `226`, was timestamped.

## Executive Conclusion

The root cause is a proposer/finality failure after a large non-final deploy
block, not Rholang contract execution and not client submission.

Block `226` carried `128` stored-event deploys, took `299.504s` to propose, and
remained non-final. After that, the deploy-inclusion leader repeatedly selected
new deploys for block `227`, but every block `227` attempt restarted before a
`Propose finished` log and no block `227` became visible in the DAG.

At the same time, the branch state was already pathological:

- LFB was stuck at `223`.
- The DAG scope above LFB had grown to `206` blocks.
- The leader saw `520` valid deploys, but `136` were already in non-final DAG
  scope.
- The remaining fresh work stayed local and selectable, but selected deploys
  did not become an accepted block.

So the immediate failure is: **selected deploys did not survive block creation
after the large block `226`; the proposer restarted before publishing block
`227`, and support/finality never moved past LFB `223`.**

## Canonical Coverage

All checked nodes agreed on coverage:

| Node | Hit blocks | Included batches | Finalized batches |
| --- | ---: | ---: | ---: |
| `rnode.validator1` | 7 | 162 | 26 |
| `rnode.validator2` | 7 | 162 | 26 |
| `rnode.validator3` | 7 | 162 | 26 |
| `rnode.bootstrap` | 7 | 162 | 26 |

Coverage against the submitted workload:

| Metric | Value |
| --- | ---: |
| Finalized batches | `26 / 546` (`4.762%`) |
| Finalized events | `2,600 / 54,543` (`4.767%`) |
| Included batches, finalized + non-final | `162 / 546` (`29.670%`) |
| Included events, finalized + non-final | `16,200 / 54,543` (`29.701%`) |
| Not observed in any hit block | `384 / 546` batches |

The non-final branch carried most of the observed work:

| Metric | Finalized | Non-final | Observed total |
| --- | ---: | ---: | ---: |
| Batches | 26 | 136 | 162 |
| Cost | `14,334,161` | `75,589,206` | `89,923,367` |
| Block bytes | `5,597,295` | `29,177,427` | `34,774,722` |

Block `226` alone was `79.172%` of observed cost and `78.925%` of observed
bytes.

## Block Timeline

| Block | Hash prefix | Timestamp | Batches | Finalized | Cost | Size |
| ---: | --- | --- | ---: | --- | ---: | ---: |
| `211` | `90b88df31fe0` | `18:15:04.896Z` | 0-5 | yes | `3,296,937` | `1,290,113` |
| `214` | `ea7edaa2744b` | `18:15:49.158Z` | 6-13 | yes | `4,418,998` | `1,720,781` |
| `218` | `cc0030467ad8` | `18:16:44.123Z` | 14-21 | yes | `4,412,837` | `1,719,474` |
| `223` | `8949bfb04330` | `18:17:31.721Z` | 22-25 | yes | `2,205,389` | `866,927` |
| `224` | `b75faf07ba28` | `18:17:57.700Z` | 26-29 | no | `2,200,926` | `866,432` |
| `225` | `f542c19b7e2a` | `18:18:18.204Z` | 30-33 | no | `2,194,256` | `865,133` |
| `226` | `01bfa14540be` | `18:18:47.443Z` | 34-160, 205 | no | `71,194,024` | `27,445,862` |

Block `226` metrics:

| Metric | Value |
| --- | ---: |
| Deploys | `128` |
| Events represented | `12,800` |
| Size | `26.174 MiB` |
| Cost/event | `5,562.033` |
| Bytes/event | `2,144.208` |
| Proposal time | `299.504s` |
| Proposal time/deploy | `2.340s` |
| Proposal throughput | `42.737 events/s` |

The block did not error at Rholang level: `errors=0`.
Its batch-id coverage was not contiguous: it included `34-160` and `205`,
leaving `161-204` and `206-545` unobserved.

## Post-226 Retry Loop

The critical transition happened after block `226`:

```text
18:18:50Z block #226 selected=128
18:23:46Z Propose timing: total_ms=299504
18:23:46Z Block #226 created and added
18:23:49Z Creating block #227
18:23:56Z block #227 selected=8, pool=520, valid=520, alreadyInScope=136
18:25:10Z validator3 runtime restarted before block #227 finished
```

After that, the same pattern repeated. Parsed `validator3` logs showed 20
measured block `#227` attempts with selection data:

| Metric | Value |
| --- | ---: |
| Attempts with `selected=8` | `20` measured |
| Attempts that reached `Propose finished` | `0` |
| Attempts ending in runtime restart | `20` |
| Selection pool on every attempt | `520` |
| Valid deploys on every attempt | `520` |
| Already-in-scope deploys on every attempt | `136` |
| Deferred deploys on every attempt | `376` |
| Typical restart after selection | `56-106s` |

Later logs continued the same shape. As of `18:51Z`, `validator3` had logged
`22` creates for block `#227` and zero successful block `#227` completions.

This rules out "no deploys were eligible" as the direct cause. The leader found
eligible work and selected it. The failure occurred after selection, while
building or publishing the next block on top of the non-final deploy branch.

## Validator Roles During The Stall

`validator3` was the only node observed repeatedly selecting user deploys for
block `#227`:

```text
pool=520 valid=520 alreadyInScope=136 selected=8
```

`validator2` mostly produced support-only attempts:

```text
Ordinary user deploy selection deferred to deploy-inclusion leader
pool=0 valid=0 selected=0
```

Recent log counters over the analysis window:

| Node | Runtime restarts | Block `#227` creates | `selected=0` logs | Support-only deferrals | Already-in-scope filters |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rnode.validator2` | 20 | 19 | 156 | 39 | 0 |
| `rnode.validator3` | 23 | 22 | 122 | 8 | 3,528 |

Docker state as of the final check:

| Node | Restart count | OOM killed | Exit code | Last start |
| --- | ---: | --- | ---: | --- |
| `rnode.validator1` | 1 | false | 0 | `2026-07-14T18:00:09.91829188Z` |
| `rnode.validator2` | 19 | false | 0 | `2026-07-14T18:50:32.048389575Z` |
| `rnode.validator3` | 22 | false | 0 | `2026-07-14T18:51:11.696874703Z` |

There is no Docker OOM-kill evidence. The logs show repeated clean-looking
runtime reinitialization, but the effect is the same for the workload: proposer
state is lost before block `#227` is emitted.

## Why This Was Not The Contract

The Rholang batch-anchor path is not the observed bottleneck:

- all deploys were accepted by the node;
- early stored-event batches finalized successfully;
- block `226` executed `128` deploys with `errors=0`;
- per-event cost stayed near prior batch-anchor results, around
  `5,562 phlo/event` for block `226`;
- after block `226`, eligible deploys remained in the pool, but selected block
  `#227` attempts never produced an accepted block.

The contract can still be made smaller by not passing inline event pointers to
`putBatchEvents`, but that is not enough to explain the failure. The current
failure is at the proposer/finality layer after the large block exists.

## Root Cause

Primary cause:

The shard cannot make canonical progress after a large non-final deploy block.
Block `226` was large enough to take about five minutes to propose. Once it was
added but not finalized, the DAG above LFB grew to roughly `206` blocks. The
next deploy-bearing block repeatedly got as far as selecting deploys, then the
leader restarted before publishing the block.

Secondary cause:

Deploy-inclusion leadership prevents non-leaders from competing with fresh user
deploy packaging, but the selected leader is not completing its own block. That
turns leadership into a single point of liveness for user deploys: non-leaders
support or select zero, while the leader repeatedly restarts mid-proposal.

Contributing factors:

1. **Large block #226 amplified DAG merge cost.** The successful `128`-deploy
   block took `299.504s` to propose and left a `26.174 MiB` non-final branch.

2. **The next proposal starts from a huge non-final scope.** Post-selection logs
   report `DagMerger.merge: scope=207 blocks, actualBlocks=206`.

3. **The retry cap is too small to drain the backlog after the stall.** Even if
   block `#227` succeeded, `selected=8` with `deferred=376` would need dozens of
   successful blocks to drain the fresh backlog.

4. **Already-in-scope suppression is now noisy and expensive.** `validator3`
   emitted thousands of already-in-scope filters while still seeing `520` valid
   deploys.

5. **Support-only proposals do not resolve the deploy branch.** `validator2`
   repeatedly tried support-only block `#227` with `selected=0`, while LFB
   stayed at `223`.

## Recommended Fixes

1. **Bound deploy block size by proposal time and bytes, not only deploy count.**
   A `128`-deploy block took `299.504s` and produced a `26.174 MiB` block. The
   cap should drop before proposals exceed a target such as `10-30s`.

2. **Make deploy-inclusion leadership fail over.** If the leader selects deploys
   but does not publish a block within a bounded window, another validator
   should be allowed to package the same fresh deploys or become the temporary
   inclusion leader.

3. **Treat non-final in-scope deploys as recoverable, not suppressive.** A deploy
   in a non-final branch should not block re-packaging indefinitely. In-scope
   should be scoped to finalized or actively supported branches, or have a short
   timeout when LFB is stale.

4. **Make support proposals explicitly support the deploy-heavy branch.** If
   block `226` contains deploy work and LFB is at `223`, support blocks should
   bias toward the `226` branch instead of creating repeated block `#227`
   attempts that do not advance finality.

5. **Add a stuck-propose watchdog with diagnostics.** The logs currently show
   restart but not the exact internal reason. The watchdog should emit the
   current stage, memory, DAG scope size, parent set, selected deploy count, and
   elapsed time before restarting.

## Regression Tests

1. Submit a real-size `546x100` workload or an equivalent byte-volume synthetic
   workload.

2. Force or permit a `25-30 MiB` non-final deploy block.

3. Assert one of these outcomes within a bounded time:
   - that block finalizes; or
   - the deploys are reselected into a finalized branch; or
   - leadership fails over and another validator packages fresh deploys.

4. Fail the test if:
   - LFB remains unchanged for more than the configured recovery window;
   - the same node creates block `#227` repeatedly without any `Propose
     finished` event;
   - selected deploys are followed by runtime restart more than once for the
     same height;
   - non-leaders select zero while the leader is repeatedly failing to publish.

5. Track block bytes, proposal time, DAG scope size, and selected deploys as
   first-class metrics.

## Bottom Line

The stored-events run proved the batch-anchor contract can accept and execute
real event pointers, but the shard cannot yet guarantee canonical progress for
a full stored snapshot. The breaking point was not `54,543` events directly. It
was the combination of a large non-final deploy block, a huge post-LFB DAG
scope, and deploy-inclusion leadership without fast failover when the leader
restarted before publishing the next block.

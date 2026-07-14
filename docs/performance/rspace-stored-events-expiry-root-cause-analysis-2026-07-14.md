# Stored Events Deploy Expiry Root Cause Analysis - 2026-07-14

## Scope

This RCA explains why the post-restart stored-event retest expired most of the
accepted deploys.

Run id:
`rspace-stored-events-batch-anchor-20260714T211039Z`

Artifact:
`docs/performance/artifacts/rspace-stored-events-batch-anchor-retest-partial-20260714T211039Z.json`

Shard source inspected:
`/home/purplezky/work/asi/f1r3node-rust`, branch
`fix/merge-recovery-finalization`, commit
`6012c6a3 Bound deploy admission by encoded bytes`.

## Outcome

The runner submitted all stored events:

| Metric | Value |
| --- | ---: |
| Submitted events | `54,647` |
| Submitted deploys | `547` |
| Batch size | `100` events/deploy |
| Submit span | `593.905s` |
| Submit acceptance rate | `92.013 events/s` |
| Workload `validAfterBlockNumber` | `219` |
| Finalized batches | `160 / 547` |
| Finalized events | `16,000 / 54,647` |
| Missing batches | `387 / 547` |
| Missing events | `38,647 / 54,647` |
| Rholang errors in finalized deploy blocks | `0` |

The deploys expired at proposer block `269`:

```text
Deploy selection for block #269: pool=399, future=0
(validAfterBlockNumber >= 269), blockExpired=399
(validAfterBlockNumber <= 219), timeExpired=0, valid=0,
alreadyInScope=0, selected=0
```

This was block-height expiry, not wall-clock expiry. `timeExpired=0`.

## Expiry Rule

The node source sets deploy lifespan to `50` blocks:

- `node/src/rust/runtime/setup.rs`: `deploy_lifespan: 50`
- `casper/src/rust/engine/casper_launch.rs`: `deploy_lifespan: 50`

The proposer computes:

```text
earliest_block_number = block_number - deploy_lifespan
```

and filters deploys when:

```text
validAfterBlockNumber <= earliest_block_number
```

For this run:

| Value | Calculation |
| --- | ---: |
| `validAfterBlockNumber` | `219` |
| `deploy_lifespan` | `50` |
| First eligible block height | `220` |
| Last eligible block height | `268` |
| Expiry block height | `269` |

At block `268`, `earliestBlock=218`, so `validAfter=219` was still valid.
At block `269`, `earliestBlock=219`, so every remaining `validAfter=219`
deploy was block-expired and then removed from deploy storage.

## Capacity Calculation

The retest used one fixed `validAfter=219` for all `547` deploys. Therefore the
entire burst had to fit into the lifespan window ending at block `268`.

The theoretical valid block-height window was `220..268`, or `49` block
heights. Stored-event deploys were not actually available for selection until
block `227`, because the client was still submitting the burst. From block
`227` through block `268`, there were `42` possible block heights and `40`
actual deploy-carrying blocks.

Every deploy-carrying block selected exactly `4` stored-event deploys:

| Metric | Value |
| --- | ---: |
| Deploy-carrying blocks before expiry | `40` |
| Deploys selected per deploy-carrying block | `4` |
| Deploys finalized before expiry | `160` |
| Deploys submitted | `547` |
| Shortfall | `387` deploys |

At `4` deploys/block, the workload needed:

```text
ceil(547 / 4) = 137 deploy-carrying blocks
```

Only `40` deploy-carrying blocks happened before expiry. The run was short by
`97` deploy-carrying blocks.

## Why Only 4 Deploys Per Block?

The current shard source has two deploy byte budgets:

| Budget | Value |
| --- | ---: |
| Normal user deploy byte budget | `2,097,152` bytes |
| Backpressure user deploy byte budget | `524,288` bytes |

Backpressure turns on when finality lag is at least `4` blocks. The logs show
the run was in backpressure mode throughout the useful selection window. Before
stored batches started, logs already showed `lfb_lag=11..16` and
`backpressure=true`. During the stored-event drain, blocks continued with
`backpressure=true`.

The active byte budget was therefore `524,288` bytes.

Observed byte-budget selection:

| Metric | Value |
| --- | ---: |
| Byte-capped deploy blocks | `40` |
| Average selected bytes/block | `455,964.925` |
| Median selected bytes/block | `454,651.5` |
| Min/max selected bytes/block | `448,795` / `490,961` |
| Average selected bytes/deploy | `113,991.231` |

The last deploy-carrying block before expiry reported:

```text
Deploy selection byte budget capped block #268:
selected_bytes=490961, deferred_bytes=45055798,
byte_budget=524288, selected=4, deferred=387
```

So the count cap was not the effective limiter. The byte budget was. A fifth
real stored-event deploy would exceed the 512 KiB backpressure budget.

To drain the submitted burst in the available window:

| Window assumption | Required deploys/block | Approx byte budget at observed bytes/deploy |
| --- | ---: | ---: |
| Full `49`-height lifespan window | `11.16` | about `1.37 MiB` for 12 deploys |
| Actual `42` heights after stored deploys appeared | `13.02` | about `1.60 MiB` for 14 deploys |
| Actual `40` deploy-carrying blocks | `13.68` | about `1.60 MiB` for 14 deploys |

The active budget was only `0.5 MiB`.

## Timeline

Approximate timing from run output and logs:

| Event | Time |
| --- | ---: |
| Scoped contract finalized | after `195.564s` |
| Workload began with `validAfter=219` | about `21:13:55Z` |
| First stored deploy selection, block `227` | `21:14:25.978863Z` |
| Submit loop finished | about `21:23:49Z` |
| Last deploy-carrying selection, block `268` | `21:38:30.334267Z` |
| Expiry selection, block `269` | `21:39:35.369293Z` |

Elapsed:

| Interval | Duration |
| --- | ---: |
| Workload start to expiry | `1,539.905s` |
| First stored selection to expiry | `1,509.390s` |
| Submit finish to expiry | `946.000s` |

The deploys expired after about `25.7` minutes from workload start, but the
protocol decision was block-height based. Once block `269` was proposed, the
height window closed regardless of remaining backlog.

## Causal Chain

1. The runner chose `validAfter=219` once from the LFB and reused it for all
   `547` deploys.

2. The protocol gives deploys a `50`-block lifespan. For `validAfter=219`, the
   last selectable block was `268`.

3. The shard was already in finality-lag backpressure. Backpressure reduced the
   deploy byte budget from `2 MiB` to `512 KiB`.

4. Each stored-event deploy carried inline pointers for up to `100` real
   events. The encoded deploy size was around `114 KiB`, so only `4` fit under
   the active byte budget.

5. The submit loop itself took `593.905s`, so the full backlog was not available
   near the beginning of the valid block-height window.

6. The proposer produced `40` byte-capped deploy-carrying blocks before block
   `269`, selecting `160` deploys.

7. At block `269`, the remaining `399` pool deploys were block-expired. This
   set corresponds to the `387` never-canonical deferred deploys plus `12`
   deploys that had been counted as already in scope at block `268`.

8. Expired deploy cleanup removed them from storage. Blocks after `269` showed
   `pool=0`.

## Not The Cause

- Not Rholang execution: finalized deploy blocks had `0` Rholang errors.
- Not time expiration: the expiry log had `timeExpired=0`.
- Not finality of included work: all observed run batches were finalized.
- Not the prior non-final huge-block dead end: this retest did not stall on a
  25-30 MiB non-final deploy block. It drained cleanly until the lifespan
  boundary.

## Root Cause

The accepted deploy burst exceeded the shard's guaranteed inclusion capacity
inside a 50-block deploy lifespan.

The immediate limiter was the 512 KiB backpressure byte budget. The structural
cause was that deploy admission accepted a 547-deploy, real-pointer, inline
payload burst without either:

- pacing it to the measured byte-budget drain rate,
- assigning fresher `validAfter` values as the burst progressed,
- extending lifespan for accepted backlog,
- rejecting deploys that could not be included before expiry, or
- shrinking the on-chain deploy payload to anchor-only terms.

## Fix Direction

1. Keep the encoded-byte bound; it prevented another giant non-final block.

2. Add admission backpressure before deploy acceptance. If pending bytes exceed
   `remaining_lifespan_blocks * active_byte_budget`, the API should reject or
   ask the client to retry later instead of accepting deploys that will expire.

3. Stop using one fixed `validAfter` for a long burst. The client runner should
   refresh `validAfter` per chunk or pace batches against observed finality.

4. Avoid inline event-pointer payloads for production-scale ingestion. Use
   anchor-only deploys that reference DA manifests. The current compatibility
   path proves contract cost is stable, but the deploy terms are too large for
   byte-budgeted inclusion under backpressure.

5. Add a regression for this exact shape:
   `547x100` real-size deploys, `deploy_lifespan=50`, backpressure budget
   `512 KiB`, and assert that accepted deploys either finalize or receive a
   clear admission failure before block expiry.

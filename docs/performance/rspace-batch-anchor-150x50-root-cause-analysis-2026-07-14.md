# RSpace Batch Anchor 150x50 Root Cause Analysis - 2026-07-14

## Incident

The post-fix `150x50` retest submitted 150 deploys, each anchoring 50 event
traces, against a freshly deployed scoped batch-anchor contract:

```text
event-trace-memory:EventTraceRSpaceIndexUri:leadership-20260714T113330Z
```

The shard accepted the workload and executed all 150 logical batches into
deploy-carrying blocks. None of those blocks became canonical. Finalized
coverage stayed at `0 / 150` while the last finalized block advanced to `127`.

This was a different failure mode from the prior `2026-07-14T092913Z` retest.
The prior run combined non-final deploy branches with all-node memory pressure
and repeated restarts. In this run, memory stayed below `1 GiB` in the captured
samples for validator1, validator2, and validator3, and validator2/validator3
remained stable. The remaining problem was canonical inclusion.

## Executive Conclusion

The root cause is canonical-branch starvation of deploy-heavy proposals,
followed by deploy lifetime expiry that prevented recovery.

The Rholang batch-anchor contract was not the bottleneck. Contract deployment
finalized in `32.264s`, the client submitted all 150 workload deploys in
`54.545s`, and the shard executed all 150 logical batches into non-final
blocks. The workload failed because the blocks that carried those deploys were
slower to construct and lost finality to same-height or later zero-deploy
support blocks.

Once those deploys were visible in non-final DAG scope, the proposer filters
treated them as already present or invalid after the lifespan window. The final
recovery path then selected no deploys, and finalized coverage remained zero.

## Key Measurements

| Measurement | Value |
| --- | ---: |
| Run id | `rspace-leadership-150x50-20260714T113330Z` |
| Workload | `150` deploys x `50` traces |
| Declared events | `7,500` |
| Contract finality | `32.264s`, block `70` |
| Workload `validAfterBlockNumber` | `71` |
| Workload submit span | `54.545s` |
| Logical batches included in non-final blocks | `150 / 150` |
| Logical batches finalized | `0 / 150` |
| Last finalized block during analysis | `127` |
| Canonical throughput | `0 events/s` |
| Non-final deploy hit blocks | `4` |
| Non-final deploy hit block sizes, summed | `41,419,206 bytes` (`39.50 MiB`) |
| Largest non-final deploy hit block | `17,898,997 bytes` (`17.07 MiB`) |
| Non-final deploy hit costs, summed | `64,965,166 phlo` |

The non-final cost sum is useful as an execution-size signal, but it is not a
canonical workload cost because the deploy-carrying blocks did not finalize and
some logical batches appeared in multiple non-final branches.

## Canonical vs Non-Canonical Evidence

Validator2 and validator3 both saw the same four deploy-carrying hit blocks:

| Block | Hash prefix | Finalized | Deploys | Batches | Size bytes | Cost |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| `75` | `79ca799d3136` | no | `18` | `18` | `2,528,922` | `3,945,438` |
| `78` | `1fc5cf2ddcc8` | no | `64` | `64` | `8,954,085` | `14,028,224` |
| `79` | `eae5366fb280` | no | `86` | `86` | `12,037,202` | `18,904,676` |
| `84` | `ec357e5d3ede` | no | `128` | `128` | `17,898,997` | `28,086,828` |

At the same heights, the finalized branch chose zero-deploy siblings:

| Height | Finalized block | Deploys | Non-final deploy block |
| ---: | --- | ---: | --- |
| `75` | `32f4e3e9ab94` | `0` | `79ca799d3136`, `18` deploys |
| `78` | `c41642e79c18` | `0` | `1fc5cf2ddcc8`, `64` deploys |
| `79` | `7e4f29756ecc` | `0` | `eae5366fb280`, `86` deploys |
| `84` | `984899e9c42f` | `0` | `ec357e5d3ede`, `128` deploys |

The finalized chain then continued through zero-deploy blocks. Blocks `91`,
`119`, `121`, `123`, `125`, and `127` were finalized with `0` deploys. This
rules out an LFB stall as the primary cause: finality moved, but it moved on
the wrong branch for the workload.

## Proposer Timing

Validator1 built deploy-heavy proposals, but proposal time grew with body size:

| Block | Selected/logical deploys | Final block deploys | `propose_core` | Approx seconds per final deploy |
| ---: | ---: | ---: | ---: | ---: |
| `75` | `18` | `18` | `18.689s` | `1.038s` |
| `78` | `82` selected, `18` self-chain filtered | `64` | `67.556s` | `1.056s` |
| `79` | `86` | `86` | `116.122s` | `1.350s` |
| `84` | `128` | `128` | `195.507s` | `1.527s` |

The `128`-deploy proposal took more than three minutes to construct. During
that window, other validators could continue producing and supporting small
zero-deploy blocks. The result was not missing execution; it was losing
canonical finality to faster support branches.

## Deploy Recovery and Expiry Evidence

The workload used `validAfterBlockNumber=71`. Later, at block `130`, validator1
reported:

```text
pool=150 valid=0 blockExpired=22 selected=0
validAfterBlockNumber=71 <= earliestBlock=80
Removing 22 expired deploy(s) from storage and rejected-deploy buffer
```

The `22` count matches the deploys deferred by the `128` deploy cap at blocks
`83` and `84`.

Validator1 later reported:

```text
pool=128 valid=0 blockExpired=0 selected=0
```

That second state is the recovery dead end. The remaining 128 deploys were
already seen in DAG scope, but they were not finalized. They were invalid for
selection after the lifespan window and also not counted as block-expired
cleanup candidates.

The local f1r3node source inspected for this run was:

```text
/home/purplezky/work/asi/f1r3node-rust
commit bec6325f
casper/src/rust/blocks/proposer/block_creator.rs
```

The relevant mechanics are:

- `block_expired_deploys` excludes deploys already in `deploys_in_scope`.
- `valid` still requires `not_expired_deploy(...)` unless the deploy is in a
  recovered or rejected-ready path.
- Therefore an in-scope deploy past the lifespan window can become invalid for
  proposal while also not being removed as `blockExpired`.
- The final self-chain filter runs after the selection/cap logs, which explains
  log lines that say `selected=128` followed by actual zero-deploy blocks when
  the selected deploys were filtered from the body.

This explains the observed sequence:

1. Deploy-heavy blocks were created but did not finalize.
2. Their deploy signatures became visible in non-final DAG scope.
3. Same-height zero-deploy siblings finalized instead.
4. Later proposers avoided or filtered the deploys because they were already in
   scope or already in the local self chain.
5. Once the deploy lifespan moved past the workload's `validAfterBlockNumber`,
   recovery stopped selecting them.
6. Finalized coverage stayed at zero even though inclusion coverage had reached
   150.

## Why This Was Not the Contract

The batch-anchor path only stores a batch anchor and manifest pointers on-chain.
It does not write full per-event posting indexes for every trace. The failure
matches consensus/proposer behavior, not Rholang contract behavior:

- the contract deployment itself finalized quickly;
- all workload deploys were accepted and executed into blocks;
- no workload deploy errored in the observed hit blocks;
- finalized blocks at the same heights had no deploys and unchanged state;
- the final canonical cost for the workload was zero because no workload block
  finalized.

The contract path can still be optimized further, but contract execution does
not explain `0 / 150` finalized batches while the DAG contains non-final
deploy-carrying blocks for all 150 batches.

## Root Cause

Primary cause:

Deploy-heavy proposals take long enough that finality support advances through
faster zero-deploy branches before the deploy-carrying branch receives enough
support to become canonical.

Secondary cause:

The recovery path treats non-final in-scope deploys as suppressing duplicate
selection, then lets them become invalid after the deploy lifespan without a
canonical reinclusion path. The deploys are neither finalized nor recoverably
reselected.

Contributing factors:

1. The `128` ordinary deploy cap is too high for this workload on the current
   shard. A `128` deploy block took `195.507s` to propose, which is too slow to
   reliably win finality against zero-deploy support traffic.
2. Finality support does not appear sufficiently biased toward the
   deploy-carrying branch once a deploy-inclusion leader starts heavy work.
3. Selection logs are misleading because they report pre-self-chain-filter
   counts. This hides actual zero-deploy outcomes unless the block body is
   inspected.
4. Deploy lifetime handling has a gap for expired deploys already present in
   non-final scope.

## Recommended Fixes

1. **Bias finality support toward in-flight deploy work**

   When a deploy-inclusion leader is constructing a deploy-heavy block, support
   proposals should avoid canonizing same-height zero-deploy siblings ahead of
   it. The protocol needs an explicit rule that prefers supporting the
   deploy-carrying branch, or waits within a bounded window, before racing ahead
   with empty support.

2. **Reduce or adapt the deploy cap**

   For this workload, `128` deploys per block produced a `195.507s` proposal.
   The cap should be adaptive to measured proposal time, block size, or
   finality lag. A fixed cap that allows multi-minute proposal construction is
   a finality risk, not just a throughput knob.

3. **Make non-final in-scope deploys recoverable until canonical**

   A deploy in DAG scope should not suppress reinclusion indefinitely unless a
   finalized ancestor already contains it. Non-final scope is not enough to
   mark the deploy done. The recovery path should allow re-proposal of
   non-final in-scope deploys before expiry, or explicitly refresh/recover them
   after losing-branch expiry.

4. **Fix expiry accounting for in-scope deploys**

   The `pool=128 valid=0 blockExpired=0 selected=0` state should be impossible.
   If an in-scope deploy is invalid because the lifespan window passed and it
   is not finalized, the proposer must either recover it or clean it up with a
   clear terminal status.

5. **Move post-filter counts into the logs and metrics**

   Selection logs should report both pre-filter and block-body deploy counts.
   A block that logs `selected=128` but carries `0` deploys is operationally
   misleading and makes benchmark analysis unnecessarily slow.

6. **Add regression assertions**

   Add a load test around this exact shape:

   - submit `150x50`;
   - assert that logical inclusion is not counted successful until finalized;
   - assert no same-height zero-deploy sibling finalizes over a deploy-carrying
     sibling without recovery;
   - assert no proposer remains in `pool>0 && valid=0 && blockExpired=0 &&
     selected=0` for non-final in-scope deploys.

## Expected Improvement Target

The last successful `150x50` post-fix retest finalized 7,500 events in
`1,468.320s`, or `5.108 events/s`. The current run regressed to canonical
throughput `0 events/s` despite full non-final inclusion.

The immediate target is not higher raw submission speed. It is restoring
canonical inclusion so that:

- every logical batch is finalized exactly once or recovered into finality;
- deploy-carrying branches are not consistently beaten by empty siblings;
- expired non-final deploys cannot remain in a non-selectable limbo state.

Only after those invariants hold should larger batch sizes be used to tune
throughput.

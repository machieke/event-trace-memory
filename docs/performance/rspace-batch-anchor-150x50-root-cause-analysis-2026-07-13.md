# RSpace Batch Anchor 150x50 Root Cause Analysis - 2026-07-13

## Incident

The `150x50` batch-anchor probe submitted 150 deploys of 50 event pointers each
against the existing scoped contract:

```text
event-trace-memory:EventTraceRSpaceIndexUri:leadership-20260713T140641Z
```

It should have been directly comparable to `100x75`: both declare 7,500 event
traces. Instead, `150x50` never reached a deploy-carrying block before the
submitting node restarted.

## Summary

The immediate cause was not Rholang execution cost. No `150x50` deploy reached
Rholang execution.

The root cause was a deploy-inclusion leadership liveness failure under a stale,
unresolved deploy scope:

1. `validator1` accepted all 150 `150x50` deploys.
2. `validator1` then treated ordinary deploy packaging as deferred to the
   deploy-inclusion leader because old unfinalized user-deploy work was still in
   scope.
3. The apparent deploy-inclusion/recovery side was still occupied by the old
   `100x75` unresolved branches. `validator3` repeatedly restarted and either
   saw no deploys or saw old deploys already in scope.
4. No node packaged the fresh `150x50` deploys into an observed block before
   `validator1` restarted.

This made the deploy-inclusion leadership optimization an availability
bottleneck: the node with the fresh deploys refused to package them, while the
selected leader path did not make them canonical.

## Key Measurements

| Measurement | Value |
| --- | ---: |
| `150x50` run id | `rspace-leadership-150x50-20260713T193527Z` |
| Declared events | `7,500` |
| Submitted deploys | `150` |
| Submit span | `47.082s` |
| Run-specific `Received DeployData` on validator1 | `150` |
| Run-specific `Received DeployData` on validator2/validator3/bootstrap/readonly | `0` observed |
| Pre-restart no-inclusion lower bound | `>593s` |
| Run-specific hit blocks before validator1 restart | `0` |
| Included batches before validator1 restart | `0 / 150` |
| Finalized batches before validator1 restart | `0 / 150` |
| LFB during probe | block `633` |
| Old `100x75` deploy blocks still non-final | blocks `631`, `632`, `634`, `635`, `638`, `639`, `640`, `643` |

## Timeline

| Time UTC | Event |
| --- | --- |
| `19:35:27.760524Z` | First `150x50` `Received DeployData` on validator1. |
| `19:36:14.636338Z` | Last `150x50` `Received DeployData` on validator1. |
| `19:35:32Z` to `19:43:40Z` | Validator1 made 64 heartbeat proposals because pending user deploys existed in storage. |
| same window | Validator1 logged 64 deferrals: ordinary user deploy selection deferred to deploy-inclusion leader. |
| same window | Validator1 deploy selection was `selected=0` in 63/64 attempts. One attempt selected 5 recovered deploys, not the `150x50` run. |
| `19:37:33Z`, `19:40:11Z` | Validator3 saw `pool=95`, `valid=95`, `alreadyInScope=95`, `selected=0`, indicating old unresolved deploys, not new work. |
| `19:43:41Z` | Validator1 warned `visible_blocks=897`, `floor_distance=9`, `max_scope=512`. |
| `19:45:20Z` | Validator1 restarted; no `150x50` hit block had been observed. |

Validator3 restarted five times in the same `19:35:00Z` to `19:45:21Z`
window, and it logged no run-specific `Received DeployData` entries for
`rspace-leadership-150x50-20260713T193527Z`.

## Proposal Path Evidence

Validator1 had the deploys, but the leadership gate disabled ordinary deploy
selection:

```text
Ordinary user deploy selection deferred to deploy-inclusion leader ...
Deploy selection for block #641: pool=0 ... valid=0, alreadyInScope=0, selected=0
```

Quantified over the pre-restart window:

| Validator1 proposal metric | Count |
| --- | ---: |
| Heartbeat proposals due to pending user deploys | `64` |
| Deploy-inclusion deferrals | `64` |
| Deploy selections with `selected=0` | `63` |
| Deploy selections with `selected=5` recovered deploys | `1` |
| Run-specific deploy-carrying blocks found | `0` |

Validator3, the unstable recovery/leader side, did not package the new deploys:

| Validator3 metric | Count |
| --- | ---: |
| Restarts in the same window | `5` |
| Run-specific `Received DeployData` entries | `0` observed |
| Deploy selections | `5` |
| Deploy selections with `selected=0` | `5` |
| `merge scope unusually large` warnings | `5` |

The two validator3 selections with a non-empty pool were:

```text
pool=95, valid=95, alreadyInScope=95, selected=0
```

Those are not fresh `150x50` deploys. They match stale unresolved deploy work
already visible in the DAG from the previous `100x75` run.

## Code Path

The local f1r3node source at `/home/purplezky/work/asi/f1r3node-rust` is at:

```text
f584e9e9 Gate user deploy packaging by inclusion leader
```

The relevant logic is in
`casper/src/rust/blocks/proposer/block_creator.rs`.

`user_work_in_flight` is true when any of these are true:

- unfinalized user deploys are in scope,
- unresolved in-scope deploys are in local storage,
- user deploys are in the proposer's self-chain.

When `user_work_in_flight` is true, ordinary deploys are allowed only if the
node is the deploy-inclusion leader:

```rust
fn allow_ordinary_user_deploys(
    rejected_buffer_non_empty: bool,
    allow_recovered_deploys: bool,
    user_work_in_flight: bool,
    allow_deploy_inclusion: bool,
) -> bool {
    (!rejected_buffer_non_empty || allow_recovered_deploys)
        && (!user_work_in_flight || allow_deploy_inclusion)
}
```

That rule is correct only if the deploy-inclusion leader can actually see and
package the fresh deploys. In this run it could not. The node with the fresh
deploys, validator1, was not allowed to package them because old `100x75`
branches made `user_work_in_flight` true.

The leader selection also starts from existing unfinalized deploy branches:

```rust
if let Some(sender) =
    branch_unfinalized_user_deploy_sender(casper_snapshot, block_store, &parent.block_hash)?
{
    return Ok(Some(sender));
}

if scope_has_unfinalized_user_deploys(casper_snapshot, block_store)? {
    return Ok(recovered_deploy_leader(casper_snapshot));
}
```

That means stale deploy branches can pin inclusion leadership independently of
where new deploys are stored.

## Root Cause

The root cause is a missing liveness fallback in deploy-inclusion leadership.

The implementation assumes that, once ordinary deploy packaging is delegated to
the inclusion leader, the leader will have access to the pending deploys and be
healthy enough to package them. During this run that assumption was false:

- validator1 had all 150 fresh deploys;
- validator1 repeatedly deferred ordinary packaging;
- validator3 repeatedly restarted and never logged receipt of the `150x50`
  deploys;
- stale `100x75` branches kept user-deploy work in scope and the LFB stuck at
  `633`;
- no fallback let validator1 package its own fresh deploys after repeated empty
  leader/deferral cycles.

## Contributing Factors

1. **Stale non-final deploy branches**

   The previous `100x75` run left deploy-carrying blocks at `631`, `632`,
   `634`, `635`, `638`, `639`, `640`, and `643`, all non-final. These blocks
   kept user-deploy work in scope.

2. **Already-in-scope backlog**

   Validator3 saw `pool=95`, `valid=95`, `alreadyInScope=95`, `selected=0`.
   That is a pure backlog symptom: deploys exist locally but are filtered
   because their signatures are already in unresolved scope.

3. **Large merge scope**

   Both validator1 and validator3 logged large merge scope warnings around
   `visible_blocks=896-897` with `max_scope=512`. This indicates the DAG view
   was far beyond the intended merge comfort zone.

4. **Validator restarts**

   Validator3 restarted five times during the `150x50` observation window.
   Validator1 restarted at `19:45:20Z`, ending the conservative measurement
   window. Later `docker inspect` showed clean exits, not OOM:

   ```text
   validator1 exit=0 oom=false
   validator3 exit=0 oom=false
   ```

5. **No run-specific propagation evidence**

   Run-specific `Received DeployData` logs were observed only on validator1.
   This is not proof that no network propagation happened, but it is enough to
   show the leader path did not visibly acquire and package the deploys.

## Why This Was Not Rholang Cost

The earlier `100x75` probe reached Rholang execution and produced non-final
deploy blocks. Its problem was finality after inclusion.

`150x50` failed earlier:

| Run | Inclusion state | Rholang cost measurable? |
| --- | --- | --- |
| `100x75` | `100 / 100` batches included in non-final blocks | yes, non-final candidate cost |
| `150x50` | `0 / 150` batches included | no |

Therefore this incident cannot be explained by per-event or per-batch contract
cost. The contract was never invoked in an observed block for this run.

## Recommended Fixes

1. **Add a leader lease/fallback**

   If a node has local ordinary deploys and observes repeated
   finality-support-only proposals without inclusion, allow it to package a
   bounded number of fresh deploys even when `user_work_in_flight` is true.
   A practical trigger would be either `N` consecutive deferrals or `T` seconds
   since first local pending deploy.

2. **Separate stale in-scope work from fresh local work**

   Do not let old `alreadyInScope` deploy branches suppress packaging of fresh
   deploys that are not themselves in scope. `user_work_in_flight` should not be
   a single global gate for both old recovery work and new deploy admission.

3. **Make inclusion leadership follow deploy availability**

   If leadership is pinned by old branch senders, require either:

   - explicit handoff of fresh deploys to the selected leader, or
   - leader selection that considers where fresh pending deploys are stored.

4. **Detect and drain `pool == alreadyInScope` loops**

   The repeated `pool=95`, `alreadyInScope=95`, `selected=0` state should be a
   first-class recovery condition. Those deploys are not useful candidate work;
   they are stale unresolved scope noise.

5. **Bound merge scope before accepting more performance probes**

   A shard with `visible_blocks` near `900`, `max_scope=512`, and LFB stuck at
   `633` is not a valid baseline for ingestion scaling. The next benchmark
   should wait until old deploy branches finalize or the shard is reset.

6. **Improve observability**

   Add structured log fields for:

   - selected deploy-inclusion leader public key,
   - local stored ordinary deploy count,
   - fresh deploys filtered only because `allow_ordinary_deploys=false`,
   - count of pending deploys already in scope versus not in scope,
   - whether the selected leader has acknowledged receipt of new deploys.

## Follow-Up Retest - 2026-07-14

After the shard was restarted with deploy-inclusion leadership changes, the
same logical workload was retested:

```text
rspace-leadership-150x50-20260714T080824Z
```

The raw artifact is:

```text
docs/performance/artifacts/rspace-batch-anchor-leadership-150x50-retest-20260714T080823Z.json
```

The fix restored liveness for this workload:

| Metric | 2026-07-13 degraded run | 2026-07-14 post-fix retest |
| --- | ---: | ---: |
| Submitted deploys | `150` | `150` |
| First inclusion | none before `>593s` | `208.940s` |
| All included | never observed | `1,035.536s` |
| Finality | never observed | `1,468.320s` |
| Finalized batches | `0 / 150` | `150 / 150` |
| Finalized throughput | n/a | `5.108 events/s` |

The root failure from this incident, no inclusion for fresh `150x50` deploys,
was fixed. The remaining bottleneck is later in the pipeline: duplicate branch
packaging and finality lag. The completed retest observed `15` total hit blocks
but only `5` finalized canonical deploy blocks, and finalized coverage stalled
at `109 / 150` before later blocks finalized the remaining `41` batches.

## Bottom Line

`150x50` did not fail because 7,500 event traces were too expensive for the
RSpace batch-anchor contract. It failed because the deploy-inclusion leadership
path lost liveness in the presence of stale unresolved deploy branches.

The node with the fresh deploys repeatedly deferred packaging, while the
leader/recovery path was pinned to old in-scope work and unstable. The fix is to
make deploy-inclusion leadership recovery-aware and availability-aware, with a
bounded fallback for fresh local deploys.

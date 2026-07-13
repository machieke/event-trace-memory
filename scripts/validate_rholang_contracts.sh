#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${RHOLANG_DOCKER_IMAGE:-f1r3flyindustries/f1r3fly-rust-node:latest}"
CONTAINER="${RHOLANG_CONTAINER_NAME:-event-trace-memory-rholang-validator}"
DATA_DIR="${RHOLANG_DATA_DIR:-}"
VALIDATOR_PRIVATE_KEY="${RHOLANG_VALIDATOR_PRIVATE_KEY:-5f668a7ee96d944a4494cc947e4005e172d7ab3461ee5538f1f2a45a835e9657}"
VALIDATOR_PUBLIC_KEY="${RHOLANG_VALIDATOR_PUBLIC_KEY:-04ffc016579a68050d655d55df4e09f04605164543e257c8e6df10361e6068a5336588e9b355ea859c5ab4285a5ef0efdf62bc28b80320ce99e26bb1607b3ad93d}"
VALIDATOR_REV_ADDRESS="${RHOLANG_VALIDATOR_REV_ADDRESS:-1111AtahZeefej4tvVR6ti9TJtv8yxLebT31SCEVDCKMNikBk5r3g}"
SHARD_ID="${RHOLANG_SHARD_ID:-root}"
CONFIG_PATH=""

contracts=(
  "EventTraceIndex.rho"
  "EventTraceRSpaceIndex.rho"
  "DerivedArtifactIndex.rho"
)
TMP_DIR=""

cleanup_tmp_dir() {
  if [[ -z "${TMP_DIR}" || ! -d "${TMP_DIR}" ]]; then
    return 0
  fi

  rm -rf "${TMP_DIR}" >/dev/null 2>&1 && return 0

  docker run --rm \
    --user root \
    --entrypoint sh \
    -v "${TMP_DIR}:/cleanup" \
    "${IMAGE}" \
    -c 'rm -rf /cleanup/* /cleanup/.[!.]* /cleanup/..?*' >/dev/null 2>&1 || true
  rm -rf "${TMP_DIR}" >/dev/null 2>&1 || true
}

cleanup() {
  if [[ "${KEEP_RHOLANG_NODE:-0}" != "1" ]]; then
    docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
    cleanup_tmp_dir
  fi
}
trap cleanup EXIT

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required for Rholang runtime validation" >&2
    exit 1
  fi
  if ! command -v timeout >/dev/null 2>&1; then
    echo "timeout is required for Rholang data-at-name validation" >&2
    exit 1
  fi
}

prepare_node_files() {
  TMP_DIR="$(mktemp -d)"
  if [[ -z "${DATA_DIR}" ]]; then
    DATA_DIR="${TMP_DIR}/rnode-data"
  fi
  CONFIG_PATH="${TMP_DIR}/rnode.conf"

  mkdir -p "${DATA_DIR}/genesis"
  chmod 777 "${DATA_DIR}" "${DATA_DIR}/genesis"

  cat > "${CONFIG_PATH}" <<'CONF'
standalone = true
dev-mode = true
protocol-server {
  network-id = "event-trace-memory-validation"
  allow-private-addresses = true
  no-upnp = true
}
casper {
  fault-tolerance-threshold = 0.0
  synchrony-constraint-threshold = 0.0
  casper-loop-interval = 5 seconds
  requested-blocks-timeout = 60 seconds
  fork-choice-stale-threshold = 30 seconds
  fork-choice-check-if-stale-interval = 1 minutes
  max-number-of-parents = 100
  enable-mergeable-channel-gc = true
  heartbeat {
    enabled = false
    check-interval = 5 seconds
    max-lfb-age = 10 seconds
  }
  genesis-ceremony {
    required-signatures = 0
    approve-interval = 1 seconds
    approve-duration = 1 seconds
    autogen-shard-size = 1
    ceremony-master-mode = true
  }
  genesis-block-data {
    number-of-active-validators = 1
    pos-multi-sig-quorum = 1
  }
}
metrics { prometheus = true }
CONF

  printf '%s 1000\n' "${VALIDATOR_PUBLIC_KEY}" > "${DATA_DIR}/genesis/bonds.txt"
  printf '%s,50000000000000000\n' "${VALIDATOR_REV_ADDRESS}" > "${DATA_DIR}/genesis/wallets.txt"
  chmod 666 "${DATA_DIR}/genesis/bonds.txt" "${DATA_DIR}/genesis/wallets.txt"
}

start_node() {
  docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true

  if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    docker pull "${IMAGE}"
  fi

  docker run -d \
    --name "${CONTAINER}" \
    -v "${DATA_DIR}:/var/lib/rnode" \
    -v "${CONFIG_PATH}:/var/lib/rnode/rnode.conf" \
    "${IMAGE}" \
    run \
    --standalone \
    --config-file /var/lib/rnode/rnode.conf \
    --host 127.0.0.1 \
    --api-host 127.0.0.1 \
    --validator-private-key "${VALIDATOR_PRIVATE_KEY}" \
    --allow-private-addresses \
    --no-upnp >/dev/null

  for _ in $(seq 1 90); do
    if docker logs "${CONTAINER}" 2>&1 | grep -q "Making a transition to Running state"; then
      return 0
    fi
    if [[ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null || echo false)" != "true" ]]; then
      docker logs "${CONTAINER}" >&2 || true
      echo "Rholang validation node exited before becoming ready" >&2
      exit 1
    fi
    sleep 1
  done

  docker logs "${CONTAINER}" >&2 || true
  echo "Rholang validation node did not become ready in time" >&2
  exit 1
}

eval_rho_file() {
  local local_path="$1"
  local label="$2"
  local expected="${3:-}"
  local remote_path="/tmp/${label}"
  local output

  docker cp "${local_path}" "${CONTAINER}:${remote_path}"
  output="$(docker exec "${CONTAINER}" /opt/docker/bin/node eval --print-unmatched-sends-only "${remote_path}" 2>&1)"
  echo "${output}"

  if ! grep -q "Deployment cost:" <<<"${output}"; then
    echo "Missing deployment cost for ${label}; eval likely failed" >&2
    exit 1
  fi
  if grep -q "Result for .*Error:" <<<"${output}"; then
    echo "Runtime eval failed for ${label}" >&2
    exit 1
  fi
  if [[ -n "${expected}" ]] && ! grep -q "${expected}" <<<"${output}"; then
    echo "Expected '${expected}' in runtime output for ${label}" >&2
    exit 1
  fi
}

eval_contract() {
  local contract="$1"
  eval_rho_file "${ROOT_DIR}/contracts/${contract}" "${contract}"
}

build_event_smoke() {
  local out="$1"
  sed '$d' "${ROOT_DIR}/contracts/EventTraceIndex.rho" > "${out}"
  cat >> "${out}" <<'RHO'

  |

  new putAck, queryResult in {
    eventTraceIndex!(
      "putEvent",
      {
        "kind": "event-pointer",
        "schema": "event-pointer-v0.1",
        "eventId": "event:smoke-1",
        "eventCid": "cid:event-smoke-1",
        "payloadCid": "cid:payload-smoke-1",
        "timePrefixKeys": ["/2026", "/2026/06", "/2026/06/27", "/2026/06/27/14"],
        "actorPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/user", "/irc/libera/user/alice"],
        "channelPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/channel", "/irc/libera/channel/%23chat"],
        "valueKind": "message",
        "parentEventIds": [],
        "rootEventId": "event:smoke-1"
      },
      *putAck
    )
    |
    for (@_ <- putAck) {
      eventTraceIndex!("byTimePrefix", "/2026/06/27/14", *queryResult)
    }
  }
}
RHO
}

build_rspace_event_smoke() {
  local out="$1"
  sed '$d' "${ROOT_DIR}/contracts/EventTraceRSpaceIndex.rho" > "${out}"
  cat >> "${out}" <<'RHO'

  |

  new batchAck, detailAck in {
    eventTraceRSpaceIndex!(
      "putBatchEvents",
      {
        "kind": "event-trace-batch-anchor",
        "schema": "event-trace-batch-anchor-v0.1",
        "batchId": "batch:rspace-smoke-1",
        "shardPath": "/2026/06/27/14",
        "eventCount": 1,
        "minObservedAt": "2026-06-27T14:35:00Z",
        "maxObservedAt": "2026-06-27T14:35:00Z",
        "eventManifestCid": "cid:event-manifest-rspace-smoke-1",
        "postingsManifestCid": "cid:postings-rspace-smoke-1",
        "merkleRoot": "merkle:rspace-smoke-1"
      },
      [],
      *batchAck
    )
    |
    for (@_ <- batchAck) {
      eventTraceRSpaceIndex!(
        "putEventFact",
        {
          "kind": "event-pointer",
          "schema": "event-pointer-v0.1",
          "eventId": "event:rspace-smoke-1",
          "eventCid": "cid:event-rspace-smoke-1",
          "payloadCid": "cid:payload-rspace-smoke-1",
          "timePrefixKeys": ["/2026", "/2026/06", "/2026/06/27", "/2026/06/27/14"],
          "actorPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/user", "/irc/libera/user/alice"],
          "channelPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/channel", "/irc/libera/channel/%23chat"],
          "valueKind": "message",
          "parentEventIds": [],
          "rootEventId": "event:rspace-smoke-1"
        },
        *detailAck
      )
    }
  }
}
RHO
}

build_derived_smoke() {
  local out="$1"
  sed '$d' "${ROOT_DIR}/contracts/DerivedArtifactIndex.rho" > "${out}"
  cat >> "${out}" <<'RHO'

  |

  new runAck, claimAck, occurrenceAck, claimResult in {
    derivedArtifactIndex!(
      "putRun",
      {
        "kind": "run-pointer",
        "schema": "run-pointer-v0.1",
        "runId": "run:smoke-1",
        "runCid": "cid:run-smoke-1",
        "runType": "claim-extraction",
        "inputEventIds": ["event:smoke-1"],
        "outputArtifactIds": [],
        "extractorKey": "omega-claw-claim-extractor:0.1.0",
        "minerKey": "",
        "reasonerKey": "",
        "tool": {"name": "omega-claw-claim-extractor", "version": "0.1.0"},
        "config": {"claimSchema": "claim-core-v0.1"}
      },
      *runAck
    )
    |
    for (@_ <- runAck) {
      derivedArtifactIndex!(
        "putClaim",
        {
          "kind": "claim-pointer",
          "schema": "claim-pointer-v0.1",
          "claimId": "claim:smoke-1",
          "claimCid": "cid:claim-smoke-1",
          "subjectKey": "subject:event-trace-store",
          "predicateKey": "predicate:should-index-by",
          "objectKey": "object:time-actor-channel"
        },
        *claimAck
      )
    }
    |
    for (@_ <- claimAck) {
      derivedArtifactIndex!(
        "putClaimOccurrence",
        {
          "kind": "claim-occurrence-pointer",
          "schema": "claim-occurrence-pointer-v0.1",
          "occurrenceId": "claim-occ:smoke-1",
          "occurrenceCid": "cid:claim-occ-smoke-1",
          "claimId": "claim:smoke-1",
          "claimCid": "cid:claim-smoke-1",
          "sourceEventId": "event:smoke-1",
          "sourceEventCid": "cid:event-smoke-1",
          "sourcePayloadCid": "cid:payload-smoke-1",
          "extractionRunId": "run:smoke-1",
          "polarity": "asserted",
          "confidence": 82
        },
        *occurrenceAck
      )
    }
    |
    for (@_ <- occurrenceAck) {
      derivedArtifactIndex!("byClaim", "claim:smoke-1", *claimResult)
    }
  }
}
RHO
}

build_event_deploy_smoke() {
  local out="$1"
  cat > "${out}" <<'RHO'
new lookup(`rho:registry:lookup`), lookedUp,
    putRootAck, putChildAck, duplicateCidResult,
    timeResult, eventResult, actorResult, channelResult, kindResult,
    parentResult, rootResult, payloadResult, eventCidResult, statsResult
in {
  for (@uri <- @"event-trace-memory:EventTraceIndexUri") {
    @"event-trace-memory:EventTraceIndexUri"!(uri)
    |
    lookup!(uri, *lookedUp)
    |
    for (@eventTraceIndex <- lookedUp) {
      @eventTraceIndex!(
        "putEvent",
        {
          "kind": "event-pointer",
          "schema": "event-pointer-v0.1",
          "eventId": "event:deploy-smoke-1",
          "eventCid": "cid:event-deploy-smoke-1",
          "payloadCid": "cid:payload-deploy-smoke-1",
          "timePrefixKeys": ["/2026", "/2026/06", "/2026/06/28", "/2026/06/28/13", "/2026/06/28/13"],
          "actorPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/user", "/irc/libera/user/bob"],
          "channelPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/channel", "/irc/libera/channel/%23deploy"],
          "valueKind": "message",
          "parentEventIds": [],
          "rootEventId": "event:deploy-smoke-1"
        },
        *putRootAck
      )
      |
      for (@_ <- putRootAck) {
        @eventTraceIndex!(
          "putEvent",
          {
            "kind": "event-pointer",
            "schema": "event-pointer-v0.1",
            "eventId": "event:deploy-smoke-child-1",
            "eventCid": "cid:event-deploy-smoke-child-1",
            "payloadCid": "cid:payload-deploy-smoke-child-1",
            "timePrefixKeys": ["/2026", "/2026/06", "/2026/06/28", "/2026/06/28/14"],
            "actorPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/user", "/irc/libera/user/carol", "/irc/libera/user/carol"],
            "channelPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/channel", "/irc/libera/channel/%23deploy-child", "/irc/libera/channel/%23deploy-child"],
            "valueKind": "memory-query",
            "parentEventIds": ["event:deploy-smoke-1", "event:deploy-smoke-1"],
            "rootEventId": "event:deploy-smoke-1"
          },
          *putChildAck
        )
      }
      |
      for (@_ <- putChildAck) {
        @eventTraceIndex!("byTimePrefix", "/2026/06/28/13", *timeResult)
        |
        @eventTraceIndex!("getEvent", "event:deploy-smoke-child-1", *eventResult)
        |
        @eventTraceIndex!("byActorPrefix", "/irc/libera/user/carol", *actorResult)
        |
        @eventTraceIndex!("byChannelPrefix", "/irc/libera/channel/%23deploy-child", *channelResult)
        |
        @eventTraceIndex!("byKind", "memory-query", *kindResult)
        |
        @eventTraceIndex!("byParent", "event:deploy-smoke-1", *parentResult)
        |
        @eventTraceIndex!("byRoot", "event:deploy-smoke-1", *rootResult)
        |
        @eventTraceIndex!("byPayloadCid", "cid:payload-deploy-smoke-child-1", *payloadResult)
        |
        @eventTraceIndex!("byEventCid", "cid:event-deploy-smoke-child-1", *eventCidResult)
        |
        @eventTraceIndex!(
          "putEvent",
          {
            "kind": "event-pointer",
            "schema": "event-pointer-v0.1",
            "eventId": "event:deploy-smoke-duplicate-cid",
            "eventCid": "cid:event-deploy-smoke-child-1",
            "payloadCid": "cid:payload-deploy-smoke-duplicate-cid",
            "timePrefixKeys": ["/2026", "/2026/06", "/2026/06/28", "/2026/06/28/14"],
            "actorPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/user", "/irc/libera/user/dave"],
            "channelPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/channel", "/irc/libera/channel/%23deploy-duplicate"],
            "valueKind": "message",
            "parentEventIds": [],
            "rootEventId": "event:deploy-smoke-duplicate-cid"
          },
          *duplicateCidResult
        )
        |
        @eventTraceIndex!("getStateStats", *statsResult)
      }
    }
    |
    for (@result <- timeResult) {
      if (result.get("eventIds") == ["event:deploy-smoke-1"]) {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:event:deploy-smoke-1"!(true)
      }
    }
    |
    for (@result <- eventResult) {
      if (result.get("event").get("eventId") == "event:deploy-smoke-child-1") {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:getEvent"!(true)
      }
    }
    |
    for (@result <- actorResult) {
      if (result.get("eventIds") == ["event:deploy-smoke-child-1"]) {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:byActorPrefix"!(true)
      }
    }
    |
    for (@result <- channelResult) {
      if (result.get("eventIds") == ["event:deploy-smoke-child-1"]) {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:byChannelPrefix"!(true)
      }
    }
    |
    for (@result <- kindResult) {
      if (result.get("eventIds").nth(0) == "event:deploy-smoke-child-1") {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:byKind"!(true)
      }
    }
    |
    for (@result <- parentResult) {
      if (result.get("eventIds") == ["event:deploy-smoke-child-1"]) {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:byParent"!(true)
      }
    }
    |
    for (@result <- rootResult) {
      if (result.get("eventIds").nth(1) == "event:deploy-smoke-child-1") {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:byRoot"!(true)
      }
    }
    |
    for (@result <- payloadResult) {
      if (result.get("eventIds").nth(0) == "event:deploy-smoke-child-1") {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:byPayloadCid"!(true)
      }
    }
    |
    for (@result <- eventCidResult) {
      if (result.get("eventId") == "event:deploy-smoke-child-1") {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:byEventCid"!(true)
      }
    }
    |
    for (@result <- duplicateCidResult) {
      if (result.get("error") == "duplicate-event-cid") {
        if (result.get("eventId") == "event:deploy-smoke-child-1") {
          @"event-trace-memory:EventTraceIndexDeploySmokeOk:duplicateEventCid"!(true)
        }
      }
    }
    |
    for (@result <- statsResult) {
      if (result.get("events") == 2) {
        if (result.get("timeKeys") == 5) {
          if (result.get("actorKeys") == 5) {
            if (result.get("channelKeys") == 5) {
              if (result.get("kindKeys") == 2) {
                if (result.get("parentKeys") == 1) {
                  if (result.get("rootKeys") == 1) {
                    if (result.get("payloadKeys") == 2) {
                      if (result.get("eventCidKeys") == 2) {
                        @"event-trace-memory:EventTraceIndexDeploySmokeOk:getStateStats"!(true)
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
RHO
}

build_rspace_event_deploy_smoke() {
  local out="$1"
  cat > "${out}" <<'RHO'
new lookup(`rho:registry:lookup`), lookedUp, putAck, detailAck, hintsResult in {
  for (@uri <- @"event-trace-memory:EventTraceRSpaceIndexUri") {
    @"event-trace-memory:EventTraceRSpaceIndexUri"!(uri)
    |
    lookup!(uri, *lookedUp)
    |
    for (@eventTraceRSpaceIndex <- lookedUp) {
      @eventTraceRSpaceIndex!(
        "putBatchEvents",
        {
          "kind": "event-trace-batch-anchor",
          "schema": "event-trace-batch-anchor-v0.1",
          "batchId": "batch:rspace-deploy-smoke-1",
          "shardPath": "/2026/06/28/13",
          "eventCount": 1,
          "minObservedAt": "2026-06-28T13:00:00Z",
          "maxObservedAt": "2026-06-28T13:00:00Z",
          "eventManifestCid": "cid:event-manifest-rspace-deploy-smoke-1",
          "postingsManifestCid": "cid:postings-rspace-deploy-smoke-1",
          "merkleRoot": "merkle:rspace-deploy-smoke-1"
        },
        [],
        *putAck
      )
      |
      for (@result <- putAck) {
        if (result.get("ok")) {
          if (result.get("batchId") == "batch:rspace-deploy-smoke-1") {
            @"event-trace-memory:EventTraceRSpaceIndexDeploySmokeOk:putBatchEvents"!(true)
            |
            @eventTraceRSpaceIndex!(
              "putEventFact",
              {
                "kind": "event-pointer",
                "schema": "event-pointer-v0.1",
                "eventId": "event:rspace-deploy-smoke-1",
                "eventCid": "cid:event-rspace-deploy-smoke-1",
                "payloadCid": "cid:payload-rspace-deploy-smoke-1",
                "timePrefixKeys": ["/2026", "/2026/06", "/2026/06/28", "/2026/06/28/13"],
                "actorPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/user", "/irc/libera/user/rspace"],
                "channelPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/channel", "/irc/libera/channel/%23rspace"],
                "valueKind": "message",
                "parentEventIds": [],
                "rootEventId": "event:rspace-deploy-smoke-1"
              },
              *detailAck
            )
          }
        }
      }
      |
      @eventTraceRSpaceIndex!("getNameHints", "batch:rspace-deploy-smoke-1", "event:rspace-deploy-smoke-1", *hintsResult)
    }
    |
    for (@result <- detailAck) {
      if (result.get("ok")) {
        if (result.get("eventId") == "event:rspace-deploy-smoke-1") {
          @"event-trace-memory:EventTraceRSpaceIndexDeploySmokeOk:putEventFact"!(true)
        }
      }
    }
    |
    for (@hints <- hintsResult) {
      if (hints.get("batch") == "event-trace-memory:RSpaceBatch:batch:rspace-deploy-smoke-1") {
        @"event-trace-memory:EventTraceRSpaceIndexDeploySmokeOk:getNameHints"!(true)
      }
    }
  }
}
RHO
}

build_derived_deploy_smoke() {
  local out="$1"
  cat > "${out}" <<'RHO'
new lookup(`rho:registry:lookup`), lookedUp,
    runAck, dedupeRunAck, claimAck, claimOccurrenceAck, clusterAck,
    featureAck, featureOccurrenceAck, patternAck, patternOccurrenceAck,
    reasoningInputAck, reasoningOutputAck, beliefHistoryAck,
    claimReady, featureReady, patternReady, reasoningReady, clusterReady, dedupeReady,
    runLookupResult, claimLookupResult, claimOccurrenceLookupResult,
    clusterLookupResult, featureLookupResult, featureOccurrenceLookupResult,
    patternLookupResult, patternOccurrenceLookupResult,
    reasoningInputLookupResult, reasoningOutputLookupResult, beliefHistoryLookupResult,
    dedupeRunResult, dedupeOutputResult,
    runsByInputResult, runsByOutputResult,
    claimsBySubjectResult, claimsByPredicateResult, claimsByObjectResult,
    featuresByTypeResult, patternsByTypeResult, patternsBySnapshotResult, patternsByMinerResult,
    reasoningClaimResult, reasoningRunResult,
    claimResult, sourceEventResult, featureResult, runResult,
    extractorResult, minerResult, reasonerResult, patternResult, patternRootResult,
    clusterResult, reasoningInputResult, beliefClaimResult, beliefOutputResult, statsResult
in {
  for (@uri <- @"event-trace-memory:DerivedArtifactIndexUri") {
    @"event-trace-memory:DerivedArtifactIndexUri"!(uri)
    |
    lookup!(uri, *lookedUp)
    |
    for (@derivedArtifactIndex <- lookedUp) {
      @derivedArtifactIndex!(
        "putRun",
        {
          "kind": "run-pointer",
          "schema": "run-pointer-v0.1",
          "runId": "run:deploy-smoke-1",
          "runCid": "cid:run-deploy-smoke-1",
          "runType": "claim-extraction",
          "inputEventIds": ["event:deploy-smoke-1", "event:deploy-smoke-1"],
          "outputArtifactIds": [],
          "extractorKey": "omega-claw-claim-extractor:0.1.0",
          "minerKey": "pattern-miner:0.1.0",
          "reasonerKey": "nal-reasoner:0.1.0",
          "tool": {"name": "omega-claw-claim-extractor", "version": "0.1.0"},
          "config": {"claimSchema": "claim-core-v0.1"}
        },
        *runAck
      )
      |
      for (@_ <- runAck) {
        @derivedArtifactIndex!(
          "putRun",
          {
            "kind": "run-pointer",
            "schema": "run-pointer-v0.1",
            "runId": "run:deploy-smoke-dedupe",
            "runCid": "cid:run-deploy-smoke-dedupe",
            "runType": "dedupe-smoke",
            "inputEventIds": ["event:deploy-smoke-dedupe", "event:deploy-smoke-dedupe"],
            "outputArtifactIds": ["artifact:deploy-smoke-dedupe-output", "artifact:deploy-smoke-dedupe-output"],
            "extractorKey": "",
            "minerKey": "",
            "reasonerKey": "",
            "tool": {"name": "dedupe-smoke", "version": "0.1.0"},
            "config": {}
          },
          *dedupeRunAck
        )
        |
        @derivedArtifactIndex!(
          "putClaim",
          {
            "kind": "claim-pointer",
            "schema": "claim-pointer-v0.1",
            "claimId": "claim:deploy-smoke-1",
            "claimCid": "cid:claim-deploy-smoke-1",
            "subjectKey": "subject:event-trace-store",
            "predicateKey": "predicate:should-index-by",
            "objectKey": "object:time-actor-channel"
          },
          *claimAck
        )
        |
        @derivedArtifactIndex!(
          "putFeature",
          {
            "kind": "feature-pointer",
            "schema": "feature-pointer-v0.1",
            "featureId": "feature:deploy-smoke-1",
            "featureCid": "cid:feature-deploy-smoke-1",
            "featureType": "workflow-step"
          },
          *featureAck
        )
        |
        @derivedArtifactIndex!(
          "putPattern",
          {
            "kind": "pattern-pointer",
            "schema": "pattern-pointer-v0.1",
            "patternId": "pattern:deploy-smoke-1",
            "patternCid": "cid:pattern-deploy-smoke-1",
            "patternType": "sequence",
            "inputSnapshotCids": ["cid:snapshot-deploy-smoke-1", "cid:snapshot-deploy-smoke-1"],
            "minerKey": "pattern-miner:0.1.0"
          },
          *patternAck
        )
        |
        @derivedArtifactIndex!(
          "putReasoningInput",
          {
            "kind": "reasoning-input-pointer",
            "schema": "reasoning-input-pointer-v0.1",
            "inputId": "reasoning-input:deploy-smoke-1",
            "inputCid": "cid:reasoning-input-deploy-smoke-1",
            "claimId": "claim:deploy-smoke-1"
          },
          *reasoningInputAck
        )
      }
      |
      for (@_ <- claimAck) {
        @derivedArtifactIndex!(
          "putClaimOccurrence",
          {
            "kind": "claim-occurrence-pointer",
            "schema": "claim-occurrence-pointer-v0.1",
            "occurrenceId": "claim-occ:deploy-smoke-1",
            "occurrenceCid": "cid:claim-occ-deploy-smoke-1",
            "claimId": "claim:deploy-smoke-1",
            "claimCid": "cid:claim-deploy-smoke-1",
            "sourceEventId": "event:deploy-smoke-1",
            "sourceEventCid": "cid:event-deploy-smoke-1",
            "sourcePayloadCid": "cid:payload-deploy-smoke-1",
            "extractionRunId": "run:deploy-smoke-1",
            "polarity": "asserted",
            "confidence": 82
          },
          *claimOccurrenceAck
        )
        |
        @derivedArtifactIndex!(
          "putClaimCluster",
          {
            "kind": "claim-cluster-pointer",
            "schema": "claim-cluster-pointer-v0.1",
            "clusterId": "claim-cluster:deploy-smoke-1",
            "clusterCid": "cid:claim-cluster-deploy-smoke-1",
            "relation": "same-subject",
            "members": ["claim:deploy-smoke-1", "claim:deploy-smoke-1"]
          },
          *clusterAck
        )
      }
      |
      for (@_ <- featureAck) {
        @derivedArtifactIndex!(
          "putFeatureOccurrence",
          {
            "kind": "feature-occurrence-pointer",
            "schema": "feature-occurrence-pointer-v0.1",
            "occurrenceId": "feature-occ:deploy-smoke-1",
            "occurrenceCid": "cid:feature-occ-deploy-smoke-1",
            "featureId": "feature:deploy-smoke-1",
            "featureCid": "cid:feature-deploy-smoke-1",
            "sourceEventId": "event:deploy-smoke-1",
            "extractionRunId": "run:deploy-smoke-1",
            "confidence": 91
          },
          *featureOccurrenceAck
        )
      }
      |
      for (@_ <- patternAck) {
        @derivedArtifactIndex!(
          "putPatternOccurrence",
          {
            "kind": "pattern-occurrence-pointer",
            "schema": "pattern-occurrence-pointer-v0.1",
            "occurrenceId": "pattern-occ:deploy-smoke-1",
            "occurrenceCid": "cid:pattern-occ-deploy-smoke-1",
            "patternId": "pattern:deploy-smoke-1",
            "patternCid": "cid:pattern-deploy-smoke-1",
            "rootEventId": "event:deploy-smoke-1",
            "minedBy": "run:deploy-smoke-1"
          },
          *patternOccurrenceAck
        )
      }
      |
      for (@_ <- reasoningInputAck) {
        @derivedArtifactIndex!(
          "putReasoningOutput",
          {
            "kind": "reasoning-output-pointer",
            "schema": "reasoning-output-pointer-v0.1",
            "outputId": "reasoning-output:deploy-smoke-1",
            "outputCid": "cid:reasoning-output-deploy-smoke-1",
            "inputId": "reasoning-input:deploy-smoke-1",
            "claimId": "claim:deploy-smoke-1",
            "reasoningRunId": "run:deploy-smoke-1"
          },
          *reasoningOutputAck
        )
      }
      |
      for (@_ <- claimOccurrenceAck) {
        @derivedArtifactIndex!("byClaim", "claim:deploy-smoke-1", *claimResult)
        |
        claimReady!(true)
      }
      |
      for (@_ <- featureOccurrenceAck) {
        @derivedArtifactIndex!("byFeature", "feature:deploy-smoke-1", *featureResult)
        |
        featureReady!(true)
      }
      |
      for (@_ <- patternOccurrenceAck) {
        @derivedArtifactIndex!("byPattern", "pattern:deploy-smoke-1", *patternResult)
        |
        @derivedArtifactIndex!("byPatternRoot", "event:deploy-smoke-1", *patternRootResult)
        |
        patternReady!(true)
      }
      |
      for (@_ <- reasoningOutputAck) {
        @derivedArtifactIndex!(
          "putBeliefRevisionHistory",
          {
            "kind": "belief-revision-history-pointer",
            "schema": "belief-revision-history-pointer-v0.1",
            "historyId": "belief-revision-history:deploy-smoke-1",
            "historyCid": "cid:belief-revision-history-deploy-smoke-1",
            "claimId": "claim:deploy-smoke-1",
            "outputIds": ["reasoning-output:deploy-smoke-1", "reasoning-output:deploy-smoke-1"]
          },
          *beliefHistoryAck
        )
      }
      |
      for (@_ <- beliefHistoryAck) {
        @derivedArtifactIndex!("reasoningOutputsByInput", "reasoning-input:deploy-smoke-1", *reasoningInputResult)
        |
        @derivedArtifactIndex!("beliefHistoriesByClaim", "claim:deploy-smoke-1", *beliefClaimResult)
        |
        @derivedArtifactIndex!("beliefHistoriesByOutput", "reasoning-output:deploy-smoke-1", *beliefOutputResult)
        |
        reasoningReady!(true)
      }
      |
      for (@_ <- clusterAck) {
        @derivedArtifactIndex!("clustersForClaim", "claim:deploy-smoke-1", *clusterResult)
        |
        clusterReady!(true)
      }
      |
      for (@_ <- dedupeRunAck) {
        @derivedArtifactIndex!("byRun", "run:deploy-smoke-dedupe", *dedupeRunResult)
        |
        @derivedArtifactIndex!("runsByOutputArtifact", "artifact:deploy-smoke-dedupe-output", *dedupeOutputResult)
        |
        dedupeReady!(true)
      }
      |
      for (_ <- claimReady; _ <- featureReady; _ <- patternReady; _ <- reasoningReady; _ <- clusterReady; _ <- dedupeReady) {
        @derivedArtifactIndex!("getRun", "run:deploy-smoke-1", *runLookupResult)
        |
        @derivedArtifactIndex!("getClaim", "claim:deploy-smoke-1", *claimLookupResult)
        |
        @derivedArtifactIndex!("getClaimOccurrence", "claim-occ:deploy-smoke-1", *claimOccurrenceLookupResult)
        |
        @derivedArtifactIndex!("getClaimCluster", "claim-cluster:deploy-smoke-1", *clusterLookupResult)
        |
        @derivedArtifactIndex!("getFeature", "feature:deploy-smoke-1", *featureLookupResult)
        |
        @derivedArtifactIndex!("getFeatureOccurrence", "feature-occ:deploy-smoke-1", *featureOccurrenceLookupResult)
        |
        @derivedArtifactIndex!("getPattern", "pattern:deploy-smoke-1", *patternLookupResult)
        |
        @derivedArtifactIndex!("getPatternOccurrence", "pattern-occ:deploy-smoke-1", *patternOccurrenceLookupResult)
        |
        @derivedArtifactIndex!("getReasoningInput", "reasoning-input:deploy-smoke-1", *reasoningInputLookupResult)
        |
        @derivedArtifactIndex!("getReasoningOutput", "reasoning-output:deploy-smoke-1", *reasoningOutputLookupResult)
        |
        @derivedArtifactIndex!("getBeliefRevisionHistory", "belief-revision-history:deploy-smoke-1", *beliefHistoryLookupResult)
        |
        @derivedArtifactIndex!("bySourceEvent", "event:deploy-smoke-1", *sourceEventResult)
        |
        @derivedArtifactIndex!("runsByInputEvent", "event:deploy-smoke-1", *runsByInputResult)
        |
        @derivedArtifactIndex!("runsByOutputArtifact", "claim-occ:deploy-smoke-1", *runsByOutputResult)
        |
        @derivedArtifactIndex!("claimsBySubject", "subject:event-trace-store", *claimsBySubjectResult)
        |
        @derivedArtifactIndex!("claimsByPredicate", "predicate:should-index-by", *claimsByPredicateResult)
        |
        @derivedArtifactIndex!("claimsByObject", "object:time-actor-channel", *claimsByObjectResult)
        |
        @derivedArtifactIndex!("featuresByType", "workflow-step", *featuresByTypeResult)
        |
        @derivedArtifactIndex!("byRun", "run:deploy-smoke-1", *runResult)
        |
        @derivedArtifactIndex!("byExtractor", "omega-claw-claim-extractor:0.1.0", *extractorResult)
        |
        @derivedArtifactIndex!("byMiner", "pattern-miner:0.1.0", *minerResult)
        |
        @derivedArtifactIndex!("byReasoner", "nal-reasoner:0.1.0", *reasonerResult)
        |
        @derivedArtifactIndex!("patternsByType", "sequence", *patternsByTypeResult)
        |
        @derivedArtifactIndex!("patternsByInputSnapshot", "cid:snapshot-deploy-smoke-1", *patternsBySnapshotResult)
        |
        @derivedArtifactIndex!("patternsByMiner", "pattern-miner:0.1.0", *patternsByMinerResult)
        |
        @derivedArtifactIndex!("reasoningOutputsByClaim", "claim:deploy-smoke-1", *reasoningClaimResult)
        |
        @derivedArtifactIndex!("reasoningOutputsByRun", "run:deploy-smoke-1", *reasoningRunResult)
        |
        @derivedArtifactIndex!("getStateStats", *statsResult)
      }
    }
    |
    for (@byRun <- dedupeRunResult; @byOutput <- dedupeOutputResult) {
      if (byRun.get("artifactIds") == ["artifact:deploy-smoke-dedupe-output"]) {
        if (byOutput.get("runIds") == ["run:deploy-smoke-dedupe"]) {
          @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:dedupePostings"!(true)
        }
      }
    }
    |
    for (@result <- claimResult) {
      if (result.get("occurrenceIds").nth(0) == "claim-occ:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claim-occ:deploy-smoke-1"!(true)
      }
    }
    |
    for (@result <- runLookupResult) {
      if (result.get("run").get("runId") == "run:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getRun"!(true)
      }
    }
    |
    for (@result <- claimLookupResult) {
      if (result.get("claim").get("claimId") == "claim:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getClaim"!(true)
      }
    }
    |
    for (@result <- claimOccurrenceLookupResult) {
      if (result.get("claimOccurrence").get("occurrenceId") == "claim-occ:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getClaimOccurrence"!(true)
      }
    }
    |
    for (@result <- clusterLookupResult) {
      if (result.get("claimCluster").get("clusterId") == "claim-cluster:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getClaimCluster"!(true)
      }
    }
    |
    for (@result <- featureLookupResult) {
      if (result.get("feature").get("featureId") == "feature:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getFeature"!(true)
      }
    }
    |
    for (@result <- featureOccurrenceLookupResult) {
      if (result.get("featureOccurrence").get("occurrenceId") == "feature-occ:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getFeatureOccurrence"!(true)
      }
    }
    |
    for (@result <- patternLookupResult) {
      if (result.get("pattern").get("patternId") == "pattern:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getPattern"!(true)
      }
    }
    |
    for (@result <- patternOccurrenceLookupResult) {
      if (result.get("patternOccurrence").get("occurrenceId") == "pattern-occ:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getPatternOccurrence"!(true)
      }
    }
    |
    for (@result <- reasoningInputLookupResult) {
      if (result.get("reasoningInput").get("inputId") == "reasoning-input:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getReasoningInput"!(true)
      }
    }
    |
    for (@result <- reasoningOutputLookupResult) {
      if (result.get("reasoningOutput").get("outputId") == "reasoning-output:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getReasoningOutput"!(true)
      }
    }
    |
    for (@result <- beliefHistoryLookupResult) {
      if (result.get("beliefRevisionHistory").get("historyId") == "belief-revision-history:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getBeliefRevisionHistory"!(true)
      }
    }
    |
    for (@result <- sourceEventResult) {
      if (result.get("claimOccurrenceIds").nth(0) == "claim-occ:deploy-smoke-1") {
        if (result.get("featureOccurrenceIds").nth(0) == "feature-occ:deploy-smoke-1") {
          @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:bySourceEvent"!(true)
        }
      }
    }
    |
    for (@result <- runsByInputResult) {
      if (result.get("runIds") == ["run:deploy-smoke-1"]) {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:runsByInputEvent"!(true)
      }
    }
    |
    for (@result <- runsByOutputResult) {
      if (result.get("runIds").nth(0) == "run:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:runsByOutputArtifact"!(true)
      }
    }
    |
    for (@result <- claimsBySubjectResult) {
      if (result.get("claimIds").nth(0) == "claim:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claimsBySubject"!(true)
      }
    }
    |
    for (@result <- claimsByPredicateResult) {
      if (result.get("claimIds").nth(0) == "claim:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claimsByPredicate"!(true)
      }
    }
    |
    for (@result <- claimsByObjectResult) {
      if (result.get("claimIds").nth(0) == "claim:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claimsByObject"!(true)
      }
    }
    |
    for (@result <- featureResult) {
      if (result.get("occurrenceIds").nth(0) == "feature-occ:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byFeature"!(true)
      }
    }
    |
    for (@result <- featuresByTypeResult) {
      if (result.get("featureIds").nth(0) == "feature:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:featuresByType"!(true)
      }
    }
    |
    for (@result <- runResult) {
      if (result.get("artifactIds").nth(0) == "claim-occ:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byRun"!(true)
      }
    }
    |
    for (@result <- extractorResult) {
      if (result.get("runIds").nth(0) == "run:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byExtractor"!(true)
      }
    }
    |
    for (@result <- minerResult) {
      if (result.get("runIds").nth(0) == "run:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byMiner"!(true)
      }
    }
    |
    for (@result <- reasonerResult) {
      if (result.get("runIds").nth(0) == "run:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byReasoner"!(true)
      }
    }
    |
    for (@result <- patternResult) {
      if (result.get("occurrenceIds").nth(0) == "pattern-occ:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byPattern"!(true)
      }
    }
    |
    for (@result <- patternRootResult) {
      if (result.get("occurrenceIds").nth(0) == "pattern-occ:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byPatternRoot"!(true)
      }
    }
    |
    for (@result <- patternsByTypeResult) {
      if (result.get("patternIds").nth(0) == "pattern:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:patternsByType"!(true)
      }
    }
    |
    for (@result <- patternsBySnapshotResult) {
      if (result.get("patternIds") == ["pattern:deploy-smoke-1"]) {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:patternsByInputSnapshot"!(true)
      }
    }
    |
    for (@result <- patternsByMinerResult) {
      if (result.get("patternIds").nth(0) == "pattern:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:patternsByMiner"!(true)
      }
    }
    |
    for (@result <- clusterResult) {
      if (result.get("clusterIds") == ["claim-cluster:deploy-smoke-1"]) {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:clustersForClaim"!(true)
      }
    }
    |
    for (@result <- reasoningInputResult) {
      if (result.get("outputIds").nth(0) == "reasoning-output:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:reasoningOutputsByInput"!(true)
      }
    }
    |
    for (@result <- reasoningClaimResult) {
      if (result.get("outputIds").nth(0) == "reasoning-output:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:reasoningOutputsByClaim"!(true)
      }
    }
    |
    for (@result <- reasoningRunResult) {
      if (result.get("outputIds").nth(0) == "reasoning-output:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:reasoningOutputsByRun"!(true)
      }
    }
    |
    for (@result <- beliefClaimResult) {
      if (result.get("historyIds").nth(0) == "belief-revision-history:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:beliefHistoriesByClaim"!(true)
      }
    }
    |
    for (@result <- beliefOutputResult) {
      if (result.get("historyIds") == ["belief-revision-history:deploy-smoke-1"]) {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:beliefHistoriesByOutput"!(true)
      }
    }
    |
    for (@result <- statsResult) {
      if (result.get("runs") == 2) {
        if (result.get("claims") == 1) {
          if (result.get("claimOccurrences") == 1) {
            if (result.get("claimClusters") == 1) {
              if (result.get("features") == 1) {
                if (result.get("featureOccurrences") == 1) {
                  if (result.get("patterns") == 1) {
                    if (result.get("patternOccurrences") == 1) {
                      if (result.get("reasoningInputs") == 1) {
                        if (result.get("reasoningOutputs") == 1) {
                          if (result.get("beliefRevisionHistories") == 1) {
                            @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getStateStats"!(true)
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
RHO
}

deploy_rho_file() {
  local local_path="$1"
  local label="$2"
  local valid_after="$3"
  local phlo_limit="${4:-1000000000}"
  local remote_path="/tmp/${label}"
  local output

  docker cp "${local_path}" "${CONTAINER}:${remote_path}"
  output="$(
    docker exec "${CONTAINER}" /opt/docker/bin/node deploy \
      "${phlo_limit}" \
      1 \
      "${valid_after}" \
      "${VALIDATOR_PRIVATE_KEY}" \
      /tmp/event-trace-memory-unused-private-key-path \
      "${remote_path}" \
      "${SHARD_ID}" 2>&1
  )"
  echo "${output}"

  if ! grep -q "Response: Success!" <<<"${output}"; then
    echo "Deploy failed for ${label}" >&2
    exit 1
  fi
  if ! grep -q "^DeployId is:" <<<"${output}"; then
    echo "Missing deploy id for ${label}" >&2
    exit 1
  fi
}

propose_block() {
  local expected_deploy_count="$1"
  local output
  local block_hash
  local block

  output="$(docker exec "${CONTAINER}" /opt/docker/bin/node propose --print-unmatched-sends 2>&1)"
  echo "${output}"
  if ! grep -q "Response: Success! Block" <<<"${output}"; then
    echo "Propose failed" >&2
    exit 1
  fi

  block_hash="$(sed -n 's/^Response: Success! Block \([0-9a-f]*\) created and added\.$/\1/p' <<<"${output}")"
  if [[ -z "${block_hash}" ]]; then
    echo "Could not parse proposed block hash" >&2
    exit 1
  fi

  block="$(docker exec "${CONTAINER}" /opt/docker/bin/node show-block "${block_hash}" 2>&1)"
  echo "${block}"
  if ! grep -q "deploy_count: ${expected_deploy_count}" <<<"${block}"; then
    echo "Expected deploy_count ${expected_deploy_count} for block ${block_hash}" >&2
    exit 1
  fi
  if grep -q "errored: true" <<<"${block}"; then
    echo "Proposed block ${block_hash} contains an errored deploy" >&2
    exit 1
  fi
}

assert_data_at_name() {
  local name="$1"
  local expected_size="${2:-1}"
  local output
  local status

  set +e
  output="$(timeout 10 docker exec "${CONTAINER}" /opt/docker/bin/node data-at-name "\"${name}\"" 2>&1)"
  status=$?
  set -e
  echo "${output}"

  if [[ "${status}" != "0" && "${status}" != "124" ]]; then
    echo "data-at-name failed for ${name}" >&2
    exit 1
  fi
  if ! grep -q "Initial data size: ${expected_size}" <<<"${output}"; then
    echo "Expected data size ${expected_size} at public name ${name}" >&2
    exit 1
  fi
}

require_docker
prepare_node_files
start_node

for contract in "${contracts[@]}"; do
  eval_contract "${contract}"
done

build_event_smoke "${TMP_DIR}/EventTraceIndexSmoke.rho"
build_rspace_event_smoke "${TMP_DIR}/EventTraceRSpaceIndexSmoke.rho"
build_derived_smoke "${TMP_DIR}/DerivedArtifactIndexSmoke.rho"

eval_rho_file "${TMP_DIR}/EventTraceIndexSmoke.rho" "EventTraceIndexSmoke.rho" "event:smoke-1"
eval_rho_file "${TMP_DIR}/EventTraceRSpaceIndexSmoke.rho" "EventTraceRSpaceIndexSmoke.rho" "event:rspace-smoke-1"
eval_rho_file "${TMP_DIR}/DerivedArtifactIndexSmoke.rho" "DerivedArtifactIndexSmoke.rho" "claim-occ:smoke-1"

deploy_rho_file "${ROOT_DIR}/contracts/EventTraceIndex.rho" "EventTraceIndexDeploy.rho" 0
deploy_rho_file "${ROOT_DIR}/contracts/EventTraceRSpaceIndex.rho" "EventTraceRSpaceIndexDeploy.rho" 0
deploy_rho_file "${ROOT_DIR}/contracts/DerivedArtifactIndex.rho" "DerivedArtifactIndexDeploy.rho" 0
propose_block 3

assert_data_at_name "event-trace-memory:EventTraceIndexUri"
assert_data_at_name "event-trace-memory:EventTraceRSpaceIndexUri"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexUri"

build_event_deploy_smoke "${TMP_DIR}/EventTraceIndexDeploySmoke.rho"
build_rspace_event_deploy_smoke "${TMP_DIR}/EventTraceRSpaceIndexDeploySmoke.rho"
build_derived_deploy_smoke "${TMP_DIR}/DerivedArtifactIndexDeploySmoke.rho"

deploy_rho_file "${TMP_DIR}/EventTraceIndexDeploySmoke.rho" "EventTraceIndexDeploySmoke.rho" 1
deploy_rho_file "${TMP_DIR}/EventTraceRSpaceIndexDeploySmoke.rho" "EventTraceRSpaceIndexDeploySmoke.rho" 1
deploy_rho_file "${TMP_DIR}/DerivedArtifactIndexDeploySmoke.rho" "DerivedArtifactIndexDeploySmoke.rho" 1
propose_block 3

assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:event:deploy-smoke-1"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:getEvent"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:byActorPrefix"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:byChannelPrefix"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:byKind"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:byParent"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:byRoot"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:byPayloadCid"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:byEventCid"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:duplicateEventCid"
assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:getStateStats"
assert_data_at_name "event-trace-memory:EventTraceRSpaceIndexDeploySmokeOk:putBatchEvents"
assert_data_at_name "event-trace-memory:EventTraceRSpaceIndexDeploySmokeOk:putEventFact"
assert_data_at_name "event-trace-memory:EventTraceRSpaceIndexDeploySmokeOk:getNameHints"
assert_data_at_name "event-trace-memory:RSpaceBatch:batch:rspace-deploy-smoke-1"
assert_data_at_name "event-trace-memory:RSpaceBatchByShard:/2026/06/28/13"
assert_data_at_name "event-trace-memory:RSpaceBatchByEventManifest:cid:event-manifest-rspace-deploy-smoke-1"
assert_data_at_name "event-trace-memory:RSpaceBatchByPostingsManifest:cid:postings-rspace-deploy-smoke-1"
assert_data_at_name "event-trace-memory:RSpaceBatchByMerkleRoot:merkle:rspace-deploy-smoke-1"
assert_data_at_name "event-trace-memory:RSpaceEvent:event:rspace-deploy-smoke-1"
assert_data_at_name "event-trace-memory:RSpaceEventCid:cid:event-rspace-deploy-smoke-1"
assert_data_at_name "event-trace-memory:RSpacePosting:time:/2026/06/28/13"
assert_data_at_name "event-trace-memory:RSpacePosting:actor:/irc/libera/user/rspace"
assert_data_at_name "event-trace-memory:RSpacePosting:channel:/irc/libera/channel/%23rspace"
assert_data_at_name "event-trace-memory:RSpacePosting:kind:message"
assert_data_at_name "event-trace-memory:RSpacePosting:root:event:rspace-deploy-smoke-1"
assert_data_at_name "event-trace-memory:RSpacePosting:payload:cid:payload-rspace-deploy-smoke-1"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claim-occ:deploy-smoke-1"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:dedupePostings"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getRun"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getClaim"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getClaimOccurrence"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getClaimCluster"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getFeature"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getFeatureOccurrence"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getPattern"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getPatternOccurrence"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getReasoningInput"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getReasoningOutput"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getBeliefRevisionHistory"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:bySourceEvent"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:runsByInputEvent"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:runsByOutputArtifact"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claimsBySubject"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claimsByPredicate"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claimsByObject"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byFeature"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:featuresByType"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byRun"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byExtractor"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byMiner"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byReasoner"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byPattern"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:byPatternRoot"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:patternsByType"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:patternsByInputSnapshot"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:patternsByMiner"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:clustersForClaim"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:reasoningOutputsByInput"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:reasoningOutputsByClaim"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:reasoningOutputsByRun"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:beliefHistoriesByClaim"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:beliefHistoriesByOutput"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:getStateStats"

echo "Rholang runtime validation, deploy/propose, and registry smoke calls passed for ${#contracts[@]} contracts."

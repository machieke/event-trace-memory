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
new lookup(`rho:registry:lookup`), lookedUp, putAck, queryResult in {
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
          "timePrefixKeys": ["/2026", "/2026/06", "/2026/06/28", "/2026/06/28/13"],
          "actorPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/user", "/irc/libera/user/bob"],
          "channelPrefixKeys": ["/irc", "/irc/libera", "/irc/libera/channel", "/irc/libera/channel/%23deploy"],
          "valueKind": "message",
          "parentEventIds": [],
          "rootEventId": "event:deploy-smoke-1"
        },
        *putAck
      )
      |
      for (@_ <- putAck) {
        @eventTraceIndex!("byTimePrefix", "/2026/06/28/13", *queryResult)
      }
    }
    |
    for (@result <- queryResult) {
      if (result.get("eventIds").nth(0) == "event:deploy-smoke-1") {
        @"event-trace-memory:EventTraceIndexDeploySmokeOk:event:deploy-smoke-1"!(true)
      }
    }
  }
}
RHO
}

build_derived_deploy_smoke() {
  local out="$1"
  cat > "${out}" <<'RHO'
new lookup(`rho:registry:lookup`), lookedUp, runAck, claimAck, occurrenceAck, claimResult in {
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
          "inputEventIds": ["event:deploy-smoke-1"],
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
          *occurrenceAck
        )
      }
      |
      for (@_ <- occurrenceAck) {
        @derivedArtifactIndex!("byClaim", "claim:deploy-smoke-1", *claimResult)
      }
    }
    |
    for (@result <- claimResult) {
      if (result.get("occurrenceIds").nth(0) == "claim-occ:deploy-smoke-1") {
        @"event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claim-occ:deploy-smoke-1"!(true)
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
  if ! grep -q "Initial data size: 1" <<<"${output}"; then
    echo "Expected data at public name ${name}" >&2
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
build_derived_smoke "${TMP_DIR}/DerivedArtifactIndexSmoke.rho"

eval_rho_file "${TMP_DIR}/EventTraceIndexSmoke.rho" "EventTraceIndexSmoke.rho" "event:smoke-1"
eval_rho_file "${TMP_DIR}/DerivedArtifactIndexSmoke.rho" "DerivedArtifactIndexSmoke.rho" "claim-occ:smoke-1"

deploy_rho_file "${ROOT_DIR}/contracts/EventTraceIndex.rho" "EventTraceIndexDeploy.rho" 0
deploy_rho_file "${ROOT_DIR}/contracts/DerivedArtifactIndex.rho" "DerivedArtifactIndexDeploy.rho" 0
propose_block 2

assert_data_at_name "event-trace-memory:EventTraceIndexUri"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexUri"

build_event_deploy_smoke "${TMP_DIR}/EventTraceIndexDeploySmoke.rho"
build_derived_deploy_smoke "${TMP_DIR}/DerivedArtifactIndexDeploySmoke.rho"

deploy_rho_file "${TMP_DIR}/EventTraceIndexDeploySmoke.rho" "EventTraceIndexDeploySmoke.rho" 1
deploy_rho_file "${TMP_DIR}/DerivedArtifactIndexDeploySmoke.rho" "DerivedArtifactIndexDeploySmoke.rho" 1
propose_block 2

assert_data_at_name "event-trace-memory:EventTraceIndexDeploySmokeOk:event:deploy-smoke-1"
assert_data_at_name "event-trace-memory:DerivedArtifactIndexDeploySmokeOk:claim-occ:deploy-smoke-1"

echo "Rholang runtime validation, deploy/propose, and registry smoke calls passed for ${#contracts[@]} contracts."

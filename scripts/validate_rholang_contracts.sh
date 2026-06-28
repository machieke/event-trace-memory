#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${RHOLANG_DOCKER_IMAGE:-f1r3flyindustries/f1r3fly-rust-node:latest}"
CONTAINER="${RHOLANG_CONTAINER_NAME:-event-trace-memory-rholang-validator}"
DATA_DIR="${RHOLANG_DATA_DIR:-/tmp/event-trace-memory-rholang-data}"

contracts=(
  "EventTraceIndex.rho"
  "DerivedArtifactIndex.rho"
)
TMP_DIR=""

cleanup() {
  if [[ "${KEEP_RHOLANG_NODE:-0}" != "1" ]]; then
    docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup EXIT

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required for Rholang runtime validation" >&2
    exit 1
  fi
}

start_node() {
  docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
  mkdir -p "${DATA_DIR}"
  chmod 777 "${DATA_DIR}"

  if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    docker pull "${IMAGE}"
  fi

  docker run -d \
    --name "${CONTAINER}" \
    -v "${DATA_DIR}:/var/lib/rnode" \
    "${IMAGE}" \
    run \
    --standalone \
    --host 127.0.0.1 \
    --api-host 127.0.0.1 \
    --dev-mode \
    --no-upnp \
    --allow-private-addresses >/dev/null

  for _ in $(seq 1 60); do
    if docker logs "${CONTAINER}" 2>&1 | grep -q "All tasks started. Node is now running."; then
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

require_docker
start_node

for contract in "${contracts[@]}"; do
  eval_contract "${contract}"
done

TMP_DIR="$(mktemp -d)"
build_event_smoke "${TMP_DIR}/EventTraceIndexSmoke.rho"
build_derived_smoke "${TMP_DIR}/DerivedArtifactIndexSmoke.rho"

eval_rho_file "${TMP_DIR}/EventTraceIndexSmoke.rho" "EventTraceIndexSmoke.rho" "event:smoke-1"
eval_rho_file "${TMP_DIR}/DerivedArtifactIndexSmoke.rho" "DerivedArtifactIndexSmoke.rho" "claim-occ:smoke-1"

echo "Rholang runtime validation and smoke calls passed for ${#contracts[@]} contracts."

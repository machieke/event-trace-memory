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

cleanup() {
  if [[ "${KEEP_RHOLANG_NODE:-0}" != "1" ]]; then
    docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
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

eval_contract() {
  local contract="$1"
  local local_path="${ROOT_DIR}/contracts/${contract}"
  local remote_path="/tmp/${contract}"
  local output

  docker cp "${local_path}" "${CONTAINER}:${remote_path}"
  output="$(docker exec "${CONTAINER}" /opt/docker/bin/node eval "${remote_path}" 2>&1)"
  echo "${output}"

  if ! grep -q "Deployment cost:" <<<"${output}"; then
    echo "Missing deployment cost for ${contract}; eval likely failed" >&2
    exit 1
  fi
  if grep -q "Result for .*Error:" <<<"${output}"; then
    echo "Runtime eval failed for ${contract}" >&2
    exit 1
  fi
}

require_docker
start_node

for contract in "${contracts[@]}"; do
  eval_contract "${contract}"
done

echo "Rholang runtime validation passed for ${#contracts[@]} contracts."

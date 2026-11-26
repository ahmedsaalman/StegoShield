#!/usr/bin/env bash
# Move the VM to one commit of main: its compose files and its image from ghcr.io, then wait until healthy.
#
#   update.sh            -> latest main, image tag "latest"   (used by setup.sh)
#   update.sh <sha>      -> that commit, image tag <sha>      (GitHub Actions sends the sha over SSH; the
#                           forced command in authorized_keys passes it as SSH_ORIGINAL_COMMAND)
set -euo pipefail

HEALTH_TIMEOUT_SECONDS=240
COMMIT_PATTERN='^[0-9a-f]{40}$'

# Everything lives in main() so bash has read the whole script before `git checkout` can rewrite this file.
main() {
  local target="${1:-${SSH_ORIGINAL_COMMAND:-}}" repo_dir image_tag
  repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  cd "$repo_dir"
  git fetch --quiet origin main

  if [ -z "$target" ]; then
    target="$(git rev-parse origin/main)"
    image_tag=latest
  elif [[ "$target" =~ $COMMIT_PATTERN ]]; then
    image_tag="$target"
  else
    echo "Refusing to deploy: expected a 40-character commit sha, got '$target'." >&2
    return 2
  fi

  # The server mirrors GitHub: never edit files here. The untracked .env survives the checkout.
  git checkout --quiet --force --detach "$target"
  echo "Deploying $(git log --oneline -1)"

  cd deploy/vm
  APP_IMAGE_TAG="$image_tag" docker compose pull --quiet
  APP_IMAGE_TAG="$image_tag" docker compose up -d --remove-orphans
  docker image prune -f >/dev/null
  wait_until_healthy
}

wait_until_healthy() {
  local container status waited=0
  container="$(docker compose ps -q app)"
  while [ "$waited" -lt "$HEALTH_TIMEOUT_SECONDS" ]; do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$container")"
    if [ "$status" = "healthy" ]; then
      echo "App is healthy."
      return 0
    fi
    sleep 5
    waited=$((waited + 5))
  done
  echo "App did not become healthy within ${HEALTH_TIMEOUT_SECONDS}s. Recent logs:" >&2
  docker compose logs --tail 50 app >&2
  return 1
}

main "$@"

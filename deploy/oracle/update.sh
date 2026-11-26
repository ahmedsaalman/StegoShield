#!/usr/bin/env bash
# Bring the VM to exactly what is on GitHub's main branch, rebuild, and wait until the app is healthy.
# Run by setup.sh, and by GitHub Actions (over SSH) after each push to main.
set -euo pipefail

HEALTH_TIMEOUT_SECONDS=180

# Everything lives in main() so bash has read the whole script before `git reset` can rewrite this file.
main() {
  local repo_dir
  repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  cd "$repo_dir"
  # The server is a mirror of GitHub: never edit files here. Untracked .env survives the reset.
  git fetch --quiet origin main
  git reset --quiet --hard origin/main
  echo "Deploying $(git log --oneline -1)"

  cd deploy/oracle
  docker compose up -d --build --remove-orphans
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

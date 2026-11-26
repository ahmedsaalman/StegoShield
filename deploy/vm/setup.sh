#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu/Debian VM (Google Cloud e2-micro, Oracle, or any other). Run on the VM:
#
#   curl -fsSL https://raw.githubusercontent.com/ahmedsaalman/StegoShield/main/deploy/vm/setup.sh -o setup.sh
#   DEPLOY_PUBLIC_KEY="ssh-ed25519 AAAA... stegoshield-deploy" bash setup.sh
#
# Needs the image ghcr.io/ahmedsaalman/stegoshield to exist and be public (GitHub Actions builds it).
# Optional environment variables:
#   SITE_ADDRESS       hostname for HTTPS (default: <public-ip-with-dashes>.sslip.io, which needs no domain)
#   DEPLOY_PUBLIC_KEY  GitHub Actions' public key; it is authorised to run update.sh and nothing else
#   REPO_URL, APP_DIR  where to clone from and to
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/ahmedsaalman/StegoShield.git}"
APP_DIR="${APP_DIR:-$HOME/StegoShield}"
SMALL_VM_MEMORY_MB=2048
SWAP_SIZE=2G

main() {
  ensure_swap
  install_docker
  open_web_ports
  clone_repo
  write_site_address
  authorise_deploy_key
  # A new docker group membership only applies to new logins, hence sg for this first run.
  sg docker -c "bash '$APP_DIR/deploy/vm/update.sh'"
  echo
  echo "StegoShield is live at: https://$(site_address)"
  echo "For GitHub Actions, set the variable VM_USER to: $(whoami)"
}

# On a 1 GB VM a brief memory spike should slow things down, not kill the app.
ensure_swap() {
  local memory_mb
  memory_mb="$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)"
  if [ "$memory_mb" -ge "$SMALL_VM_MEMORY_MB" ] || [ -n "$(swapon --show --noheadings)" ]; then return; fi
  sudo fallocate -l "$SWAP_SIZE" /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then return; fi
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
}

# Oracle's Ubuntu images ship iptables rules that reject everything except SSH, on top of the cloud
# firewall; most other images have no such rules, and then this does nothing.
open_web_ports() {
  if ! sudo iptables -S INPUT 2>/dev/null | grep -q -- "-j REJECT"; then return; fi
  local rule
  for rule in "tcp 80" "tcp 443" "udp 443"; do
    set -- $rule
    sudo iptables -C INPUT -p "$1" --dport "$2" -j ACCEPT 2>/dev/null ||
      sudo iptables -I INPUT 1 -p "$1" --dport "$2" -j ACCEPT
  done
  if command -v netfilter-persistent >/dev/null 2>&1; then sudo netfilter-persistent save; fi
}

clone_repo() {
  if [ -d "$APP_DIR/.git" ]; then return; fi
  command -v git >/dev/null 2>&1 || sudo apt-get install -y -qq git >/dev/null
  git clone --quiet "$REPO_URL" "$APP_DIR"
}

write_site_address() {
  local env_file="$APP_DIR/deploy/vm/.env"
  if [ -n "${SITE_ADDRESS:-}" ] || [ ! -f "$env_file" ]; then
    echo "SITE_ADDRESS=${SITE_ADDRESS:-$(curl -fsS https://api.ipify.org | tr . -).sslip.io}" >"$env_file"
  fi
}

site_address() {
  sed -n 's/^SITE_ADDRESS=//p' "$APP_DIR/deploy/vm/.env"
}

# The forced command means a leaked deploy key can only redeploy a commit that is already on GitHub.
authorise_deploy_key() {
  if [ -z "${DEPLOY_PUBLIC_KEY:-}" ]; then return; fi
  local entry="command=\"bash $APP_DIR/deploy/vm/update.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $DEPLOY_PUBLIC_KEY"
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  grep -qxF "$entry" "$HOME/.ssh/authorized_keys" 2>/dev/null || echo "$entry" >>"$HOME/.ssh/authorized_keys"
}

main "$@"

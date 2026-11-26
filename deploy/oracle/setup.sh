#!/usr/bin/env bash
# One-time setup of a fresh Oracle Cloud Ubuntu VM (24.04, ARM or x86). Run on the VM as the default user:
#
#   curl -fsSL https://raw.githubusercontent.com/ahmedsaalman/StegoShield/main/deploy/oracle/setup.sh -o setup.sh
#   DEPLOY_PUBLIC_KEY="ssh-ed25519 AAAA... stegoshield-deploy" bash setup.sh
#
# Optional environment variables:
#   SITE_ADDRESS       hostname for HTTPS (default: <public-ip-with-dashes>.sslip.io, which needs no domain)
#   DEPLOY_PUBLIC_KEY  GitHub Actions' public key; it is authorised to run update.sh and nothing else
#   REPO_URL, APP_DIR  where to clone from and to
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/ahmedsaalman/StegoShield.git}"
APP_DIR="${APP_DIR:-$HOME/StegoShield}"

main() {
  install_docker
  open_web_ports
  clone_repo
  write_site_address
  authorise_deploy_key
  # A new docker group membership only applies to new logins, hence sg for this first run.
  sg docker -c "bash '$APP_DIR/deploy/oracle/update.sh'"
  echo
  echo "StegoShield is live at: https://$(site_address)"
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then return; fi
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
}

# Oracle's Ubuntu images ship iptables rules that reject everything except SSH, on top of the
# cloud security list. Both must allow 80/443.
open_web_ports() {
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
  sudo apt-get install -y -qq git >/dev/null
  git clone --quiet "$REPO_URL" "$APP_DIR"
}

write_site_address() {
  local env_file="$APP_DIR/deploy/oracle/.env"
  if [ -n "${SITE_ADDRESS:-}" ] || [ ! -f "$env_file" ]; then
    echo "SITE_ADDRESS=${SITE_ADDRESS:-$(curl -fsS https://api.ipify.org | tr . -).sslip.io}" >"$env_file"
  fi
}

site_address() {
  sed -n 's/^SITE_ADDRESS=//p' "$APP_DIR/deploy/oracle/.env"
}

# The forced command means a leaked deploy key can only redeploy the code already on GitHub.
authorise_deploy_key() {
  if [ -z "${DEPLOY_PUBLIC_KEY:-}" ]; then return; fi
  local entry="command=\"bash $APP_DIR/deploy/oracle/update.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $DEPLOY_PUBLIC_KEY"
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  grep -qxF "$entry" "$HOME/.ssh/authorized_keys" 2>/dev/null || echo "$entry" >>"$HOME/.ssh/authorized_keys"
}

main "$@"

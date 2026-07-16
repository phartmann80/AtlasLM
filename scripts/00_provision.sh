#!/usr/bin/env bash
# Patch 016A - Step 0: provision the fresh AtlasLM server.
# Target: STRATO VPS 85.215.225.0, Ubuntu 24.04. Domain: atlaslm.cloud
# Run AS ROOT on the NEW server. Idempotent: safe to re-run.
set -euo pipefail

DEPLOY_USER="atlas"
TZ_REGION="Europe/Berlin"

echo "[*] Updating base system"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg ufw fail2ban unattended-upgrades \
                   git jq htop rsync postgresql-client

echo "[*] Timezone"
timedatectl set-timezone "$TZ_REGION" || true

echo "[*] Creating deploy user '$DEPLOY_USER'"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
  usermod -aG sudo "$DEPLOY_USER"
fi

# Carry over root's authorized_keys so your STRATO key works for the deploy user.
if [ -f /root/.ssh/authorized_keys ]; then
  mkdir -p /home/$DEPLOY_USER/.ssh
  cp /root/.ssh/authorized_keys /home/$DEPLOY_USER/.ssh/authorized_keys
  chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh
  chmod 700 /home/$DEPLOY_USER/.ssh
  chmod 600 /home/$DEPLOY_USER/.ssh/authorized_keys
fi

echo "[*] Firewall: allow SSH, HTTP, HTTPS only"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "[*] Hardening SSH: no root login, no passwords"
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh || systemctl restart sshd || true

echo "[*] Enabling automatic security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades || true

echo "[OK] Provision complete."
echo "    Next: log in as '$DEPLOY_USER' and run 01_docker.sh"

#!/usr/bin/env bash
# Patch 016A - Step 1: install Docker Engine + Compose plugin.
# Target: STRATO VPS 85.215.225.0. Run as the deploy user 'atlas' (has sudo).
# Idempotent: safe to re-run.
set -euo pipefail

if command -v docker >/dev/null 2>&1; then
  echo "[*] Docker already installed: $(docker --version)"
else
  echo "[*] Installing Docker Engine"
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                          docker-buildx-plugin docker-compose-plugin
fi

echo "[*] Enabling Docker on boot and adding '$USER' to docker group"
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo "[OK] Docker ready: $(docker compose version 2>/dev/null || echo 'compose plugin installed')"
echo "    Log out and back in so the docker group applies, then continue with 02_dump_old.sh (run on OLD server)."

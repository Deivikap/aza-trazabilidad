#!/usr/bin/env bash
# Prepara una VM Ubuntu 24.04 limpia: Docker, firewall (22/80/443), parches automáticos y fail2ban.
# Uso:  sudo bash deploy/provision_ubuntu.sh
set -euo pipefail
apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl ufw fail2ban unattended-upgrades git
curl -fsSL https://get.docker.com | sh
usermod -aG docker "${SUDO_USER:-ubuntu}"
ufw default deny incoming && ufw default allow outgoing
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp
ufw --force enable
systemctl enable --now fail2ban unattended-upgrades
echo "Listo. Cierra sesión y vuelve a entrar para usar docker sin sudo."

#!/usr/bin/env bash
# Cài Viefs lên máy chủ Ubuntu 24.04. Chạy:  bash setup-server.sh viefs.com
# (không có tên miền thì bỏ trống: bash setup-server.sh  → chạy bằng địa chỉ IP, chưa có https)
set -euo pipefail
DOMAIN="${1:-}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/srv/viefs

echo "== 1/5 Cài phần mềm"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq python3 python3-requests rsync ufw curl gnupg debian-keyring debian-archive-keyring apt-transport-https
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q && apt-get install -yq caddy
fi

echo "== 2/5 Chép website vào $APP"
id viefs >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin viefs
mkdir -p "$APP"
rsync -a --exclude '__pycache__' "$SRC/" "$APP/"
chown -R viefs:viefs "$APP"

echo "== 3/5 Mật khẩu admin"
if [ ! -f "$APP/private/admin_config.json" ]; then
  sudo -u viefs python3 "$APP/serve.py" --set-password
else
  echo "Dùng lại mật khẩu cũ từ máy bạn."
fi

echo "== 4/5 Cho chạy liên tục + tự đồng bộ mỗi 3 giờ"
cat > /etc/systemd/system/viefs.service <<UNIT
[Unit]
Description=Viefs website
After=network-online.target
Wants=network-online.target

[Service]
User=viefs
WorkingDirectory=$APP
Environment=PORT=8000 HOST=127.0.0.1 AUTO_SYNC_HOURS=3
ExecStart=/usr/bin/python3 $APP/serve.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now viefs
systemctl restart viefs

echo "== 5/5 Mở cổng web (https tự động nếu có tên miền)"
if [ -n "$DOMAIN" ]; then
  printf '%s, www.%s {\n  encode gzip\n  reverse_proxy 127.0.0.1:8000\n}\n' "$DOMAIN" "$DOMAIN" > /etc/caddy/Caddyfile
  URL="https://$DOMAIN"
else
  printf ':80 {\n  encode gzip\n  reverse_proxy 127.0.0.1:8000\n}\n' > /etc/caddy/Caddyfile
  URL="http://$(curl -s -4 ifconfig.me || hostname -I | cut -d' ' -f1)"
fi
systemctl restart caddy
ufw allow OpenSSH >/dev/null; ufw allow 80 >/dev/null; ufw allow 443 >/dev/null; ufw --force enable >/dev/null

sleep 2
systemctl is-active --quiet viefs && echo "✓ Website đang chạy" || { echo "✗ Có lỗi, xem: journalctl -u viefs -n 50"; exit 1; }
echo
echo "Website: $URL"
echo "Admin:   $URL/admin"
echo "Xem nhật ký đồng bộ:  journalctl -u viefs -f"

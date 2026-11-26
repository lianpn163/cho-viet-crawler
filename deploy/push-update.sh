#!/usr/bin/env bash
# Chạy TRÊN MÁY MAC khi có bản code mới: đẩy code lên máy chủ, KHÔNG đụng dữ liệu/đơn hàng trên đó.
# Cách dùng:  bash deploy/push-update.sh 123.45.67.89
set -euo pipefail
IP="$1"; cd "$(dirname "$0")/.."
rsync -az --exclude '__pycache__' --exclude 'site/data/' --exclude 'private/' --exclude 'brands.json' ./ "root@$IP:/srv/viefs/"
ssh "root@$IP" 'chown -R viefs:viefs /srv/viefs && systemctl restart viefs && echo "✓ Đã cập nhật"'

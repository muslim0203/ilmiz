#!/usr/bin/env bash
# Sayt statistikasi: nginx loglaridan GoAccess HTML hisoboti.
#
#   ILMIZ_STATS_DIR=/var/lib/ilmiz/stats bash deploy/generate_stats.sh
#
# Saytga hech qanday kuzatuv skripti qo'shilmaydi — hisobot server
# loglaridan quriladi. Hisobot ommaviy emas: uni faqat `/api/admin/stats`
# beradi (admin himoyasi ostida).
set -euo pipefail
out="${ILMIZ_STATS_DIR:-/var/lib/ilmiz/stats}"
log_dir="${ILMIZ_NGINX_LOG_DIR:-/var/log/nginx}"
command -v goaccess >/dev/null || { echo 'goaccess o‘rnatilmagan: sudo bash deploy/install_stats.sh'; exit 1; }

shopt -s nullglob
# Joriy kun + logrotate saqlagan 14 kun (siqilgani ham).
logs=("$log_dir"/access.log "$log_dir"/access.log.1 "$log_dir"/access.log.*.gz)
[[ ${#logs[@]} -gt 0 ]] || { echo "Log topilmadi: $log_dir/access.log"; exit 1; }

install -d -m 750 "$out"
tmp="$out/.index.html.tmp"
# `zcat -f` siqilmagan faylni ham o'tkazadi. Botlar chiqarib tashlanadi:
# kunlik 42 ming so'rovning katta qismi qidiruv robotlari.
zcat -f -- "${logs[@]}" | goaccess - \
    --log-format=COMBINED \
    --tz="${ILMIZ_STATS_TZ:-Asia/Tashkent}" \
    --ignore-crawlers \
    --no-progress \
    --html-report-title='IlmIz — sayt statistikasi' \
    -o "$tmp"
mv -f "$tmp" "$out/index.html"
chmod 640 "$out/index.html"
echo "Hisobot tayyor: $out/index.html ($(stat -c %s "$out/index.html") bayt)"

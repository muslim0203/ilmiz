#!/usr/bin/env bash
# OAI-PMH harvest jadvalini o'rnatish (takror ishga tushirish xavfsiz).
#
#   sudo bash /opt/ilmiz/app/deploy/install_harvest_timer.sh
#
# Nima qiladi: log katalogini yaratadi, to'rtta unit faylni nusxalaydi,
# timer'larni yoqadi. Bazaga, API xizmatiga va muhit fayliga tegmaydi.
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'sudo bilan ishga tushiring'; exit 1; }
app=/opt/ilmiz/app
[[ -f "$app/backend/manage.py" ]] || { echo "Ilova topilmadi: $app"; exit 1; }
[[ -f /etc/ilmiz/staging.env ]] || { echo 'Muhit fayli yo‘q: /etc/ilmiz/staging.env'; exit 1; }
grep -q '^DATABASE_URL=' /etc/ilmiz/staging.env || { echo 'staging.env da DATABASE_URL yo‘q'; exit 1; }

install -d -m 700 -o ilmiz -g ilmiz /var/lib/ilmiz/logs
for unit in ilmiz-harvest.service ilmiz-harvest.timer ilmiz-harvest-retry.service ilmiz-harvest-retry.timer; do
    install -m 644 "$app/deploy/$unit" "/etc/systemd/system/$unit"
    systemd-analyze verify "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now ilmiz-harvest.timer ilmiz-harvest-retry.timer
systemctl list-timers --no-pager 'ilmiz-*'
echo
echo 'Birinchi yurgizishni kutmasdan boshlash:  sudo systemctl start ilmiz-harvest.service'
echo 'Jarayonni kuzatish:                       sudo journalctl -fu ilmiz-harvest.service'

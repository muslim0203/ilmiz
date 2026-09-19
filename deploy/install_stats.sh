#!/usr/bin/env bash
# Sayt statistikasini o'rnatish (takror ishga tushirish xavfsiz).
#
#   sudo bash /opt/ilmiz/app/deploy/install_stats.sh
#
# GoAccess ni o'rnatadi, hisobot katalogini yaratadi, kunlik jadvalni yoqadi
# va birinchi hisobotni darhol tayyorlaydi. Bazaga, API xizmatiga va nginx
# sozlamalariga tegmaydi.
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'sudo bilan ishga tushiring'; exit 1; }
app=/opt/ilmiz/app
[[ -f "$app/deploy/generate_stats.sh" ]] || { echo "Ilova topilmadi: $app"; exit 1; }

if ! command -v goaccess >/dev/null; then
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq goaccess
fi
goaccess --version | head -1

install -d -m 750 -o ilmiz -g ilmiz /var/lib/ilmiz/stats
for unit in ilmiz-stats.service ilmiz-stats.timer; do
    install -m 644 "$app/deploy/$unit" "/etc/systemd/system/$unit"
    systemd-analyze verify "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now ilmiz-stats.timer
systemctl start ilmiz-stats.service
systemctl list-timers --no-pager 'ilmiz-stats*'
echo
echo 'Hisobot: /var/lib/ilmiz/stats/index.html'
echo 'Saytda:  https://ilmiz.uz/api/admin/stats (faqat admin hisobi bilan)'

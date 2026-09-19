#!/usr/bin/env bash
# Sayt statistikasi: nginx loglaridan GoAccess HTML hisobotlari (o'zbekcha).
#
#   ILMIZ_STATS_DIR=/var/lib/ilmiz/stats bash deploy/generate_stats.sh
#
# Ikkita hisobot: `index.html` — tirik tashrifchilar (botlarsiz),
# `botlar.html` — faqat qidiruv robotlari. Saytga kuzatuv skripti
# qo'shilmaydi; ikkalasini ham faqat `/api/admin/stats` beradi.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="${ILMIZ_STATS_DIR:-/var/lib/ilmiz/stats}"
log_dir="${ILMIZ_NGINX_LOG_DIR:-/var/log/nginx}"
command -v goaccess >/dev/null || { echo 'goaccess o‘rnatilmagan: sudo bash deploy/install_stats.sh'; exit 1; }
python="${ILMIZ_PYTHON:-}"
[[ -n "$python" ]] || python=$([[ -x /opt/ilmiz/venv/bin/python ]] && echo /opt/ilmiz/venv/bin/python || echo python3)

shopt -s nullglob
# Joriy kun + logrotate saqlagan 14 kun (siqilgani ham).
logs=("$log_dir"/access.log "$log_dir"/access.log.1 "$log_dir"/access.log.*.gz)
[[ ${#logs[@]} -gt 0 ]] || { echo "Log topilmadi: $log_dir/access.log"; exit 1; }

install -d -m 750 "$out"

report() {
    local title="$1" name="$2"
    shift 2
    # Vaqtinchalik fayl ham `.html` bilan tugashi shart: GoAccess boshqa
    # kengaytmani rad etadi va hisobot umuman yozilmaydi.
    local tmp="$out/.$name.new.html"
    zcat -f -- "${logs[@]}" | goaccess - \
        --log-format=COMBINED \
        --tz="${ILMIZ_STATS_TZ:-Asia/Tashkent}" \
        --no-progress \
        --html-report-title="$title" \
        "$@" \
        -o "$tmp"
    # Yorliqlarni o'zbekchaga o'girish (GoAccess'ning o'zida uz locale yo'q).
    "$python" "$here/translate_stats.py" "$tmp" >/dev/null
    mv -f "$tmp" "$out/$name"
    chmod 640 "$out/$name"
    echo "Hisobot tayyor: $out/$name ($(stat -c %s "$out/$name") bayt)"
}

report 'IlmIz — sayt statistikasi (botlarsiz)' index.html --ignore-crawlers
report 'IlmIz — botlar statistikasi' botlar.html --crawlers-only

#!/usr/bin/env bash
# Ishlab turgan serverdagi kodni tekshirilgan runtime arxivi bilan yangilash.
#
#   sudo bash update_app.sh <yuklangan katalog> <release nomi>
#   masalan: sudo bash update_app.sh /home/ubuntu/ilmiz-harvest-20260906 harvest-20260906
#
# Katalogda `runtime.tar.gz` va `SHA256SUMS` (package_runtime.py natijasi)
# bo'lishi kerak. Qadamlar: checksum -> alohida katalogga ochish -> shu
# yerda testlar -> WAL-xavfsiz baza zaxirasi -> xizmatni to'xtatib kodni
# almashtirish -> health tekshiruvi. Health o'tmasa eski kod qaytariladi.
# Baza (/var/lib/ilmiz) va muhit fayli (/etc/ilmiz) ga tegilmaydi;
# migratsiya xizmat startida `init_db()` orqali o'zi bajariladi.
set -euo pipefail
umask 022
[[ "$(id -u)" == 0 ]] || { echo 'sudo bilan ishga tushiring'; exit 1; }
upload="$(realpath -- "${1:?Yuklangan katalogni bering}")"
release_id="${2:?Release nomini bering}"
[[ "$release_id" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'Release nomi faqat harf, raqam, . _ -'; exit 1; }
app=/opt/ilmiz/app
release="/opt/ilmiz/releases/$release_id"
previous="/opt/ilmiz/app-before-$release_id"
[[ -d "$app" ]] || { echo "Ilova topilmadi: $app"; exit 1; }
[[ ! -e "$release" && ! -e "$previous" ]] || { echo "Bu release nomi ishlatilgan: $release yoki $previous bor"; exit 1; }
[[ -f /etc/ilmiz/staging.env ]] || { echo 'Muhit fayli yo‘q: /etc/ilmiz/staging.env'; exit 1; }

cd "$upload"
sha256sum --check SHA256SUMS
install -d -m 755 /opt/ilmiz/releases "$release" "$release/app"
tar -xzf runtime.tar.gz -C "$release/app" --no-same-owner
chmod -R u=rwX,go=rX "$release/app"

cd "$release/app"
# Testlar vaqtinchalik bazalar bilan; `DATABASE_URL` muhitda qolsa
# `test_auth.py` uni `setdefault` bilan olib jonli bazaga tegardi.
runuser -u ilmiz -- env -u DATABASE_URL PYTHONDONTWRITEBYTECODE=1 \
    /opt/ilmiz/venv/bin/python -W ignore::ResourceWarning -m unittest discover -s backend/tests -p 'test_*.py'
runuser -u ilmiz -- env -u DATABASE_URL PYTHONDONTWRITEBYTECODE=1 \
    /opt/ilmiz/venv/bin/python -m unittest harvester.test_oai_harvester

install -d -m 700 /var/backups/ilmiz
backup="/var/backups/ilmiz/before-$release_id.db"
/opt/ilmiz/venv/bin/python -c "from pathlib import Path; from deploy.prepare_staging import snapshot; snapshot(Path('/var/lib/ilmiz/ilmiz.db'), Path('$backup')); print('Baza zaxirasi tekshirildi: $backup')"

systemctl stop ilmiz-staging
mv -- "$app" "$previous"
rollback() {
    systemctl stop ilmiz-staging || true
    if [[ -d "$app" ]]; then
        mv -- "$app" "/opt/ilmiz/app-failed-$release_id"
    fi
    mv -- "$previous" "$app"
    systemctl start ilmiz-staging
    echo "YANGILASH MUVAFFAQIYATSIZ: eski kod qaytarildi, baza o'zgarmadi. Yiqilgan nusxa: /opt/ilmiz/app-failed-$release_id"
}
trap rollback ERR
mv -- "$release/app" "$app"
systemctl start ilmiz-staging
for _ in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then break; fi
    sleep 1
done
curl -fsS http://127.0.0.1:8000/api/health
echo
curl -fsS 'http://127.0.0.1:8000/api/seo?path=%2Fmaqolalar%3Fsahifa%3D2' >/dev/null
trap - ERR
rmdir -- "$release" 2>/dev/null || true
systemctl is-active ilmiz-staging
curl -fsS http://127.0.0.1:8000/api/stats
echo
echo "Yangilandi. Eski kod: $previous, zaxira: $backup"

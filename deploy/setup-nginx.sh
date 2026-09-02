#!/usr/bin/env bash
#
# ilmiz.uz uchun nginx + Let's Encrypt sertifikatini o'rnatadi.
#
# Nega alohida skript: `DOMAIN.md` dagi tartibda 443 bloklarini qo'lda
# izohga olib, sertifikat olingach qaytarish kerak edi. Bu yerda o'sha
# raqs yo'q — avval faqat 80-portli vaqtinchalik konfiguratsiya qo'yiladi,
# sertifikat olingach esa to'liq konfiguratsiya almashtiriladi.
#
# Qayta ishga tushirsa bo'ladi: har qadam avval holatni tekshiradi.
#
#   sudo bash /opt/ilmiz/app/deploy/setup-nginx.sh
#
# Bazaga tegmaydi.

set -euo pipefail

DOMAIN=ilmiz.uz
WWW=www.ilmiz.uz
APP=127.0.0.1:8000
REPO=${REPO:-/opt/ilmiz/app}
WEBROOT=/var/www/certbot
LIVE=/etc/letsencrypt/live/$DOMAIN/fullchain.pem
FULL_CONF=${FULL_CONF:-$REPO/deploy/nginx-ilmiz.conf}
CERTBOT_EMAIL=${CERTBOT_EMAIL:-info@ilmiz.uz}

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mXATO: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "root kerak: sudo bash $0"
[ -f "$FULL_CONF" ] || die "$FULL_CONF topilmadi — repo $REPO da emasmi?"

say "1/7 Kerakli paketlar"
missing=()
command -v nginx   >/dev/null || missing+=(nginx)
command -v certbot >/dev/null || missing+=(certbot)
if [ ${#missing[@]} -gt 0 ]; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
else
  echo "nginx va certbot allaqachon bor"
fi

say "2/7 Tarmoq devori"
if command -v ufw >/dev/null && ufw status | grep -q "^Status: active"; then
  ufw allow 'Nginx Full' >/dev/null
  echo "ufw: 80 va 443 ochildi"
else
  echo "ufw faol emas — o'tkazib yuborildi"
fi
echo "Eslatma: OVH panelidagi tarmoq devori alohida, uni skript o'zgartira olmaydi."

say "3/7 ACME katalogi"
mkdir -p "$WEBROOT"
chown -R www-data:www-data "$WEBROOT" 2>/dev/null || true

say "4/7 Vaqtinchalik 80-portli konfiguratsiya"
# Sertifikat hali yo'q, shuning uchun to'liq konfiguratsiya `nginx -t` dan
# o'tmaydi. Avval shu minimal variant qo'yiladi: ACME tekshiruvi o'tadi va
# sayt HTTP orqali darrov javob bera boshlaydi.
cat > /etc/nginx/sites-available/ilmiz <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN $WWW;

    location /.well-known/acme-challenge/ {
        root $WEBROOT;
    }

    location / {
        proxy_pass http://$APP;
        proxy_http_version 1.1;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/ilmiz /etc/nginx/sites-enabled/ilmiz
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx >/dev/null 2>&1 || true
systemctl reload nginx
echo "HTTP tayyor"

say "5/7 Ilova javob berayaptimi"
if curl -fsS --max-time 10 -o /dev/null "http://$APP/"; then
  echo "ilova $APP da javob beryapti"
else
  echo "DIQQAT: $APP javob bermayapti. Sertifikat baribir olinadi, lekin"
  echo "sayt bo'sh qaytaradi. Tekshiring: systemctl status ilmiz-staging"
fi

say "6/7 Sertifikat"
if [ -f "$LIVE" ]; then
  echo "sertifikat allaqachon bor, yangilanishi tekshirilmoqda"
  certbot renew --quiet || true
else
  certbot certonly --non-interactive --agree-tos --email "$CERTBOT_EMAIL" \
    --webroot -w "$WEBROOT" -d "$DOMAIN" -d "$WWW"
fi
[ -f "$LIVE" ] || die "sertifikat olinmadi — yuqoridagi certbot xabarini o'qing"

say "7/7 To'liq konfiguratsiya (HTTPS)"
cp "$FULL_CONF" /etc/nginx/sites-available/ilmiz
nginx -t
systemctl reload nginx

say "Tekshiruv"
echo -n "http  -> "; curl -s -o /dev/null -w '%{http_code} (kutilgani 301)\n' --max-time 10 "http://$DOMAIN/" || echo "javob yo'q"
echo -n "https -> "; curl -s -o /dev/null -w '%{http_code} (kutilgani 200)\n' --max-time 10 "https://$DOMAIN/" || echo "javob yo'q"
echo -n "www   -> "; curl -s -o /dev/null -w '%{http_code} (kutilgani 301)\n' --max-time 10 "https://$WWW/" || echo "javob yo'q"
echo
echo "robots.txt:"
curl -s --max-time 10 "https://$DOMAIN/robots.txt" | head -5 || true
echo
echo "Agar robots.txt da 'Disallow: /' chiqsa — /etc/ilmiz/production.env dagi"
echo "ILMIZ_SITE_URL https:// bilan boshlanmayapti yoki ILMIZ_NOINDEX=1 qolgan."
echo
say "Tugadi"

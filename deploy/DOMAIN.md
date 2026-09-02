# ilmiz.uz domenini ulash

Ilova tomoni tayyor va tekshirildi. Qolgani — serverdagi ish.

## Ilovaning holati

`ILMIZ_SITE_URL=https://ilmiz.uz` qo'yilganda lokal tekshiruv shuni
ko'rsatdi:

| Tekshiruv | Natija |
| --- | --- |
| `robots.txt` | `Host: ilmiz.uz`, `Sitemap: https://ilmiz.uz/sitemap.xml`, indekslashga ruxsat |
| `sitemap.xml` | barcha havolalar `https://ilmiz.uz/...` |
| Bosh sahifa | `canonical` va `og:url` — `https://ilmiz.uz/`, `robots: index, follow` |

**Xavfsizlik sharti:** `seo.is_production_host()` faqat **HTTPS** da rost
qaytaradi. Ya'ni sertifikat o'rnatilmaguncha sayt qidiruv tizimlariga
ochilmaydi — `ILMIZ_SITE_URL=http://ilmiz.uz` qo'yilsa ham `noindex`
saqlanadi. Bu ataylab shunday.

## Bosqichlar

### 1. DNS — siz qilasiz

Registrator panelida ilmiz.uz uchun:

```
A     ilmiz.uz       -> <server IP>
A     www.ilmiz.uz   -> <server IP>
```

Tarqalishini kuting va tekshiring:

```bash
dig +short ilmiz.uz
```

### 2. nginx

`deploy/nginx-ilmiz.conf` tayyor. Serverda:

```bash
sudo cp /opt/ilmiz/app/deploy/nginx-ilmiz.conf /etc/nginx/sites-available/ilmiz
sudo ln -s /etc/nginx/sites-available/ilmiz /etc/nginx/sites-enabled/ilmiz
sudo mkdir -p /var/www/certbot
sudo nginx -t
```

`nginx -t` sertifikat yo'qligidan shikoyat qiladi — bu normal, keyingi
qadamda hal bo'ladi. Avval faqat 80-portli blok ishlasin:
443 bloklarini vaqtincha izohga oling, `nginx -t && sudo systemctl reload nginx`.

### 3. TLS sertifikati

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d ilmiz.uz -d www.ilmiz.uz
```

So'ng 443 bloklarini izohdan chiqarib:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Certbot yangilanishni o'zi rejalashtiradi; tekshirish:
`sudo certbot renew --dry-run`.

### 4. Ilova sozlamalari

`deploy/production.env.example` dan nusxa oling:

```bash
sudo cp /opt/ilmiz/app/deploy/production.env.example /etc/ilmiz/production.env
sudo chown root:ilmiz /etc/ilmiz/production.env
sudo chmod 640 /etc/ilmiz/production.env
```

Ichida `ILMIZ_ADMIN_TOKEN` va OAuth kalitlarini to'ldiring, so'ng
xizmat faylida `EnvironmentFile` ni shu faylga qarating va:

```bash
sudo systemctl daemon-reload && sudo systemctl restart ilmiz-staging
```

### 5. OAuth qaytish manzillari — siz qilasiz

ORCID va Google konsollarida ruxsat etilgan manzillarga **aynan**
quyidagilarni qo'shing:

```
https://ilmiz.uz/api/auth/orcid/callback
https://ilmiz.uz/api/auth/google/callback
```

Bularni men qo'sha olmayman — hisoblar sizniki.

### 6. Tekshirish

```bash
curl -sI https://ilmiz.uz | head -1
curl -s https://ilmiz.uz/robots.txt
curl -s https://ilmiz.uz/sitemap.xml | head -5
```

`robots.txt` da `Sitemap: https://ilmiz.uz/sitemap.xml` va indekslashga
ruxsat ko'rinishi kerak. Agar `Disallow: /` chiqsa, demak
`ILMIZ_SITE_URL` HTTPS emas yoki `ILMIZ_NOINDEX=1` qolgan.

## Diqqat qilinadigan joylar

**Baza almashtirilmasin.** `install_staging.sh` faqat birinchi o'rnatish
uchun va mavjud bazani ataylab qayta yozmaydi. Serverda foydalanuvchi
hisoblari va tasdiqlangan maqolalar to'planadi — ular fayl bilan
almashtirilsa yo'qoladi.

**Migratsiyalar startda ishlaydi.** Yangi kod chiqqanda `init_db()`
`alembic upgrade head` ni bajaradi. FTS5 indeksi qurilishi ~12 soniya
davom etadi va ~0.24 GB joy egallaydi.

**`--no-proxy-headers` qolaveradi.** Kod so'rovdan absolyut URL
qurmaydi: yo'naltirishlar nisbiy, kanonik havolalar esa
`ILMIZ_SITE_URL` dan olinadi. Kelajakda `request.url` dan absolyut
manzil yasalsa, bu bayroqni qayta ko'rib chiqish kerak bo'ladi.

**Mavjud jurnal saytining DNS'iga tegilmasin.** ilmiz.uz alohida domen.

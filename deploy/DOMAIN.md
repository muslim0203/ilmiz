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

### 1. DNS — bajarildi (02.09.2026)

Registrator: **aHOST** (`clients.ahost.uz`, domen id 295388).

`Nameservers` yorlig'ida **Use DNS Manager** tanlangan — bu domenni
aHOST'ning `rdns1.ahost.uz`, `rdns2.ahost.uz`, `rdns3.ahost.uz`
serverlariga bog'laydi. `DNS hosting -> DNS manager` da zona:

```
@      A       14400   51.79.165.112     # sayt
mail   A       14400   185.196.212.52    # aHOST pochta serveri
www    CNAME   14400   ilmiz.uz
@      MX  0   14400   mail.ilmiz.uz
```

`ftp` CNAME, SPF, DKIM va DMARC yozuvlari aHOST andozasidan qolgan.
Pochta sozlamalari quyida, «Pochta» bo'limida.

Zona uchala nom serverida ham to'g'ri javob beradi:

```bash
nslookup ilmiz.uz rdns1.ahost.uz   # -> 51.79.165.112
```

**Kutilayotgan qadam:** `.uz` reyestri hali eski delegatsiyani
(`dns1/dns2.ahost.uz`, `ns1/ns2.ahost.cloud`) ko'rsatmoqda. aHOST
paneli 24 soatgacha tarqalishini ogohlantiradi. Tayyor bo'lganini
shundan bilasiz:

```bash
nslookup -type=NS ilmiz.uz ns1.uz    # rdns1..3.ahost.uz chiqishi kerak
nslookup ilmiz.uz 8.8.8.8            # 51.79.165.112
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

### 5. OAuth

Qaytish manzillari kodda `ILMIZ_PUBLIC_URL` dan quriladi
(`auth.redirect_uri`), ya'ni aynan quyidagilar:

```
https://ilmiz.uz/api/auth/orcid/callback
https://ilmiz.uz/api/auth/google/callback
```

**Google — bajarildi (02.09.2026).** `journalmaturidi@gmail.com`
hisobida `IlmIz` (`ilmiz-507405`) loyihasi yaratildi, OAuth ekrani
sozlandi (External), `IlmIz web (ilmiz.uz)` nomli Web application
clienti qaytish manzili bilan qo'shildi va ilova **In production**
holatiga o'tkazildi. Scope'lar `openid email profile` — nosezgir,
shuning uchun Google tekshiruvi talab qilinmaydi.

`production.env` ga `GOOGLE_CLIENT_ID` va `GOOGLE_CLIENT_SECRET` ni
o'zingiz kiritasiz — sirlar repoga ham, suhbatga ham tushmaydi.

**ORCID — hal qilinmagan.** Hisobda bitta ilova bor: `Moturidiylik`
(Client ID `APP-F16HNV4B9YSEF2FU`), u allaqachon uchta saytga xizmat
qiladi (maturidijournal.org va mijournals.com). ORCID bir hisobda
faqat bitta ilovaga ruxsat beradi, shuning uchun ilmiz.uz ham shu
ro'yxatga qo'shilishi kerak edi.

Lekin `developer-tools/update-client.json` **403** qaytaradi —
sessiyani yangilagandan keyin ham, hatto **hech narsa
o'zgartirmasdan** saqlashga urinilganda ham. Ya'ni muammo qo'shilayotgan
manzilda emas: ORCID bu ilovaga umuman tahrir kiritishga yo'l
qo'ymayapti. Mavjud uchta manzil buzilmadi.

Keyingi qadam — ORCID qo'llab-quvvatlash xizmatiga yozish
(support@orcid.org), Client ID va 403 xatosini ko'rsatib. Shu
hal bo'lguncha saytda faqat Google orqali kirish ishlaydi:
`available_providers()` sozlanmagan provayderni ro'yxatga qo'shmaydi,
shuning uchun ORCID tugmasi shunchaki ko'rinmaydi.

### 6. Tekshirish

```bash
curl -sI https://ilmiz.uz | head -1
curl -s https://ilmiz.uz/robots.txt
curl -s https://ilmiz.uz/sitemap.xml | head -5
```

`robots.txt` da `Sitemap: https://ilmiz.uz/sitemap.xml` va indekslashga
ruxsat ko'rinishi kerak. Agar `Disallow: /` chiqsa, demak
`ILMIZ_SITE_URL` HTTPS emas yoki `ILMIZ_NOINDEX=1` qolgan.

## Pochta (@ilmiz.uz)

aHOST domen bilan birga **bepul pochta yo'naltirish** beradi. Ilova
o'zi pochta yubormaydi (kodda SMTP yo'q), shuning uchun bu faqat
aloqa manzillari uchun.

Sozlangan yo'naltirishlar — `DNS hosting -> Email forwarding`:

| Manzil | Qayerga |
| --- | --- |
| info@ilmiz.uz | journalmaturidi@gmail.com |
| admin@ilmiz.uz | journalmaturidi@gmail.com |

**Nega `mail` alohida A yozuvi.** aHOST yo'naltirishi MX yozuvi
`185.196.212.52` ga qaraydigan nomga ko'rsatilishini talab qiladi.
`ilmiz.uz` ning o'zi esa sayt serveriga (51.79.165.112) qarashi
shart. Shuning uchun andozadagi `mail CNAME -> ilmiz.uz` o'chirilib,
o'rniga `mail A -> 185.196.212.52` qo'yildi va MX `mail.ilmiz.uz` ga
qaratildi.

**Cheklov:** bu faqat **qabul qilish**. `@ilmiz.uz` dan xat yuborish
uchun haqiqiy pochta quti (pullik xizmat) kerak bo'ladi.

Panel DNS tarqalmaguncha «Доменное имя ilmiz.uz не направлено на
почтовый сервер» degan ogohlantirishni ko'rsatib turadi — bu kutilgan
holat, ular ommaviy DNS orqali tekshiradi.

Tekshirish:

```bash
nslookup -type=MX ilmiz.uz rdns1.ahost.uz   # mail.ilmiz.uz
nslookup mail.ilmiz.uz rdns1.ahost.uz       # 185.196.212.52
```

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

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

Delegatsiya ham tarqaldi (02.09.2026): reyestr `rdns1..3.ahost.uz`
ni ko'rsatadi va ommaviy DNS domenni to'g'ri hal qiladi.

```bash
nslookup -type=NS ilmiz.uz ns1.uz    # rdns1..3.ahost.uz
nslookup ilmiz.uz 8.8.8.8            # 51.79.165.112
```

### 2. nginx — bajarildi (02.09.2026)

Serverga nginx 1.28.3 o'rnatildi. `deploy/nginx-ilmiz.conf` faol;
`http://ilmiz.uz` va `www` asosiy HTTPS manzilga 301 qaytaradi, asosiy
HTTPS manzil esa ilovaga uzatiladi. Serverdagi UFW faol emas; tashqi 80/443
ham javob berayotgani uchun OVH tarmoq devori bu portlarni to'smayapti.

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

### 3. TLS sertifikati — bajarildi (02.09.2026)

Let's Encrypt sertifikati `ilmiz.uz` va `www.ilmiz.uz` uchun olindi;
amal qilish muddati 2026-12-01. Certbot timer yoqildi va
`renew --dry-run --no-random-sleep-on-renew` muvaffaqiyatli o'tdi.

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d ilmiz.uz -d www.ilmiz.uz
```

So'ng 443 bloklarini izohdan chiqarib:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Certbot yangilanishni o'zi rejalashtiradi; tekshirish:
`sudo certbot renew --dry-run`.

### 4. Ilova sozlamalari — domen qismi bajarildi (02.09.2026)

Ishlayotgan xizmatning `/etc/ilmiz/staging.env` fayli xavfsiz zaxiralandi
va `ILMIZ_SITE_URL=https://ilmiz.uz`, `ILMIZ_PUBLIC_URL=https://ilmiz.uz`,
`ILMIZ_NOINDEX=0` qilib yangilandi. Xizmat nomi hozircha
`ilmiz-staging.service`; bu nom ishlashiga ta'sir qilmaydi. Google OAuth va
admin token sirlari hali serverda yo'q.

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

### 6. Tekshirish — domen va SEO bajarildi (02.09.2026)

Tashqi tekshiruv: HTTPS 200, HTTP va `www` 301, sitemap 200, bosh sahifada
`canonical=https://ilmiz.uz/` hamda `robots=index, follow`; `robots.txt`
indekslashga ruxsat beradi va admin/auth API yo'llarini taqiqlaydi.
`/api/auth/providers` sirlar kiritilmagani sabab hozircha bo'sh ro'yxat beradi.

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

Yo'naltirish faol: DNS tarqalgach panel «не направлено на почтовый
сервер» ogohlantirishini olib tashladi (02.09.2026 tekshirildi).

Tekshirish:

```bash
nslookup -type=MX ilmiz.uz rdns1.ahost.uz   # mail.ilmiz.uz
nslookup mail.ilmiz.uz rdns1.ahost.uz       # 185.196.212.52
```

## Serverni yangilash (02.09.2026)

Server git orqali emas, fayllarni nusxalash bilan joylashtirilgan
(`/opt/ilmiz/app` da `.git` yo'q), shuning uchun `git pull` ishlamaydi.
Yangilash tartibi quyidagicha bo'ldi.

**Holat:** serverdagi kod 31-avgustdagi holatda edi — migratsiyalar
katalogi, FTS5 indeksi va OpenAlex xizmati umuman yo'q, `alembic`
paketi ham o'rnatilmagan.

**Bajarilgani:**

1. Zaxira: `/opt/ilmiz/app-before-migrations-20260902-1741` va
   `VACUUM INTO` bilan `ilmiz.backup-20260902-1741-pre-migrations.db`
   (1.03 GB, ruxsati 600).
2. `alembic==1.19.1` venv'ga o'rnatildi (mahalliy versiya bilan bir xil).
3. 18 ta fayl yuklandi: `alembic.ini`, `backend/migrations/**`,
   `db.py`, `main.py`, `ingest.py`, `openalex.py`, `search_index.py`,
   `manage.py` va testlar. Nazorat summalari taqqoslab tekshirildi.
4. Serverda **300 ta test o'tdi** (Python 3.14.4). `DATABASE_URL` ni
   o'chirib ishga tushirish shart: `test_auth.py` uni `setdefault`
   bilan oladi, ya'ni muhitda qolsa ishlab turgan bazaga tegardi.
5. Xizmat to'xtatilib, `init_db()` qo'lda bajarildi — **39 soniya**.
   Startda emas, chunki `TimeoutStartSec` 90 soniya va FTS qurilishi
   unga sig'masligi mumkin edi.

**Natija:** `ec3312949a85` belgilandi, so'ng `6b31a7083731` va
`b83feb85c26a` qo'llandi. Baza 1.230 -> 1.305 GB. Ma'lumot butun
qoldi: 467 jurnal, 104 809 maqola, 2 foydalanuvchi, 5 tasdiqlangan
maqola, 1 sessiya — hammasi o'zgarmadi.

FTS5 tekshiruvi serverda: `search_index.available()` -> True,
so'rovlar 15-38 ms, API 54-125 ms, uchala sinxronlash trigger'i joyida.

**Hali qilinmagan:** serverdagi bazada OpenAlex importlari yo'q —
mahalliy bazada 129 616, serverda 104 809 maqola. Kod endi tayyor,
lekin importning o'zi alohida ish.

## OpenAlex importi serverda (02.09.2026)

`manage.py openalex <slug> --apply` 51 jurnal uchun ketma-ket ishga
tushirildi. Uzoq davom etgani uchun `setsid nohup` bilan fonda —
SSH uzilsa ham to'xtamasin.

- Davomiyligi: **12 daqiqa** (17:59 -> 18:11)
- Qo'shilgan maqolalar: **25 012** (50 jurnal muvaffaqiyatli)
- Baza: 104 809 -> **129 907** maqola

FTS indeksi trigger'lar orqali o'zi yangilandi (129 949 yozuv), ya'ni
alohida qayta qurish kerak bo'lmadi. Foydalanuvchi hisoblari va
tasdiqlangan maqolalar tegilmadi.

**`manage.py` uchun `logs/` katalogi kerak.** U `PROJECT_ROOT/logs` ga
yozadi va yo'lni o'zgartirib bo'lmaydi, shuning uchun
`/opt/ilmiz/app/logs` `ilmiz` egaligida yaratildi.

**Ikkita jurnal tuzatildi.** `fan-sportga` importi «OpenAlex'da
topilmadi» bilan tugadi, chunki serverdagi ISSN eski edi. Mahalliy
bazadagi tuzatishlar bilan taqqoslaganda butun `journals` jadvalida
atigi 3 ta maydon farq qilardi:

| Jurnal | Maydon | Edi | Bo'ldi |
| --- | --- | --- | --- |
| fan-sportga (#156) | ISSN | 3030-3087 | 2181-7804 |
| fan-sportga (#156) | sayt | sport-science.uz | (bo'sh, bosma jurnal) |
| TTIT (#312) | sayt | tibbiyot-talimi-va-... | tipme.uz/.../ttvit_magazine |

Asoslari `docs/manual-corrections.md` da. Tuzatish `journal_edit.apply_edits`
orqali qilindi — `manual:` provenance belgisi va completeness qayta
hisobi shu bilan birga bajariladi. So'ng import takrorlanib, 86 maqola
qo'shildi.

Qolgan jadvallar (kontaktlar, tahririyat, profillar, completeness)
mahalliy baza bilan aynan bir xil chiqdi.

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

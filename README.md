# IlmIz — OAK jurnallari va maqolalar indeksi

IlmIz O‘zbekiston OAK ro‘yxatidagi jurnallarni kataloglashtirish va jurnal repozitoriylaridan OAI-PMH 2.0 orqali maqola metama’lumotlarini muntazam yig‘ish uchun qurilayotgan platforma.

## Hozirgi MVP

- Responsive jurnal va maqola katalogi
- Qidiruv, soha, shahar va OAI holati filtrlari
- 24 ta OAK sohasi 10 guruhga ajratilgan, ko‘p tanlovli fan yo‘nalishi modali
- Shahar nomlarining kirill/lotin variantlari bitta kanonik nomga birlashtirilgan
- Jurnal profil drawer'i va OAI monitoring ko‘rinishi
- Boy jurnal profili: aloqa, tahririyat, siyosatlar, bo‘limlar, OAK qarorlari va maydon provenance'i
- PostgreSQL uchun normalizatsiyalangan ma’lumotlar modeli
- Dependency-free Python OAI-PMH CLI
- `resumptionToken`, incremental sana oralig‘i va deleted record qo‘llovi
- FastAPI REST API va SQLAlchemy repository qatlami
- SQLite lokal fallback va `DATABASE_URL` orqali PostgreSQL qo‘llovi
- OAI endpoint audit, harvest run va raw provenance saqlash
- Frontendning jonli API bilan integratsiyasi
- OAK rasmiy elektron reestri importer'i va source hash tarixi
- OAI endpoint discovery navbati va worker CLI
- Operatsion admin dashboard
- Server tomonda render qilinadigan SEO qatlami: har bir jurnal, maqola, soha va shahar uchun alohida manzil, meta, JSON-LD va sitemap

Seed yozuvlar `DEMO`, harvest qilingan yozuvlar esa `OAI-PMH` belgisi bilan ko‘rsatiladi. Agro Inform OAI endpointidan birinchi real pilot yozuvlar import qilingan.

## Ishga tushirish

GitHub tekshiruvlari va OVH deploy holati: [GitHub ulanishi](docs/GITHUB-DEPLOY.md).

### Lokal ishga tushirish

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Frontend (ikkinchi terminalda):

```powershell
npm install
npm run dev
```

API hujjatlari: `http://127.0.0.1:8000/docs`

Admin panel frontendning yuqori o‘ng qismidagi **Admin panel** tugmasi orqali ochiladi.

### Foydalanuvchi profillari

Tadqiqotchilar **ORCID** yoki **Google** orqali kiradi — parol saqlanmaydi.

> Google Scholar’da OAuth ham, ochiq API ham yo‘q, shuning uchun u orqali
> kirish texnik jihatdan mumkin emas. Foydalanuvchi o‘z Scholar profil
> havolasini profilida qo‘lda ko‘rsatadi.

```powershell
$env:ILMIZ_PUBLIC_URL = "http://localhost:5173"
$env:ORCID_CLIENT_ID = "<orcid.org/developer-tools dan>"
$env:ORCID_CLIENT_SECRET = "<...>"
$env:GOOGLE_CLIENT_ID = "<console.cloud.google.com dan>"
$env:GOOGLE_CLIENT_SECRET = "<...>"
```

Redirect URI’lar: `<ILMIZ_PUBLIC_URL>/api/auth/orcid/callback` va
`<ILMIZ_PUBLIC_URL>/api/auth/google/callback`.

Sozlanmagan provayder kirish oynasida ko‘rsatilmaydi. Endpointlar:

- `GET /api/auth/providers` — sozlangan provayderlar
- `GET /api/auth/{provider}/start` — OAuth oqimini boshlash
- `GET /api/auth/{provider}/callback` — sessiya cookie’sini o‘rnatadi
- `GET /api/auth/me` — joriy foydalanuvchi (kirmagan bo‘lsa `null`)
- `PATCH /api/auth/me` — ism, ish joyi, Scholar havolasi
- `POST /api/auth/logout` — sessiyani bekor qiladi

`/api/admin/*` ga ikki yo‘l bilan kirish mumkin:

1. **Hisob orqali** — `is_admin` bo‘lgan foydalanuvchi ORCID/Google bilan
   kiradi, alohida token kerak emas. Admin panel tugmasi faqat shunday
   foydalanuvchiga ko‘rinadi.
2. **Token orqali** — `ILMIZ_ADMIN_TOKEN`. Bu zaxira yo‘l: birinchi adminni
   tayinlash uchun kerak, aks holda hech kim kira olmay qolardi.

Adminni tayinlash (ORCID iD yoki e-pochta bo‘yicha):

```powershell
.\.venv\Scripts\python.exe backend\manage.py grant-admin 0000-0002-1825-0097
.\.venv\Scripts\python.exe backend\manage.py grant-admin admin@example.uz --revoke
```

Birorta admin ham yo‘q va token ham sozlanmagan bo‘lsa, admin API butunlay
yopiq (HTTP 503):

```powershell
$env:ILMIZ_ADMIN_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000
```

Token `X-Admin-Token: <token>` yoki `Authorization: Bearer <token>` header'i
orqali yuboriladi. Admin panel uni birinchi kirishda so‘raydi va brauzerda
saqlaydi.

Production build:

```bash
npm run build
npm run preview
```

## SEO va indekslash

Sayt SPA bo‘lgani uchun qidiruv robotlariga bo‘sh `<div id="root">` ketardi:
Yandex JavaScript’ni deyarli render qilmaydi, Googlebot esa 100 mingdan ortiq
maqolani render navbatida hech qachon ko‘rib ulgurmaydi. Endi **har bir URL
uchun HTML serverda to‘ldiriladi**: `<head>` meta’lari, JSON-LD va `#root`
ichidagi haqiqiy matn. React yuklangach o‘sha joyni egallaydi — mazmun bir xil.

Prodda FastAPI ham API’ni, ham saytni beradi (`dist/` static + SEO qobiq):

```bash
npm run build
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

### Manzil tuzilmasi

| URL | Nima |
| --- | --- |
| `/` | Bosh sahifa |
| `/jurnallar`, `?sahifa=N` | OAK jurnallari ro‘yxati |
| `/jurnal/{slug}` | Jurnal profili |
| `/jurnal/{slug}/{yil}` | Jurnalning yillik arxivi |
| `/maqolalar`, `?sahifa=N` | Maqolalar bazasi |
| `/maqola/{id}-{sarlavha}` | Maqola sahifasi (eski slug 301 bilan kanonikka) |
| `/sohalar`, `/soha/{slug}` | Ilmiy soha bo‘yicha qo‘nish sahifalari |
| `/shaharlar`, `/shahar/{slug}` | Shahar bo‘yicha qo‘nish sahifalari |
| `/loyiha` | Loyiha haqida |
| `/qidiruv?q=` | Sayt qidiruvi (`noindex`, `SearchAction` shu yerga ishora qiladi) |
| `/robots.txt`, `/sitemap.xml` | Robotlar uchun |

Sitemap indeks: `sitemap-pages.xml`, `sitemap-journals.xml` (jurnallar +
yillik arxivlar) va har biri 25 000 URL’dan iborat `sitemap-articles-N.xml`.

Maqola sahifalarida Google Scholar o‘qiydigan `citation_*` va agregatorlar
uchun `DC.*` meta’lari, JSON-LD’da esa `ScholarlyArticle` →
`PublicationIssue` → `PublicationVolume` → `Periodical` zanjiri beriladi.

### Sozlamalar

| O‘zgaruvchi | Vazifasi |
| --- | --- |
| `ILMIZ_SITE_URL` | **Majburiy.** Kanonik domen, masalan `https://ilmiz.uz`. Sozlanmasa sayt butunlay `noindex` bo‘lib qoladi. |
| `ILMIZ_ALLOW_INDEXING=1` | Boshqa domenda (staging) indekslashni majburan yoqish |
| `ILMIZ_NOINDEX=1` | Indekslashni majburan o‘chirish |
| `GOOGLE_SITE_VERIFICATION` | Search Console meta tasdiqlash kodi |
| `YANDEX_VERIFICATION` | Yandex Webmaster meta tasdiqlash kodi |
| `BING_SITE_VERIFICATION` | Bing Webmaster kodi |
| `ILMIZ_INDEXNOW_KEY` | IndexNow kaliti; `/<kalit>.txt` avtomatik beriladi |
| `ILMIZ_DIST_DIR` | `dist/` boshqa joyda bo‘lsa |

Tasdiqlash **fayli** (`googlexxxx.html` kabi) `public/` ga qo‘yiladi — Vite
uni `dist/` ga ko‘chiradi va FastAPI o‘sha yerdan beradi.

Staging nusxa `ILMIZ_SITE_URL`siz ishga tushirilsa, `robots.txt` da
`Disallow: /` qaytadi va hamma sahifa `noindex` bo‘ladi. Bu ataylab:
indekslangan staging asosiy domen bilan to‘liq dublikat bo‘lib, ikkalasining
ham o‘rnini pasaytiradi.

### Ishga tushirishdan keyin

1. Google Search Console va Yandex Webmaster’da domenni tasdiqlang
   (yuqoridagi env yoki `public/` dagi fayl orqali).
2. Ikkalasiga ham `https://<domen>/sitemap.xml` ni qo‘shing.
3. Yandex Webmaster’da IndexNow kalitini yarating, uni
   `ILMIZ_INDEXNOW_KEY` ga yozing va tekshiring: `https://<domen>/<kalit>.txt`
   o‘sha kalitni qaytarishi kerak.

Harvest’dan keyin o‘zgargan manzillarni Yandex va Bing’ga bildirish
(Google IndexNow’ni qo‘llamaydi — u sitemap’dagi `lastmod` bo‘yicha keladi):

```bash
python backend/manage.py indexnow --days 7            # quruq yurish
python backend/manage.py indexnow --days 7 --apply    # haqiqatan yuboradi
```

## Harvester

Endpointni aniqlash:

```bash
python harvester/oai_harvester.py identify https://journal.example.uz/oai
python harvester/oai_harvester.py formats https://journal.example.uz/oai
```

Incremental yozuvlarni JSONL formatida olish:

```bash
python harvester/oai_harvester.py harvest https://journal.example.uz/oai \
  --from-date 2026-08-01 \
  --metadata-prefix oai_dc \
  --output harvest-output/journal.jsonl
```

Windows PowerShell'da yuqoridagi buyruqni bitta qatorda yozish mumkin.

Endpointni bazaga audit qilish va bir sahifa yozuvni import qilish:

```powershell
.\.venv\Scripts\python.exe backend\manage.py audit agro-inform https://agro-inform.uz/index.php/agro-inform/oai
.\.venv\Scripts\python.exe backend\manage.py harvest agro-inform https://agro-inform.uz/index.php/agro-inform/oai --from-date 2026-01-01 --page-limit 1
```

Rasmiy OAK reestrini yangilash va endpoint audit navbatini boshqarish:

```powershell
.\.venv\Scripts\python.exe backend\manage.py import-oak
.\.venv\Scripts\python.exe backend\manage.py queue-audits
.\.venv\Scripts\python.exe backend\manage.py process-audits --limit 10

# Barcha audit navbatini parallel yakunlash
.\.venv\Scripts\python.exe backend\manage.py drain-audits --batch-size 24 --workers 4

# Barcha faol OAI manbalarni yangilash. Standart rejim inkremental: har manba
# o‘z `last_success_at` idan 1 kun oldingi sanadan boshlaydi, hech qachon
# muvaffaqiyatli bo‘lmagan manba to‘liq tortiladi.
.\.venv\Scripts\python.exe backend\manage.py harvest-all --workers 3

.\.venv\Scripts\python.exe backend\manage.py harvest-all --full                 # to‘liq tarix
.\.venv\Scripts\python.exe backend\manage.py harvest-all --from-date 2026-08-20 # bitta sana
.\.venv\Scripts\python.exe backend\manage.py harvest-all --retry-failed         # yiqilganlarni qayta audit
```

Manba holatlari: `healthy` — oxirgi harvest o‘tgan; `degraded` — oxirgi
urinish(lar) yiqilgan, lekin manba hali ro‘yxatda va ketma-ket xatolar soniga
qarab 2, 4, 8 … soat (ko‘pi bilan bir hafta) kutib qayta uriniladi
(`--ignore-backoff` kutmaydi); `failed` — 10 ta ketma-ket xato yoki audit
o‘tmagan, faqat `--retry-failed` yoki `harvest <slug> <url>` qaytaradi.
Harvester HTTP 429/500/502/503/504 va uzilgan ulanishlarni 3 martagacha qayta
uradi, `badResumptionToken` da oxirgi ko‘rilgan sanadan davom etadi.

Serverda harvest **systemd timer** bilan har kuni 03:00 UTC da,
yiqilganlarni qayta audit qilish yakshanba 14:00 UTC da bajariladi:

```bash
sudo bash /opt/ilmiz/app/deploy/install_harvest_timer.sh   # bir marta
sudo systemctl start ilmiz-harvest.service                 # kutmasdan boshlash
sudo journalctl -fu ilmiz-harvest.service                  # kuzatish
```

`manage.py` ni serverda qo‘lda ishga tushirganda muhit faylini ko‘rsating,
aks holda `DATABASE_URL` siz u joriy katalogda yangi bo‘sh baza yaratadi:

```bash
sudo -u ilmiz env ILMIZ_ENV_FILE=/etc/ilmiz/staging.env ILMIZ_LOG_DIR=/var/lib/ilmiz/logs   /opt/ilmiz/venv/bin/python /opt/ilmiz/app/backend/manage.py harvest-all --workers 3
```

Saqlangan `raw_metadata` dan jild/son/betlarni qayta hisoblash (qayta harvest
qilmasdan, parser tuzatilgandan keyin):

```powershell
.\.venv\Scripts\python.exe backend\manage.py reparse-bibliographic          # quruq yurish
.\.venv\Scripts\python.exe backend\manage.py reparse-bibliographic --apply  # qo‘llash
```

`source_records` faqat `raw_xml` ni saqlaydi; oai_dc metama’lumoti undan
`metadata_from_xml()` orqali aynan tiklanadi. Eski bazadan ortiqcha
`raw_metadata` ustunini o‘chirish va faylni siqish:

```powershell
.\.venv\Scripts\python.exe backend\manage.py drop-raw-metadata
```

Harvest xatolari `logs/ilmiz.log` ga (yoki `ILMIZ_LOG_DIR` katalogiga) yoziladi
va `harvest-all` natijasida `errors[]` sifatida qaytadi.

### tadqiq.uz dan yetishmayotgan maydonlarni to‘ldirish

tadqiq.uz mahalliy OAK katalogidan ISSN, rasmiy sayt, asos solingan yil, til,
chiqish davriyligi va taqriz turini oladi. Faqat bo‘sh maydonlar to‘ldiriladi;
har bir qiymat manba URLi bilan `journal_profile_fields` ga yoziladi.

```powershell
.\.venv\Scripts\python.exe backend\manage.py import-tadqiq                      # quruq yurish
.\.venv\Scripts\python.exe backend\manage.py import-tadqiq --apply              # qo‘llash
.\.venv\Scripts\python.exe backend\manage.py import-tadqiq --cache-dir .cache   # sahifalarni keshlash
.\.venv\Scripts\python.exe backend\manage.py import-tadqiq --apply --fix-dead-sites
```

`--fix-dead-sites` eskirgan sayt manzilini almashtiradi, lekin faqat jurnalning
barcha OAI manbalari yiqilgan va host boshqa bo‘lgan hollarda. Sayt tuzatilgach
`queue-audits` + `drain-audits` yangi OAI endpointlarni topishi mumkin.

So‘rovlar sekundiga bittadan yuboriladi. `--cache-dir` berilsa sahifalar
keshdan o‘qiladi va saytga qayta murojaat qilinmaydi.

`import-oak` rasmiy reestrdagi bir jurnalning turli fan/qaror yozuvlarini bitta jurnal profiliga birlashtiradi, original yozuvlarni esa `oak_registry_entries` jadvalida provenance sifatida saqlaydi.
Har bir importda `oak_registry_snapshot_entries` va `oak_registry_snapshot_meta`
orqali aynan o‘sha paytdagi joriy ro‘yxat saqlanadi. Shu sabab eski/o‘zgargan
yozuvlar bugungi OAK sonlariga aralashmaydi.

### Jurnalning boy profilini yig‘ish

OJS jurnalining ochiq sahifalaridan About, Contact, Editorial Team, Submissions,
Current Issue hamda navigatsiyada topilgan maxsus siyosat sahifalarini yig‘ish:

```powershell
.venv\Scripts\python.exe backend\manage.py profile agro-inform
```

Natijalar `journal_profiles`, `journal_contacts`, `editorial_members`,
`journal_policies`, `journal_sections`, `journal_indexing_claims`, `journal_links`
va `journal_profile_fields` jadvallarida saqlanadi. Har bir yozuvda manba URL'i
va yig‘ilgan vaqt bor; indeksatsiya nomlari tashqi tasdiq bo‘lmasa `claimed`
holatida qoladi.

API:

- `GET /api/facets` — filtr uchun soha guruhlari va shaharlar (sanoqlari bilan)
- `GET /api/journals?field=A&field=B&city=Toshkent` — ko‘p sohali filtr (OR)
- `GET /api/journals?sort=activity` — standart tartib: so‘nggi yillarda eng
  ko‘p maqola chiqargan jurnallardan boshlab. `sort=name` alifbo tartibi.
- `GET /api/articles?field=A&city=Toshkent` — maqolalarni serverda filtrlash
- `GET /api/articles?q=...` — sarlavha, annotatsiya va mualliflar bo‘yicha.
  So‘rov so‘zlarga ajratiladi (tartib muhim emas) va kirill/lotin yozuvi
  farqi hisobga olinadi: «Сулайманова» va «Sulaymanova» bir xil natija beradi.

Qidiruv `articles.search_text` ustunida ishlaydi — u kichik harfga keltirilgan
va lotinlashtirilgan sarlavha + annotatsiya + mualliflar. Normalizatsiya
qoidasi o‘zgarsa qayta qurish kerak:

```powershell
.\.venv\Scripts\python.exe backend\manage.py rebuild-search-index
```
- `GET /api/journals/{slug}` — asosiy ma’lumot, boy profil va OAK reestr yozuvlari
- `POST /api/admin/profiles/collect` — bitta jurnal profilini qayta yig‘ish

### OAK asosidagi ommaviy profil navbati

```powershell
.venv\Scripts\python.exe backend\manage.py queue-profiles
.venv\Scripts\python.exe backend\manage.py process-profiles --limit 25 --workers 3
.venv\Scripts\python.exe backend\manage.py drain-profiles --batch-size 25 --workers 3
.venv\Scripts\python.exe backend\manage.py retry-profiles --max-attempts 2
.venv\Scripts\python.exe backend\manage.py refresh-incomplete --score-below 70 --max-attempts 3
```

Navbat faqat OAK’da faol va rasmiy sayt havolasi mavjud milliy jurnallar uchun
yaratiladi. OJS/OAI aniqlangan saytlar birinchi bo‘lib qayta ishlanadi. Natija
`succeeded` (70%+), `partial` yoki `failed` holatida, to‘liqlik balli va xato
sababi bilan `profile_jobs` jadvaliga yoziladi.

- `GET /api/admin/profile/jobs` — profil navbati natijalari
- `POST /api/admin/profiles/queue` — navbatni to‘ldirish
- `POST /api/admin/profiles/process` — cheklangan batchni qayta ishlash

PostgreSQL ishlatish uchun:

```powershell
$env:DATABASE_URL="postgresql+psycopg://ilmiz:password@127.0.0.1:5432/ilmiz"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000
```

Testlar:

```bash
python -m unittest discover -s harvester -p "test_*.py"
python -m unittest backend.tests.test_api backend.tests.test_ingest backend.tests.test_registry backend.tests.test_profile_collector
```

## Tuzilma

```text
src/                  React/Vite ilovasi
backend/app/          FastAPI, ORM va ingest service
backend/app/seo_routes.py  robots.txt, sitemap va SEO HTML qobig‘i
backend/manage.py     Audit/harvest boshqaruv CLI
public/               Statik fayllar (favicon, og-image, tasdiqlash fayllari)
database/schema.sql   To‘liq PostgreSQL production sxemasi
harvester/            OAI-PMH discovery va harvest client
```

## Keyingi vertikal

1. DOI/ORCID deduplikatsiyasi va metama’lumot sifati.
3. Admin autentifikatsiyasi va rol nazorati.
4. Production PostgreSQL va to‘liq matnli qidiruv.

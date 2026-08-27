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

Seed yozuvlar `DEMO`, harvest qilingan yozuvlar esa `OAI-PMH` belgisi bilan ko‘rsatiladi. Agro Inform OAI endpointidan birinchi real pilot yozuvlar import qilingan.

## Ishga tushirish

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

`/api/admin/*` endpointlari `ILMIZ_ADMIN_TOKEN` bilan himoyalangan. Token
sozlanmagan bo‘lsa admin API butunlay yopiq (HTTP 503):

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

# Topilgan barcha OAI manbalardan to‘liq tarixni olish (page-limit yo‘q)
.\.venv\Scripts\python.exe backend\manage.py harvest-all --workers 3
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

Harvest xatolari `logs/ilmiz.log` ga yoziladi va `harvest-all` natijasida
`errors[]` sifatida qaytadi.

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
- `GET /api/articles?field=A&city=Toshkent` — maqolalarni serverda filtrlash
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
backend/manage.py     Audit/harvest boshqaruv CLI
database/schema.sql   To‘liq PostgreSQL production sxemasi
harvester/            OAI-PMH discovery va harvest client
```

## Keyingi vertikal

1. Auditdan o‘tgan manbalar uchun harvest scheduler.
2. DOI/ORCID deduplikatsiyasi va metama’lumot sifati.
3. Admin autentifikatsiyasi va rol nazorati.
4. Production PostgreSQL, qidiruv va sitemap/schema.org integratsiyasi.

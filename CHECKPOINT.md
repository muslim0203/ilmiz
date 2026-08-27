# IlmIz checkpoint — 2026-08-26 (2-sessiya, yakuniy)

Bu fayl ishni xavfsiz davom ettirish nuqtasini belgilaydi.

## Ushbu sessiyada bajarilgan

### Kritik bug tuzatildi: harvest jimgina yiqilardi

Avvalgi checkpointda 16 ta run `running` holatida qolgani `Ctrl+C` ga yozilgan
edi. **Bu tashxis noto‘g‘ri.** Toza ishga tushirishda ayni holat 20 soniya
ichida qayta takrorlandi. Logging qo‘shilgach haqiqiy sabab ko‘rindi:

```
UNIQUE constraint failed: source_records.source_id, source_records.oai_identifier
```

Sessiya `autoflush=False` bilan ochilgan, shu sababli `_upsert_record` dagi
`SELECT` hali flush qilinmagan yozuvni ko‘rmasdi. Bitta OAI oqimida ayni
`oai_identifier` ikki marta kelsa (deleted headerlar va bir nechta `setSpec`
aynan shunday keladi), ikkinchi `INSERT` commit paytida constraintni buzardi va
**butun manba harvest'i yiqilardi**. Xato hech qayerda saqlanmagani uchun run
abadiy `running` da qolar, manba esa `healthy` ko‘rinardi.

Tuzatishlar:

| Fayl | O‘zgarish |
| --- | --- |
| `backend/app/db.py` | SQLite connect listener: `journal_mode=WAL`, `busy_timeout=30000`, `synchronous=NORMAL`, `foreign_keys=ON` |
| `backend/app/services/ingest.py` | `_BatchCache` — commit oralig‘idagi flush qilinmagan `SourceRecord`/`Article` obyektlarini identifier, DOI va (jurnal, sarlavha, yil) bo‘yicha keshlaydi |
| `backend/app/services/ingest.py` | `_mark_run_failed()` — xato holatini toza sessiyada yozadi; ilgari yiqilgan sessiya bilan commit ham yiqilib, status umuman saqlanmasdi |
| `backend/app/services/ingest.py` | `_ingest_source_by_id` endi traceback yozadi va `error` maydonini qaytaradi (avval `except Exception: return failed` hammasini yutib yuborardi) |
| `backend/manage.py` | `configure_logging()` → `logs/ilmiz.log` fayli + konsolga WARNING+ |

`harvest-all` natijasi endi `errors[]` massivi va `logFile` yo‘lini qaytaradi.

Regressiya testlari: `backend/tests/test_ingest.py` — takroriy identifier,
takroriy DOI, bir batchdagi bir xil sarlavha. Eski kodda bu testlar rostdan
yiqilishi tasdiqlangan.

### Kritik bug 2: jild/son/bet parseri buzuq ma’lumot yozardi

UI ni vizual tekshirishda iqtibos panelida `4(MY)` ko‘rindi. `_bibliographic_parts`
regexlarida word boundary yo‘q edi:

- `ECONOMY` ichidagi `no` → son `MY` (8 217 maqola);
- `INNOVATION` ichidagi `no` → son `vation` / `vative` / `vations` (12 506 maqola);
- kirilcha `автоматики` ichidagi `том` → jild `ки` (493 maqola).

Jami **36 393 maqolada (35%) son buzuq** edi va bu APA/MLA/Chicago/Harvard/BibTeX
iqtiboslarining hammasiga tushardi.

Tuzatildi:

- `` word boundary qo‘shildi, qiymat raqamdan boshlanishi talab qilinadi;
- o‘zbekcha postfiks shakl qo‘shildi (`4-jild`, `2-son`, `10-20 bet`) va u
  birinchi sinaladi — aks holda inglizcha pattern `5-jild 3-son` da jildni
  `3-son` deb olardi;
- OJS `dc:source` ning markersiz oxirgi segmenti (`...; 37-40`) betlar uchun
  qo‘shildi, yil oralig‘i (`2019-2020`) filtrlanadi.

Mavjud ma’lumot `reparse-bibliographic` CLI orqali saqlangan `raw_metadata` dan
qayta hisoblandi (qayta harvest qilinmadi, hech narsa uydirilmadi):

| Maydon | Avval | Hozir |
| --- | --- | --- |
| pages | 5 093 (4.9%) | **61 516 (57.7%)** |
| issue | 103 150 (buning 36 393 tasi buzuq) | 99 512 (buzuq 0) |
| volume | 83 087 (521 tasi buzuq) | 83 059 (buzuq 0) |

Buyruqdan oldin `ilmiz.backup-2026-08-26.db` zaxira nusxasi olingan
(`VACUUM INTO`, 1.72 GB). Buyruq idempotent: ikkinchi yurish 0 o‘zgarish beradi.

```powershell
.\.venv\Scripts\python.exe backend\manage.py reparse-bibliographic          # quruq yurish
.\.venv\Scripts\python.exe backend\manage.py reparse-bibliographic --apply  # qo‘llash
```

### Harvest natijalari

Tuzatishdan keyin 22 manba qayta yig‘ildi:

- maqolalar: **76 171 → 106 586** (+30 415, +40%);
- `source_records`: 84 872 → 115 874;
- maqolasi bor jurnallar: 106 → 113;
- **`running` holatida osilib qolgan run: 0** (avval 16 ta edi).

Testlar: **65/65** (59 backend + 6 harvester), ikkala tartibda ham.
`npm run build`: ✅ 243 kB JS / 35 kB CSS.

## Hozirgi baza holati

| | |
| --- | --- |
| Jonli maqolalar | 106 586 |
| O‘chirilgan maqolalar | 15 |
| Jurnallar | 493 (113 tasida maqola bor) |
| Healthy OAI manbalar | 113 / 754 |
| Harvest runs | 118 succeeded, 52 failed, 0 running |
| Baza hajmi | **1.01 GB** (WAL rejimida) |

Metadata coverage (jonli maqolalar bo‘yicha):

| Maydon | % |
| --- | --- |
| landing_url | 100.0 |
| publication_date | 100.0 |
| authors | 100.0 |
| abstract | 98.6 |
| language | 97.1 |
| issue | 93.4 |
| volume | 77.9 |
| pages | 57.7 |
| doi | 28.5 |
| pdf_url | 1.1 |

Yillar bo‘yicha: 2026 — 26 380, 2025 — 27 229, 2024 — 20 941, 2023 — 12 520,
2022 — 7 403, 2021 — 6 917, 2020 — 1 494, 2019 — 361.

## Yig‘ilmagan manbalar

Quyidagi 5 manba jurnal serverining o‘z xatosi sabab yig‘ilmadi. Ma’lumot
uydirib to‘ldirilmasin; xato matnlari `harvest_sources.last_error` da saqlangan.

| ID | URL | Xato |
| --- | --- | --- |
| 8 | energy.tdtu.uz | HTTP 504 Gateway Timeout |
| 89 | sciencetech.uz | HTTP 500 Internal Server Error |
| 119 | www.techscience.uz | HTTP 521 |
| 161 | mining.tdtu.uz | HTTP 504 Gateway Timeout |
| 232 | sciencetech.uz (89 bilan bir xil URL) | HTTP 500 Internal Server Error |

Source 143 (`yashil-iqtisodiyot-taraqqiyot.uz`) HTTP 429 Too Many Requests oldi
— bu bizning so‘rov tezligimiz sabab, qayta urinish kerak.

### `raw_metadata` ustuni olib tashlandi (1.73 GB → 1.01 GB)

`source_records.raw_metadata` — bu `raw_xml` dan `_parse_record()` orqali
olingan dict, ya’ni to‘liq takrorlanish. `raw_xml` esa `ET.tostring(record)`,
ya’ni to‘liq record elementi.

O‘chirishdan oldin tiklanish aniqligi butun bazada tekshirildi:

```
raw_xml bor yozuvlar: 118 666
aynan mos           : 118 666
farq                : 0
parse xato          : 0
```

Bajarilgani:

- `harvester/oai_harvester.py` ga `metadata_from_xml()` qo‘shildi;
- `SourceRecord.raw_metadata` modeldan olib tashlandi, `_upsert_record` endi
  unga yozmaydi;
- `reparse_bibliographic` `raw_xml` dan o‘qiydi — o‘tkazilgandan keyin
  106 584 maqolada **0 o‘zgarish, 0 xato**, ya’ni natija aynan bir xil;
- `drop-raw-metadata` CLI ustunni o‘chiradi va VACUUM qiladi (12.8 s).

| | Avval | Hozir |
| --- | --- | --- |
| Baza hajmi | 1.73 GB | **1.01 GB** (−720 MB, 42%) |

Tekshirildi: `pragma integrity_check` = ok, `foreign_key_check` = 0 muammo,
106 586 maqola / 118 666 source_record / 483 MB raw_xml joyida, yangi harvest
smoke testi (`--source-id 36 --page-limit 1`) muvaffaqiyatli.

Zaxira nusxalar (ikkalasi ham `.gitignore` da):

- `ilmiz.backup-2026-08-26.db` — reparse’dan oldingi holat;
- `ilmiz.backup-2026-08-26-pre-drop.db` — ustun o‘chirilishidan oldingi holat.

Kerak bo‘lmasa ikkalasini o‘chirib ~3.4 GB bo‘shatish mumkin.

```powershell
.\.venv\Scripts\python.exe backend\manage.py drop-raw-metadata
```

### Admin API himoyalandi

`/api/admin/*` ilgari **butunlay ochiq** edi — hech qanday token so‘ralmasdan
harvest ishga tushirish, navbat to‘ldirish va profil yig‘ish mumkin edi.

Yechim — `ILMIZ_ADMIN_TOKEN` muhit o‘zgaruvchisi asosidagi bitta admin token,
ikki qatlamda:

1. `APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])` —
   12 ta endpoint routerga ko‘chirildi, shuning uchun yangi admin endpoint
   qo‘shilsa ham avtomatik yopiq bo‘ladi;
2. `admin_guard` HTTP middleware — tokenni marshrutlashdan oldin tekshiradi.
   FastAPI body’ni dependency’lardan oldin parse qilgani uchun buzuq JSON
   401 o‘rniga 422 berardi; middleware javobni bir xil qiladi va
   `/api/admin` ostidagi mavjud bo‘lmagan yo‘llarni ham qamrab oladi.

Muhim tafsilotlar:

- **Fail-closed**: token sozlanmagan bo‘lsa hamma so‘rov 503 bilan rad etiladi.
  Standart holat ochiq bo‘lib qolmasligi shart.
- Token `secrets.compare_digest` bilan solishtiriladi.
- Ikkala header shakli ishlaydi: `X-Admin-Token: <token>` va
  `Authorization: Bearer <token>`.
- Token har so‘rovda `os.getenv` orqali o‘qiladi — almashtirish uchun restart
  shart emas.
- Frontend tokenni `localStorage` da saqlaydi; 401/503 kelganda admin panel
  o‘rniga kirish ekrani ko‘rsatiladi (`AdminAuthError`).

Jonli tekshirildi:

| So‘rov | Natija |
| --- | --- |
| 12 ta admin endpoint, tokensiz | 401 |
| noto‘g‘ri token | 401 |
| buzuq JSON body, tokensiz | 401 |
| `/api/admin/mavjud-emas` | 401 (404 emas) |
| `X-Admin-Token` / `Bearer` to‘g‘ri token | 200 |
| ochiq endpointlar (`health`, `stats`, `journals`, `articles`) | 200 |

UI: token ekrani → noto‘g‘ri token rad etildi → to‘g‘ri token bilan dashboard
ochildi. Brauzerdan header’siz xom `fetch` hamon 401 oladi.

Ishga tushirish:

```powershell
$env:ILMIZ_ADMIN_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000
```

### Kategoriya va filtr tizimi qayta qurildi

Filtrni tekshirganda uchta jiddiy muammo chiqdi.

**1. Soha ro‘yxati demo ma’lumotdan qattiq yozilgan edi.** `src/data.ts` da 7 ta
soha bor edi, bazada esa 24 ta. Ya’ni **17 ta soha umuman tanlanmasdi** —
Veterinariya, Farmatsevtika, San’atshunoslik, Geologiya-mineralogiya,
Islomshunoslik va boshqalar filtrda yo‘q edi. Hero’dagi “23 Ilmiy sohalar”
raqami ham qo‘lda yozilgan edi.

**2. Maqola filtri faqat yuklangan 500 ta maqola ichida ishlardi.** Soha tanlansa
mijoz tarafida `article.fields.includes(field)` bajarilardi, lekin brauzerda
faqat eng yangi 500 ta maqola bor edi. Natijada:

| Soha | Eski (mijozda) | Yangi (serverda) |
| --- | --- | --- |
| Veterinariya | **0** maqola | 500 |
| Geologiya-mineralogiya | **0** maqola | 500 |
| San’atshunoslik | **0** maqola | 500 |
| Farmatsevtika | 46 maqola | 472 |

**3. Shahar nomlari kirill/lotin bo‘yicha ikkiga bo‘lingan edi.** “Тошкент” (380)
va “Toshkent” (3) alohida punkt edi; “Фарғона”/“Farg‘ona”, “Қарши”/“Qarshi”,
“Урганч”/“Urgаnсh” ham (oxirgisida kirill homogliflari bor). 24 ta “shahar”
aslida 20 ta.

Bundan tashqari `/api/journals` da SQL `limit` filtrdan **oldin** qo‘llanardi —
`field=X&limit=1` so‘rovi “alifboda birinchi jurnal shu sohada bo‘lsagina”
natija berardi.

Bajarilgani:

| Fayl | O‘zgarish |
| --- | --- |
| `backend/app/services/taxonomy.py` | 24 ta OAK sohasini 10 guruhga ajratadi; shahar nomlarini kanonik shaklga keltiradi |
| `backend/app/main.py` | `GET /api/facets` — haqiqiy soha/shahar ro‘yxati va sanoqlari; `field`/`city` endi takrorlanuvchi parametr (OR); limit filtrdan keyin qo‘llanadi |
| `src/FieldPicker.tsx` | Guruhlangan ko‘p tanlovli modal: guruh checkboxi, ichki qidiruv, sanoqlar, Esc bilan yopish |
| `src/App.tsx` | Bitta `field` o‘rniga `selectedFields[]`, chiplar, ma’lumotga asoslangan “Ko‘p qidirilgan” havolalari |
| `src/data.ts` | Qattiq yozilgan `fields` ro‘yxati olib tashlandi |

**Guruh sanoqlari qo‘shish emas, birlashma.** Dastlab guruh sanog‘ini sohalar
yig‘indisi qilib yozgandim; bir jurnal guruh ichidagi ikki sohaga tegishli
bo‘lsa ikki marta sanalardi. Jonli tekshirishda ko‘rindi: Gumanitar fanlar
yig‘indi bo‘yicha 241, aslida **135**. Endi barcha 10 guruhda facets sanog‘i
haqiqiy filtr natijasiga aynan teng (test bilan qopланgan).

Yana bir tuzatish: `loadCatalog` va yangi qidiruv effekti bir xil so‘rovni ikki
marta yuborardi. Endi har sahifa yuklanishida aniq 4 ta so‘rov.

Natija: **24 ta soha, 10 guruh, 20 ta kanonik shahar** — hammasi filtrda
tanlanadi.

### tadqiq.uz dan jurnal maydonlari import qilindi

Jurnal profillari to‘liq emas edi: ISSN 493 tadan faqat 111 tasida, asos
solingan yil 10 tasida. tadqiq.uz aynan o‘sha OAK reestrini boyitilgan holda
e’lon qiladi (436 jurnal). robots.txt bu sahifalarga ruxsat beradi.

Sahifalarda **JSON-LD structured data** (`@type: Periodical`) bor — HTML
scraping o‘rniga o‘shandan o‘qiymiz. U ISSN, rasmiy sayt, nashriyot, shahar va
eng muhimi **kirillcha muqobil nom** beradi.

436 sahifa sekundiga bitta so‘rov bilan yuklandi (436/436 xatosiz).

Natija:

| Maydon | Avval | Hozir |
| --- | --- | --- |
| ISSN | 111 | **270** |
| Asos solingan yil | 10 | **233** |
| Rasmiy sayt | 342 | **400** |
| Profillar | 299 | **463** |
| Chiqish davriyligi | ~49 | 235 |
| Taqriz turi | 0 | 148 |
| Tillar | — | 355 |

Moslashtirish: ISSN 41, aniq nom 322, o‘xshash nom 58, mos kelmadi 15
(**421/436 = 96.6%**).

Siyosat: faqat bo‘sh maydonlar to‘ldiriladi; har bir qiymat manba URLi bilan
`journal_profile_fields` ga `tadqiq:*` prefiksi ostida yoziladi (1 779 yozuv);
ishonch past bo‘lsa jurnal chetlab o‘tiladi.

```powershell
.\.venv\Scripts\python.exe backend\manage.py import-tadqiq              # quruq yurish
.\.venv\Scripts\python.exe backend\manage.py import-tadqiq --apply      # qo‘llash
```

#### Yo‘l-yo‘lakay tuzatilgan to‘rt xato

1. **Containment yolg‘iz yetarli emas.** Bazamizda “Молия”, “Психология” kabi
   bir so‘zli nomlar bor; ular boshqa jurnalning uzun nomida uchrasa 1.00 ball
   chiqib butunlay boshqa jurnalga bog‘lanardi. Kamida 2 ta umumiy token va
   Jaccard ≥ 0.4 talab qilindi. Bu nafaqat noto‘g‘rilarni kesdi, balki
   to‘g‘rilarini ochdi — soxta 1.00 ballar haqiqiy mosliklarni to‘sib turgan
   ekan.
2. **ISSN mosligi tasdiqlanmasdi.** `seed.py` dagi demo jurnallarda ISSN qo‘lda
   yozilgan va bir nechtasi boshqa jurnalniki bo‘lib chiqdi (`Acta CAMU` ↔
   `Inter education & global study`). Endi ISSN mosligi nom bilan tasdiqlanadi;
   tasdiqlanmasa nom bo‘yicha izlashda davom etiladi. 5 ta ziddiyat aniqlandi.
   Birinchi import shu sabab bekor qilinib, baza zaxiradan tiklandi va qayta
   yurgizildi.
3. **`journal_profile_fields` da UNIQUE constraint buzilishi.** Sessiya
   `autoflush=False` bilan ochilgani uchun `select` shu tranzaksiyada qo‘shilgan
   qatorni ko‘rmasdi (aynan `_upsert_record` dagi xato sinfi). Bir jurnalga ikki
   marta yozilganda import yiqilardi. Kesh qo‘shildi.
4. **Til ro‘yxati va placeholderlar.** Sayt tillarni “Oʻzbek, Rus, Ingliz” deb
   bitta satrda beradi va bo‘sh maydonlarni “Maʼlumot topilmadi” matni bilan
   ko‘rsatadi. Ikkalasi ham bazaga tushib qolgan edi — parser tuzatildi,
   yozilgan 153 ta ro‘yxat va 89 ta placeholder tozalandi.

#### Ikkinchi bosqich: tahririyat tasdig‘idan keyin

Moturidiylik jurnali tahrirchisi bizdagi va tadqiq.uz dagi maʼlumot farq
qilishini ko‘rsatdi va tadqiq.uz maʼlumotlari to‘g‘riligini tasdiqladi. Bir
jurnalni tekshirish uchta tizimli kamchilikni ochdi.

**1. Parser yon paneldagi maydonlarning bir qismini o‘qimasdi.** `e-ISSN`,
`Soʻnggi son` va “Jurnal haqida” tavsifi umuman olinmagan edi. Butun keshda
76 ta e-ISSN, 190 ta so‘nggi son va 256 ta haqiqiy tavsif o‘qilmay qolgan.

**2. Tavsiflarimizning 487/493 tasi shablon matn** edi —
`"OAK rasmiy elektron reestridan import qilingan jurnal."`. Bu maʼlumot emas.
Endi tadqiq.uz da haqiqiy tavsif bo‘lsa almashtiriladi; tahririyat yozgan
haqiqiy tavsifga tegilmaydi (test bilan qoplangan).

**3. `Fill-only-empty` siyosati noto‘g‘ri qiymatni himoya qilardi.** Bizda
`maturidijournal.uz` (o‘lik domen), haqiqiysi `maturidijournal.org`. Eski
qiymat bo‘sh bo‘lmagani uchun to‘g‘risi yozilmasdi. `--fix-dead-sites` bayrog‘i
qo‘shildi: sayt faqat jurnalning **barcha OAI manbalari yiqilgan** bo‘lsa va
host boshqa bo‘lsagina almashtiriladi — yaʼni bizdagi manzil ishlamayotgani
isbotlangan hollarda. 53 ta sayt tuzatildi.

Bundan tashqari `profile_collector` o‘lik/parked saytlardan yig‘gan 19 ta axlat
`summary` tozalandi (`"You need to enable JavaScript"`, `"Home / About the
Journal"`, `"NASHRLAR"`, `"TEZ KUNDA isoftware.uz"`).

**Natija — tuzatilgan saytlar yangi OAI manbalarni ochdi.** Moturidiylik
ilgari umuman yig‘ib bo‘lmaydigan edi (0 maqola); `.org` manzilida OAI
endpoint ishlaydi. 109 ta audit qayta yurgizilib **28 ta yangi ishlaydigan
OAI endpoint** topildi (healthy manbalar 113 → 141).

| Maydon | Boshida | Ikkinchi bosqichdan keyin |
| --- | --- | --- |
| ISSN | 111 | 270 |
| e-ISSN | 52 | 111 |
| Asos solingan yil | 10 | 233 |
| Haqiqiy tavsif | 6 | 245 |
| So‘nggi son | — | 132 |
| Healthy OAI manbalar | 113 | 141 |

```powershell
.\.venv\Scripts\python.exe backend\manage.py import-tadqiq --apply --fix-dead-sites
.\.venv\Scripts\python.exe backend\manage.py queue-audits
.\.venv\Scripts\python.exe backend\manage.py drain-audits --batch-size 24 --workers 4
```

#### Alohida topilma: bazamizda dublikat jurnallar

Mos kelmagan yozuvlarni tekshirganda chiqdi: **25 ta guruh, 51 ta jurnal** bir
xil nom, faqat kirill va lotin yozuvda ikki marta ro‘yxatga olingan
(`Meros` #75 / `Мерос` #200; `Farmatsevtika jurnali` #14 / #164 / #186).
493 raqami shu sabab ~26 taga shishgan; haqiqiysi ~467 (tadqiq.uz 436 deydi).
Importer bunday hollarda taxmin qilmaydi — chetlab o‘tadi.

Birlashtirish qaytarib bo‘lmaydigan amal, alohida hal qilinsin.

## UI tekshiruvi (bajarildi)

`http://localhost:5173` da tekshirilgan:

- jurnallar katalogi, filtrlar, maqola soni va son soni — ishlaydi;
- maqolalar oynasi: sarlavha, muallif, annotatsiya, sana, jild/son, jurnal nomi,
  OAI-PMH belgisi, «Maqola sahifasi» havolasi, DOI — ishlaydi;
- iqtibos paneli: APA, MLA, Chicago, Harvard + «Nusxa olish» — ishlaydi;
  tuzatishdan keyin `4(MY)` → `4(1)`;
- qidiruv `q=pedagogika`: 335 ms, 500 natija.

### `/api/journals` tezlashtirildi (3.15 s → 0.21 s)

`journal_payload` `journal.articles` ni o‘qir, `selectinload` esa barcha
106 586 Article ORM obyektini xotiraga yuklardi — faqat `articleCount` va
`issueCount` ni sanash uchun. Bosh sahifa har ochilganda shu endpoint
chaqiriladi.

Endi `journal_counts()` bitta aggregate so‘rov bilan hisoblaydi
(`count()` + `count(distinct jild|son|yil)`), `selectinload(Journal.articles)`
ikkala endpointdan ham olib tashlandi.

| | Avval | Hozir |
| --- | --- | --- |
| `/api/journals?limit=500` | 3.15 s | **0.21 s** |
| `/api/journals/{slug}` | — | 0.13 s |

To‘g‘riligi 493 jurnalning hammasida SQL ground truth bilan solishtirilgan:
**0 farq**. Testlar: `test_journal_counts_are_aggregated`,
`test_journal_detail_counts_match_list`.

## Keyingi sessiyada davom ettirish

1. **Dublikat jurnallarni birlashtirish** — 25 guruh, 51 jurnal (yuqoriga qarang).
2. Frontendda pagination — hozir `limit=500` bilan cheklangan.
3. 115 ta takroriy `base_url` — bir OAI endpoint ikki marta yig‘ilmoqda.
3. Sohalarni yanada chuqurlashtirish (ASJC uslubidagi ichki kategoriyalar) —
   OAK reestrida faqat `XX.00.00` darajasi bor, shuning uchun bunga tashqi
   manba yoki maqola kalit so‘zlaridan qurilgan xarita kerak.
3. Yuqoridagi 5 manbani vaqti-vaqti bilan qayta urinish (rejalashtiruvchi bilan).
4. Foydalanuvchi alohida rozilik bermaguncha deploy qilinmasin.

## Keyinga qoldirilgan: yo‘qolgan 15 282 maqolani tiklash

Platforma manbalari jurnallarga ajratilganda (`split-platform-source`), 48 ta
yo‘l bizdagi jurnalga 0.9 chegarasida moslasha olmadi va ularning maqolalari
o‘chirildi. Ba’zilari haqiqiy OAK jurnallari bo‘lishi mumkin — nomlar
avtomatik moslashmagan.

To‘liq ro‘yxat: `docs/unmatched-platform-paths.json` (48 yo‘l, 15 282 maqola).
**Bu faylni saqlash shart** — ifloslangan manbalar o‘chirilgani uchun ro‘yxatni
qayta hosil qilib bo‘lmaydi.

Eng kattalari:

| Maqola | Yo‘l | repositoryName |
| --- | --- | --- |
| 2 090 | `/gtfj` | Журнал гуманитарных и естественных наук |
| 1 498 | `/Conferences` | Konferensiyalar (jurnal emas) |
| 1 300 | `/law` | ЖУРНАЛ ПРАВОВЫХ ИССЛЕДОВАНИЙ |
| 1 210 | `/ijrs` | International Journal of Recently Scientific Research |
| 793 | `/conference` | E-Conference platform (jurnal emas) |
| 573 | `/tas` | ОСНОВЫ МЕДИЦИНЫ |
| 531 | `/cajm` | Central Asian Journal of Medicine |
| 495 | `/pedagogy` | ИННОВАЦИИ В ПЕДАГОГИКЕ И ПСИХОЛОГИИ |

Tiklash yo‘li: har bir yo‘l uchun `<platforma>/index.php/<yol>/oai` manzilini
tegishli jurnalga qo‘lda biriktirib, `harvest-all` bilan yig‘ish. Xaritalashni
qo‘lda tasdiqlash kerak — avtomatik moslashtirish chegarani pasaytirishni
talab qiladi, bu esa yana noto‘g‘ri biriktirishga olib keladi.

## Ochiq muammolar (muhimlik tartibida)

1. ~~Admin endpointlarida autentifikatsiya yo‘q~~ — tuzatildi
   (`ILMIZ_ADMIN_TOKEN`). Keyingi bosqich: ko‘p foydalanuvchi va rol nazorati,
   agar kerak bo‘lsa.
2. ~~Baza 1.72 GB, ortiqcha `raw_metadata`~~ — tuzatildi (1.01 GB).
   Qolgan 483 MB `raw_xml` — provenance uchun kerak; zarur bo‘lsa zlib bilan
   siqish mumkin.
3. ~~`/api/journals` 3.15 s~~ — tuzatildi (0.21 s). Maqola qidiruvi 335 ms,
   hozircha FTS5 shart emas.
4. **Frontendda pagination yo‘q.** `src/api.ts` doim `limit=500` so‘raydi,
   `offset` ishlatilmaydi, API total count qaytarmaydi.
5. **`pages` 4.9% va `pdf_url` 1.1%.** `oai_dc` da bu ma’lumot yo‘q. Yechim:
   OJS'ning `mods`/`jats` prefiksini so‘rash yoki landing sahifadan olish.
   Citation sifatiga to‘g‘ridan-to‘g‘ri ta’sir qiladi.
6. **115 ta takroriy `base_url`.** Bir OAI endpoint bir nechta jurnal ostida
   ro‘yxatga olingan (masalan source 89 va 232 — bir xil sciencetech.uz).
   Natijada bir repozitoriy ikki marta yig‘iladi.
7. **~630 ta dublikat sarlavha.** Dedupe kaliti
   `(journal_id, normalized_title, publication_year)` — yil turlicha kelsa
   dublikat yaraladi. Yilsiz fallback tekshiruv kerak.
8. **Migratsiya tizimi yo‘q.** `init_db()` da qo‘lda `ALTER TABLE`. Shu sabab
   `ix_articles_publication_date` modelda `index=True` bo‘lsa-da bazada
   mavjud emas. Alembic kerak.
9. **Git yo‘q.** `.gitignore` tayyor (`ilmiz.db`, `logs` uchun `*.log` ichida),
   `git init` qilish mumkin.

## Muhim fayllar

- `backend/app/db.py` — engine, SQLite PRAGMA sozlamalari, ad-hoc migration.
- `backend/app/services/ingest.py` — OAI ingest, `_BatchCache`, dedupe, bulk harvest.
- `backend/app/services/audit_queue.py` — parallel OAI discovery/audit.
- `backend/app/services/citations.py` — citation formatterlar.
- `backend/manage.py` — logging, `drain-audits`, `harvest-all` va worker CLI.
- `backend/app/main.py` — maqola API, qidiruv, facets, `require_admin` va admin router.
- `backend/app/services/taxonomy.py` — soha guruhlari va shahar kanonizatsiyasi.
- `src/FieldPicker.tsx` — fan yo‘nalishi tanlash modali.
- `backend/app/services/tadqiq_import.py` — tadqiq.uz importi va nom moslashtirish.
- `backend/tests/test_ingest.py` — batch dedupe regressiya testlari.
- `src/App.tsx`, `src/api.ts`, `src/types.ts`, `src/styles.css` — maqola UI.
- `logs/ilmiz.log` — harvest xatolari va tracebacklar.
- `harvester/oai_harvester.py` — `metadata_from_xml()` va OAI client.
- `ilmiz.backup-2026-08-26*.db` — zaxira nusxalar.

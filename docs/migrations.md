# Baza migratsiyalari (Alembic)

## Nega kerak bo'ldi

Ilgari sxema `backend/app/db.py` dagi `init_db()` ichida qo'lda boshqarilardi:
`Base.metadata.create_all()` yangi jadval qo'shardi, yangi ustunlar esa
har biri uchun alohida yozilgan `ALTER TABLE` bloklari bilan qo'shilardi.

Bu ikki narsani qila olmasdi:

1. **Indeks yaratmasdi.** `ALTER TABLE ... ADD COLUMN` faqat ustun qo'shadi.
   Modelda `index=True` yozilgan bo'lsa ham indeks paydo bo'lmasdi.
   Alembic joriy qilinganda aynan shunday ikkita nomuvofiqlik topildi —
   jonli bazada `ix_articles_publication_date` va `ix_users_is_admin` yo'q edi.
2. **Sxema versiyasini yozmasdi.** Bazaning qaysi holatda ekanini bilishning
   yo'li yo'q edi, ya'ni server va lokal ajralib ketsa ham sezilmasdi.

## Qanday ishlaydi

`init_db()` ishga tushishda `alembic upgrade head` ni bajaradi va uch holatni
qamrab oladi:

| Holat | Nima bo'ladi |
| --- | --- |
| Baza bo'sh | Migratsiyalar butun sxemani quradi |
| Baza to'la, Alembic belgisi yo'q | Boshlang'ichda belgilanadi (DDL bajarilmaydi), keyin yangilari qo'llanadi |
| Baza belgilangan | Faqat yangi migratsiyalar qo'llanadi |

Ikkinchi holat mavjud o'rnatmalarni avtomatik qabul qiladi, ya'ni serverda
qo'lda buyruq berish shart emas. Belgi `alembic_version` jadvalining
borligiga emas, undagi **versiya yozuviga** qarab aniqlanadi: Alembic bu
jadvalni o'qish uchun ham yaratib qo'yadi.

Xizmat `--workers 1` bilan ishlaydi, shuning uchun startdagi migratsiya
poyga holatiga tushmaydi. Ishchilar soni oshirilsa, migratsiyani startdan
ajratib, deploy qadamiga ko'chirish kerak bo'ladi.

## Yangi o'zgarish qo'shish

```bash
.venv/Scripts/python.exe -m alembic revision --autogenerate -m "qisqa izoh"
```

So'ng yaratilgan faylni **albatta o'qib chiqing**. Ikki narsaga e'tibor:

- **Ifoda-indekslar.** SQLAlchemy 2.0 SQLite'da `text("publication_year DESC")`
  kabi indekslarni aks ettira olmaydi, shuning uchun autogenerate ularni
  o'tkazib yuboradi yoki "o'zgargan" deb noto'g'ri belgilaydi. Ular
  boshlang'ich migratsiyada qo'lda `op.execute(...)` bilan yozilgan.
- **Soxta farqlar.** Yuqoridagi sabab bilan `ix_articles_feed` va
  `ix_articles_journal_feed` har autogenerate'da "o'zgargan" bo'lib chiqadi.
  Ularni migratsiyaga kiritmang.

Tekshirish:

```bash
.venv/Scripts/python.exe backend/manage.py migrate
```

`backend/tests/test_migrations.py` migratsiyalar modellar bilan bir qadamda
turishini tekshiradi: bo'sh bazadan qurilgan jadvallar to'plami
`Base.metadata` bilan bir xil bo'lishi va e'lon qilingan indekslar
yaratilishi shart. Modelga jadval qo'shib migratsiya yozilmasa, test yiqiladi.

## Zaxira

Jonli bazada migratsiya ishlatishdan oldin nusxa oling:

```bash
.venv/Scripts/python.exe -c "import sqlite3; sqlite3.connect('ilmiz.db').execute('VACUUM INTO ?', ('ilmiz.backup.db',))"
```

## Qidiruv indeksi (FTS5)

`b83feb85c26a` migratsiyasi `articles_fts` virtual jadvalini va uni
sinxron ushlab turuvchi uchta triggerni yaratadi.

Tokenizator ataylab **`trigram`**, `unicode61` emas. `unicode61` so'z
boshidan qidiradi va qo'shma so'zlarni topmaydi: "pedagogika" so'rovida
"artpedagogika", "xalqpedagogikasi", "oligofrenopedagogika" tushib qolardi
— 1149 natijadan 61 tasi. Trigram qism-so'z bo'yicha topadi va eski
`LIKE '%so'z%'` bilan **aynan bir xil** natija beradi.

O'lchov (104 519 maqola, hisob + birinchi 50 qator):

| So'rov | Eski `LIKE` | FTS5 |
| --- | --- | --- |
| pedagogika | 0.284s | 0.018s |
| morfologiya | 0.300s | 0.011s |
| iqtisodiy tahlil | 0.339s | 0.040s |
| kamoliddin sharofiddinov | 0.486s | 0.010s |

Narxi: indeks ~0.24 GB joy egallaydi va migratsiya ~12 soniya davom etadi.

**Triggerlar ommaviy yangilashni sekinlashtiradi**: 5000 qatorni yangilash
0.01s o'rniga 2.7s. Oddiy yig'ishda bu sezilmaydi (bir necha yuz qator),
lekin `rebuild-search-index` kabi butun jadvalni aylanadigan buyruq
sezilarli uzayadi. Kerak bo'lsa triggerlarni vaqtincha o'chirib, keyin
`manage.py fts --rebuild` bilan indeksni qayta qurish mumkin.

Tekshirish:

```bash
.venv/Scripts/python.exe backend/manage.py fts
```

`integrity: true` — indeks asosiy jadvalga mos. `--rebuild` qo'shilsa
indeks noldan quriladi.

PostgreSQL'da FTS5 yo'q. `services/search_index.py` buni tekshiradi va
qidiruv eski `LIKE` yo'lidan ketaveradi.

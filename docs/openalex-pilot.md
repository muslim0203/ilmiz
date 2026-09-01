# OpenAlex piloti — 2026-08-31

## Nega qaraldi

Loyihaning eng katta bo'shlig'i — **346 ta jurnalda umuman maqola yo'q**.
Ularning 237 tasida OAI sinalgan va ishlamagan, 90 tasida sayt ham yo'q.
Zotero (sayt tahlili) va GROBID (PDF) piloti ikkalasi ham bu bo'shliqqa
yetmadi.

[OpenAlex](https://openalex.org) — bepul, ochiq ilmiy indeks. U Crossref
va DataCite'ni ham qamraydi.

## Natija: eng istiqbolli yo'l shu

**1. Crossref topa olmaganini topadi.**

| Prefiks | Crossref | OpenAlex |
| --- | --- | --- |
| 10.5281 (Zenodo, 11 600 maqola) | 0/4 | **6/6** |
| umumiy namuna | 55% | 50% |

Qamrovlari bir-birini to'ldiradi, ustma-ust tushmaydi.

**2. Maqolasiz jurnallarning yarmi OpenAlex'da bor.**

12 ta maqolasiz jurnal tekshirilganda 6 tasi topildi:

| Jurnal | OpenAlex'dagi ishlar |
| --- | --- |
| Химия природных соединений | 15 872 |
| Samarqand DU ilmiy axborotnomasi | 1 403 |
| Kimyo va kimyo texnologiyasi | 447 |
| Кимёвий технология | 245 |
| Toshkent DTU | 134 |
| Adabiy meros | 62 |

**3. Ma'lumot sifati import uchun yetarli.**

| Maydon | 5 tadan |
| --- | --- |
| sarlavha | 5 |
| DOI | 5 |
| yil | 5 |
| mualliflar | 4 |
| betlar | 1 |

Annotatsiya `abstract_inverted_index` orqali **10/10** ta ishda bor va
tiklanadi.

## Ko'lami

| | Soni |
| --- | --- |
| Maqolasiz jurnallar | 346 |
| Shundan ISSN'i bor (qidirsa bo'ladi) | **171** |
| Namunaviy topilish darajasi | ~50% |
| **Taxminiy qamrab olinadigan** | **~85 jurnal** |

## Ehtiyot bo'lish kerak bo'lgan joylar

1. **Hammasi bizniki emas.** «Химия природных соединений» da 15 872 ish
   bor, lekin bu jurnalning butun xalqaro tarixi. OAK ro'yxatidagi
   nashrga tegishli qismini ajratish kerak — aks holda indeks buziladi.
2. **`publication_year` ishonchsiz.** Namunada 2024 deb ko'rsatilgan
   ishning `biblio.volume` qiymati 2022 edi. Import qilishdan oldin
   solishtirish kerak.
3. **Betlar ko'pincha yo'q** (5 tadan 1 tasida).
4. **Provenance.** Bu yozuvlar jurnalning o'zidan emas, OpenAlex'dan
   keladi. Loyihaning qoidasi bo'yicha manba saqlanishi va ular OAI
   orqali yig'ilganlardan ajratilishi kerak.

## Iqtibos soni foyda bermaydi

Namunadagi 15 ta ishning **hammasida iqtibos soni nol**. Ya'ni OpenAlex'ni
«ta'sir ko'rsatkichi» uchun olish mantiqsiz — bu jurnallar indekslangan
adabiyotda iqtibos qilinmaydi.

## Tavsiya

Bitta o'rta hajmdagi jurnaldan boshlansin (masalan «Kimyo va kimyo
texnologiyasi», 447 ish): import qilib, natijani ko'zdan kechirib, keyin
kengaytirilsin. Katta xalqaro jurnallar (15 000+) qo'lda tasdiqlanmaguncha
tegilmasin.

API bepul, kalit talab qilmaydi; so'rovlarda `mailto` ko'rsatiladi.
Kutubxona kerak emas — `httpx` yetarli.


---

## Birinchi import — 2026-08-31

«Kimyo va kimyo texnologiyasi» (#15, ISSN 1992-9498) dan boshlandi.

```bash
.venv/Scripts/python.exe backend/manage.py openalex kimyo-va-kimyo-texnologiyasi
.venv/Scripts/python.exe backend/manage.py openalex kimyo-va-kimyo-texnologiyasi --apply
```

Natija: OpenAlex'dagi 447 ishdan **427 tasi** qo'shildi (20 tasi maqola
turida emas — dataset, tahririyat xati va shu kabilar). Jurnal 0 dan 427
maqolaga chiqdi, 34 ta son. Jami maqola: 104 519 -> 104 946.

To'ldirilganlik (40 ta yozuv namunasida):

| Maydon | % |
| --- | --- |
| sarlavha, annotatsiya, sana, DOI, til, havola | 100 |
| mualliflar | 92 |
| jild, son | 88 |
| betlar | 18 |

### Provenance

Yozuvlar `harvest_sources` da alohida manba sifatida belgilanadi:
`metadata_prefix='openalex'`, `repository_name='OpenAlex'`. Har maqolaning
`source_records` yozuvida `openalex:W…` identifikatori saqlanadi.

`ingest_all_sources` endi faqat `metadata_prefix='oai_dc'` manbalarini
oladi. Bu himoya kerak edi: aks holda `harvest-all` OpenAlex URL'ini OAI
deb yig'ishga urinib, manbani `failed` deb belgilardi.

### Mavjud ma'lumot ustiga yozilmaydi

Import DOI yoki OpenAlex ID bo'yicha topilgan maqolani o'tkazib yuboradi.
Jurnalning o'z OAI endpointi ishlayotgan bo'lsa, o'sha ustun bo'lib
qolaveradi — OpenAlex uchinchi tomon indeksi.

### Yo'l-yo'lakay

Jurnal sanoqlari 300 soniya keshlanadi. Import qilgan odam natijani
kutib turmasligi uchun `seo.invalidate("journal_counts")` qo'shildi.

FTS indeksi triggerlar orqali o'zi yangilandi — yangi maqolalar darhol
qidiruvda topiladi.


## Keyingi to'rtta jurnal — 2026-09-01

| Jurnal | OpenAlex'da | Qo'shildi |
| --- | --- | --- |
| Кимёвий технология. Назорат ва бошқарув | 245 | 238 |
| Тошкент давлат техника университети хабарлари | 134 | 133 |
| Adabiy meros | 62 | 62 |
| Samarqand DU ilmiy tadqiqotlar axborotnomasi | 1 403 | 1 381 |

Jami maqola: 104 946 -> **106 760**. Maqolasiz jurnallar: 346 -> **341**.

### Tuzatilgan xato: ikkala ISSN sinalishi kerak

`import_journal` faqat `journal.issn or journal.eissn` ni, ya'ni
**bittasini** sinardi. «Adabiy meros» shu sababli «OpenAlex'da topilmadi»
deb qaytdi: uning bosma ISSN'i (2181-1320) OpenAlex'da yo'q, e-ISSN'i
(3093-916X) esa bor.

Endi ikkalasi ham sinaladi. Bu boshqa jurnallarga ham tegishli bo'lishi
mumkin — bosma ISSN OpenAlex'da ko'pincha ro'yxatga olinmagan.

Diqqat: «Adabiy meros» ning OpenAlex yozuvida ISSN'lar
`['2181-2500', '3093-916X']` — bizdagi bosma ISSN 2181-1320 ularning
hech biriga mos kelmaydi. Qaysi biri to'g'ri ekani tekshirilmagan.

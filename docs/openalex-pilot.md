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

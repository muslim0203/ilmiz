# PDF'dan maqola yozuvlarini olish — 2026-08-31 piloti

## Xulosa: GROBID mos kelmadi

[GROBID](https://github.com/kermitt2/grobid) ilmiy PDF'dan metama'lumot
ajratadi va men uni tavsiya qilgan edim. **Bu tavsiya noto'g'ri edi** —
PDF'lar qanday ekanini tekshirmasdan aytilgan.

Tekshiruv natijasi:

| Jurnal | Fayl | Betlar |
| --- | --- | --- |
| Guliston DU axborotnomasi | `1-axb-2013.pdf` | 88 |
| TTA vestnik | `ttaa-2022-1.pdf` | 210 |
| SamDAQI ilmiy jurnali | `2026_1.pdf` | 507 |

Bular **butun sonlar**, alohida maqola emas. GROBID esa bitta hujjatdan
bitta sarlavha ajratadi — ya'ni har sondan bitta «maqola» chiqardi.

Qo'shimcha to'siq: mashinada Docker yo'q, Java 17 (GROBID 21 talab qiladi).

## Mos keladigani: mundarijani o'qish

Har uch sonning mundarijasi bor va u tuzilgan. Prototip (`scratchpad`,
bazaga yozmaydi) shuni ko'rsatdi:

| Jurnal | Mundarija | Ajratilgan yozuv | Bet raqamlari |
| --- | --- | --- | --- |
| Guliston | 84-bet | 15 | to'g'ri (3, 11, 16, 25...) |
| SamDAQI | 502-bet | 39 | to'g'ri (3, 8, 11, 17...) |
| TTA | 4-bet | — | qatorda emas, ustunda |

Ya'ni **yozuv chegaralari va bet raqamlari ishonchli ajraladi**. Bu
ML talab qilmaydi, Docker ham kerak emas — oddiy matn tahlili.

## Nima hal qilinmagan

1. **Muallif/sarlavha ajratish formatga bog'liq.** Guliston
   `Mualliflar, SARLAVHA` ishlatadi, SamDAQI esa `Mualliflar. Sarlavha`.
   Har jurnal uchun kichik qoida kerak — ko'p emas, lekin bitta umumiy
   parser yetmaydi.
2. **TTA'ning ikki tilli mundarijasi** ustunli joylashgan; `pypdf` bet
   raqamlarini qator oxiriga qo'ymaydi. Layoutni hisobga oladigan
   ajratish kerak.
3. **Bu yozuvlarda annotatsiya va DOI bo'lmaydi.** Faqat sarlavha,
   mualliflar, bet oralig'i va bo'lim. `pdf_url` butun songa ishora
   qiladi, maqolaga emas.

## Ko'lami

Maqolasiz 40 jurnal tekshirilganda 7 tasi **bosh sahifasidayoq** PDF
tarqatardi (81, 75, 60 tadan). Arxiv sahifalari hisobga olinmagan.
345 jurnalga qiyoslaganda taxminan 60 tasi shu yo'l bilan ochilishi
mumkin.

## Tavsiya

GROBID olinmasin. Uning o'rniga mundarija tahlilini kichik xizmat
sifatida qurish, ikkita ishlaydigan formatdan boshlab. Har bir yozuv
mundarijada nima yozilgan bo'lsa — faqat shu; taxmin qo'shilmasin.

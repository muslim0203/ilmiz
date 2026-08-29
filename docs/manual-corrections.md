# Qo'lda kiritilgan tuzatishlar

Bu yerda **yuqori manba (OAK reestri, tadqiq.uz) xato bo'lgani uchun** qo'lda
tuzatilgan yozuvlar qayd etiladi. Ularni "manbaga moslash" uchun orqaga
qaytarmang — manbaning o'zi noto'g'ri.

`oak_registry.py` `if not journal.website` shartini tekshiradi, shuning uchun
reestr qayta import qilinganda bu tuzatishlar saqlanib qoladi.

---

## Infolib (#444) — 2026-08-28

**Muammo.** OAK rasmiy reestrida Infolib uchun havola sifatida
`https://lingvospektr.uz/index.php/lngsp/index` ko'rsatilgan. Bu Lingvospektr
jurnalining manzili. tadqiq.uz ham shu xatoni takrorlagan
(`tadqiq.uz/mahalliy-oak-jurnallar/infolib`). Natijada Infolib yozuvi
butunlay Lingvospektr ma'lumotlari bilan to'lgan edi: sayt, ISSN, uchala OAI
manbasi, profil, aloqa ma'lumotlari va 1778 maqola — barchasi
Lingvospektr'niki, `#445` dagi maqolalar bilan 100% ustma-ust
(bir xil `oai:ojs2.lingvospektr.uz:article/N` identifikatorlari).

**Tekshiruv.**

| Dalil | Natija |
| --- | --- |
| `portal.issn.org` ISSN 3060-4958 | Lingvospektr, sayt `.../lngsp/about` |
| `portal.issn.org` ISSN 2181-8207 | Infolib (bosma), bog'langan e-ISSN 3093-902X |
| `.../lngsp/oai?verb=Identify` | `repositoryName` = The Lingua Spectrum |
| `.../lngsap/index` | 404 |
| `einfolib.uz` | "INFOLIB - Ахборот-кутубхона журнали", Milliy kutubxona |

**Tuzatildi.**

- `#444 Infolib` — 1778 maqola, 3 OAI manba, profil/aloqa/siyosat/havolalar
  o'chirildi. Sayt `https://einfolib.uz/`, ISSN `2181-8207`,
  e-ISSN `3093-902X`. einfolib.uz WordPress'da, OAI endpointi yo'q, shuning
  uchun jurnal yig'ilmaydi va 0 maqola bilan qoladi.
- `#445 Lingvospektr` — sayt o'lik `lngsap` yo'lidan `lngsp` ga o'tkazildi,
  yagona OAI manbasi sayt darajasidagi `/index.php/index/oai` dan jurnalga xos
  `/index.php/lngsp/oai` ga qaratildi. OAI identifikatorlari endpointga bog'liq
  emas, shuning uchun mavjud yozuvlar buzilmadi.

`oak_registry_entries` dagi #2421 yozuvi **ataylab tegilmadi** — u OAK nima
e'lon qilganini qayd etuvchi tarixiy iz.

---

## Tekshirilmagan shubhali juftlar

Infolib bilan bir xil naqsh: juftning biri jurnalga xos OAI yo'lini, ikkinchisi
sayt darajasidagi `/index.php/index/oai` ni ishlatgan va ikkalasi bir xil
maqolalarni olgan. Har biri alohida tekshiruvni talab qiladi — ba'zilari
haqiqatan ikki xil jurnal (Infolib kabi), ba'zilari esa bitta jurnalning ikki
tildagi nomi bo'lishi mumkin (u holda birlashtirish kerak).

| Juft | Umumiy maqola | Izoh |
| --- | --- | --- |
| #458 Спорт илм-фанининг... ↔ #156 Фан спортга | 287 / 287 | bir xil ISSN 3030-3087, nashriyotlar har xil |
| #263 Наука и инновационные... ↔ #453 Илм-фан ва технологиялар | 98 / 98 | bir xil ISSN 0009-0003, nashriyotlar har xil |
| #457 Фан ва жамият ↔ #39 Ilim ha'm ja'miyet | 50 / 50 | bir nashriyot — ehtimol bitta jurnalning ikki nomi |
| #27 Қорақалпоғистон... ↔ #89 Қарақалпақ ДУ хабаршысы | 28 / 28 | bir nashriyot, bir xil ISSN 2010-9075 |
| #5 Agro Inform ↔ #213 AGRO BIZNES INFORM | 6 / 6 | nashriyotlar har xil |

Aniqlash usuli: bir xil hostdan yig'ilgan va sarlavhalari to'liq ustma-ust
tushgan jurnal juftlarini qidirish. **Faqat OAI identifikatorini taqqoslash
yaramaydi** — sozlanmagan OJS o'rnatmalari hammasi `oai:ojs.pkp.sfu.ca:article/N`
qaytaradi, shuning uchun yuzlab bog'liq bo'lmagan jurnal tasodifan bir xil
identifikatorga ega.

---

## Admin panel orqali tahrirlash

Jurnal maydonlarini admin panelning «Jurnal ma'lumotlarini tahrirlash»
blokidan tuzatish mumkin. Har bir o'zgarish `journal_profile_fields` da
`manual:<maydon>` nomi va `verification_status="manual"` bilan qayd etiladi.

Importlar bu belgini hurmat qiladi:

- OAK reestri va tadqiq.uz importlari faqat **bo'sh** maydonlarni to'ldiradi,
  shuning uchun qo'lda kiritilgan qiymat qayta yozilmaydi.
- `collect_profile` (profil qayta yig'ish) aloqa yozuvlari va provenance
  qatorlarini **butunlay** o'chirib qayta yozardi — ya'ni qo'lda kiritilgan
  tuzatish ham, "tegmang" belgisi ham yo'qolardi. Endi manbasi
  `admin:manual` bo'lgan aloqa yozuvlari va `manual` belgili provenance
  qatorlari saqlanadi.
- `fields` (ilmiy sohalar) istisno edi — OAK importi uni har safar qo'shib
  borardi, ya'ni olib tashlangan soha qaytib kelaverardi. Endi qo'lda
  tahrirlangan bo'lsa, importi unga tegmaydi.
- `oak_status` doim OAK reestridan olinadi — jurnalning ro'yxatdaligini
  belgilash OAK ning vakolati.

ISSN takrorlansa saqlash bloklanmaydi, lekin ogohlantirish chiqadi: bazada
allaqachon 16 ta takror bor va ularni tuzatish jarayonida vaqtinchalik
ikkilanish bo'lishi tabiiy.

### Aloqa ma'lumotlari

Manzil, email va telefonlarni ham shu formadan tahrirlash mumkin. Ro'yxat
butunlay almashtiriladi, lekin qiymati o'zgarmagan yozuv o'z manbasini
saqlab qoladi — qayerdan olingani ma'lum bo'lib turadi.

Tekshiruvlar: email formati; telefon uchun `is_valid_phone` (sana, ISSN va
yillar ro'yxatini rad etadi); manzil uchun 400 belgi cheklovi.

### Manzillarni tozalash — 2026-08-29

«Manzil» maydoniga aloqa sahifasidagi yonma-yon matn ham tushib qolgan edi:
tahririyat a'zolari ro'yxati, `document.write(unescape(...))` bilan
yashirilgan email kodi, va butunlay boshqa sahifa (mualliflar uchun qoida,
maxfiylik siyosati). 68 tadan 11 tasi qisqartirildi, 18 tasi o'chirildi.

`profile_collector.clean_address` uch bosqichda ishlaydi: axlat boshlangan
joydan kesadi, matnda «Manzil:» belgisi bo'lsa undan keyingi qismni oladi
(oxirgi uchrashini — «telegram manzili:» ham mos keladi), so'ng qolgani
manzil bo'la oladimi deb baholaydi.

Qoida **ataylab ehtiyotkor**: shubhali yozuv saqlanadi. «Manzilga o'xshamasa
o'chir» degan qat'iy qoida haqiqiy manzillarni ham yeb qo'yardi —
`114, Shota Rustaveli, Tashkent, Uzbekistan` da ko'cha so'zi yo'q,
`г.Ташкент, М.Улугбекский район` da raqam yo'q, pochta indeksining o'zi
(`100197`) esa to'liq manzil emas, lekin xato ham emas.

### Regex naqshlaridagi backspace

Patch skriptlari `` ni xom bo'lmagan Python satrida yozganda u so'z
chegarasi emas, **backspace belgisiga (0x08)** aylanib faylga yozilgan.
Natijada `tel\.?:` naqshi hech qachon mos kelmagan. 2026-08-29 da
`profile_collector.py` dan 18 ta, `ingest.py` dan 1 ta (izohda) topilib
tuzatildi — jumladan `BOILERPLATE_RE` dagi `var` ham ishlamay turgan edi.
Bunday naqsh yozganda natijani albatta sinab ko'rish kerak.

Telefon raqamlaridagi juftlashmagan qavslar avtomatik tuzatiladi. Scraper'ning
`\+?\d[\d ()\-]{7,}\d` naqshi raqamdan boshlangani uchun `+998(71) 262-31-69`
dan `+99871) 262-31-69` qolgan. Ochuvchi qavs qayerda turganini taxmin
qilmaymiz (u `+998` dan keyin edi), shuning uchun ortiqcha qavs olib
tashlanadi — raqam buzilmaydi.

**2026-08-29 da bazadagi hammasi tuzatildi**: 121 ta raqam normallashtirildi,
1 tasi o'chirildi (`2026-2027) 29` — yillar oralig'i, telefon emas), 2 tasi
normallashgach mavjud yozuv bilan bir xil bo'lib qolgani uchun olib
tashlandi. `source_url` tegilmadi: raqamlar o'sha sahifadan kelgan, faqat
qavs tuzatilgan — bu odamning qarori emas, shuning uchun `admin:manual`
deb belgilash provenance'ni buzardi.

`balance_parens` endi `profile_collector` da, ya'ni yangi yig'ilgan raqamlar
darhol toza bo'ladi va muammo qaytmaydi.

---

## Profil to'liqligi bali

Ball 10 ta belgining nechtasi to'ldirilganini o'lchaydi, har biri 10%:
tavsif, manzil, aloqa, tahririyat a'zolari, siyosatlar, so'nggi son,
indekslanish, ISSN, sohalar, tillar.

**Bu jurnalning sifati emas** — u ma'lumot to'liqligini o'lchaydi, xolos.
Ball to'ldirilganini sanaydi, to'g'riligini emas: jQuery kodi «tavsif»
sifatida turgan jurnal bo'sh qoldirgandan ko'ra baland ball olardi.
Tozalash natijasida 28 ta jurnalning bali pasaydi — ma'lumot yaxshilandi,
raqam esa haqiqatga yaqinlashdi.

Hisob `services/completeness.py` da, bazadagi holatdan olinadi. Ilgari u
`collect_profile` ichida, yig'ish paytidagi lokal o'zgaruvchilar ustidan
bajarilardi — shuning uchun qo'lda kiritilgan ma'lumot ballga umuman
ta'sir qilmasdi. Endi `apply_edits` va `replace_contacts` ham uni
chaqiradi.

Ikkita maydon nomi chalkash, ular boshqa-boshqa joyda:

| Ball sanaydigan | Qayerda | Panelda |
| --- | --- | --- |
| `summary` | `journal_profiles.summary` | «Tavsif (profil)» |
| — | `journals.description` | «Tavsif (katalog)» |
| `address` | `journal_profiles.address` | «Manzil» |
| `contacts` | `journal_contacts` | Aloqa bloki |

Ya'ni aloqa blokidagi manzil yozuvi `address` belgisini yopmaydi.

2026-08-29 da 443 profildan 316 tasining saqlangan bali hozirgi
ma'lumotga mos kelmasdi (288 tasi past, 28 tasi baland ko'rsatilgan edi) —
hammasi qayta hisoblandi.

---

## Ma'lum muammolar

- `source_records` da ~8300 yetim yozuv bor (maqolasi o'chirilgan, yozuvi
  qolgan). Ilgarigi tozalashlardan qolgan, hozircha zarar bermaydi.

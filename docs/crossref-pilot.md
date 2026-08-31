# Crossref / habanero piloti — 2026-08-31

## Xulosa: metama'lumot to'ldirish uchun arzimaydi

[habanero](https://github.com/sckott/habanero) Crossref'dan DOI bo'yicha
bibliografik ma'lumot oladi. Uni «yetishmayotgan betlar va jildlarni
to'ldiradi» deb tavsiya qilgan edim. O'lchov buni tasdiqlamadi.

**1. DOI'larimizning yarmi Crossref'da yo'q.**

| Prefiks | Maqola | Izoh |
| --- | --- | --- |
| 10.5281 | 11 600 | **Zenodo** — DOI'ni DataCite beradi, Crossref emas |
| qolgan 39 prefiks | 33 387 | qisman Crossref |

60 ta tasodifiy DOI'dan **33 tasi (55%)** Crossref'da topildi.

**2. Topilganlari ham deyarli yangi narsa bermaydi.**

33 ta moslikdan:

| Maydon | Bizda yo'q, Crossref'da bor | Ikkalasida bor, farq qiladi |
| --- | --- | --- |
| jild | 2 | 3 |
| son | 0 | 0 |
| betlar | 1 | 0 |
| annotatsiya | 0 | — |

Ya'ni 60 maqoladan atigi 3 ta maydon to'ldirilardi, ziddiyat esa 3 ta.

Sabab oddiy: biz metama'lumotni jurnalning **o'z OAI endpointidan**
olamiz, DOI'ni ham o'sha jurnal ro'yxatdan o'tkazgan. Crossref bir xil
manbaning nusxasini qaytaradi.

## Lekin: tekshiruv belgisi sifatida qimmatli

Crossref har yozuv bilan **jurnal ISSN'ini** beradi. Bu bizning
biriktirishimizni mustaqil tekshiradi:

| Natija | Soni |
| --- | --- |
| ISSN mos keldi | 24 |
| **ISSN mos kelmadi** | **1** |
| Crossref'da ISSN yo'q | 1 |

Topilgan nomuvofiqlik haqiqiy edi: maqola «Камолиддин Беҳзод номидаги
МРДИ Ахборотномаси» (ISSN 2181-1822) ga biriktirilgan, Crossref esa uni
ISSN 2181-2918 da deydi — bu bizning bazamizda **#347 «Art and social
sciences»**.

Bu aynan shu sessiyada qo'lda tuzatilgan xato turi (Infolib, TTIT,
Фан спортга). ~4% nomuvofiqlik darajasida, Crossref'da topiladigan
~22 000 maqola ichida taxminan 900 ta tekshirishga arzigulik holat
chiqadi.

Qo'shimcha: **muallif ORCID** mosliklarning 33% ida bor. Bu «Maqolalarimni
qidirish» funksiyasini kuchaytiradi — ism bo'yicha taxmin qilish o'rniga
ORCID bo'yicha aniq bog'lash mumkin bo'ladi.

## habanero kutubxonasining o'zi kerak emas

Butun bu pilot `httpx` bilan bajarildi — u allaqachon bog'liqlikda bor.
Crossref REST API bitta `GET api.crossref.org/works/{doi}`. Bitta
so'rov uchun kutubxona qo'shish ortiqcha.

So'rovlarda `mailto` ko'rsatildi (Crossref'ning «polite pool» qoidasi).

## Tavsiya

habanero olinmasin, metama'lumot to'ldirish ham qilinmasin. Uning
o'rniga kichik **Crossref audit** qurilsin: DOI bor maqolalarning ISSN'ini
tekshirib, biriktirilgan jurnalga mos kelmaganini admin panelda
belgilasin. Bu qo'lda topayotgan muammoni avtomatlashtiradi.

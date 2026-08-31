# GitHub ulanishi

Repozitoriy: https://github.com/muslim0203/ilmiz

2026-08-31: foydalanuvchi repo Public (ochiq) qolishini tasdiqladi.
Mahalliy build hamda backend, harvester va deploy/guard testlari o'tdi.
Git tarixi va indeksidagi fayllar guard tekshiruvidan o'tdi.

## Tayyorlangan jarayon

`main` yoki `master` ga push, pull request va qo'lda Run workflow orqali:

1. Git'dagi fayllarda baza, maxfiy fayllar va ayrim credential naqshlari tekshiriladi.
2. Python 3.14 va Node.js 22 da bog'liqliklar o'rnatiladi.
3. Backend, harvester va deploy testlari ishlaydi.
4. Frontend build qilinadi; shell skriptlari sintaksisi tekshiriladi.
5. Faqat koddan iborat runtime arxivi va SHA256 7 kunga artifact sifatida saqlanadi.

CI hech qachon haqiqiy bazaga ulanmaydi va serverga deploy qilmaydi.
Push huquqi bo'lmagan pull request'lar ham faqat tekshiruvdan o'tadi.
Actions to'liq commit SHA bilan belgilangan, token faqat `contents: read`.

## Maxfiy ma'lumotlar

- Maqolalar va foydalanuvchilar bazasi OVH'da qoladi.
- `.env`, SSH private kalitlari, bazalar/zaxiralar GitHub'ga yuklanmaydi.
- Lokal nusxalar `.deploy-artifacts/` da qoladi; ushbu papka Git'dan chiqarilgan.
- Mavjud server IP manzili, shaxsiy kalit nomi, ichki yo'llar yozilgan operator
  hujjatlari va bir martalik server skriptlari mahalliy saqlanadi; ommaviy
  repo hamda CI runtime artifact'iga kiritilmaydi.
- Guard to'liq secret audit emas: yangi credential turlari va oddiy parollar
  avtomatik aniqlanmasligi mumkin. GitHub secret scanning va inson tekshiruvi
  ham zarur. Guard xatolari faqat fayl nomi va sababni chiqaradi.
- Birinchi push'dan oldin: `python deploy/check_repository.py --history`.
  Oddiy guard Git indeksini tekshiradi; yangi fayllar stage qilingandan keyin
  qayta ishlatiladi.

## Avtomatik OVH deploy uchun keyingi bosqich

Hali yoqilmagan. GitHub'dagi CI va OVH deploy ikki alohida bosqich:
CI muvaffaqiyati o'z-o'zidan server yangilandi degani emas.

Deployni yoqish uchun alohida cheklangan SSH deploy kaliti va serverdagi
ishonchli deploy yordamchisi kerak. Shaxsiy SSH private kaliti CI'ga
ko'chirilmaydi. Alohida kalit GitHub Environment secret sifatida saqlanadi;
server host kaliti oldindan tekshiriladi (`StrictHostKeyChecking=yes`).

Deploy faqat asosiy branchning muvaffaqiyatli tekshirilgan natijasini olishi,
bir vaqtda bitta yangilanish bajarishi, eski kod va mos venv'ni saqlashi,
WAL-safe baza backup olishi va health check muvaffaqiyatsiz bo'lsa oldingi
kodga qaytishi kerak. Baza migratsiyasi bo'lsa, kod rollback'i bazani orqaga
qaytarmaydi: alohida ko'rib chiqish zarur. Serverdagi mavjud bir martalik
`install_staging.sh`/`update_seo_staging.sh` ni CI'dan qayta ishga tushirmang.

Hozirgi `noindex`, yopiq port va SSH tunnel rejimi o'zgartirilmaydi.

## Rasmiy tavsiyalar

- [GitHub Actions xavfsizligi](https://docs.github.com/en/actions/reference/security/secure-use)
- [Deploy environment va secret'lar](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)

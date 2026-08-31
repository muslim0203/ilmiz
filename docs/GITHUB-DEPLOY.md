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

`verify` vazifasi hech qachon haqiqiy bazaga ulanmaydi. Alohida `deploy`
vazifasi faqat pastdagi sozlamalar yoqilgandan keyin serverni yangilaydi.
Pull request'lar faqat tekshiruvdan o'tadi, deploy secret'lariga kira olmaydi.
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

## Avtomatik OVH deploy

Workflow tayyor; yangi doimiy server kirish vakolatini o'rnatish alohida
tasdiq talab qiladi. `OVH_DEPLOY_ENABLED=true` sozlanmaguncha deploy o'tkazib
yuboriladi. GitHub'dagi CI muvaffaqiyati o'z-o'zidan server yangilandi degani emas.

Yoqilganda faqat `main` branchga push yoki shu branchda qo'lda Run workflow
deploy qiladi. `verify` o'tmasa deploy boshlanmaydi. Tayyor artifact shu
workflow run ichidan olinadi va SHA256 tekshiriladi. Yangilanishlar birma-bir
bajariladi, keyingi push boshlangan deployni bekor qilmaydi.

`ovh-staging` Environment faqat `main` branchga ruxsat berishi va quyidagi
to'rtta secret'ni saqlashi kerak (qiymatlarini kod yoki logga kiritmang):

- `OVH_DEPLOY_HOST`
- `OVH_DEPLOY_USER`
- `OVH_DEPLOY_KEY`
- `OVH_KNOWN_HOSTS`

Tezkor to'xtatish: repo Variables ichida `OVH_DEPLOY_ENABLED` ni `false`
qilish yangi deploylarni to'xtatadi. Allaqachon boshlangan deploy yakunlanishi
mumkin; uni majburan to'xtatish o'rniga server operatori holatni tekshiradi.

Deployni yoqish uchun alohida cheklangan SSH deploy kaliti va serverdagi
ishonchli deploy yordamchisi kerak. Shaxsiy SSH private kaliti CI'ga
ko'chirilmaydi. Alohida kalit GitHub Environment secret sifatida saqlanadi;
server host kaliti oldindan tekshiriladi (`StrictHostKeyChecking=yes`).

Tayyorlangan server yordamchisi arxivdan faqat ruxsat etilgan oddiy fayllarni
qabul qiladi; linklar, yashirin fayllar, yo'lni buzuvchi nomlar va haddan katta
arxivlar rad etiladi. Testlar tarmoqsiz, haqiqiy bazaga kira olmaydigan alohida
akkauntda ishlaydi. Keyin WAL-safe backup va yangi kodning health tekshiruvi
bajariladi; xatoda eski kod saqlangan nusxadan qaytariladi.

Baza sxemasi yoki tekshirilgan Python dependencies o'zgarsa, yordamchi
deployni to'xtatadi — operator migratsiya/venv'ni alohida tasdiqlashi kerak.
Bu boshlang'ich versiyada venv o'zgarmaydi. Baza migratsiyasidan keyin kod
rollback'i bazani orqaga qaytarmaydi. Backup va eski kod avtomatik
o'chirilmaydi; bo'sh disk yetarli bo'lmasa deploy to'xtaydi.
Serverdagi mavjud bir martalik
`install_staging.sh`/`update_seo_staging.sh` ni CI'dan qayta ishga tushirmang.

Hozirgi `noindex`, yopiq port va SSH tunnel rejimi o'zgartirilmaydi.

## Rasmiy tavsiyalar

- [GitHub Actions xavfsizligi](https://docs.github.com/en/actions/reference/security/secure-use)
- [Deploy environment va secret'lar](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)

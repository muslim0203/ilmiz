import { useEffect } from "react";

import { AppLink } from "@/components/app-link";
import { setHead } from "@/lib/head";
import { cn } from "@/lib/utils";

const SHELL = "mx-auto w-full max-w-[1200px] px-4 sm:px-6";

/** `/maxfiylik` — maxfiylik siyosati.
 *
 * Matn kodda haqiqatan saqlanadigan maydonlardan yozilgan (`models.py`:
 * `User`, `UserSession`, `UserArticle`, `OAuthState`). Yangi maydon
 * qo'shilsa, bu sahifa ham yangilanishi kerak.
 *
 * Google OAuth ilovasini "Production" holatiga o'tkazish uchun ham shu
 * sahifaning ochiq manzili talab qilinadi.
 */
export default function PrivacyPage() {
  useEffect(() => {
    setHead({
      title: "Maxfiylik siyosati — IlmIz",
      description:
        "IlmIz qanday ma’lumot saqlaydi: ORCID va Google orqali kirish, sessiya, o‘zlashtirilgan maqolalar. Reklama va kuzatuv skriptlari yo‘q.",
      path: "/maxfiylik",
    });
  }, []);

  return (
    <div className={cn(SHELL, "py-10 sm:py-14")}>
      <nav aria-label="Yo‘nalish" className="mb-5 flex items-center gap-1.5 text-xs text-muted-foreground">
        <AppLink to="/" className="hover:text-foreground">
          Bosh sahifa
        </AppLink>
        <span aria-hidden="true">/</span>
        <span aria-current="page">Maxfiylik siyosati</span>
      </nav>

      <div className="max-w-2xl">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          Maxfiylik siyosati
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
          IlmIz — OAK ro‘yxatidagi ilmiy jurnallar va maqolalarning ochiq indeksi. Saytdan
          foydalanish uchun ro‘yxatdan o‘tish shart emas. Quyida qaysi ma’lumot, nima uchun va
          qancha muddat saqlanishi yozilgan.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Kirmasdan foydalanganda</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Qidiruv, jurnal va maqola sahifalari hisobsiz ochiladi. Bunda hech qanday shaxsiy
          ma’lumot saqlanmaydi. Veb-server odatiy texnik jurnal yuritadi (so‘rov manzili, vaqti,
          brauzer turi va IP manzil) — u faqat nosozliklarni aniqlash va suiiste’molning oldini
          olish uchun kerak.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">ORCID yoki Google orqali kirganda</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Parol so‘ralmaydi va saqlanmaydi — kirish butunlay provayder tomonida bo‘lib o‘tadi.
          Provayder bizga qaytargan quyidagi maydonlar saqlanadi:
        </p>
        <ul className="mt-2 space-y-2 text-sm leading-relaxed text-muted-foreground">
          <li>provayder nomi (ORCID yoki Google) va undagi barqaror identifikatoringiz;</li>
          <li>ORCID iD — agar ORCID orqali kirgan bo‘lsangiz;</li>
          <li>elektron pochta manzili va ko‘rsatiladigan ism;</li>
          <li>ish joyi (affiliatsiya) — agar provayder uni bergan bo‘lsa;</li>
          <li>hisob yaratilgan va oxirgi marta kirilgan vaqt.</li>
        </ul>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Bu ma’lumot faqat sizni tanish, profilingizni ko‘rsatish va o‘zingiz tasdiqlagan
          maqolalarni hisobingizga bog‘lash uchun ishlatiladi.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Sessiya va cookie</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Kirganingizdan so‘ng brauzeringizga <code className="font-mono text-xs">ilmiz_session</code>{" "}
          nomli bitta cookie qo‘yiladi. U <span className="text-foreground">HttpOnly</span> (JavaScript
          o‘qiy olmaydi), <span className="text-foreground">SameSite=Lax</span> va HTTPS’da{" "}
          <span className="text-foreground">Secure</span> bayrog‘i bilan yuboriladi. Amal qilish
          muddati — 30 kun.
        </p>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Serverda sessiya tokenining o‘zi emas, uning SHA-256 hash’i saqlanadi: baza o‘qib
          olinsa ham tayyor tokenlar qo‘lga tushmaydi. Sessiya yozuvida yaratilgan va tugash
          vaqti hamda brauzeringiz nomi (user-agent) turadi — bu faol seanslarni ajratish uchun.
          Kirish jarayonida ishlatiladigan vaqtinchalik <code className="font-mono text-xs">state</code>{" "}
          qiymati qaytish bilan darhol o‘chiriladi.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">O‘zlashtirilgan maqolalar</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Mualliflik ism-familiya bo‘yicha taxmin qilinadi, shuning uchun tizim maqolalarni
          o‘zi bog‘lamaydi — faqat nomzodlarni ko‘rsatadi. Qaysi biri o‘zingizniki ekanini
          siz tasdiqlaysiz. Saqlanadigan narsa: hisobingiz, maqola va tasdiqlangan vaqt.
          Istalgan paytda ro‘yxatdan olib tashlashingiz mumkin.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Nima qilmaymiz</h2>
        <ul className="mt-2 space-y-2 text-sm leading-relaxed text-muted-foreground">
          <li>Reklama ko‘rsatmaymiz.</li>
          <li>
            Kuzatuv va analitika skriptlari ishlatmaymiz — saytda uchinchi tomon skriptlari yo‘q.
          </li>
          <li>Ma’lumotlaringizni sotmaymiz va reklama maqsadida uchinchi shaxslarga bermaymiz.</li>
          <li>Parolingizni ko‘rmaymiz va saqlamaymiz.</li>
        </ul>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Indeksdagi ochiq ma’lumot</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Jurnal va maqola metama’lumotlari ochiq manbalardan yig‘iladi: OAK rasmiy reestri,
          jurnallarning o‘z OAI-PMH endpointlari va ochiq indekslar. Bu yerga jurnal saytlarida
          allaqachon e’lon qilingan tahririyat a’zolarining ism va aloqa ma’lumotlari ham kirishi
          mumkin. Agar o‘zingiz haqingizdagi yozuv noto‘g‘ri bo‘lsa yoki uni olib tashlashni
          istasangiz, yozing — tekshirib tuzatamiz yoki o‘chiramiz.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Sizning huquqlaringiz</h2>
        <ul className="mt-2 space-y-2 text-sm leading-relaxed text-muted-foreground">
          <li>Chiqish tugmasi joriy sessiyani serverda bekor qiladi.</li>
          <li>Tasdiqlagan maqolalaringizni istalgan vaqt profilingizdan olib tashlashingiz mumkin.</li>
          <li>
            Hisobingizni butunlay o‘chirishni so‘rasangiz, unga bog‘langan barcha yozuvlar bilan
            birga o‘chiramiz. Buning uchun quyidagi manzilga yozing.
          </li>
        </ul>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Aloqa</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Maxfiylik bo‘yicha savollar, tuzatish va o‘chirish so‘rovlari:{" "}
          <a href="mailto:info@ilmiz.uz" className="text-primary hover:underline">
            info@ilmiz.uz
          </a>
          .
        </p>

        <p className="mt-8 text-xs text-muted-foreground">
          Oxirgi yangilanish: 2026-yil 2-sentyabr. Siyosat o‘zgarsa, shu sahifada yangilanadi.
        </p>
      </div>
    </div>
  );
}

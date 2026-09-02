import { useEffect } from "react";

import { AppLink } from "@/components/app-link";
import { setHead } from "@/lib/head";
import { cn } from "@/lib/utils";

const SHELL = "mx-auto w-full max-w-[1200px] px-4 sm:px-6";

/** `/shartlar` — foydalanish shartlari.
 *
 * Maqsad — nima va’da qilinayotganini aniq chegaralash: IlmIz to'liq
 * matnlarni saqlamaydi, metama'lumot uchinchi tomon manbalaridan keladi
 * va rasmiy holat uchun OAK reestri birlamchi hisoblanadi.
 */
export default function TermsPage() {
  useEffect(() => {
    setHead({
      title: "Foydalanish shartlari — IlmIz",
      description:
        "IlmIz’dan foydalanish shartlari: bepul kirish, metama’lumot manbalari, hisob va maqolalarni o‘zlashtirish qoidalari.",
      path: "/shartlar",
    });
  }, []);

  return (
    <div className={cn(SHELL, "py-10 sm:py-14")}>
      <nav aria-label="Yo‘nalish" className="mb-5 flex items-center gap-1.5 text-xs text-muted-foreground">
        <AppLink to="/" className="hover:text-foreground">
          Bosh sahifa
        </AppLink>
        <span aria-hidden="true">/</span>
        <span aria-current="page">Foydalanish shartlari</span>
      </nav>

      <div className="max-w-2xl">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          Foydalanish shartlari
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
          Saytdan foydalanish shu shartlarni qabul qilishni bildiradi.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Xizmat nima</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          IlmIz — O‘zbekiston OAK ro‘yxatidagi ilmiy jurnallar va ularda chop etilgan
          maqolalarning qidiruv indeksi. Qidiruv va metama’lumotlar barcha uchun bepul,
          ro‘yxatdan o‘tish talab qilinmaydi.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Metama’lumot va mualliflik huquqi</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          IlmIz maqolalarning to‘liq matnini saqlamaydi va tarqatmaydi — faqat metama’lumot
          (sarlavha, mualliflar, annotatsiya, kalit so‘zlar, DOI) va nashriyot sahifasiga havola
          ko‘rsatiladi. Maqolalarga bo‘lgan huquqlar mualliflar va nashriyotlarda qoladi;
          to‘liq matndan foydalanish tartibini o‘sha jurnalning o‘zi belgilaydi.
        </p>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Ma’lumot OAK reestri, jurnallarning OAI-PMH endpointlari va ochiq indekslardan
          yig‘iladi. Har bir maydonning manbasi saqlanadi. Jurnalning rasmiy OAK holati uchun
          birlamchi manba — OAK reestrining o‘zi; IlmIz uning nusxasi bo‘lgani uchun kechikish
          bo‘lishi mumkin.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Hisob va maqolalarni o‘zlashtirish</h2>
        <ul className="mt-2 space-y-2 text-sm leading-relaxed text-muted-foreground">
          <li>
            Hisob ORCID yoki Google orqali ochiladi. Berilgan ma’lumot haqiqiy bo‘lishi kerak.
          </li>
          <li>
            Profilingizga faqat <span className="text-foreground">o‘zingiz muallif bo‘lgan</span>{" "}
            maqolalarni qo‘shing. Tizim mualliflikni ism bo‘yicha taxmin qiladi, tasdiq esa
            sizning zimmangizda.
          </li>
          <li>
            Boshqa odamning maqolalarini o‘zlashtirish yoki soxta ma’lumot kiritish aniqlansa,
            yozuvlar olib tashlanadi va hisob to‘xtatilishi mumkin.
          </li>
        </ul>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Xatolarni tuzatish</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Indeksda xato bo‘lishi mumkin: manba saytlarda noto‘g‘ri havola yoki ISSN uchraydi.
          Xato ko‘rsangiz yozing — tekshirib tuzatamiz. Jurnal yoki muallif haqidagi yozuvni
          olib tashlash so‘rovlari ham shu manzilga.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Kafolatlar</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Xizmat “borligicha” taqdim etiladi. Ma’lumotning to‘liqligi va uzluksiz ishlashi
          kafolatlanmaydi. Rasmiy qarorlar (dissertatsiya, attestatsiya va shu kabilar) uchun
          birlamchi manbalarga — OAK reestri va jurnalning o‘z nashriga — tayaning.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Aloqa</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Savol, tuzatish va so‘rovlar:{" "}
          <a href="mailto:info@ilmiz.uz" className="text-primary hover:underline">
            info@ilmiz.uz
          </a>
          . Shaxsiy ma’lumot qanday saqlanishi{" "}
          <AppLink to="/maxfiylik" className="text-primary hover:underline">
            maxfiylik siyosatida
          </AppLink>{" "}
          yozilgan.
        </p>

        <p className="mt-8 text-xs text-muted-foreground">
          Oxirgi yangilanish: 2026-yil 2-sentyabr.
        </p>
      </div>
    </div>
  );
}

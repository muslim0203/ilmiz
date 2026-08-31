import { useEffect } from "react";
import { CalendarDays, Globe2, ShieldCheck } from "lucide-react";

import type { PlatformStats } from "@/api";
import { AppLink } from "@/components/app-link";
import { Card, CardContent } from "@/components/ui/card";
import { number } from "@/lib/format";
import { setHead } from "@/lib/head";
import { cn } from "@/lib/utils";

const SHELL = "mx-auto w-full max-w-[1200px] px-4 sm:px-6";

/** `/loyiha` — loyihaning o'z sahifasi.
 *
 * Ilgari bu matn bosh sahifadagi `#about` langari edi: qidiruvda alohida
 * chiqmasdi va "IlmIz nima" so'roviga javob beradigan URL yo'q edi.
 */
export default function AboutPage({ stats }: { stats: PlatformStats }) {
  useEffect(() => {
    setHead({
      title: "Loyiha haqida — IlmIz OAK jurnallari indeksi",
      description:
        "IlmIz qanday ishlaydi: OAK reestri va OAI-PMH orqali yig‘iladigan ochiq ilmiy indeks, manba provenance’i va bepul foydalanish shartlari.",
      path: "/loyiha",
    });
  }, []);

  return (
    <div className={cn(SHELL, "py-10 sm:py-14")}>
      <nav aria-label="Yo‘nalish" className="mb-5 flex items-center gap-1.5 text-xs text-muted-foreground">
        <AppLink to="/" className="hover:text-foreground">
          Bosh sahifa
        </AppLink>
        <span aria-hidden="true">/</span>
        <span aria-current="page">Loyiha haqida</span>
      </nav>

      <div className="max-w-2xl">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          IlmIz loyihasi haqida
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
          IlmIz — O‘zbekiston Oliy attestatsiya komissiyasi (OAK) ro‘yxatidagi ilmiy jurnallar va
          ularda chop etilgan maqolalarning ochiq indeksi.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Indeks nimadan iborat</h2>
        <ul className="mt-2 space-y-2 text-sm leading-relaxed text-muted-foreground">
          <li>
            <strong className="text-foreground">{number.format(stats.journals)} ta OAK jurnali</strong>{" "}
            profili: ISSN, nashriyot, tahririyat, nashr siyosatlari va OAK qarorlari.
          </li>
          <li>
            <strong className="text-foreground">{number.format(stats.articles)} ta maqola</strong>{" "}
            metama’lumoti: mualliflar, annotatsiya, kalit so‘zlar, DOI va to‘liq matn havolasi.
          </li>
          <li>Har bir maydonning manbasi va olingan vaqti saqlanadi.</li>
        </ul>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Ma’lumot qayerdan olinadi</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Jurnal metama’lumotlari OAK rasmiy elektron reestridan, maqolalar esa jurnal
          repozitoriylaridan OAI-PMH 2.0 protokoli orqali muntazam yig‘iladi. Faqat o‘zgargan
          yozuvlar olinadi, shuning uchun indeks eskirmaydi.
        </p>

        <h2 className="mt-8 text-lg font-semibold tracking-tight">Foydalanish</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Qidiruv va metama’lumotlar barcha uchun bepul.{" "}
          <AppLink to="/jurnallar" className="text-primary hover:underline">
            Jurnallar
          </AppLink>
          ,{" "}
          <AppLink to="/maqolalar" className="text-primary hover:underline">
            maqolalar
          </AppLink>
          ,{" "}
          <AppLink to="/sohalar" className="text-primary hover:underline">
            sohalar
          </AppLink>{" "}
          va{" "}
          <AppLink to="/shaharlar" className="text-primary hover:underline">
            shaharlar
          </AppLink>{" "}
          bo‘limlaridan boshlang.
        </p>
      </div>

      <div className="mt-10 grid gap-3 md:grid-cols-3">
        {[
          {
            icon: Globe2,
            title: "Ochiqlik",
            text: "Metama’lumotlar va qidiruv barcha foydalanuvchilar uchun ochiq.",
          },
          {
            icon: ShieldCheck,
            title: "Manba aniqligi",
            text: "Har bir maydon qayerdan va qachon olingani qayd etiladi.",
          },
          {
            icon: CalendarDays,
            title: "Doimiy yangilanish",
            text: "Faqat o‘zgargan yozuvlar muntazam olinadi, indeks eskirmaydi.",
          },
        ].map((item) => (
          <Card key={item.title} className="gap-3 py-5">
            <CardContent className="space-y-2.5 px-5">
              <span className="flex size-9 items-center justify-center rounded-md border bg-muted text-muted-foreground">
                <item.icon className="size-4" />
              </span>
              <h3 className="text-base font-semibold tracking-tight">{item.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">{item.text}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

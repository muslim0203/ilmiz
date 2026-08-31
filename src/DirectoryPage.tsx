import { useEffect } from "react";
import { BookOpen, FileText, Layers3, MapPin } from "lucide-react";

import type { Facets } from "@/api";
import { AppLink } from "@/components/app-link";
import { Card, CardContent } from "@/components/ui/card";
import { number } from "@/lib/format";
import { setHead } from "@/lib/head";
import { cityPath, fieldPath } from "@/lib/slug";
import { cn } from "@/lib/utils";

const SHELL = "mx-auto w-full max-w-[1200px] px-4 sm:px-6";

type Entry = { name: string; journals: number; articles: number; href: string };

function EntryCard({ entry }: { entry: Entry }) {
  return (
    <Card className="gap-0 py-0 transition-colors hover:border-primary/40 hover:bg-accent/40">
      <CardContent className="p-4">
        <AppLink to={entry.href} className="block text-[15px] font-semibold tracking-tight hover:text-primary">
          {entry.name}
        </AppLink>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <BookOpen className="size-3.5" />
            {number.format(entry.journals)} jurnal
          </span>
          <span className="inline-flex items-center gap-1">
            <FileText className="size-3.5" />
            {number.format(entry.articles)} maqola
          </span>
        </p>
      </CardContent>
    </Card>
  );
}

/** `/sohalar` va `/shaharlar` — indeksni kesib ko'rsatuvchi qo'nish sahifalari.
 *
 * Ular ichki havola grafigining asosiy tuguni: robot bosh sahifadan har bir
 * soha va shahar sahifasiga, u yerdan esa jurnallarga o'tadi.
 */
export default function DirectoryPage({ kind, facets }: { kind: "fields" | "cities"; facets: Facets }) {
  const isFields = kind === "fields";

  useEffect(() => {
    setHead(
      isFields
        ? {
            title: "Ilmiy sohalar — OAK jurnallari yo‘nalishlari bo‘yicha",
            description:
              "OAK ro‘yxatidagi ilmiy jurnallarni fan yo‘nalishi bo‘yicha ko‘ring: tibbiyot, pedagogika, iqtisodiyot, filologiya, texnika, yuridik va boshqa sohalar.",
            path: "/sohalar",
          }
        : {
            title: "Shaharlar bo‘yicha OAK jurnallari — O‘zbekiston",
            description:
              "O‘zbekiston shaharlari bo‘yicha OAK ro‘yxatidagi ilmiy jurnallar: Toshkent, Samarqand, Buxoro, Namangan, Farg‘ona, Nukus va boshqalar.",
            path: "/shaharlar",
          },
    );
  }, [isFields]);

  const cityEntries: Entry[] = facets.cities.map((item) => ({
    name: item.name,
    journals: item.journals,
    articles: item.articles,
    href: cityPath(item.name),
  }));

  return (
    <div className={cn(SHELL, "py-10 sm:py-14")}>
      <nav aria-label="Yo‘nalish" className="mb-5 flex items-center gap-1.5 text-xs text-muted-foreground">
        <AppLink to="/" className="hover:text-foreground">
          Bosh sahifa
        </AppLink>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{isFields ? "Sohalar" : "Shaharlar"}</span>
      </nav>

      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-lg border bg-muted text-muted-foreground">
          {isFields ? <Layers3 className="size-5" /> : <MapPin className="size-5" />}
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            {isFields ? "Ilmiy sohalar bo‘yicha OAK jurnallari" : "Shaharlar bo‘yicha OAK jurnallari"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isFields
              ? "OAK ro‘yxatidagi jurnallar fan yo‘nalishlari bo‘yicha guruhlangan."
              : "Jurnal qaysi shaharda nashr etilishiga qarab tanlang."}
          </p>
        </div>
      </div>

      {isFields ? (
        <div className="mt-8 space-y-8">
          {facets.fieldGroups.map((group) => (
            <section key={group.group}>
              <h2 className="text-lg font-semibold tracking-tight">{group.group}</h2>
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {group.fields.map((item) => (
                  <EntryCard
                    key={item.name}
                    entry={{
                      name: item.name,
                      journals: item.journals,
                      articles: item.articles,
                      href: fieldPath(item.name),
                    }}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {cityEntries.map((entry) => (
            <EntryCard key={entry.name} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}

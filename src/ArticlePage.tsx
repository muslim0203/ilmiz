import { useEffect, useState } from "react";
import { Check, Copy, Download, ExternalLink, Link2, Loader2, UsersRound } from "lucide-react";

import { loadArticle, loadJournalArticles } from "@/api";
import { AppLink } from "@/components/app-link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { clip, setHead } from "@/lib/head";
import { articlePath, fieldPath, journalPath, journalYearPath } from "@/lib/slug";
import { cn } from "@/lib/utils";
import type { Article } from "@/types";

const SHELL = "mx-auto w-full max-w-[1200px] px-4 sm:px-6";

/** `/maqola/{id}` — maqolaning o'z sahifasi.
 *
 * Serverda shu manzil uchun to'liq meta, `citation_*` teglari va JSON-LD
 * beriladi; bu komponent o'sha sahifaning interaktiv ko'rinishi.
 */
export default function ArticlePage({ id }: { id: string }) {
  const [article, setArticle] = useState<Article | null>(null);
  const [related, setRelated] = useState<Article[]>([]);
  const [error, setError] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setArticle(null);
    setError(false);
    loadArticle(id)
      .then((value) => {
        if (!active) return;
        setArticle(value);
        setHead({
          title: value.title,
          description: clip(value.abstract),
          path: articlePath(value.id, value.title),
        });
        const slug = value.journalSlug ?? value.journalId;
        if (slug) {
          void loadJournalArticles(slug, 6).then((items) => {
            if (active) setRelated(items.filter((item) => item.id !== value.id).slice(0, 5));
          });
        }
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [id]);

  if (error) {
    return (
      <div className={cn(SHELL, "py-20 text-center")}>
        <h1 className="text-2xl font-semibold tracking-tight">Maqola topilmadi</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Bu manzil bo‘yicha yozuv indeksda yo‘q.
        </p>
        <Button className="mt-6" asChild>
          <AppLink to="/maqolalar">Maqolalar ro‘yxatiga qaytish</AppLink>
        </Button>
      </div>
    );
  }

  if (!article) {
    return (
      <div className={cn(SHELL, "flex justify-center py-24 text-muted-foreground")}>
        <Loader2 className="size-6 animate-spin" />
      </div>
    );
  }

  const slug = article.journalSlug ?? article.journalId;
  const published = article.publicationDate || (article.year ? String(article.year) : null);
  const facts: Array<[string, string | null | undefined]> = [
    ["Jurnal", article.journalName],
    ["Nashr sanasi", published],
    ["Jild", article.volume !== "—" ? article.volume : null],
    ["Son", article.issue !== "—" ? article.issue : null],
    ["Betlar", article.pages !== "—" ? article.pages : null],
    ["Til", article.language],
    ["DOI", article.doi],
  ];

  const copy = (format: string, value: string) => {
    void navigator.clipboard?.writeText(value);
    setCopied(format);
    window.setTimeout(() => setCopied(null), 1600);
  };

  return (
    <article className={cn(SHELL, "py-8 sm:py-12")}>
      <nav aria-label="Yo‘nalish" className="mb-5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <AppLink to="/" className="hover:text-foreground">
          Bosh sahifa
        </AppLink>
        <span aria-hidden="true">/</span>
        <AppLink to="/maqolalar" className="hover:text-foreground">
          Maqolalar
        </AppLink>
        {slug && article.journalName && (
          <>
            <span aria-hidden="true">/</span>
            <AppLink to={journalPath(slug)} className="truncate hover:text-foreground">
              {article.journalName}
            </AppLink>
          </>
        )}
      </nav>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          <h1 className="text-balance text-2xl font-semibold leading-snug tracking-tight sm:text-3xl">
            {article.title}
          </h1>

          <p className="mt-4 flex items-start gap-2 text-sm text-muted-foreground">
            <UsersRound className="mt-0.5 size-4 shrink-0" />
            <span>{article.authors.join(", ")}</span>
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            {slug && article.journalName && (
              <AppLink to={journalPath(slug)} className="font-medium text-foreground hover:text-primary">
                {article.journalName}
              </AppLink>
            )}
            {slug && article.year > 0 && (
              <>
                <span aria-hidden="true">·</span>
                <AppLink to={journalYearPath(slug, article.year)} className="hover:text-primary">
                  {article.year}-yil
                </AppLink>
              </>
            )}
          </div>

          <div className="mt-5 flex flex-wrap gap-1.5">
            {article.fields.map((field) => (
              <Badge key={field} variant="secondary" className="font-normal" asChild>
                <AppLink to={fieldPath(field)}>{field}</AppLink>
              </Badge>
            ))}
            <Badge variant="outline" className="font-normal text-muted-foreground">
              {article.language}
            </Badge>
          </div>

          <h2 className="mt-8 text-lg font-semibold tracking-tight">Annotatsiya</h2>
          <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{article.abstract}</p>

          {article.keywords.length > 0 && (
            <>
              <h2 className="mt-8 text-lg font-semibold tracking-tight">Kalit so‘zlar</h2>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {article.keywords.map((word) => (
                  <Badge key={word} variant="outline" className="font-normal">
                    {word}
                  </Badge>
                ))}
              </div>
            </>
          )}

          <h2 className="mt-8 text-lg font-semibold tracking-tight">Maqola ma’lumotlari</h2>
          <dl className="mt-2 divide-y rounded-lg border">
            {facts
              .filter(([, value]) => Boolean(value))
              .map(([label, value]) => (
                <div key={label} className="flex gap-4 px-4 py-2.5 text-sm">
                  <dt className="w-32 shrink-0 text-muted-foreground">{label}</dt>
                  <dd className="min-w-0 flex-1 break-words">{value}</dd>
                </div>
              ))}
          </dl>

          {article.citations && (
            <>
              <h2 className="mt-8 text-lg font-semibold tracking-tight">Iqtibos formatlari</h2>
              <div className="mt-2 grid gap-2">
                {Object.entries(article.citations).map(([format, value]) => (
                  <div
                    key={format}
                    className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-start"
                  >
                    <Badge variant="outline" className="shrink-0 font-mono uppercase">
                      {format}
                    </Badge>
                    <p className="min-w-0 flex-1 break-words text-xs leading-relaxed text-muted-foreground">
                      {value}
                    </p>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="shrink-0"
                      onClick={() => copy(format, value)}
                    >
                      {copied === format ? <Check className="text-success" /> : <Copy />}
                      {copied === format ? "Nusxa olindi" : "Nusxa olish"}
                    </Button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Card className="gap-3 py-4">
            <CardContent className="space-y-2 px-4">
              <strong className="text-sm font-semibold">To‘liq matn</strong>
              <Separator />
              {article.landingUrl && (
                <Button variant="outline" className="w-full justify-start" asChild>
                  <a href={article.landingUrl} target="_blank" rel="noreferrer nofollow">
                    <ExternalLink /> Jurnaldagi sahifa
                  </a>
                </Button>
              )}
              {article.pdfUrl && (
                <Button variant="outline" className="w-full justify-start" asChild>
                  <a href={article.pdfUrl} target="_blank" rel="noreferrer nofollow">
                    <Download /> PDF
                  </a>
                </Button>
              )}
              {article.doi && (
                <Button variant="outline" className="w-full justify-start" asChild>
                  <a href={`https://doi.org/${article.doi}`} target="_blank" rel="noreferrer nofollow">
                    <Link2 /> DOI
                  </a>
                </Button>
              )}
              {!article.landingUrl && !article.pdfUrl && !article.doi && (
                <p className="text-xs text-muted-foreground">
                  Bu yozuv uchun tashqi havola ko‘rsatilmagan.
                </p>
              )}
            </CardContent>
          </Card>

          {related.length > 0 && slug && (
            <Card className="gap-3 py-4">
              <CardContent className="space-y-3 px-4">
                <strong className="text-sm font-semibold">Shu jurnaldan yana</strong>
                <Separator />
                <ul className="space-y-3">
                  {related.map((item) => (
                    <li key={item.id}>
                      <AppLink
                        to={articlePath(item.id, item.title)}
                        className="text-sm font-medium leading-snug hover:text-primary"
                      >
                        {item.title}
                      </AppLink>
                      <p className="mt-0.5 text-xs text-muted-foreground">{item.year || ""}</p>
                    </li>
                  ))}
                </ul>
                <Button variant="ghost" size="sm" className="w-full" asChild>
                  <AppLink to={journalPath(slug)}>Barcha maqolalar</AppLink>
                </Button>
              </CardContent>
            </Card>
          )}
        </aside>
      </div>
    </article>
  );
}

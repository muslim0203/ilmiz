import { useState } from "react";
import { Check, Copy, Download, ExternalLink, Link2, UsersRound } from "lucide-react";

import { AppLink } from "@/components/app-link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { monogram } from "@/lib/format";
import { articlePath, fieldPath, journalPath } from "@/lib/slug";
import { cn } from "@/lib/utils";
import type { Article, Journal } from "@/types";

export function ArticleCard({ article, journal }: { article: Article; journal: Journal }) {
  const [open, setOpen] = useState(false);
  const [citationsOpen, setCitationsOpen] = useState(false);
  const href = articlePath(article.id, article.title);
  const [copied, setCopied] = useState<string | null>(null);
  const published =
    article.publicationDate || (article.year ? String(article.year) : "Sana ko‘rsatilmagan");

  const copyCitation = (format: string, value: string) => {
    void navigator.clipboard?.writeText(value);
    setCopied(format);
    window.setTimeout(() => setCopied(null), 1600);
  };

  const meta = [
    published,
    article.volume !== "—" ? `${article.volume}-jild` : null,
    article.issue !== "—" ? `${article.issue}-son` : null,
    article.pages !== "—" ? `${article.pages}-bet` : null,
  ].filter(Boolean);

  return (
    <Card className="gap-0 py-0 transition-colors hover:border-primary/40">
      <div className="space-y-3 p-4 sm:p-5">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-md border bg-muted text-[11px] font-semibold text-muted-foreground">
            {monogram(journal.shortName)}
          </span>
          <div className="min-w-0 flex-1">
            <AppLink
              to={journalPath(journal.id)}
              className="block truncate text-sm font-medium leading-tight hover:text-primary"
            >
              {journal.name}
            </AppLink>
            <div className="truncate text-xs text-muted-foreground">{meta.join(" · ")}</div>
          </div>
          {article.isDemo && (
            <Badge variant="outline" className="font-mono text-[10px]">
              DEMO
            </Badge>
          )}
        </div>

        {/* Sarlavha — maqolaning doimiy manzili. Ilgari bu shunchaki
            annotatsiyani ochadigan tugma edi va maqolaga havola yo'q edi. */}
        <AppLink
          to={href}
          className="block cursor-pointer text-left text-[15px] font-semibold leading-snug tracking-tight outline-none hover:text-primary focus-visible:rounded-md focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          {article.title}
        </AppLink>

        <p className="flex items-start gap-1.5 text-sm text-muted-foreground">
          <UsersRound className="mt-0.5 size-4 shrink-0" />
          <span>{article.authors.join(", ")}</span>
        </p>

        <p
          className={cn(
            "text-sm leading-relaxed text-muted-foreground",
            !open && "line-clamp-2",
          )}
        >
          {article.abstract}
        </p>
        <button
          onClick={() => setOpen((value) => !value)}
          className="cursor-pointer text-xs font-medium text-muted-foreground outline-none hover:text-foreground"
        >
          {open ? "Yig‘ish" : "Annotatsiyani ochish"}
        </button>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex flex-wrap gap-1.5">
            {article.fields.map((field) => (
              <Badge key={field} variant="secondary" className="font-normal" asChild>
                <AppLink to={fieldPath(field)}>{field}</AppLink>
              </Badge>
            ))}
            <Badge variant="outline" className="font-normal text-muted-foreground">
              {article.language}
            </Badge>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <Button variant="ghost" size="sm" asChild>
              <AppLink to={href}>Batafsil</AppLink>
            </Button>
            {article.landingUrl && (
              <Button variant="ghost" size="sm" asChild>
                <a href={article.landingUrl} target="_blank" rel="noreferrer nofollow">
                  <ExternalLink /> Maqola sahifasi
                </a>
              </Button>
            )}
            {article.doi && (
              <Button variant="ghost" size="sm" asChild>
                <a href={`https://doi.org/${article.doi}`} target="_blank" rel="noreferrer nofollow" title="DOI">
                  <Link2 /> DOI
                </a>
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              title="Iqtibos formatlari"
              onClick={() => setCitationsOpen((value) => !value)}
            >
              <Download /> Iqtibos
            </Button>
          </div>
        </div>
      </div>

      {citationsOpen && article.citations && (
        <>
          <Separator />
          <div className="grid gap-2 bg-muted/40 p-4 sm:p-5">
            {Object.entries(article.citations).map(([format, value]) => (
              <div
                key={format}
                className="flex flex-col gap-2 rounded-lg border bg-background p-3 sm:flex-row sm:items-start"
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
                  onClick={() => copyCitation(format, value)}
                >
                  {copied === format ? <Check className="text-success" /> : <Copy />}
                  {copied === format ? "Nusxa olindi" : "Nusxa olish"}
                </Button>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

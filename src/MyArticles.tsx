import { useEffect, useState } from "react";
import { BookMarked, Check, Plus, Search, X } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  claimArticle,
  loadArticleSuggestions,
  loadMyArticles,
  unclaimArticle,
  type ArticleSuggestion,
  type AuthorshipStats,
} from "@/authApi";
import type { Article } from "@/types";

/** Maqola qatori — profilga qo'shish yoki olib tashlash uchun. */
function ArticleRow({
  article,
  note,
  action,
  busy,
}: {
  article: Article;
  note?: React.ReactNode;
  action: React.ReactNode;
  busy: boolean;
}) {
  return (
    <li className="flex items-start gap-3 rounded-lg border p-3">
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-sm font-medium leading-snug">{article.title}</p>
        <p className="truncate text-xs text-muted-foreground">
          {article.authors.join(", ") || "Mualliflar ko‘rsatilmagan"}
        </p>
        <p className="truncate text-xs text-muted-foreground">
          {article.journalName ?? "—"}
          {article.year ? ` · ${article.year}` : ""}
        </p>
        {note}
      </div>
      <div className={busy ? "pointer-events-none shrink-0 opacity-50" : "shrink-0"}>{action}</div>
    </li>
  );
}

export default function MyArticles({ displayName }: { displayName: string }) {
  const [mine, setMine] = useState<Article[]>([]);
  const [stats, setStats] = useState<AuthorshipStats | null>(null);
  const [suggestions, setSuggestions] = useState<ArticleSuggestion[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [needsFullName, setNeedsFullName] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    loadMyArticles()
      .then((data) => {
        if (!active) return;
        setMine(data.articles);
        setStats(data.stats);
      })
      .catch(() => active && setError("Maqolalaringiz olinmadi."))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const search = async () => {
    setSearching(true);
    setError(null);
    try {
      const data = await loadArticleSuggestions();
      setSuggestions(data.suggestions);
      setNeedsFullName(data.needsFullName);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Qidiruv bajarilmadi");
    } finally {
      setSearching(false);
    }
  };

  const add = async (article: ArticleSuggestion) => {
    setBusyId(article.id);
    setError(null);
    try {
      setStats(await claimArticle(article.id));
      setMine((current) => [article, ...current]);
      setSuggestions((current) => current?.filter((item) => item.id !== article.id) ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Qo‘shilmadi");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (article: Article) => {
    setBusyId(article.id);
    setError(null);
    try {
      setStats(await unclaimArticle(article.id));
      setMine((current) => current.filter((item) => item.id !== article.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Olib tashlanmadi");
    } finally {
      setBusyId(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  return (
    // `min-w-0` shart: DialogContent grid, grid elementining standart
    // `min-width: auto` qiymati `truncate` (white-space: nowrap) bo'lgan uzun
    // mualliflar qatorini siqilishga qo'ymay, butun oynani kengaytirib yuboradi.
    <div className="min-w-0 space-y-4">
      {stats && stats.articles > 0 && (
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-lg border p-3 text-center">
            <div className="text-lg font-semibold">{stats.articles}</div>
            <div className="text-xs text-muted-foreground">Maqola</div>
          </div>
          <div className="rounded-lg border p-3 text-center">
            <div className="text-lg font-semibold">{stats.journals}</div>
            <div className="text-xs text-muted-foreground">Jurnal</div>
          </div>
          <div className="rounded-lg border p-3 text-center">
            <div className="text-lg font-semibold">
              {stats.firstYear && stats.lastYear
                ? stats.firstYear === stats.lastYear
                  ? stats.firstYear
                  : `${stats.firstYear}–${stats.lastYear}`
                : "—"}
            </div>
            <div className="text-xs text-muted-foreground">Yillar</div>
          </div>
        </div>
      )}

      <Button className="w-full" size="lg" onClick={() => void search()} disabled={searching}>
        <Search /> {searching ? "Qidirilmoqda..." : "Maqolalarimni qidirish"}
      </Button>
      <p className="text-xs leading-relaxed text-muted-foreground">
        Qidiruv <span className="font-medium text-foreground">{displayName}</span> ismi bo‘yicha
        bajariladi. Topilganlar taxmin — qaysi biri sizniki ekanini o‘zingiz tasdiqlaysiz.
      </p>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {needsFullName && (
        <Alert>
          <AlertDescription>
            Qidiruv uchun ism va familiya kerak. Yuqoridagi maydonga ikkalasini yozib saqlang.
          </AlertDescription>
        </Alert>
      )}

      {suggestions !== null && !needsFullName && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">
            Topilgan nomzodlar{" "}
            <span className="font-normal text-muted-foreground">({suggestions.length})</span>
          </h4>
          {suggestions.length === 0 ? (
            <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
              Bu ism bo‘yicha maqola topilmadi.
            </p>
          ) : (
            <ul className="space-y-2">
              {suggestions.map((article) => (
                <ArticleRow
                  key={article.id}
                  article={article}
                  busy={busyId === article.id}
                  note={
                    // Muallif ismi uzun bo'lishi mumkin — `Badge` o'z-o'zicha
                    // satr ko'chirmaydi va butun qatorni kengaytirib yuboradi.
                    <Badge
                      variant={article.confidence === "exact" ? "secondary" : "outline"}
                      className="max-w-full gap-1 font-normal"
                    >
                      {article.confidence === "exact" && <Check className="size-3 shrink-0" />}
                      <span className="truncate">
                        {article.confidence === "exact"
                          ? article.matchedAuthor
                          : `Faqat bosh harf: ${article.matchedAuthor}`}
                      </span>
                    </Badge>
                  }
                  action={
                    <Button size="sm" variant="outline" onClick={() => void add(article)}>
                      <Plus /> Qo‘shish
                    </Button>
                  }
                />
              ))}
            </ul>
          )}
        </div>
      )}

      {mine.length > 0 && (
        <>
          <Separator />
          <div className="space-y-2">
            <h4 className="flex items-center gap-1.5 text-sm font-semibold">
              <BookMarked className="size-4" /> Mening maqolalarim{" "}
              <span className="font-normal text-muted-foreground">({mine.length})</span>
            </h4>
            <ul className="space-y-2">
              {mine.map((article) => (
                <ArticleRow
                  key={article.id}
                  article={article}
                  busy={busyId === article.id}
                  action={
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => void remove(article)}
                      aria-label="Profildan olib tashlash"
                    >
                      <X />
                    </Button>
                  }
                />
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

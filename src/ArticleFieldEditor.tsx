import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, RotateCcw, Search, TriangleAlert } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  loadArticleForEdit,
  loadUnclassifiedArticles,
  saveArticleFields,
  type AdminArticle,
} from "@/adminApi";

/** "123", "/maqola/123-sarlavha" yoki to'liq havola — maqola ID'si. */
function articleIdFrom(text: string): number | null {
  const match = text.trim().match(/(?:maqola\/)?(\d+)/);
  return match ? Number(match[1]) : null;
}

/**
 * Maqola sohasini qo'lda qo'yish. Avtomatik tasnif ko'p sohali jurnalda
 * aniq g'olib topmasa sohani bo'sh qoldiradi — ular shu yerdan to'ldiriladi.
 */
export default function ArticleFieldEditor() {
  const [queue, setQueue] = useState<AdminArticle[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [allFields, setAllFields] = useState<string[]>([]);
  const [lookup, setLookup] = useState("");
  const [article, setArticle] = useState<AdminArticle | null>(null);
  const [draft, setDraft] = useState<string[]>([]);
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const refreshQueue = useCallback(async (start: number) => {
    const data = await loadUnclassifiedArticles(start);
    setQueue(data.articles);
    setTotal(data.total);
    setAllFields(data.allFields);
    setOffset(start);
  }, []);

  useEffect(() => {
    void refreshQueue(0).catch(() => setMessage({ ok: false, text: "Ro‘yxat yuklanmadi" }));
  }, [refreshQueue]);

  function select(item: AdminArticle) {
    setArticle(item);
    setDraft(item.fields);
    setShowAll(false);
    setMessage(null);
  }

  async function open() {
    const id = articleIdFrom(lookup);
    if (id === null) {
      setMessage({ ok: false, text: "Maqola ID yoki havolasini kiriting" });
      return;
    }
    setBusy(true);
    try {
      const data = await loadArticleForEdit(id);
      setAllFields(data.allFields);
      select(data);
    } catch (error) {
      setMessage({ ok: false, text: error instanceof Error ? error.message : "Maqola topilmadi" });
    } finally {
      setBusy(false);
    }
  }

  async function save(fields: string[] | null) {
    if (!article) return;
    setBusy(true);
    try {
      const saved = await saveArticleFields(article.id, fields);
      select(saved);
      setMessage({
        ok: true,
        text: fields === null ? "Avtomatik tasnifga qaytarildi" : "Soha saqlandi — harvest unga tegmaydi",
      });
      await refreshQueue(offset);
    } catch (error) {
      setMessage({ ok: false, text: error instanceof Error ? error.message : "Saqlanmadi" });
    } finally {
      setBusy(false);
    }
  }

  function toggle(name: string, checked: boolean) {
    setDraft((current) => (checked ? [...current, name] : current.filter((item) => item !== name)));
  }

  const options = article
    ? showAll
      ? allFields
      : Array.from(new Set([...article.journalFields, ...draft]))
    : [];

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <div className="space-y-3">
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void open();
          }}
        >
          <Input
            value={lookup}
            onChange={(event) => setLookup(event.target.value)}
            placeholder="Maqola ID yoki havolasi"
            aria-label="Maqola ID yoki havolasi"
          />
          <Button type="submit" variant="outline" disabled={busy}>
            <Search className="size-4" /> Ochish
          </Button>
        </form>
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>Sohasiz maqolalar: {total.toLocaleString("uz")}</span>
          <span className="flex gap-1">
            <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => void refreshQueue(Math.max(0, offset - 20))}>
              Oldingi
            </Button>
            <Button size="sm" variant="ghost" disabled={offset + 20 >= total} onClick={() => void refreshQueue(offset + 20)}>
              Keyingi
            </Button>
          </span>
        </div>
        <ul className="divide-y rounded-md border">
          {queue.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => select(item)}
                className="w-full cursor-pointer px-3 py-2 text-left text-sm hover:bg-accent/50 aria-[current=true]:bg-accent"
                aria-current={article?.id === item.id}
              >
                <span className="line-clamp-2 font-medium">{item.title}</span>
                <span className="text-xs text-muted-foreground">{item.journalName}</span>
              </button>
            </li>
          ))}
          {queue.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted-foreground">Sohasiz maqola yo‘q</li>}
        </ul>
      </div>

      <div className="space-y-4">
        {message && (
          <Alert variant={message.ok ? "default" : "destructive"}>
            {message.ok ? <CheckCircle2 className="size-4" /> : <TriangleAlert className="size-4" />}
            <AlertDescription>{message.text}</AlertDescription>
          </Alert>
        )}
        {article ? (
          <>
            <div className="space-y-1">
              <a
                href={`/maqola/${article.id}`}
                target="_blank"
                rel="noreferrer"
                className="font-semibold hover:underline"
              >
                {article.title}
              </a>
              <p className="text-sm text-muted-foreground">
                #{article.id} · {article.journalName}
                {article.fieldsManual && <Badge variant="secondary" className="ml-2">qo‘lda</Badge>}
              </p>
              {article.keywords.length > 0 && (
                <p className="text-xs text-muted-foreground">Kalit so‘zlar: {article.keywords.join(", ")}</p>
              )}
            </div>
            <Separator />
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>{showAll ? "Barcha OAK sohalari" : "Jurnal sohalari"}</Label>
                <Button size="sm" variant="ghost" onClick={() => setShowAll((value) => !value)}>
                  {showAll ? "Faqat jurnal sohalari" : "Barcha sohalar"}
                </Button>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {options.map((name) => (
                  <label key={name} className="flex cursor-pointer items-center gap-2 text-sm">
                    <Checkbox checked={draft.includes(name)} onCheckedChange={(value) => toggle(name, value === true)} />
                    {name}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void save(draft)} disabled={busy || draft.length === 0}>
                Saqlash
              </Button>
              {article.fieldsManual && (
                <Button variant="outline" onClick={() => void save(null)} disabled={busy}>
                  <RotateCcw className="size-4" /> Avtomatikka qaytarish
                </Button>
              )}
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Chapdagi ro‘yxatdan maqolani tanlang yoki ID kiriting.</p>
        )}
      </div>
    </div>
  );
}

import { useState } from "react";
import { Check, Copy, Search } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AppLink } from "@/components/app-link";
import { loadArticle, searchArticles } from "@/api";
import { articlePath } from "@/lib/slug";
import type { Article } from "@/types";

type Formats = Record<"gost" | "apa" | "mla" | "chicago", string>;
type Result = { formats: Formats; source: string; articleUrl?: string | null };

const LABELS: Array<[keyof Formats, string]> = [
  ["gost", "GOST (OAK)"],
  ["apa", "APA"],
  ["mla", "MLA"],
  ["chicago", "Chicago"],
];

const MANUAL_FIELDS: Array<[string, string, string]> = [
  ["authors", "Mualliflar", "Karimov A., Aliyeva B. — vergul bilan"],
  ["title", "Sarlavha", "Maqola sarlavhasi"],
  ["journal", "Jurnal", "Jurnal nomi"],
  ["year", "Yil", "2025"],
  ["volume", "Jild", "3"],
  ["issue", "Son", "2"],
  ["pages", "Betlar", "10–15"],
  ["doi", "DOI", "10.1234/abcd"],
];

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error((payload as { detail?: string } | null)?.detail || `Xato ${response.status}`);
  return payload as T;
}

/** `/iqtibos` — maqola sahifasidagi formatlash qoidalari bilan bir xil iqtibos. */
export default function CitationTool() {
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [doi, setDoi] = useState("");
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Article[] | null>(null);
  const [manual, setManual] = useState<Record<string, string>>({});

  const run = async (task: () => Promise<Result>) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await task());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Bajarilmadi");
    } finally {
      setBusy(false);
    }
  };

  const byDoi = (event: React.FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const response = await fetch(`/api/citations/doi?doi=${encodeURIComponent(doi.trim())}`);
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error((payload as { detail?: string } | null)?.detail || "Topilmadi");
      return payload as Result;
    });
  };

  const search = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      setFound((await searchArticles(query)).items.slice(0, 8));
    } catch {
      setError("Qidiruv bajarilmadi");
    } finally {
      setBusy(false);
    }
  };

  const pick = (item: Article) =>
    void run(async () => {
      const article = await loadArticle(item.id);
      if (!article.citations) throw new Error("Bu maqola uchun iqtibos tayyorlanmadi");
      const { gost, apa, mla, chicago } = article.citations;
      return { formats: { gost, apa, mla, chicago }, source: "ilmiz", articleUrl: articlePath(article.id, article.title) };
    });

  const byHand = (event: React.FormEvent) => {
    event.preventDefault();
    const authors = (manual.authors ?? "").split(",").map((name) => name.trim()).filter(Boolean);
    const year = manual.year?.trim() ? Number(manual.year) : null;
    void run(async () => {
      const data = await postJson<{ formats: Formats }>("/api/citations/format", {
        ...Object.fromEntries(Object.entries(manual).filter(([key, value]) => key !== "authors" && key !== "year" && value.trim())),
        authors,
        year,
        language: manual.language ?? "uz",
        title: manual.title ?? "",
        journal: manual.journal ?? "",
      });
      return { formats: data.formats, source: "manual" };
    });
  };

  const copy = async (key: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      setError("Nusxalashga ruxsat berilmadi. Matnni belgilab, qo‘lda nusxalang.");
    }
  };

  return (
    <section className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight">Iqtibos generatori</h1>
      <p className="mt-2 text-muted-foreground">
        GOST (OAK), APA, MLA va Chicago formatida bibliografik yozuv. DOI kiriting, IlmIz bazasidan
        qidiring yoki ma’lumotlarni qo‘lda yozing.
      </p>

      <Tabs defaultValue="doi" className="mt-6">
        <TabsList>
          <TabsTrigger value="doi">DOI</TabsTrigger>
          <TabsTrigger value="search">Bazadan qidirish</TabsTrigger>
          <TabsTrigger value="manual">Qo‘lda</TabsTrigger>
        </TabsList>

        <TabsContent value="doi">
          <form className="mt-4 flex gap-2" onSubmit={byDoi}>
            <Input value={doi} onChange={(event) => setDoi(event.target.value)} placeholder="10.5281/zenodo.123456" aria-label="DOI" />
            <Button type="submit" disabled={busy || !doi.trim()}>Tayyorlash</Button>
          </form>
        </TabsContent>

        <TabsContent value="search">
          <form className="mt-4 flex gap-2" onSubmit={search}>
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Sarlavha yoki muallif" aria-label="Maqola qidirish" />
            <Button type="submit" disabled={busy || !query.trim()}>
              <Search className="size-4" /> Qidirish
            </Button>
          </form>
          {found && (
            <ul className="mt-3 divide-y rounded-md border">
              {found.length === 0 && <li className="p-3 text-sm text-muted-foreground">Topilmadi.</li>}
              {found.map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => pick(item)} className="w-full cursor-pointer p-3 text-left hover:bg-accent/50">
                    <span className="line-clamp-2 text-sm font-medium">{item.title}</span>
                    <span className="text-xs text-muted-foreground">{item.journalName} · {item.year || "—"}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="manual">
          <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={byHand}>
            {MANUAL_FIELDS.map(([key, label, hint]) => (
              <div key={key} className={key === "title" || key === "authors" || key === "journal" ? "space-y-1 sm:col-span-2" : "space-y-1"}>
                <Label htmlFor={`cite-${key}`}>{label}</Label>
                <Input
                  id={`cite-${key}`}
                  value={manual[key] ?? ""}
                  placeholder={hint}
                  inputMode={key === "year" ? "numeric" : undefined}
                  onChange={(event) => setManual({ ...manual, [key]: event.target.value })}
                />
              </div>
            ))}
            <div className="space-y-1">
              <Label htmlFor="cite-language">Maqola tili</Label>
              <select
                id="cite-language"
                className="h-9 w-full rounded-md border bg-transparent px-3 text-sm"
                value={manual.language ?? "uz"}
                onChange={(event) => setManual({ ...manual, language: event.target.value })}
              >
                <option value="uz">O‘zbek (GOST: B.)</option>
                <option value="ru">Rus (GOST: С.)</option>
                <option value="en">Ingliz (GOST: P.)</option>
              </select>
            </div>
            <Button type="submit" className="sm:col-span-2" disabled={busy}>Tayyorlash</Button>
          </form>
        </TabsContent>
      </Tabs>

      {error && (
        <Alert variant="destructive" className="mt-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {result && (
        <div className="mt-6 space-y-3" aria-live="polite">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            Manba:
            <Badge variant="outline">
              {result.source === "ilmiz" ? "IlmIz bazasi" : result.source === "crossref" ? "Crossref" : "qo‘lda kiritilgan"}
            </Badge>
            {result.articleUrl && <AppLink to={result.articleUrl} className="underline">Maqola sahifasi</AppLink>}
          </div>
          {LABELS.map(([key, label]) => (
            <div key={key} className="rounded-md border p-3">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-sm font-semibold">{label}</span>
                <Button size="sm" variant="ghost" onClick={() => void copy(key, result.formats[key])}>
                  {copied === key ? <Check className="size-4" /> : <Copy className="size-4" />}
                  {copied === key ? "Nusxalandi" : "Nusxalash"}
                </Button>
              </div>
              <p className="whitespace-pre-wrap break-words text-sm">{result.formats[key]}</p>
            </div>
          ))}
        </div>
      )}

      <p className="mt-8 text-sm text-muted-foreground">
        Jurnal yoki dissertatsiya kengashining talablari formatdan farq qilishi mumkin — ularni tekshiring.{" "}
        <AppLink to="/yoriqnoma" className="underline">Yo‘riqnoma</AppLink>
      </p>
    </section>
  );
}

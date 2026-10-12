import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Plus, Trash2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { deleteGuide, loadGuides, saveGuide, type AdminGuide, type GuideInput } from "@/adminApi";

const EMPTY: GuideInput = { slug: "", title: "", summary: "", body: "", isPublished: false };
// Server ham shu chegarani tekshiradi: yupqa sahifa chop etilmaydi.
const MIN_PUBLISH_WORDS = 150;

/** `/yoriqnoma` qo'llanmalari: yozish, chop etish, o'chirish. */
export default function GuideEditor() {
  const [guides, setGuides] = useState<AdminGuide[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<GuideInput>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => setGuides((await loadGuides()).guides);

  useEffect(() => {
    void refresh().catch(() => setError("Qo‘llanmalar yuklanmadi"));
  }, []);

  const edit = (guide: AdminGuide | null) => {
    setEditingId(guide?.id ?? null);
    setDraft(guide ? { slug: guide.slug, title: guide.title, summary: guide.summary ?? "", body: guide.body, isPublished: guide.isPublished } : EMPTY);
    setMessage(null);
    setError(null);
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveGuide(editingId, draft);
      setEditingId(saved.id);
      setMessage(saved.isPublished ? "Saqlandi va chop etildi" : "Qoralama saqlandi");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Saqlanmadi");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (editingId === null || !window.confirm("Qo‘llanma butunlay o‘chirilsinmi?")) return;
    setBusy(true);
    try {
      await deleteGuide(editingId);
      edit(null);
      await refresh();
      setMessage("O‘chirildi");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "O‘chirilmadi");
    } finally {
      setBusy(false);
    }
  };

  const words = draft.body.split(/\s+/).filter(Boolean).length;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <div className="space-y-2">
        <Button variant="outline" className="w-full" onClick={() => edit(null)}>
          <Plus className="size-4" /> Yangi qo‘llanma
        </Button>
        <ul className="divide-y rounded-md border">
          {guides.length === 0 && <li className="p-3 text-sm text-muted-foreground">Hali qo‘llanma yo‘q.</li>}
          {guides.map((guide) => (
            <li key={guide.id}>
              <button
                type="button"
                onClick={() => edit(guide)}
                aria-current={guide.id === editingId}
                className="w-full cursor-pointer p-3 text-left hover:bg-accent/50 aria-[current=true]:bg-accent"
              >
                <span className="block text-sm font-medium">{guide.title}</span>
                <span className="text-xs text-muted-foreground">
                  /yoriqnoma/{guide.slug} · {guide.words} so‘z ·{" "}
                  {guide.isPublished ? "chop etilgan" : "qoralama"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <form className="space-y-3" onSubmit={save}>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="guide-title">Sarlavha</Label>
            <Input id="guide-title" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="guide-slug">Manzil (slug)</Label>
            <Input
              id="guide-slug"
              value={draft.slug}
              placeholder="oak-talablari"
              onChange={(event) => setDraft({ ...draft, slug: event.target.value.toLowerCase() })}
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="guide-summary">Qisqacha mazmun (qidiruv tavsifi)</Label>
          <Input id="guide-summary" value={draft.summary ?? ""} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="guide-body">Matn</Label>
          <textarea
            id="guide-body"
            className="min-h-80 w-full rounded-md border bg-transparent p-3 font-mono text-sm"
            value={draft.body}
            placeholder={"## Bo‘lim sarlavhasi\nAbzas matni.\n\n- ro‘yxat bandi\n- yana bir band"}
            onChange={(event) => setDraft({ ...draft, body: event.target.value })}
          />
          <p className="text-xs text-muted-foreground">
            {words} so‘z · «## » — sarlavha, «- » — ro‘yxat, bo‘sh qator — yangi abzas. HTML qabul qilinmaydi.
            Chop etish uchun kamida {MIN_PUBLISH_WORDS} so‘z.
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <Checkbox checked={draft.isPublished} onCheckedChange={(value) => setDraft({ ...draft, isPublished: value === true })} />
          Chop etilsin (saytda va sitemap'da ko‘rinadi)
        </label>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {message && (
          <Alert variant="success">
            <CheckCircle2 />
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={busy}>Saqlash</Button>
          {editingId !== null && draft.isPublished && (
            <Button type="button" variant="outline" asChild>
              <a href={`/yoriqnoma/${draft.slug}`} target="_blank" rel="noreferrer">
                <ExternalLink className="size-4" /> Sahifani ochish
              </a>
            </Button>
          )}
          {editingId !== null && (
            <Button type="button" variant="ghost" className="text-destructive" disabled={busy} onClick={() => void remove()}>
              <Trash2 className="size-4" /> O‘chirish
            </Button>
          )}
          {editingId !== null && <Badge variant="outline" className="self-center font-normal">#{editingId}</Badge>}
        </div>
      </form>
    </div>
  );
}

import { useState } from "react";
import { CheckCircle2, PencilLine, Search, TriangleAlert } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import ContactEditor from "@/ContactEditor";
import {
  loadJournalForEdit,
  saveJournal,
  searchJournals,
  type JournalEditRecord,
  type JournalEditValues,
  type JournalSummary,
} from "@/adminApi";

/** Formada matn sifatida tahrirlanadigan maydonlar va ularning yorliqlari. */
const TEXT_LABELS: Array<[keyof JournalEditValues, string]> = [
  ["name", "Nomi"],
  ["short_name", "Qisqa nomi"],
  ["publisher", "Nashriyot"],
  ["city", "Shahar"],
  ["issn", "ISSN"],
  ["eissn", "e-ISSN"],
  ["founded", "Asos solingan yil"],
  ["website", "Sayt"],
];
const LIST_LABELS: Array<[keyof JournalEditValues, string]> = [
  ["fields", "Ilmiy sohalar"],
  ["languages", "Tillar"],
];
// Bular `journal_profiles` da turadi va to'liqlik baliga bevosita ta'sir
// qiladi — jurnal maydonlaridan alohida ko'rsatiladi.
const PROFILE_LABELS: Array<[keyof JournalEditValues, string]> = [
  ["summary", "Tavsif (profil)"],
  ["address", "Manzil"],
  ["latest_issue", "So‘nggi son"],
];

/** Har bir maydonni forma uchun matnga aylantiradi. */
function toText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

/** Formadagi matnni API kutgan turga qaytaradi. */
function fromText(field: keyof JournalEditValues, text: string): unknown {
  if (field === "fields" || field === "languages") {
    return text
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (field === "founded") return text.trim() === "" ? null : Number(text.trim());
  return text.trim();
}

/** Yorliq inputga `htmlFor` orqali bog'lanadi — aks holda ekran o'quvchi
 *  maydon nomini o'qimaydi. `children` id ni funksiya orqali oladi. */
function Field({
  name,
  label,
  manual,
  children,
}: {
  name: string;
  label: string;
  manual: boolean;
  children: (id: string) => React.ReactNode;
}) {
  const id = `journal-${name}`;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="flex items-center gap-1.5">
        {label}
        {manual && (
          <Badge variant="outline" className="gap-1 font-normal">
            <PencilLine className="size-3" /> qo‘lda
          </Badge>
        )}
      </Label>
      {children(id)}
    </div>
  );
}

export default function JournalEditor() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<JournalSummary[] | null>(null);
  const [record, setRecord] = useState<JournalEditRecord | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reset = (next: JournalEditRecord) => {
    setRecord(next);
    setDraft(
      Object.fromEntries(
        Object.entries(next.values).map(([field, value]) => [field, toText(value)]),
      ),
    );
  };

  const runSearch = async (event: React.FormEvent) => {
    event.preventDefault();
    setSearching(true);
    setError(null);
    // Ochiq forma yopilmasa, natijalar ro'yxati ko'rinmay qoladi.
    setRecord(null);
    setMessage(null);
    setWarnings([]);
    try {
      const data = await searchJournals(query);
      setResults(data.journals);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Qidiruv bajarilmadi");
    } finally {
      setSearching(false);
    }
  };

  const open = async (slug: string) => {
    setError(null);
    setMessage(null);
    setWarnings([]);
    try {
      reset(await loadJournalForEdit(slug));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Jurnal ochilmadi");
    }
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!record) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    setWarnings([]);
    // Faqat haqiqatan o'zgargan maydonlar yuboriladi — shunda tegilmagan
    // maydon "qo'lda tahrirlangan" deb belgilanmaydi.
    const changes: Record<string, unknown> = {};
    for (const [field, text] of Object.entries(draft)) {
      const key = field as keyof JournalEditValues;
      if (text !== toText(record.values[key])) changes[field] = fromText(key, text);
    }
    if (Object.keys(changes).length === 0) {
      setMessage("O‘zgarish yo‘q.");
      setSaving(false);
      return;
    }
    try {
      const result = await saveJournal(record.slug, changes as Partial<JournalEditValues>);
      reset(result);
      setWarnings(result.warnings);
      setMessage(`Saqlandi: ${result.applied.join(", ")}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Saqlanmadi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-w-0 space-y-4">
      <form className="flex gap-2" onSubmit={runSearch}>
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Jurnal nomi, nashriyot yoki ISSN..."
        />
        <Button type="submit" disabled={searching}>
          <Search /> {searching ? "Qidirilmoqda..." : "Qidirish"}
        </Button>
      </form>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {results !== null && !record && (
        <div className="space-y-2">
          {results.length === 0 ? (
            <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
              Jurnal topilmadi.
            </p>
          ) : (
            <ul className="space-y-2">
              {results.map((journal) => (
                <li key={journal.slug} className="flex items-start gap-3 rounded-lg border p-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium leading-snug">{journal.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {journal.publisher} · {journal.city}
                      {journal.issn ? ` · ISSN ${journal.issn}` : ""}
                    </p>
                    {journal.manualFields.length > 0 && (
                      <Badge variant="outline" className="mt-1 gap-1 font-normal">
                        <PencilLine className="size-3" /> {journal.manualFields.length} maydon
                        qo‘lda
                      </Badge>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    className="shrink-0"
                    onClick={() => void open(journal.slug)}
                  >
                    Tahrirlash
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {record && (
        <form className="space-y-4" onSubmit={save}>
          <div className="flex items-center justify-between gap-2">
            <h4 className="min-w-0 truncate text-sm font-semibold">{record.values.name}</h4>
            {record.completeness.score !== null && (
              <Badge variant="outline" className="shrink-0 font-normal">
                To‘liqlik {record.completeness.score}%
              </Badge>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="shrink-0"
              onClick={() => setRecord(null)}
            >
              Ro‘yxatga qaytish
            </Button>
          </div>
          <Separator />

          <div className="grid gap-3 sm:grid-cols-2">
            {TEXT_LABELS.map(([field, label]) => (
              <Field
                key={field}
                name={field}
                label={label}
                manual={record.manualFields.includes(field)}
              >
                {(id) => (
                  <Input
                    id={id}
                    value={draft[field] ?? ""}
                    onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
                  />
                )}
              </Field>
            ))}

            {LIST_LABELS.map(([field, label]) => (
              <Field
                key={field}
                name={field}
                label={label}
                manual={record.manualFields.includes(field)}
              >
                {(id) => (
                  <Input
                    id={id}
                    value={draft[field] ?? ""}
                    onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
                    placeholder="Vergul bilan ajrating"
                  />
                )}
              </Field>
            ))}

            <Field
              name="oak_status"
              label="OAK holati"
              manual={record.manualFields.includes("oak_status")}
            >
              {(id) => (
                <select
                  id={id}
                  className="h-9 w-full rounded-md border bg-transparent px-3 text-sm"
                  value={draft.oak_status ?? ""}
                  onChange={(event) => setDraft({ ...draft, oak_status: event.target.value })}
                >
                  {record.choices.oakStatus.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              )}
            </Field>

            <Field
              name="access"
              label="Kirish turi"
              manual={record.manualFields.includes("access")}
            >
              {(id) => (
                <select
                  id={id}
                  className="h-9 w-full rounded-md border bg-transparent px-3 text-sm"
                  value={draft.access ?? ""}
                  onChange={(event) => setDraft({ ...draft, access: event.target.value })}
                >
                  {record.choices.access.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>

          {PROFILE_LABELS.map(([field, label]) => (
            <Field
              key={field}
              name={field}
              label={label}
              manual={record.manualFields.includes(field)}
            >
              {(id) => (
                <Input
                  id={id}
                  value={draft[field] ?? ""}
                  onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
                />
              )}
            </Field>
          ))}

          <Field
            name="description"
            label="Tavsif (katalog)"
            manual={record.manualFields.includes("description")}
          >
            {(id) => (
              <textarea
                id={id}
                className="min-h-24 w-full rounded-md border bg-transparent p-3 text-sm"
                value={draft.description ?? ""}
                onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              />
            )}
          </Field>

          {warnings.map((warning) => (
            <Alert key={warning}>
              <TriangleAlert />
              <AlertDescription>{warning}</AlertDescription>
            </Alert>
          ))}
          {message && (
            <Alert variant="success">
              <CheckCircle2 />
              <AlertDescription>{message}</AlertDescription>
            </Alert>
          )}

          {record.completeness.missing.length > 0 && (
            <div className="rounded-lg border border-dashed p-3">
              <p className="text-xs font-medium">
                To‘liqlik uchun yetishmayapti ({record.completeness.missing.length}):
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {record.completeness.missing.join(", ")}
              </p>
            </div>
          )}

          <p className="text-xs leading-relaxed text-muted-foreground">
            Qo‘lda kiritilgan qiymatlarni OAK reestri va tadqiq.uz importlari qayta yozmaydi —
            ular faqat bo‘sh maydonlarni to‘ldiradi.
          </p>

          <Button type="submit" className="w-full" disabled={saving}>
            {saving ? "Saqlanmoqda..." : "Saqlash"}
          </Button>
        </form>
      )}

      {record && (
        <>
          <Separator />
          {/* Alohida saqlanadi: aloqa ro'yxati butunlay almashtiriladi,
              jurnal maydonlari esa faqat o'zgarganlari yuboriladi. */}
          <ContactEditor slug={record.slug} initial={record.contacts} />
        </>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { AtSign, CheckCircle2, MapPin, PencilLine, Phone, Plus, TriangleAlert, X } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { saveContacts, type ContactKind, type JournalContact } from "@/adminApi";

const KINDS: Array<{ value: ContactKind; label: string; icon: typeof Phone }> = [
  { value: "address", label: "Manzil", icon: MapPin },
  { value: "email", label: "Email", icon: AtSign },
  { value: "phone", label: "Telefon", icon: Phone },
];

const PLACEHOLDERS: Record<ContactKind, string> = {
  address: "Toshkent shahri, Universitet ko‘chasi 4",
  email: "info@jurnal.uz",
  phone: "+998 71 123-45-67",
};

export default function ContactEditor({
  slug,
  initial,
}: {
  slug: string;
  initial: JournalContact[];
}) {
  const [rows, setRows] = useState<JournalContact[]>(initial);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Boshqa jurnalga o'tilganda forma yangi ro'yxatni oladi.
  useEffect(() => {
    setRows(initial);
    setMessage(null);
    setWarnings([]);
    setError(null);
  }, [initial]);

  const update = (index: number, patch: Partial<JournalContact>) =>
    setRows(rows.map((row, position) => (position === index ? { ...row, ...patch } : row)));

  const add = (kind: ContactKind) =>
    setRows([...rows, { kind, value: "", label: null, isManual: true }]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    setWarnings([]);
    setError(null);
    try {
      const result = await saveContacts(
        slug,
        // Bo'sh qatorlar yangi qo'shilib to'ldirilmagani uchun tashlanadi.
        rows.filter((row) => row.value.trim()),
      );
      setRows(result.contacts);
      setWarnings(result.warnings);
      setMessage(`Saqlandi: ${result.contacts.length} ta yozuv.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Saqlanmadi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-w-0 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label className="text-sm font-semibold">Aloqa ma’lumotlari</Label>
        <div className="flex flex-wrap gap-1.5">
          {KINDS.map(({ value, label, icon: Icon }) => (
            <Button key={value} type="button" size="sm" variant="outline" onClick={() => add(value)}>
              <Plus /> <Icon /> {label}
            </Button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
          Aloqa ma’lumoti yo‘q.
        </p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row, index) => (
            <li key={row.id ?? `yangi-${index}`} className="flex items-start gap-2">
              <select
                aria-label="Turi"
                className="h-9 w-28 shrink-0 rounded-md border bg-transparent px-2 text-sm"
                value={row.kind}
                onChange={(event) => update(index, { kind: event.target.value as ContactKind })}
              >
                {KINDS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <div className="min-w-0 flex-1 space-y-1">
                <Input
                  aria-label={`${row.kind} qiymati`}
                  value={row.value}
                  placeholder={PLACEHOLDERS[row.kind]}
                  onChange={(event) => update(index, { value: event.target.value })}
                />
                <Input
                  aria-label="Yorliq"
                  className="h-8 text-xs"
                  value={row.label ?? ""}
                  placeholder="Yorliq (ixtiyoriy) — masalan: Bosh muharrir"
                  onChange={(event) => update(index, { label: event.target.value || null })}
                />
                {row.isManual === false && row.sourceUrl && (
                  <p className="truncate text-xs text-muted-foreground">
                    Manba: {row.sourceUrl}
                  </p>
                )}
                {row.isManual && (
                  <Badge variant="outline" className="gap-1 font-normal">
                    <PencilLine className="size-3" /> qo‘lda
                  </Badge>
                )}
              </div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="shrink-0"
                aria-label="Yozuvni o‘chirish"
                onClick={() => setRows(rows.filter((_, position) => position !== index))}
              >
                <X />
              </Button>
            </li>
          ))}
        </ul>
      )}

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
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button type="button" variant="outline" className="w-full" onClick={() => void save()} disabled={saving}>
        {saving ? "Saqlanmoqda..." : "Aloqa ma’lumotlarini saqlash"}
      </Button>
    </div>
  );
}

import { useState } from "react";
import { Download, Globe2, PencilLine, RefreshCw } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { downloadMissingAboutCsv, loadSiteCheck, type SiteCheckRow } from "@/adminApi";

/**
 * Sayti noto'g'ri bo'lishi mumkin bo'lgan jurnallar. Avtomatik tuzatilmaydi:
 * maqolalar OpenAlex yoki slib.uz kabi platformada turishi qonuniy — admin
 * ko'rib chiqib, kerak bo'lsa sayt manzilini qo'lda tuzatadi.
 */
export default function SiteCheck({ onEdit }: { onEdit: (slug: string) => void }) {
  const [rows, setRows] = useState<SiteCheckRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setRows((await loadSiteCheck()).journals);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Ro‘yxat yuklanmadi");
    } finally {
      setLoading(false);
    }
  };

  const download = async () => {
    setError(null);
    try {
      await downloadMissingAboutCsv();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "CSV yuklanmadi");
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => void load()} disabled={loading}>
          {rows ? <RefreshCw className="size-4" /> : <Globe2 className="size-4" />}
          {loading ? "Tekshirilmoqda..." : rows ? "Qayta tekshirish" : "Saytlarni tekshirish"}
        </Button>
        <Button variant="outline" onClick={() => void download()}>
          <Download className="size-4" /> Tavsifsiz jurnallar (CSV)
        </Button>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {rows && (
        <p className="text-sm text-muted-foreground">
          {rows.length === 0 ? "Muammo topilmadi." : `${rows.length} ta jurnalni ko‘rib chiqish kerak.`}
        </p>
      )}
      {rows && rows.length > 0 && (
        <ul className="max-h-[28rem] divide-y overflow-y-auto rounded-md border">
          {rows.map((row) => (
            <li key={row.slug} className="flex items-start gap-3 p-3">
              <div className="min-w-0 flex-1 space-y-1">
                <p className="text-sm font-medium leading-snug">
                  {row.name}
                  {row.manual && (
                    <Badge variant="outline" className="ml-2 font-normal">sayt tasdiqlangan</Badge>
                  )}
                </p>
                <p className="truncate text-xs text-muted-foreground">{row.website || "sayt yo‘q"}</p>
                <ul className="list-disc pl-4 text-xs text-muted-foreground">
                  {row.problems.map((problem) => (
                    <li key={problem}>{problem}</li>
                  ))}
                </ul>
              </div>
              <Button size="sm" variant="outline" className="shrink-0" onClick={() => onEdit(row.slug)}>
                <PencilLine className="size-4" /> Tahrirlash
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

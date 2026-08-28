import { useMemo, useState } from "react";
import { Check, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { number } from "@/lib/format";
import type { FieldGroup } from "@/api";

type Props = {
  groups: FieldGroup[];
  selected: string[];
  onApply: (fields: string[]) => void;
  onClose: () => void;
};

export default function FieldPicker({ groups, selected, onApply, onClose }: Props) {
  const [draft, setDraft] = useState<string[]>(selected);
  const [needle, setNeedle] = useState("");

  const query = needle.trim().toLocaleLowerCase("uz");
  const visible = useMemo(() => {
    if (!query) return groups;
    return groups
      .map((group) => ({
        ...group,
        fields: group.group.toLocaleLowerCase("uz").includes(query)
          ? group.fields
          : group.fields.filter((item) => item.name.toLocaleLowerCase("uz").includes(query)),
      }))
      .filter((group) => group.fields.length > 0);
  }, [groups, query]);

  const draftSet = useMemo(() => new Set(draft), [draft]);
  const toggleField = (name: string) => {
    setDraft((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    );
  };
  const toggleGroup = (group: FieldGroup) => {
    const names = group.fields.map((item) => item.name);
    const allOn = names.every((name) => draftSet.has(name));
    setDraft((current) =>
      allOn
        ? current.filter((item) => !names.includes(item))
        : Array.from(new Set([...current, ...names])),
    );
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="space-y-3 border-b p-6 pb-4">
          <div className="space-y-1">
            <DialogTitle>Fan yo‘nalishini tanlang</DialogTitle>
            <DialogDescription>
              Bir nechta sohani belgilab, katalogni toraytiring.
            </DialogDescription>
          </div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={needle}
              onChange={(event) => setNeedle(event.target.value)}
              placeholder="Soha nomi bo‘yicha izlash..."
              autoFocus
              className="pl-9"
            />
          </div>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-6">
          {visible.length === 0 && (
            <p className="py-10 text-center text-sm text-muted-foreground">
              “{needle}” bo‘yicha soha topilmadi.
            </p>
          )}
          {visible.map((group) => {
            const names = group.fields.map((item) => item.name);
            const allOn = names.every((name) => draftSet.has(name));
            const someOn = !allOn && names.some((name) => draftSet.has(name));
            return (
              <section key={group.group} className="space-y-2">
                <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-1 py-1 transition-colors hover:bg-accent">
                  <Checkbox
                    checked={allOn}
                    indeterminate={someOn || undefined}
                    onCheckedChange={() => toggleGroup(group)}
                  />
                  <strong className="text-sm font-semibold tracking-tight">{group.group}</strong>
                  <Badge variant="secondary" className="ml-auto font-normal tabular-nums">
                    {number.format(group.articles)}
                  </Badge>
                </label>
                <Separator />
                <ul className="grid gap-0.5 sm:grid-cols-2">
                  {group.fields.map((item) => (
                    <li key={item.name}>
                      <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-1 py-1.5 transition-colors hover:bg-accent">
                        <Checkbox
                          checked={draftSet.has(item.name)}
                          onCheckedChange={() => toggleField(item.name)}
                        />
                        <span className="min-w-0 flex-1 truncate text-sm">{item.name}</span>
                        <small className="shrink-0 text-xs tabular-nums text-muted-foreground">
                          {number.format(item.articles)}
                        </small>
                      </label>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-muted/40 p-4">
          <span className="text-sm text-muted-foreground">
            {draft.length
              ? `${draft.length} ta soha tanlandi`
              : "Soha tanlanmagan — hammasi ko‘rsatiladi"}
          </span>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => setDraft([])} disabled={draft.length === 0}>
              Tozalash
            </Button>
            <Button onClick={() => onApply(draft)}>
              <Check /> Qo‘llash
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

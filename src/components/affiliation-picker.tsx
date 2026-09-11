import { useEffect, useId, useRef, useState } from "react";
import { CheckCircle2, Loader2, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { searchRor, type RorOrganization } from "@/authApi";
import { cn } from "@/lib/utils";

export type AffiliationValue = { name: string; rorId: string | null };

const MIN_QUERY = 3;

/** Ish joyi: erkin matn yoki ROR registridan tanlangan tashkilot.
 *
 * Matn qo'lda o'zgartirilsa ROR bog'lanishi darhol uziladi — aks holda
 * "tasdiqlangan" belgisi boshqa nom yonida qolib ketardi. */
export default function AffiliationPicker({
  id,
  value,
  onChange,
}: {
  id: string;
  value: AffiliationValue;
  onChange: (next: AffiliationValue) => void;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<RorOrganization[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [active, setActive] = useState(-1);
  // Faqat foydalanuvchi yozganda qidiramiz: profil yuklanganda yoki
  // tashkilot tanlanganda ro'yxat o'z-o'zidan ochilmasin.
  const typed = useRef(false);

  const query = value.name.trim();

  useEffect(() => {
    if (!typed.current || value.rorId || query.length < MIN_QUERY) {
      setItems([]);
      setState("idle");
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setState("loading");
      searchRor(query, controller.signal)
        .then((found) => {
          setItems(found);
          setActive(-1);
          setState("ready");
        })
        .catch(() => {
          if (!controller.signal.aborted) setState("error");
        });
    }, 350);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, value.rorId]);

  const choose = (organization: RorOrganization) => {
    typed.current = false;
    onChange({ name: organization.name, rorId: organization.id });
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || items.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => (index + 1) % items.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => (index <= 0 ? items.length - 1 : index - 1));
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      choose(items[active]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    }
  };

  const showList = open && !value.rorId && state !== "idle";

  return (
    <div className="space-y-2">
      <div className="relative">
        <Input
          id={id}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          autoComplete="off"
          value={value.name}
          onChange={(event) => {
            typed.current = true;
            setOpen(true);
            onChange({ name: event.target.value, rorId: null });
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
          placeholder="Masalan: Toshkent davlat universiteti"
          className={cn(state === "loading" && "pr-9")}
        />
        {state === "loading" && (
          <Loader2 className="absolute top-1/2 right-3 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
        )}
      </div>

      {showList && (
        <div id={listId} role="listbox" className="overflow-hidden rounded-md border bg-popover text-sm">
          {state === "error" && (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              ROR vaqtincha javob bermayapti. Nomni qo‘lda yozib qoldirishingiz mumkin.
            </p>
          )}
          {state === "ready" && items.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              ROR’da topilmadi. Nomni qo‘lda yozib qoldirishingiz mumkin.
            </p>
          )}
          {items.map((item, index) => (
            <div
              key={item.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              // Blur'dan oldin ishlashi uchun: aks holda ro'yxat bosishdan oldin yopilardi.
              onMouseDown={(event) => {
                event.preventDefault();
                choose(item);
              }}
              onMouseEnter={() => setActive(index)}
              className={cn(
                "cursor-pointer border-b px-3 py-2 last:border-b-0",
                index === active && "bg-accent text-accent-foreground",
              )}
            >
              <div className="font-medium">
                {item.name}
                {item.acronym && <span className="text-muted-foreground"> · {item.acronym}</span>}
              </div>
              {item.localName && <div className="text-xs text-muted-foreground">{item.localName}</div>}
              <div className="text-xs text-muted-foreground">
                {[item.city, item.country].filter(Boolean).join(", ")}
              </div>
            </div>
          ))}
        </div>
      )}

      {value.rorId ? (
        <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <CheckCircle2 className="size-3.5 text-success" /> ROR bilan bog‘langan:{" "}
          <a
            href={`https://ror.org/${value.rorId}`}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-foreground underline-offset-4 hover:underline"
          >
            {value.rorId}
          </a>
          <button
            type="button"
            onClick={() => onChange({ name: value.name, rorId: null })}
            className="ml-1 inline-flex items-center gap-0.5 rounded px-1 hover:text-foreground"
          >
            <X className="size-3" /> uzish
          </button>
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Yozishni boshlang va ro‘yxatdan tashkilotingizni tanlang (ROR registri). Topilmasa, nomni
          qo‘lda qoldiring.
        </p>
      )}
    </div>
  );
}

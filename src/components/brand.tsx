import { BookOpen } from "lucide-react";
import { AppLink } from "@/components/app-link";
import { cn } from "@/lib/utils";

export function Brand({ className }: { className?: string }) {
  return (
    // Logotip — bosh sahifaga havola. Ilgari `#top` langari edi va robot uni
    // ichki havola deb hisoblamasdi.
    <AppLink
      to="/"
      className={cn("group flex items-center gap-2.5", className)}
      aria-label="IlmIz bosh sahifa"
    >
      <span aria-hidden="true" className="brand-mark">
        <BookOpen size={27} strokeWidth={1.3} />
      </span>
      <span className="flex flex-col leading-none">
        <strong className="brand-name">
          Ilm<span>Iz</span>
        </strong>
        <small className="text-[9px] tracking-wide text-muted-foreground">
          OCHIQ ILMIY INDEKS
        </small>
      </span>
    </AppLink>
  );
}

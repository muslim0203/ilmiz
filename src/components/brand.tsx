import { AppLink } from "@/components/app-link";
import { cn } from "@/lib/utils";

export function Brand({ className }: { className?: string }) {
  return (
    // Logotip — bosh sahifaga havola. Ilgari `#top` langari edi va robot uni
    // ichki havola deb hisoblamasdi.
    <AppLink to="/" className={cn("group flex items-center gap-2.5", className)} aria-label="IlmIz bosh sahifa">
      <span
        aria-hidden="true"
        className="flex size-8 items-end gap-[3px] rounded-md bg-primary p-1.5 transition-colors group-hover:bg-primary/90"
      >
        <i className="h-[45%] flex-1 rounded-[1px] bg-primary-foreground/60 not-italic" />
        <i className="h-[70%] flex-1 rounded-[1px] bg-primary-foreground/80 not-italic" />
        <i className="h-full flex-1 rounded-[1px] bg-primary-foreground not-italic" />
      </span>
      <span className="flex flex-col leading-none">
        <strong className="text-sm font-semibold tracking-tight">IlmIz</strong>
        <small className="text-[11px] text-muted-foreground">Ochiq ilmiy indeks</small>
      </span>
    </AppLink>
  );
}

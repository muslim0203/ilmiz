import { ArrowRight, MapPin, ShieldCheck } from "lucide-react";

import { HarvestStatus } from "@/components/harvest-status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { monogram, number } from "@/lib/format";
import type { Journal } from "@/types";

export function JournalCard({ journal, onOpen }: { journal: Journal; onOpen: () => void }) {
  return (
    <Card className="group gap-0 py-0 transition-colors hover:border-primary/40 hover:bg-accent/40">
      <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-stretch sm:gap-5 sm:p-5">
        <button
          onClick={onOpen}
          aria-label={`${journal.name} jurnalini ochish`}
          className="flex min-w-0 flex-1 cursor-pointer items-start gap-4 text-left outline-none focus-visible:rounded-md focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <span className="flex size-11 shrink-0 items-center justify-center rounded-lg border bg-muted text-sm font-semibold tracking-tight text-muted-foreground">
            {monogram(journal.shortName)}
          </span>
          <span className="min-w-0 flex-1 space-y-2">
            <span className="flex flex-wrap items-center gap-1.5">
              <Badge variant="outline" className="gap-1 font-normal">
                <ShieldCheck /> OAK
              </Badge>
              <HarvestStatus status={journal.oaiStatus} />
            </span>
            <span className="block text-[15px] font-semibold leading-snug tracking-tight text-foreground group-hover:text-primary">
              {journal.name}
            </span>
            <span className="block truncate text-sm text-muted-foreground">{journal.publisher}</span>
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3.5" />
                {journal.city}
              </span>
              <span className="font-mono">ISSN {journal.issn}</span>
            </span>
            <span className="flex flex-wrap gap-1.5 pt-0.5">
              {journal.fields.slice(0, 3).map((field) => (
                <Badge key={field} variant="secondary" className="font-normal">
                  {field}
                </Badge>
              ))}
              {journal.fields.length > 3 && (
                <Badge variant="outline" className="font-normal text-muted-foreground">
                  +{journal.fields.length - 3}
                </Badge>
              )}
            </span>
          </span>
        </button>

        <div className="flex items-center gap-5 border-t pt-4 sm:w-52 sm:shrink-0 sm:justify-end sm:border-l sm:border-t-0 sm:pl-5 sm:pt-0">
          <div className="text-right">
            <div className="text-lg font-semibold tabular-nums tracking-tight">
              {journal.articleCount ? number.format(journal.articleCount) : "—"}
            </div>
            <div className="text-xs text-muted-foreground">maqola</div>
          </div>
          <div className="text-right">
            <div className="text-lg font-semibold tabular-nums tracking-tight">
              {journal.recentArticles ? number.format(journal.recentArticles) : "—"}
            </div>
            <div className="text-xs text-muted-foreground">so‘nggi yillarda</div>
          </div>
          <Button
            variant="outline"
            size="icon"
            onClick={onOpen}
            aria-label="Batafsil"
            className="ml-auto shrink-0 sm:ml-0"
          >
            <ArrowRight />
          </Button>
        </div>
      </div>
    </Card>
  );
}

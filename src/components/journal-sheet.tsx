import { useEffect, useState } from "react";
import {
  AtSign,
  ExternalLink,
  FileText,
  Layers3,
  RefreshCw,
  Send,
  ShieldCheck,
  UsersRound,
} from "lucide-react";

import { HarvestStatus } from "@/components/harvest-status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { loadJournal, loadJournalArticles } from "@/api";
import { AppLink } from "@/components/app-link";
import { articlePath, journalYearPath } from "@/lib/slug";
import { monogram, number } from "@/lib/format";
import type { Article, Journal } from "@/types";

function SectionTitle({
  icon: Icon,
  title,
  hint,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md border bg-muted text-muted-foreground">
        <Icon className="size-4" />
      </span>
      <div>
        <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border bg-muted/40 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="truncate text-sm font-medium">{value}</div>
    </div>
  );
}

// OAK importi har bir jurnalga shu bir xil matnni yozgan — bu tavsif emas.
const OAK_PLACEHOLDER = "OAK rasmiy elektron reestridan import qilingan jurnal.";

/** Tahrirlangan tavsif jurnal saytidan yig'ilganidan ustun.
 *
 * Ilgari teskari edi: scraper yig'gan matn birinchi ko'rsatilardi va u
 * ba'zan sayt navigatsiyasi yoki hatto sahifa kodi bo'lib chiqardi. */
function aboutText(description?: string | null, summary?: string | null): string {
  const curated = description?.trim();
  if (curated && curated !== OAK_PLACEHOLDER) return curated;
  const scraped = summary?.trim();
  if (scraped) return scraped;
  return "Jurnal tavsifi hali yig‘ilmagan.";
}

// Maqola qabul qilish uchun yagona Telegram aloqa nuqtasi.
const SUBMIT_TELEGRAM_URL = "https://t.me/zarifjon0203";

export function JournalSheet({ journal, onClose }: { journal: Journal; onClose: () => void }) {
  const [detail, setDetail] = useState<Journal>(journal);
  const [detailState, setDetailState] = useState<"loading" | "ready" | "error">("loading");
  const [journalArticles, setJournalArticles] = useState<Article[]>([]);

  useEffect(() => {
    let active = true;
    setDetail(journal);
    setDetailState("loading");
    loadJournal(journal.id)
      .then((value) => {
        if (!active) return;
        setDetail(value);
        setDetailState("ready");
      })
      .catch(() => {
        if (active) setDetailState("error");
      });
    return () => {
      active = false;
    };
  }, [journal]);

  useEffect(() => {
    let active = true;
    setJournalArticles([]);
    loadJournalArticles(journal.id)
      .then((items) => {
        if (active) setJournalArticles(items);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [journal]);

  const profile = detail.profile;
  const oakRecords = detail.oakRecords ?? [];
  const areas = Array.from(new Set(oakRecords.map((item) => item.area).filter(Boolean)));
  const latestDecision = oakRecords.find((item) => item.decision || item.sourceReference);

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      {/* Panel uch qavat: sarlavha, siljiydigan tanasi va pastda qotirilgan
          tugmalar. Ilgari butun panel siljirdi va maqola yuborish tugmasiga
          yetish uchun ro'yxatning oxirigacha tushish kerak edi. */}
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-xl">
        <div className="shrink-0 space-y-3 border-b bg-muted/40 p-6">
          <span className="flex size-12 items-center justify-center rounded-lg border bg-background text-base font-semibold tracking-tight">
            {monogram(detail.shortName)}
          </span>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="outline" className="gap-1 font-normal">
              <ShieldCheck /> OAK ro‘yxatida
            </Badge>
            <HarvestStatus status={detail.oaiStatus} />
          </div>
          <SheetTitle className="text-xl leading-snug">{detail.name}</SheetTitle>
          <p className="text-sm text-muted-foreground">{detail.publisher}</p>
        </div>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-6">
          {detailState === "loading" && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <RefreshCw className="size-4 animate-spin" /> To‘liq profil yuklanmoqda...
              </div>
              <Skeleton className="h-16 w-full" />
            </div>
          )}

          {profile && (
            <div className="space-y-2 rounded-lg border p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Profil to‘liqligi</span>
                <strong className="tabular-nums">{Math.round(profile.completenessScore)}%</strong>
              </div>
              <Progress value={profile.completenessScore} />
              <p className="text-xs text-muted-foreground">
                Ochiq manbalardan {new Date(profile.fetchedAt).toLocaleDateString("uz-UZ")} kuni
                yig‘ilgan
              </p>
            </div>
          )}

          <div className="grid grid-cols-3 gap-3">
            {[
              { value: number.format(detail.articleCount), label: "Maqolalar" },
              { value: detail.issueCount, label: "Sonlar" },
              { value: detail.founded ?? "—", label: "Asos solingan" },
            ].map((item) => (
              <div key={item.label} className="rounded-lg border p-3 text-center">
                <div className="text-lg font-semibold tabular-nums tracking-tight">{item.value}</div>
                <div className="text-xs text-muted-foreground">{item.label}</div>
              </div>
            ))}
          </div>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold tracking-tight">Jurnal haqida</h3>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {aboutText(detail.description, profile?.summary)}
            </p>
            {profile?.sourceUrl && (
              <Button variant="link" size="sm" className="h-auto p-0" asChild>
                <a href={profile.sourceUrl} target="_blank" rel="noreferrer">
                  <ShieldCheck /> Manbani ko‘rish
                </a>
              </Button>
            )}
          </section>

          <div className="grid grid-cols-2 gap-2">
            <Fact label="ISSN" value={detail.issn} />
            <Fact label="e-ISSN" value={detail.eissn ?? "—"} />
            <Fact label="Shahar" value={detail.city} />
            <Fact label="Tillar" value={detail.languages.join(", ") || "—"} />
            {profile?.latestIssue && (
              <div className="col-span-2">
                <Fact label="So‘nggi son" value={profile.latestIssue} />
              </div>
            )}
            {profile?.publicationFrequency && (
              <div className="col-span-2">
                <Fact label="Davriylik" value={profile.publicationFrequency} />
              </div>
            )}
          </div>

          {!!areas.length && (
            <>
              <Separator />
              <section className="space-y-3">
                <SectionTitle
                  icon={ShieldCheck}
                  title="OAK reestri"
                  hint={`${oakRecords.length} ta rasmiy yozuv`}
                />
                <div className="flex flex-wrap gap-1.5">
                  {areas.map((area) => (
                    <Badge key={area} variant="secondary" className="font-normal">
                      {area}
                    </Badge>
                  ))}
                </div>
                {latestDecision && (
                  <div className="rounded-lg border bg-muted/40 p-3">
                    <div className="text-sm font-medium">
                      {latestDecision.decision || latestDecision.sourceReference}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {latestDecision.added
                        ? `Kiritilgan: ${latestDecision.added}`
                        : "Rasmiy reestr yozuvi"}
                    </div>
                  </div>
                )}
              </section>
            </>
          )}

          {!!profile?.indexingClaims.length && (
            <>
              <Separator />
              <section className="space-y-3">
                <SectionTitle
                  icon={Layers3}
                  title="Indekslash bazalari"
                  hint="Jurnal saytida ko‘rsatilgan da’volar"
                />
                <div className="grid gap-2 sm:grid-cols-2">
                  {profile.indexingClaims.map((claim) => (
                    <a
                      key={claim.provider}
                      href={claim.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-lg border p-3 transition-colors hover:bg-accent"
                    >
                      <div className="text-sm font-medium">{claim.provider}</div>
                      <div className="text-xs text-muted-foreground">
                        {claim.verifiedAt ? "Tekshirilgan" : "Manbada ko‘rsatilgan"}
                      </div>
                    </a>
                  ))}
                </div>
              </section>
            </>
          )}

          {!!profile?.contacts.length && (
            <>
              <Separator />
              <section className="space-y-3">
                <SectionTitle icon={AtSign} title="Aloqa ma’lumotlari" hint="Har biri manba bilan" />
                <div className="grid gap-2">
                  {profile.contacts.map((contact, index) => (
                    <a
                      key={`${contact.kind}-${contact.value}-${index}`}
                      href={contact.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center justify-between gap-3 rounded-lg border p-3 transition-colors hover:bg-accent"
                    >
                      <span className="text-xs uppercase tracking-wide text-muted-foreground">
                        {contact.kind === "email"
                          ? "Email"
                          : contact.kind === "phone"
                            ? "Telefon"
                            : "Manzil"}
                      </span>
                      <span className="min-w-0 truncate text-sm font-medium">{contact.value}</span>
                    </a>
                  ))}
                </div>
              </section>
            </>
          )}

          {!!profile?.policies.length && (
            <>
              <Separator />
              <section className="space-y-3">
                <SectionTitle
                  icon={FileText}
                  title="Siyosatlar va talablar"
                  hint="Ochiq jurnal sahifalaridan"
                />
                <div className="grid gap-2">
                  {profile.policies.map((policy) => (
                    <a
                      key={policy.type}
                      href={policy.url || policy.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-lg border p-3 transition-colors hover:bg-accent"
                    >
                      <div className="text-sm font-medium">{policy.title}</div>
                      <div className="text-xs leading-relaxed text-muted-foreground">
                        {policy.content
                          ? `${policy.content.slice(0, 150)}${policy.content.length > 150 ? "…" : ""}`
                          : "Manbani ochish"}
                      </div>
                    </a>
                  ))}
                </div>
              </section>
            </>
          )}

          {!!profile?.editorialMembers.length && (
            <>
              <Separator />
              <section className="space-y-3">
                <SectionTitle
                  icon={UsersRound}
                  title="Tahririyat a’zolari"
                  hint={`${profile.editorialMembers.length} ta yig‘ilgan yozuv`}
                />
                <div className="grid gap-2">
                  {profile.editorialMembers.map((member, index) => (
                    <a
                      key={`${member.name}-${index}`}
                      href={member.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-lg border p-3 transition-colors hover:bg-accent"
                    >
                      <div className="text-sm font-medium">{member.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {member.role || "Tahrir hay’ati"}
                        {member.affiliation ? ` · ${member.affiliation}` : ""}
                      </div>
                    </a>
                  ))}
                </div>
              </section>
            </>
          )}

          <div className="flex items-center gap-3 rounded-lg border bg-muted/40 p-4">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-background text-muted-foreground">
              <RefreshCw className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-xs text-muted-foreground">Oxirgi yangilanish</div>
              <div className="truncate text-sm font-medium">
                {detail.oaiLastSync ?? "Hozircha yangilanmagan"}
              </div>
            </div>
            <HarvestStatus status={detail.oaiStatus} />
          </div>

          <Separator />

          <section className="space-y-3">
            <div className="flex items-end justify-between">
              <div>
                <div className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
                  So‘nggi nashrlar
                </div>
                <h3 className="text-sm font-semibold tracking-tight">Maqolalar</h3>
              </div>
              <span className="text-xs text-muted-foreground">{journalArticles.length} namuna</span>
            </div>
            {!!detail.archiveYears?.length && (
              <nav aria-label="Yillar bo‘yicha arxiv" className="flex flex-wrap gap-2">
                {detail.archiveYears.map(year => (
                  <AppLink key={year} to={journalYearPath(detail.id, year)} className="rounded-md border px-3 py-1 text-sm hover:bg-accent">
                    {year}-yil
                  </AppLink>
                ))}
              </nav>
            )}
            {journalArticles.length ? (
              <div className="grid gap-2">
                {journalArticles.map((article) => (
                  <div
                    key={article.id}
                    className="flex items-start gap-2.5 rounded-lg border p-3 transition-colors hover:bg-accent"
                  >
                    <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0">
                      <AppLink to={articlePath(article.id, article.title)} className="text-sm font-medium leading-snug hover:underline">{article.title}</AppLink>
                      <div className="text-xs text-muted-foreground">
                        {article.year} · {article.issue}-son
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
                Bu jurnalning maqolalari hali yig‘ilmagan.
              </p>
            )}
          </section>

          {detailState === "ready" && !profile && (
            <p className="text-xs text-muted-foreground">
              Bu jurnal uchun to‘liq profil hali yig‘ilmagan. Asosiy OAK ma’lumotlari
              ko‘rsatilmoqda.
            </p>
          )}
          {detailState === "error" && (
            <p className="text-xs text-muted-foreground">
              To‘liq profil API’dan yuklanmadi. Asosiy katalog ma’lumotlari saqlandi.
            </p>
          )}

        </div>

        {/* Qotirilgan pastki qavat — qaysi joyga siljitilgan bo'lsa ham
            ko'rinib turadi. Shuning uchun ixcham: yordamchi matn tugma
            yorlig'ini takrorlardi, olib tashlandi. */}
        <div className="shrink-0 border-t bg-background p-4">
          <div className="flex gap-2">
            <Button className="min-w-0 flex-1" size="lg" asChild>
              <a href={SUBMIT_TELEGRAM_URL} target="_blank" rel="noreferrer">
                <Send />
                {/* Tor ekranda to'liq yorliq kesilib "…yu..." bo'lib qolardi. */}
                <span className="hidden truncate sm:inline">
                  Telegram orqali maqola yuborish
                </span>
                <span className="truncate sm:hidden">Maqola yuborish</span>
              </a>
            </Button>
            {detail.website && detail.website !== "#" && (
              <Button variant="outline" size="lg" className="shrink-0" asChild>
                <a href={detail.website} target="_blank" rel="noreferrer">
                  Sayt <ExternalLink />
                </a>
              </Button>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

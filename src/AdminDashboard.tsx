import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Database,
  ExternalLink,
  FileSearch,
  ListRestart,
  PencilLine,
  RefreshCw,
  ScanSearch,
  ServerCog,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ModeToggle } from "@/components/mode-toggle";
import JournalEditor from "@/JournalEditor";
import {
  AdminAuthError,
  getAdminToken,
  loadAdminData,
  queueAuditJobs,
  queueProfileJobs,
  setAdminToken,
  type AdminDashboardData,
  type AuditJob,
  type ImportRun,
  type ProfileJob,
} from "@/adminApi";
import { cn } from "@/lib/utils";

const formatNumber = new Intl.NumberFormat("uz-UZ");

const SHELL = "mx-auto w-full max-w-[1280px] px-4 sm:px-6";

const statusLabel: Record<string, string> = {
  queued: "Navbatda",
  running: "Ishlayapti",
  succeeded: "Topildi",
  failed: "Topilmadi",
  partial: "Qisman",
  healthy: "Sog‘lom",
  warning: "Ogohlantirish",
};

/** URL hosti; `job.website` scraper'dan kelgan matn bo‘lgani uchun
 *  `new URL` yaroqsiz qiymatda throw qilib butun panelni yiqitardi. */
function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function Status({ value }: { value: string }) {
  const Icon =
    value === "succeeded" || value === "healthy"
      ? CheckCircle2
      : value === "failed"
        ? XCircle
        : value === "running"
          ? Activity
          : value === "partial"
            ? AlertTriangle
            : Clock3;
  const variant =
    value === "succeeded" || value === "healthy"
      ? "success"
      : value === "failed"
        ? "destructive"
        : value === "partial" || value === "warning"
          ? "warning"
          : "secondary";

  return (
    <Badge variant={variant} className="gap-1 font-normal">
      <Icon />
      {statusLabel[value] ?? value}
    </Badge>
  );
}

function QueueStat({
  tone,
  value,
  label,
}: {
  tone: "pending" | "passed" | "partial" | "failed";
  value: number;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg border p-3">
      <span
        className={cn(
          "size-2 shrink-0 rounded-full",
          tone === "pending" && "bg-muted-foreground",
          tone === "passed" && "bg-success",
          tone === "partial" && "bg-warning",
          tone === "failed" && "bg-destructive",
        )}
      />
      <div className="min-w-0">
        <div className="text-lg font-semibold tabular-nums leading-none">{value}</div>
        <div className="mt-1 truncate text-xs text-muted-foreground">{label}</div>
      </div>
    </div>
  );
}

function QueueBar({ segments }: { segments: Array<{ tone: string; percent: number }> }) {
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
      {segments.map((segment, index) => (
        <span
          key={index}
          className={cn(
            "h-full transition-all",
            segment.tone === "passed" && "bg-success",
            segment.tone === "partial" && "bg-warning",
            segment.tone === "failed" && "bg-destructive",
          )}
          style={{ width: `${segment.percent}%` }}
        />
      ))}
    </div>
  );
}

function WorkerNote({ title, command }: { title: string; command: string }) {
  return (
    <div className="flex gap-3 rounded-lg border bg-muted/40 p-3">
      <Activity className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 space-y-1">
        <div className="text-xs font-medium">{title}</div>
        <code className="block overflow-x-auto whitespace-pre rounded-md border bg-background px-2 py-1.5 font-mono text-xs text-muted-foreground">
          {command}
        </code>
      </div>
    </div>
  );
}

export default function AdminDashboard({ onClose }: { onClose: () => void }) {
  const [dashboard, setDashboard] = useState<AdminDashboardData | null>(null);
  const [jobs, setJobs] = useState<AuditJob[]>([]);
  const [profileJobs, setProfileJobs] = useState<ProfileJob[]>([]);
  const [runs, setRuns] = useState<ImportRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<AdminAuthError | null>(null);
  const [tokenInput, setTokenInput] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await loadAdminData();
      setDashboard(data.dashboard);
      setJobs(data.jobs);
      setProfileJobs(data.profileJobs);
      setRuns(data.runs);
      setAuthError(null);
    } catch (caught) {
      if (caught instanceof AdminAuthError) {
        setAuthError(caught);
      } else {
        setError(caught instanceof Error ? caught.message : "Admin ma’lumotlari olinmadi");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const queueTotal = useMemo(
    () => Object.values(dashboard?.auditQueue ?? {}).reduce((sum, value) => sum + value, 0),
    [dashboard],
  );
  const queueSucceeded = dashboard?.auditQueue.succeeded ?? 0;
  const queueFailed = dashboard?.auditQueue.failed ?? 0;
  const queuePending = (dashboard?.auditQueue.queued ?? 0) + (dashboard?.auditQueue.running ?? 0);
  const profileTotal = useMemo(
    () => Object.values(dashboard?.profileQueue ?? {}).reduce((sum, value) => sum + value, 0),
    [dashboard],
  );
  const profileSucceeded = dashboard?.profileQueue.succeeded ?? 0;
  const profilePartial = dashboard?.profileQueue.partial ?? 0;
  const profileFailed = dashboard?.profileQueue.failed ?? 0;
  const profilePending =
    (dashboard?.profileQueue.queued ?? 0) + (dashboard?.profileQueue.running ?? 0);

  const handleQueue = async () => {
    setActionLoading(true);
    setMessage(null);
    try {
      const result = await queueAuditJobs();
      setMessage(
        result.queued
          ? `${result.queued} ta yangi jurnal navbatga qo‘shildi.`
          : "Barcha mos jurnallar allaqachon navbatda.",
      );
      await refresh();
    } catch (caught) {
      if (caught instanceof AdminAuthError) setAuthError(caught);
      else setError(caught instanceof Error ? caught.message : "Navbat yangilanmadi");
    } finally {
      setActionLoading(false);
    }
  };

  const handleProfileQueue = async () => {
    setActionLoading(true);
    setMessage(null);
    try {
      const result = await queueProfileJobs();
      setMessage(
        result.queued
          ? `${result.queued} ta OAK jurnali profil navbatiga qo‘shildi.`
          : "Barcha rasmiy saytli jurnallar profil navbatida.",
      );
      await refresh();
    } catch (caught) {
      if (caught instanceof AdminAuthError) setAuthError(caught);
      else setError(caught instanceof Error ? caught.message : "Profil navbati yangilanmadi");
    } finally {
      setActionLoading(false);
    }
  };

  const submitToken = (event: React.FormEvent) => {
    event.preventDefault();
    setAdminToken(tokenInput.trim());
    setTokenInput("");
    void refresh();
  };

  const header = (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-md">
      <div className={cn(SHELL, "flex h-14 items-center gap-4")}>
        <Button variant="ghost" size="sm" onClick={onClose}>
          <ArrowLeft /> Katalogga qaytish
        </Button>
        <Separator orientation="vertical" className="hidden h-5 sm:block" />
        <div className="hidden flex-col leading-none sm:flex">
          <span className="text-[11px] uppercase tracking-widest text-muted-foreground">IlmIz</span>
          <strong className="text-sm font-semibold tracking-tight">
            {authError ? "Admin kirish" : "Ma’lumotlar boshqaruvi"}
          </strong>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <ModeToggle />
          {!authError && (
            <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading}>
              <RefreshCw className={cn(loading && "animate-spin")} /> Yangilash
            </Button>
          )}
        </div>
      </div>
    </header>
  );

  if (authError) {
    return (
      <div className="flex min-h-screen flex-col bg-muted/30">
        {header}
        <main className="flex flex-1 items-center justify-center p-6">
          <Card className="w-full max-w-sm">
            <CardHeader className="items-center text-center">
              <span className="mx-auto flex size-11 items-center justify-center rounded-full border bg-muted text-muted-foreground">
                <ShieldCheck className="size-5" />
              </span>
              <CardTitle className="mt-3">Admin tokeni kerak</CardTitle>
              <CardDescription>{authError.message}</CardDescription>
            </CardHeader>
            <CardContent>
              {authError.configured ? (
                <form className="space-y-2" onSubmit={submitToken}>
                  <Input
                    type="password"
                    value={tokenInput}
                    onChange={(event) => setTokenInput(event.target.value)}
                    placeholder="Admin tokeni"
                    autoFocus
                  />
                  <Button type="submit" className="w-full" disabled={!tokenInput.trim()}>
                    Kirish
                  </Button>
                  {getAdminToken() && (
                    <Button
                      type="button"
                      variant="ghost"
                      className="w-full"
                      onClick={() => {
                        setAdminToken("");
                        void refresh();
                      }}
                    >
                      Saqlangan tokenni o‘chirish
                    </Button>
                  )}
                </form>
              ) : (
                <code className="block rounded-md border bg-muted px-3 py-2 text-center font-mono text-xs">
                  ILMIZ_ADMIN_TOKEN=&lt;token&gt;
                </code>
              )}
            </CardContent>
          </Card>
        </main>
      </div>
    );
  }

  const metrics = [
    { icon: Database, label: "OAK nashrlari", value: dashboard?.registryPublications ?? 0 },
    { icon: ShieldCheck, label: "Milliy jurnallar", value: dashboard?.activeJournals ?? 0 },
    { icon: ScanSearch, label: "Boy profillar", value: dashboard?.profiles.collected ?? 0 },
    { icon: ServerCog, label: "Sog‘lom OAI", value: dashboard?.sources.healthy ?? 0 },
    { icon: FileSearch, label: "Maqolalar", value: dashboard?.articles ?? 0 },
  ];

  return (
    <div className="flex min-h-screen flex-col bg-muted/30">
      {header}

      <main className={cn(SHELL, "flex-1 space-y-6 py-8")}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1.5">
            <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
              Operatsion panel
            </span>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              OAK katalogi va OAI monitoringi
            </h1>
            <p className="text-sm text-muted-foreground">
              Import provenance, endpoint audit navbati va harvester salomatligi.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => void handleQueue()} disabled={actionLoading}>
              <ListRestart /> OAI audit navbati
            </Button>
            <Button onClick={() => void handleProfileQueue()} disabled={actionLoading}>
              <ScanSearch /> Profil navbatini to‘ldirish
            </Button>
          </div>
        </div>

        {message && (
          <Alert variant="success">
            <CheckCircle2 />
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertTriangle />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {metrics.map((metric) => (
            <Card key={metric.label} className="gap-0 py-0">
              <CardContent className="flex items-center gap-3 p-4">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted text-muted-foreground">
                  <metric.icon className="size-4" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-xs text-muted-foreground">{metric.label}</div>
                  <div className="text-xl font-semibold tabular-nums tracking-tight">
                    {formatNumber.format(metric.value)}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </section>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PencilLine className="size-4" /> Jurnal ma’lumotlarini tahrirlash
            </CardTitle>
            <CardDescription>
              OAK reestri va tadqiq.uz ham xato qiladi. Tekshirilgan tuzatishni shu yerdan
              kiritasiz — importlar unga tegmaydi.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <JournalEditor />
          </CardContent>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
                Audit queue
              </span>
              <CardTitle>Endpoint aniqlash holati</CardTitle>
              <CardDescription>{formatNumber.format(queueTotal)} ish</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-3 gap-2">
                <QueueStat tone="pending" value={queuePending} label="Navbatda" />
                <QueueStat tone="passed" value={queueSucceeded} label="Topildi" />
                <QueueStat tone="failed" value={queueFailed} label="Topilmadi" />
              </div>
              <QueueBar
                segments={[
                  { tone: "passed", percent: queueTotal ? (queueSucceeded / queueTotal) * 100 : 0 },
                  { tone: "failed", percent: queueTotal ? (queueFailed / queueTotal) * 100 : 0 },
                ]}
              />
              <WorkerNote
                title="Worker CLI orqali boshqariladi"
                command=".venv\Scripts\python.exe backend\manage.py process-audits --limit 10"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
                OAK import
              </span>
              <CardTitle>So‘nggi rasmiy sinxronizatsiya</CardTitle>
              {dashboard?.latestImport && (
                <CardDescription>
                  <Status value={dashboard.latestImport.status} />
                </CardDescription>
              )}
            </CardHeader>
            <CardContent className="space-y-4">
              {dashboard?.latestImport ? (
                <>
                  <div className="flex items-baseline gap-2">
                    <strong className="text-3xl font-semibold tabular-nums tracking-tight">
                      {formatNumber.format(dashboard.latestImport.recordsSeen)}
                    </strong>
                    <span className="text-sm text-muted-foreground">rasmiy qaror/fan yozuvi</span>
                  </div>
                  <dl className="grid gap-2 sm:grid-cols-3">
                    {[
                      {
                        term: "Yangi registry yozuvi",
                        value: dashboard.latestImport.registryCreated,
                      },
                      { term: "Yangi jurnal", value: dashboard.latestImport.journalsCreated },
                      { term: "Yangilangan jurnal", value: dashboard.latestImport.journalsUpdated },
                    ].map((fact) => (
                      <div key={fact.term} className="rounded-lg border p-3">
                        <dt className="text-xs text-muted-foreground">{fact.term}</dt>
                        <dd className="text-base font-semibold tabular-nums">{fact.value}</dd>
                      </div>
                    ))}
                  </dl>
                  <Button variant="link" size="sm" className="h-auto p-0" asChild>
                    <a href={dashboard.latestImport.sourceUrl} target="_blank" rel="noreferrer">
                      Rasmiy manbani ochish <ExternalLink />
                    </a>
                  </Button>
                </>
              ) : (
                <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                  Import hali bajarilmagan.
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
              Profile queue
            </span>
            <CardTitle>OAK jurnallarining boy profil yig‘ilishi</CardTitle>
            <CardDescription>
              {formatNumber.format(profileTotal)} ish · o‘rtacha{" "}
              {dashboard?.profiles.averageCompleteness ?? 0}%
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <QueueStat tone="pending" value={profilePending} label="Navbatda" />
              <QueueStat tone="passed" value={profileSucceeded} label="To‘liq" />
              <QueueStat tone="partial" value={profilePartial} label="Qisman" />
              <QueueStat tone="failed" value={profileFailed} label="Xato" />
            </div>
            <QueueBar
              segments={[
                {
                  tone: "passed",
                  percent: profileTotal ? (profileSucceeded / profileTotal) * 100 : 0,
                },
                {
                  tone: "partial",
                  percent: profileTotal ? (profilePartial / profileTotal) * 100 : 0,
                },
                { tone: "failed", percent: profileTotal ? (profileFailed / profileTotal) * 100 : 0 },
              ]}
            />
            <WorkerNote
              title="OAK rasmiy sayt havolalari asosida"
              command=".venv\Scripts\python.exe backend\manage.py process-profiles --limit 25 --workers 3"
            />
          </CardContent>
        </Card>

        <Card className="gap-0 pb-0">
          <CardHeader className="pb-4">
            <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
              So‘nggi profillar
            </span>
            <CardTitle>Sayt metama’lumotlarini yig‘ish natijalari</CardTitle>
            <CardDescription>{profileJobs.length} ta oxirgi ish</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Jurnal</TableHead>
                  <TableHead>Rasmiy sayt</TableHead>
                  <TableHead>Urinish</TableHead>
                  <TableHead>Natija</TableHead>
                  <TableHead className="pr-6">To‘liqlik</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {profileJobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="max-w-xs truncate pl-6 font-medium">
                      {job.journal}
                    </TableCell>
                    <TableCell>
                      <a
                        href={job.website}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                      >
                        {hostOf(job.website)}
                        <ExternalLink className="size-3" />
                      </a>
                    </TableCell>
                    <TableCell className="tabular-nums">{job.attempts}</TableCell>
                    <TableCell>
                      <Status value={job.status} />
                    </TableCell>
                    <TableCell className="pr-6">
                      {job.completenessScore != null ? (
                        <strong className="tabular-nums">
                          {Math.round(job.completenessScore)}%
                        </strong>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {!profileJobs.length && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                      Profil ishlari yo‘q.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="gap-0 pb-0">
          <CardHeader className="pb-4">
            <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
              So‘nggi tekshiruvlar
            </span>
            <CardTitle>Jurnal endpointlari</CardTitle>
            <CardDescription>{jobs.length} ta oxirgi ish</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Jurnal</TableHead>
                  <TableHead>Sayt</TableHead>
                  <TableHead>Urinish</TableHead>
                  <TableHead>Natija</TableHead>
                  <TableHead className="pr-6">OAI endpoint</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="max-w-xs truncate pl-6 font-medium">
                      {job.journal}
                    </TableCell>
                    <TableCell>
                      <a
                        href={job.website}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                      >
                        {hostOf(job.website)}
                        <ExternalLink className="size-3" />
                      </a>
                    </TableCell>
                    <TableCell className="tabular-nums">{job.attempts}</TableCell>
                    <TableCell>
                      <Status value={job.status} />
                    </TableCell>
                    <TableCell className="pr-6">
                      {job.discoveredBaseUrl ? (
                        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                          {job.discoveredBaseUrl}
                        </code>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {!jobs.length && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                      Audit ishlari yo‘q.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {runs.length > 1 && (
          <p className="text-xs text-muted-foreground">
            Bazadagi import runlari: {runs.length}. Har bir run source hash va vaqt belgisi bilan
            saqlanadi.
          </p>
        )}
      </main>
    </div>
  );
}

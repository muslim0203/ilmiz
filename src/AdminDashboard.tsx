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
  ScanSearch,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { AdminAuthError, getAdminToken, loadAdminData, queueAuditJobs, queueProfileJobs, setAdminToken, type AdminDashboardData, type AuditJob, type ImportRun, type ProfileJob } from "./adminApi";

const formatNumber = new Intl.NumberFormat("uz-UZ");

const statusLabel: Record<string, string> = {
  queued: "Navbatda",
  running: "Ishlayapti",
  succeeded: "Topildi",
  failed: "Topilmadi",
  partial: "Qisman",
  healthy: "Sog‘lom",
  warning: "Ogohlantirish",
};

function Status({ value }: { value: string }) {
  const Icon = value === "succeeded" || value === "healthy" ? CheckCircle2 : value === "failed" ? XCircle : value === "running" ? Activity : value === "partial" ? AlertTriangle : Clock3;
  return <span className={`admin-status admin-${value}`}><Icon size={13} />{statusLabel[value] ?? value}</span>;
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

  useEffect(() => { void refresh(); }, [refresh]);

  const queueTotal = useMemo(() => Object.values(dashboard?.auditQueue ?? {}).reduce((sum, value) => sum + value, 0), [dashboard]);
  const queueSucceeded = dashboard?.auditQueue.succeeded ?? 0;
  const queueFailed = dashboard?.auditQueue.failed ?? 0;
  const queuePending = (dashboard?.auditQueue.queued ?? 0) + (dashboard?.auditQueue.running ?? 0);
  const profileTotal = useMemo(() => Object.values(dashboard?.profileQueue ?? {}).reduce((sum, value) => sum + value, 0), [dashboard]);
  const profileSucceeded = dashboard?.profileQueue.succeeded ?? 0;
  const profilePartial = dashboard?.profileQueue.partial ?? 0;
  const profileFailed = dashboard?.profileQueue.failed ?? 0;
  const profilePending = (dashboard?.profileQueue.queued ?? 0) + (dashboard?.profileQueue.running ?? 0);

  const handleQueue = async () => {
    setActionLoading(true);
    setMessage(null);
    try {
      const result = await queueAuditJobs();
      setMessage(result.queued ? `${result.queued} ta yangi jurnal navbatga qo‘shildi.` : "Barcha mos jurnallar allaqachon navbatda.");
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
      setMessage(result.queued ? `${result.queued} ta OAK jurnali profil navbatiga qo‘shildi.` : "Barcha rasmiy saytli jurnallar profil navbatida.");
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

  if (authError) {
    return (
      <div className="admin-shell">
        <header className="admin-header">
          <button className="admin-back" onClick={onClose}><ArrowLeft size={18} /> Katalogga qaytish</button>
          <div><span>IlmIz</span><strong>Admin kirish</strong></div>
          <span />
        </header>
        <form className="admin-auth" onSubmit={submitToken}>
          <ShieldCheck size={30} />
          <h2>Admin tokeni kerak</h2>
          <p>{authError.message}</p>
          {authError.configured ? (
            <>
              <input
                type="password"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
                placeholder="Admin tokeni"
                autoFocus
              />
              <button type="submit" disabled={!tokenInput.trim()}>Kirish</button>
              {getAdminToken() && (
                <button type="button" className="admin-auth-clear" onClick={() => { setAdminToken(""); void refresh(); }}>
                  Saqlangan tokenni o‘chirish
                </button>
              )}
            </>
          ) : (
            <code>ILMIZ_ADMIN_TOKEN=&lt;token&gt;</code>
          )}
        </form>
      </div>
    );
  }

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <button className="admin-back" onClick={onClose}><ArrowLeft size={18} /> Katalogga qaytish</button>
        <div><span>IlmIz</span><strong>Ma’lumotlar boshqaruvi</strong></div>
        <button className="admin-refresh" onClick={() => void refresh()} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} /> Yangilash</button>
      </header>

      <main className="admin-main">
        <div className="admin-title">
          <div><span className="eyebrow">OPERATSION PANEL</span><h1>OAK katalogi va OAI monitoringi</h1><p>Import provenance, endpoint audit navbati va harvester salomatligi.</p></div>
          <div className="admin-title-actions">
            <button className="admin-secondary" onClick={() => void handleQueue()} disabled={actionLoading}><ListRestart size={17} /> OAI audit navbati</button>
            <button className="admin-primary" onClick={() => void handleProfileQueue()} disabled={actionLoading}><ScanSearch size={17} /> Profil navbatini to‘ldirish</button>
          </div>
        </div>

        {message && <div className="admin-message success"><CheckCircle2 size={17} />{message}</div>}
        {error && <div className="admin-message error"><AlertTriangle size={17} />{error}</div>}

        <section className="admin-metrics">
          <article><Database size={20} /><span><small>OAK nashrlari</small><strong>{formatNumber.format(dashboard?.registryPublications ?? 0)}</strong></span></article>
          <article><ShieldCheck size={20} /><span><small>Milliy jurnallar</small><strong>{formatNumber.format(dashboard?.activeJournals ?? 0)}</strong></span></article>
          <article><ScanSearch size={20} /><span><small>Boy profillar</small><strong>{formatNumber.format(dashboard?.profiles.collected ?? 0)}</strong></span></article>
          <article><ServerCog size={20} /><span><small>Sog‘lom OAI</small><strong>{formatNumber.format(dashboard?.sources.healthy ?? 0)}</strong></span></article>
          <article><FileSearch size={20} /><span><small>Maqolalar</small><strong>{formatNumber.format(dashboard?.articles ?? 0)}</strong></span></article>
        </section>

        <div className="admin-grid">
          <section className="admin-panel queue-panel">
            <div className="admin-panel-head"><div><span>AUDIT QUEUE</span><h2>Endpoint aniqlash holati</h2></div><strong>{formatNumber.format(queueTotal)} ish</strong></div>
            <div className="queue-numbers">
              <div><span className="queue-dot pending" /><strong>{queuePending}</strong><small>Navbatda</small></div>
              <div><span className="queue-dot passed" /><strong>{queueSucceeded}</strong><small>Topildi</small></div>
              <div><span className="queue-dot failed" /><strong>{queueFailed}</strong><small>Topilmadi</small></div>
            </div>
            <div className="queue-bar" aria-label="Audit progress">
              <span className="passed" style={{ width: `${queueTotal ? queueSucceeded / queueTotal * 100 : 0}%` }} />
              <span className="failed" style={{ width: `${queueTotal ? queueFailed / queueTotal * 100 : 0}%` }} />
            </div>
            <div className="worker-note"><Activity size={17} /><p><strong>Worker CLI orqali boshqariladi</strong><code>.venv\Scripts\python.exe backend\manage.py process-audits --limit 10</code></p></div>
          </section>

          <section className="admin-panel import-panel">
            <div className="admin-panel-head"><div><span>OAK IMPORT</span><h2>So‘nggi rasmiy sinxronizatsiya</h2></div>{dashboard?.latestImport && <Status value={dashboard.latestImport.status} />}</div>
            {dashboard?.latestImport ? (
              <>
                <div className="import-main-number"><strong>{formatNumber.format(dashboard.latestImport.recordsSeen)}</strong><span>rasmiy qaror/fan yozuvi</span></div>
                <dl className="import-facts">
                  <div><dt>Yangi registry yozuvi</dt><dd>{dashboard.latestImport.registryCreated}</dd></div>
                  <div><dt>Yangi jurnal</dt><dd>{dashboard.latestImport.journalsCreated}</dd></div>
                  <div><dt>Yangilangan jurnal</dt><dd>{dashboard.latestImport.journalsUpdated}</dd></div>
                </dl>
                <a href={dashboard.latestImport.sourceUrl} target="_blank" rel="noreferrer">Rasmiy manbani ochish <ExternalLink size={14} /></a>
              </>
            ) : <p className="admin-empty">Import hali bajarilmagan.</p>}
          </section>
        </div>

        <section className="admin-panel profile-queue-panel">
          <div className="admin-panel-head"><div><span>PROFILE QUEUE</span><h2>OAK jurnallarining boy profil yig‘ilishi</h2></div><strong>{formatNumber.format(profileTotal)} ish · o‘rtacha {dashboard?.profiles.averageCompleteness ?? 0}%</strong></div>
          <div className="profile-queue-summary">
            <div><span className="queue-dot pending" /><strong>{profilePending}</strong><small>Navbatda</small></div>
            <div><span className="queue-dot passed" /><strong>{profileSucceeded}</strong><small>To‘liq</small></div>
            <div><span className="queue-dot partial" /><strong>{profilePartial}</strong><small>Qisman</small></div>
            <div><span className="queue-dot failed" /><strong>{profileFailed}</strong><small>Xato</small></div>
          </div>
          <div className="queue-bar" aria-label="Profil yig‘ish progressi">
            <span className="passed" style={{ width: `${profileTotal ? profileSucceeded / profileTotal * 100 : 0}%` }} />
            <span className="partial" style={{ width: `${profileTotal ? profilePartial / profileTotal * 100 : 0}%` }} />
            <span className="failed" style={{ width: `${profileTotal ? profileFailed / profileTotal * 100 : 0}%` }} />
          </div>
          <div className="worker-note"><Activity size={17} /><p><strong>OAK rasmiy sayt havolalari asosida</strong><code>.venv\Scripts\python.exe backend\manage.py process-profiles --limit 25 --workers 3</code></p></div>
        </section>

        <section className="admin-panel jobs-panel">
          <div className="admin-panel-head"><div><span>SO‘NGGI PROFILLAR</span><h2>Sayt metama’lumotlarini yig‘ish natijalari</h2></div><small>{profileJobs.length} ta oxirgi ish</small></div>
          <div className="admin-table-wrap">
            <table>
              <thead><tr><th>Jurnal</th><th>Rasmiy sayt</th><th>Urinish</th><th>Natija</th><th>To‘liqlik</th></tr></thead>
              <tbody>
                {profileJobs.map((job) => (
                  <tr key={job.id}>
                    <td><strong>{job.journal}</strong></td>
                    <td><a href={job.website} target="_blank" rel="noreferrer">{new URL(job.website).hostname}<ExternalLink size={11} /></a></td>
                    <td>{job.attempts}</td>
                    <td><Status value={job.status} /></td>
                    <td>{job.completenessScore != null ? <strong>{Math.round(job.completenessScore)}%</strong> : <span className="muted-cell">—</span>}</td>
                  </tr>
                ))}
                {!profileJobs.length && <tr><td colSpan={5} className="admin-empty">Profil ishlari yo‘q.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="admin-panel jobs-panel">
          <div className="admin-panel-head"><div><span>SO‘NGGI TEKSHIRUVLAR</span><h2>Jurnal endpointlari</h2></div><small>{jobs.length} ta oxirgi ish</small></div>
          <div className="admin-table-wrap">
            <table>
              <thead><tr><th>Jurnal</th><th>Sayt</th><th>Urinish</th><th>Natija</th><th>OAI endpoint</th></tr></thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td><strong>{job.journal}</strong></td>
                    <td><a href={job.website} target="_blank" rel="noreferrer">{new URL(job.website).hostname}<ExternalLink size={11} /></a></td>
                    <td>{job.attempts}</td>
                    <td><Status value={job.status} /></td>
                    <td>{job.discoveredBaseUrl ? <code>{job.discoveredBaseUrl}</code> : <span className="muted-cell">—</span>}</td>
                  </tr>
                ))}
                {!jobs.length && <tr><td colSpan={5} className="admin-empty">Audit ishlari yo‘q.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {runs.length > 1 && <p className="admin-footnote">Bazadagi import runlari: {runs.length}. Har bir run source hash va vaqt belgisi bilan saqlanadi.</p>}
      </main>
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  AtSign,
  ArrowRight,
  BookOpen,
  CalendarDays,
  Check,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  ExternalLink,
  FileText,
  Globe2,
  Layers3,
  Link2,
  MapPin,
  Menu,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  UsersRound,
  WifiOff,
  X,
} from "lucide-react";
import { PAGE_SIZE, loadCatalog, loadJournal, loadJournalArticles, loadJournalIndex, searchArticles, searchJournals, type Facets, type PlatformStats } from "./api";
import FieldPicker from "./FieldPicker";
import AdminDashboard from "./AdminDashboard";
import AccountPanel from "./AccountPanel";
import { loadCurrentUser, type AuthUser } from "./authApi";
import { articles as demoArticles, journals as demoJournals } from "./data";
import type { Article, Journal } from "./types";

type View = "journals" | "articles";

const statusConfig = {
  healthy: { label: "Yangilanib turadi", icon: CheckCircle2, className: "status-good" },
  warning: { label: "Tekshirilmoqda", icon: AlertTriangle, className: "status-warn" },
  missing: { label: "Qo‘lda kiritilgan", icon: WifiOff, className: "status-muted" },
};

const number = new Intl.NumberFormat("uz-UZ");

// `toLocaleDateString("uz-UZ", { month: "short" })` brauzerda "M08" beradi,
// shuning uchun oy nomlari qo'lda.
const MONTHS = ["yan", "fev", "mar", "apr", "may", "iyun", "iyul", "avg", "sen", "okt", "noy", "dek"];

function shortDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${date.getDate()}-${MONTHS[date.getMonth()]}`;
}

function Brand() {
  return (
    <a className="brand" href="#top" aria-label="IlmIz bosh sahifa">
      <span className="brand-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="brand-copy">
        <strong>IlmIz</strong>
        <small>Ochiq ilmiy indeks</small>
      </span>
    </a>
  );
}

function HarvestStatus({ status }: { status: Journal["oaiStatus"] }) {
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <span className={`status-pill ${config.className}`}>
      <Icon size={13} strokeWidth={2.4} />
      {config.label}
    </span>
  );
}

function JournalCard({ journal, onOpen }: { journal: Journal; onOpen: () => void }) {
  return (
    <article className="journal-card">
      <button className="journal-main" onClick={onOpen} aria-label={`${journal.name} jurnalini ochish`}>
        <span className="journal-monogram">{journal.shortName.slice(0, 2).toUpperCase()}</span>
        <span className="journal-copy">
          <span className="journal-topline">
            <span className="oak-badge">
              <ShieldCheck size={13} /> OAK
            </span>
            <HarvestStatus status={journal.oaiStatus} />
          </span>
          <strong>{journal.name}</strong>
          <span className="publisher">{journal.publisher}</span>
          <span className="journal-meta">
            <span><MapPin size={14} />{journal.city}</span>
            <span>ISSN {journal.issn}</span>
          </span>
          <span className="tag-row">
            {journal.fields.slice(0, 3).map((field) => (
              <span className="tag" key={field}>{field}</span>
            ))}
            {journal.fields.length > 3 && <span className="tag tag-more">+{journal.fields.length - 3}</span>}
          </span>
        </span>
      </button>
      <div className="journal-side">
        <div>
          <strong>{journal.articleCount ? number.format(journal.articleCount) : "—"}</strong>
          <span>maqola</span>
        </div>
        <div>
          <strong>{journal.issueCount || "—"}</strong>
          <span>son</span>
        </div>
        <button className="circle-button" onClick={onOpen} aria-label="Batafsil">
          <ArrowRight size={18} />
        </button>
      </div>
    </article>
  );
}

function ArticleCard({ article, journal }: { article: Article; journal: Journal }) {
  const [open, setOpen] = useState(false);
  const [citationsOpen, setCitationsOpen] = useState(false);
  const published = article.publicationDate || (article.year ? String(article.year) : "Sana ko‘rsatilmagan");

  const copyCitation = (value: string) => {
    void navigator.clipboard?.writeText(value);
  };

  return (
    <article className={`article-card ${open ? "article-open" : ""}`}>
      <div className="article-source">
        <span className="source-mark">{journal.shortName.slice(0, 2).toUpperCase()}</span>
        <div>
          <strong>{journal.name}</strong>
          <span>{published}{article.volume !== "—" ? ` · ${article.volume}-jild` : ""}{article.issue !== "—" ? ` · ${article.issue}-son` : ""}{article.pages !== "—" ? ` · ${article.pages}-bet` : ""}</span>
        </div>
        {article.isDemo && <span className="demo-badge">DEMO</span>}
      </div>
      <button className="article-title" onClick={() => setOpen((value) => !value)}>
        {article.title}
      </button>
      <p className="authors"><UsersRound size={15} /> {article.authors.join(", ")}</p>
      <p className={`abstract ${open ? "expanded" : ""}`}>{article.abstract}</p>
      <div className="article-footer">
        <div className="tag-row">
          {article.fields.map((field) => <span className="tag" key={field}>{field}</span>)}
          <span className="tag">{article.language}</span>
        </div>
        <div className="article-actions">
          {article.landingUrl && <a href={article.landingUrl} target="_blank" rel="noreferrer"><ExternalLink size={16} /> Maqola sahifasi</a>}
          {article.doi && <a href={`https://doi.org/${article.doi}`} target="_blank" rel="noreferrer" title="DOI"><Link2 size={16} /> DOI</a>}
          <button title="Iqtibos formatlari" onClick={() => setCitationsOpen((value) => !value)}><Download size={16} /> Iqtibos</button>
        </div>
      </div>
      {citationsOpen && article.citations && (
        <div className="citation-panel">
          {Object.entries(article.citations).map(([format, value]) => (
            <div key={format}>
              <span>{format.toUpperCase()}</span>
              <p>{value}</p>
              <button onClick={() => copyCitation(value)}>Nusxa olish</button>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function JournalDrawer({ journal, onClose }: { journal: Journal; onClose: () => void }) {
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
    return () => { active = false; };
  }, [journal]);

  useEffect(() => {
    let active = true;
    setJournalArticles([]);
    loadJournalArticles(journal.id)
      .then((items) => { if (active) setJournalArticles(items); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [journal]);

  const profile = detail.profile;
  const oakRecords = detail.oakRecords ?? [];
  const areas = Array.from(new Set(oakRecords.map((item) => item.area).filter(Boolean)));
  const latestDecision = oakRecords.find((item) => item.decision || item.sourceReference);

  return (
    <div className="drawer-shell" role="dialog" aria-modal="true" aria-label={`${detail.name} tafsilotlari`}>
      <button className="drawer-backdrop" onClick={onClose} aria-label="Yopish" />
      <aside className="drawer">
        <button className="drawer-close" onClick={onClose} aria-label="Yopish"><X size={20} /></button>
        <div className="drawer-head">
          <span className="drawer-monogram">{detail.shortName.slice(0, 2).toUpperCase()}</span>
          <span className="journal-topline">
            <span className="oak-badge"><ShieldCheck size={13} /> OAK ro‘yxatida</span>
            <HarvestStatus status={detail.oaiStatus} />
          </span>
          <h2>{detail.name}</h2>
          <p>{detail.publisher}</p>
        </div>

        {detailState === "loading" && <div className="profile-loading"><RefreshCw className="spin" size={15} /> To‘liq profil yuklanmoqda...</div>}
        {profile && (
          <div className="profile-completeness">
            <div><span>Profil to‘liqligi</span><strong>{Math.round(profile.completenessScore)}%</strong></div>
            <div className="completeness-track"><i style={{ width: `${profile.completenessScore}%` }} /></div>
            <small>Ochiq manbalardan {new Date(profile.fetchedAt).toLocaleDateString("uz-UZ")} kuni yig‘ilgan</small>
          </div>
        )}

        <div className="drawer-stats">
          <div><strong>{number.format(detail.articleCount)}</strong><span>Maqolalar</span></div>
          <div><strong>{detail.issueCount}</strong><span>Sonlar</span></div>
          <div><strong>{detail.founded ?? "—"}</strong><span>Asos solingan</span></div>
        </div>

        <section className="drawer-section">
          <h3>Jurnal haqida</h3>
          <p>{profile?.summary || detail.description || "Jurnal tavsifi hali yig‘ilmagan."}</p>
          {profile?.sourceUrl && <a className="source-link" href={profile.sourceUrl} target="_blank" rel="noreferrer"><ShieldCheck size={12} /> Manbani ko‘rish</a>}
        </section>

        <section className="facts-grid">
          <div><span>ISSN</span><strong>{detail.issn}</strong></div>
          <div><span>e-ISSN</span><strong>{detail.eissn ?? "—"}</strong></div>
          <div><span>Shahar</span><strong>{detail.city}</strong></div>
          <div><span>Tillar</span><strong>{detail.languages.join(", ") || "—"}</strong></div>
          {profile?.latestIssue && <div className="fact-wide"><span>So‘nggi son</span><strong>{profile.latestIssue}</strong></div>}
          {profile?.publicationFrequency && <div className="fact-wide"><span>Davriylik</span><strong>{profile.publicationFrequency}</strong></div>}
        </section>

        {!!areas.length && (
          <section className="drawer-section rich-section">
            <div className="rich-title"><span><ShieldCheck size={17} /></span><div><h3>OAK reestri</h3><small>{oakRecords.length} ta rasmiy yozuv</small></div></div>
            <div className="tag-row rich-tags">{areas.map((area) => <span className="tag" key={area}>{area}</span>)}</div>
            {latestDecision && <div className="decision-note"><strong>{latestDecision.decision || latestDecision.sourceReference}</strong><span>{latestDecision.added ? `Kiritilgan: ${latestDecision.added}` : "Rasmiy reestr yozuvi"}</span></div>}
          </section>
        )}

        {!!profile?.indexingClaims.length && (
          <section className="drawer-section rich-section">
            <div className="rich-title"><span><Layers3 size={17} /></span><div><h3>Indekslash bazalari</h3><small>Jurnal saytida ko‘rsatilgan da’volar</small></div></div>
            <div className="indexing-grid">{profile.indexingClaims.map((claim) => <a key={claim.provider} href={claim.sourceUrl} target="_blank" rel="noreferrer"><strong>{claim.provider}</strong><span>{claim.verifiedAt ? "Tekshirilgan" : "Manbada ko‘rsatilgan"}</span></a>)}</div>
          </section>
        )}

        {!!profile?.contacts.length && (
          <section className="drawer-section rich-section">
            <div className="rich-title"><span><AtSign size={17} /></span><div><h3>Aloqa ma’lumotlari</h3><small>Har biri manba bilan</small></div></div>
            <div className="contact-list">{profile.contacts.map((contact, index) => (
              <a key={`${contact.kind}-${contact.value}-${index}`} href={contact.sourceUrl} target="_blank" rel="noreferrer">
                <span>{contact.kind === "email" ? "Email" : contact.kind === "phone" ? "Telefon" : "Manzil"}</span><strong>{contact.value}</strong>
              </a>
            ))}</div>
          </section>
        )}

        {!!profile?.policies.length && (
          <section className="drawer-section rich-section">
            <div className="rich-title"><span><FileText size={17} /></span><div><h3>Siyosatlar va talablar</h3><small>Ochiq jurnal sahifalaridan</small></div></div>
            <div className="policy-list">{profile.policies.map((policy) => (
              <a key={policy.type} href={policy.url || policy.sourceUrl} target="_blank" rel="noreferrer">
                <strong>{policy.title}</strong><span>{policy.content ? `${policy.content.slice(0, 150)}${policy.content.length > 150 ? "…" : ""}` : "Manbani ochish"}</span>
              </a>
            ))}</div>
          </section>
        )}

        {!!profile?.editorialMembers.length && (
          <section className="drawer-section rich-section">
            <div className="rich-title"><span><UsersRound size={17} /></span><div><h3>Tahririyat a’zolari</h3><small>{profile.editorialMembers.length} ta yig‘ilgan yozuv</small></div></div>
            <div className="editorial-list">{profile.editorialMembers.map((member, index) => (
              <a key={`${member.name}-${index}`} href={member.sourceUrl} target="_blank" rel="noreferrer"><strong>{member.name}</strong><span>{member.role || "Tahrir hay’ati"}{member.affiliation ? ` · ${member.affiliation}` : ""}</span></a>
            ))}</div>
          </section>
        )}

        <section className="sync-card">
          <div className="sync-icon"><RefreshCw size={19} /></div>
          <div>
            <span>Oxirgi yangilanish</span>
            <strong>{detail.oaiLastSync ?? "Hozircha yangilanmagan"}</strong>
          </div>
          <HarvestStatus status={detail.oaiStatus} />
        </section>

        <section className="drawer-section">
          <div className="section-heading compact-heading">
            <div><span className="eyebrow">SO‘NGGI NASHRLAR</span><h3>Maqolalar</h3></div>
            <span>{journalArticles.length} namuna</span>
          </div>
          {journalArticles.length ? (
            <div className="mini-articles">
              {journalArticles.map((article) => (
                <div key={article.id}>
                  <FileText size={17} />
                  <span><strong>{article.title}</strong><small>{article.year} · {article.issue}-son</small></span>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-note">Bu jurnalning maqolalari hali yig‘ilmagan.</p>
          )}
        </section>

        {detailState === "ready" && !profile && <p className="profile-empty">Bu jurnal uchun to‘liq profil hali yig‘ilmagan. Asosiy OAK ma’lumotlari ko‘rsatilmoqda.</p>}
        {detailState === "error" && <p className="profile-empty">To‘liq profil API’dan yuklanmadi. Asosiy katalog ma’lumotlari saqlandi.</p>}

        <a className="primary-button full-button" href={detail.website} target="_blank" rel="noreferrer">
          Rasmiy saytga o‘tish <ExternalLink size={17} />
        </a>
      </aside>
    </div>
  );
}

function App() {
  const [catalogJournals, setCatalogJournals] = useState<Journal[]>(demoJournals);
  const [catalogArticles, setCatalogArticles] = useState<Article[]>(demoArticles);
  const [platformStats, setPlatformStats] = useState<PlatformStats>({ journals: demoJournals.length, articles: demoArticles.length, healthySources: 0 });
  const [apiState, setApiState] = useState<"loading" | "live" | "fallback">("loading");
  const [adminOpen, setAdminOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [account, setAccount] = useState<AuthUser | null>(null);
  // Maqola kartasi va drawer jurnal obyektini talab qiladi, sahifada esa
  // atigi PAGE_SIZE ta jurnal bo'ladi — shuning uchun to'liq indeks alohida.
  const [journalIndex, setJournalIndex] = useState<Journal[]>(demoJournals);
  const [journalTotal, setJournalTotal] = useState(demoJournals.length);
  const [articleTotal, setArticleTotal] = useState(demoArticles.length);
  const [loadingMore, setLoadingMore] = useState(false);
  const [view, setView] = useState<View>("journals");
  const [query, setQuery] = useState("");
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [facets, setFacets] = useState<Facets>({ fieldGroups: [], fieldCount: 0, cities: [] });
  const [pickerOpen, setPickerOpen] = useState(false);
  const [city, setCity] = useState("Barcha shaharlar");
  const [oaiOnly, setOaiOnly] = useState(false);
  const [selectedJournal, setSelectedJournal] = useState<Journal | null>(null);
  const [mobileNav, setMobileNav] = useState(false);

  useEffect(() => {
    let active = true;
    loadCatalog()
      .then((data) => {
        if (!active) return;
        setCatalogJournals(data.journals.items);
        setJournalTotal(data.journals.total);
        setCatalogArticles(data.articles.items);
        setArticleTotal(data.articles.total);
        setPlatformStats(data.stats);
        setFacets(data.facets);
        void loadJournalIndex().then((items) => { if (active) setJournalIndex(items); });
        setApiState("live");
      })
      .catch(() => {
        if (active) setApiState("fallback");
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    void loadCurrentUser()
      .then((value) => { if (active) setAccount(value); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [accountOpen]);

  const cities = ["Barcha shaharlar", ...facets.cities.map((item) => item.name)];
  const fieldSet = useMemo(() => new Set(selectedFields), [selectedFields]);
  // Ilgari bu joyda o'ylab topilgan "jonli konsol" turardi: soxta vaqtlar,
  // HTTP kodlari va yozuv sonlari. Endi haqiqiy yangilanish sanalari.
  const recentUpdates = useMemo(() => journalIndex
    .filter((journal) => journal.oaiLastSync)
    .sort((left, right) => (right.oaiLastSync ?? "").localeCompare(left.oaiLastSync ?? ""))
    .slice(0, 4)
    .map((journal) => ({
      id: journal.id,
      name: journal.name.length > 34 ? `${journal.name.slice(0, 34)}…` : journal.name,
      when: shortDate(journal.oaiLastSync as string),
      articles: number.format(journal.articleCount),
    })), [journalIndex]);

  const topFields = useMemo(() => facets.fieldGroups
    .flatMap((group) => group.fields)
    .sort((left, right) => right.articles - left.articles)
    .slice(0, 6)
    .map((item) => item.name), [facets]);
  // Qidiruv va filtrlar serverda qo'llanadi. Ilgari mijozda ham takroran
  // filtrlanardi va bu server topgan natijalarni qirqib tashlardi.
  const journalById = useMemo(
    () => new Map(journalIndex.map((journal) => [journal.id, journal])),
    [journalIndex],
  );
  const visibleJournals = catalogJournals;
  const visibleArticles = catalogArticles;
  const totalResults = view === "journals" ? journalTotal : articleTotal;
  const shown = view === "journals" ? visibleJournals.length : visibleArticles.length;

  const resetFilters = () => {
    setQuery("");
    setSelectedFields([]);
    setCity("Barcha shaharlar");
    setOaiOnly(false);
  };

  const activeCities = useMemo(
    () => (city === "Barcha shaharlar" ? [] : [city]),
    [city],
  );

  // `loadCatalog` filtrsiz ro'yxatni allaqachon olib bo'lgan. Bu effekt jonli
  // rejimga o'tgan zahoti ishga tushsa, aynan o'sha so'rovni takrorlardi.
  const skipFirstSearch = useRef(true);

  useEffect(() => {
    if (apiState !== "live") return;
    if (skipFirstSearch.current && !query.trim() && selectedFields.length === 0 && activeCities.length === 0) {
      skipFirstSearch.current = false;
      return;
    }
    skipFirstSearch.current = false;
    const timer = window.setTimeout(() => {
      const request = view === "articles"
        ? searchArticles(query, selectedFields, activeCities).then((page) => {
            setCatalogArticles(page.items);
            setArticleTotal(page.total);
          })
        : searchJournals(query, selectedFields, activeCities, 0, oaiOnly).then((page) => {
            setCatalogJournals(page.items);
            setJournalTotal(page.total);
          });
      void request.catch(() => undefined);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [activeCities, apiState, oaiOnly, query, selectedFields, view]);

  const loadMore = () => {
    if (loadingMore || apiState !== "live") return;
    setLoadingMore(true);
    const request = view === "articles"
      ? searchArticles(query, selectedFields, activeCities, visibleArticles.length).then((page) => {
          setCatalogArticles((current) => [...current, ...page.items]);
          setArticleTotal(page.total);
        })
      : searchJournals(query, selectedFields, activeCities, visibleJournals.length, oaiOnly).then((page) => {
          setCatalogJournals((current) => [...current, ...page.items]);
          setJournalTotal(page.total);
        });
    void request.catch(() => undefined).finally(() => setLoadingMore(false));
  };

  if (adminOpen) {
    return <AdminDashboard onClose={() => setAdminOpen(false)} />;
  }

  const picker = pickerOpen && (
    <FieldPicker
      groups={facets.fieldGroups}
      selected={selectedFields}
      onApply={(next) => { setSelectedFields(next); setPickerOpen(false); }}
      onClose={() => setPickerOpen(false)}
    />
  );

  return (
    <div className="app" id="top">
      <header className="site-header">
        <div className="header-inner">
          <Brand />
          <nav className={mobileNav ? "nav-open" : ""} aria-label="Asosiy navigatsiya">
            <button className={view === "journals" ? "nav-active" : ""} onClick={() => { setView("journals"); setMobileNav(false); }}>Jurnallar</button>
            <button className={view === "articles" ? "nav-active" : ""} onClick={() => { setView("articles"); setMobileNav(false); }}>Maqolalar</button>
            <a href="#monitoring" onClick={() => setMobileNav(false)}>Monitoring</a>
            <a href="#about" onClick={() => setMobileNav(false)}>Loyiha haqida</a>
            <button className="mobile-admin-link" onClick={() => { setAdminOpen(true); setMobileNav(false); }}>Admin panel</button>
          </nav>
          <div className="header-actions">
            <span className={`live-pill api-${apiState}`}><span /> {apiState === "live" ? "API ulangan" : apiState === "loading" ? "Ulanmoqda..." : "Demo rejim"}</span>
            <button className="account-button" onClick={() => setAccountOpen(true)}>{account ? account.displayName.split(" ")[0] : "Kirish"}</button>
              <button className="admin-button" onClick={() => setAdminOpen(true)}>Admin panel</button>
            <button className="mobile-menu" onClick={() => setMobileNav((value) => !value)} aria-label="Menyuni ochish"><Menu size={21} /></button>
          </div>
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="hero-grid" aria-hidden="true" />
          <div className="hero-inner">
            <div className="hero-copy">
              <span className="hero-kicker"><Database size={15} /> O‘zbekiston ilmiy nashrlari yagona indeksi</span>
              <h1>Ilmiy manbani<br /><em>bir joydan</em> toping.</h1>
              <p>OAK tasdiqlagan jurnallar va ularda chop etilgan maqolalarning muntazam yangilanadigan ochiq katalogi.</p>
            </div>
            <div className="hero-aside">
              <div className="index-note">
                <Activity size={18} />
                <div><span>Oxirgi indekslash</span><strong>bugun, 06:12</strong></div>
                <span className="index-bars"><i /><i /><i /><i /></span>
              </div>
              <p>Ma’lumotlar jurnal saytlaridan avtomatik yangilanadi.</p>
            </div>
            <div className="search-panel">
              <div className="search-box">
                <Search size={21} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={view === "journals" ? "Jurnal nomi, ISSN, nashriyot yoki sohani qidiring..." : "Maqola, muallif yoki kalit so‘zni qidiring..."}
                  aria-label="Qidiruv"
                />
                {query && <button onClick={() => setQuery("")} aria-label="Qidiruvni tozalash"><X size={17} /></button>}
              </div>
              <button className="search-button">Izlash <ArrowRight size={18} /></button>
            </div>
            <div className="quick-links">
              <span>Ko‘p qidirilgan:</span>
              {topFields.map((item) => (
                <button
                  key={item}
                  className={fieldSet.has(item) ? "active" : ""}
                  onClick={() => setSelectedFields((current) => current.includes(item)
                    ? current.filter((name) => name !== item)
                    : [...current, item])}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="metric-strip" aria-label="Platforma ko‘rsatkichlari">
          <div className="metric-inner">
            <div><BookOpen size={21} /><span><strong>{number.format(platformStats.journals)}</strong><small>OAK jurnallari</small></span></div>
            <div><FileText size={21} /><span><strong>{number.format(platformStats.articles)}</strong><small>Maqolalar</small></span></div>
            <div><RefreshCw size={21} /><span><strong>{number.format(platformStats.healthySources)}</strong><small>Yangilanadigan jurnallar</small></span></div>
            <div><Layers3 size={21} /><span><strong>{facets.fieldCount || "—"}</strong><small>Ilmiy sohalar</small></span></div>
            <p><Check size={16} /> OAK ro‘yxati: 10-iyun, 2026</p>
          </div>
        </section>

        <section className="catalog-section">
          <div className="section-heading">
            <div>
              <span className="eyebrow">OCHIQ KATALOG</span>
              <h2>{view === "journals" ? "OAK jurnallarini o‘rganing" : "Ilmiy maqolalarni izlang"}</h2>
              <p>{view === "journals" ? "Tasdiqlangan nashrlar, yangilanish holati va arxiv ko‘rsatkichlari." : "Barcha jurnallardan yig‘ilgan yagona maqolalar bazasi."}</p>
            </div>
            <div className="view-tabs" role="tablist">
              <button className={view === "journals" ? "active" : ""} onClick={() => setView("journals")}><BookOpen size={16} /> Jurnallar</button>
              <button className={view === "articles" ? "active" : ""} onClick={() => setView("articles")}><FileText size={16} /> Maqolalar</button>
            </div>
          </div>

          <div className="catalog-layout">
            <aside className="filters">
              <div className="filter-title"><SlidersHorizontal size={17} /><strong>Filtrlar</strong><button onClick={resetFilters}>Tozalash</button></div>
              <div className="filter-field">
                <span>Ilmiy soha</span>
                <button className="field-trigger" onClick={() => setPickerOpen(true)}>
                  <Layers3 size={15} />
                  {selectedFields.length === 0
                    ? (facets.fieldCount ? `Barcha sohalar (${facets.fieldCount})` : "Barcha sohalar")
                    : `${selectedFields.length} ta soha tanlandi`}
                </button>
                {selectedFields.length > 0 && (
                  <div className="field-chips">
                    {selectedFields.map((item) => (
                      <button key={item} onClick={() => setSelectedFields((current) => current.filter((name) => name !== item))}>
                        {item} <X size={11} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <label>
                <span>Shahar</span>
                <select value={city} onChange={(event) => setCity(event.target.value)}>
                  {cities.map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
              <label className="switch-row">
                <span><strong>Avtomatik yangilanadigan</strong><small>Maqolalari muntazam yig‘iladigan jurnallar</small></span>
                <input type="checkbox" checked={oaiOnly} onChange={(event) => setOaiOnly(event.target.checked)} />
                <i aria-hidden="true" />
              </label>
              <div className="filter-note">
                <ShieldCheck size={18} />
                <p><strong>Ishonchli ma’lumot</strong><span>Har bir yozuv manbasi va yangilangan vaqti bilan saqlanadi.</span></p>
              </div>
            </aside>

            <div className="results">
              <div className="results-head">
                <p><strong>{number.format(totalResults)}</strong> ta natija{shown < totalResults ? ` · ${number.format(shown)} ta ko‘rsatilmoqda` : ""}</p>
                <span><Clock3 size={14} /> Eng yangi ma’lumotlar birinchi</span>
              </div>
              <div className={view === "journals" ? "journal-list" : "article-list"}>
                {view === "journals"
                  ? visibleJournals.map((journal) => <JournalCard key={journal.id} journal={journal} onOpen={() => setSelectedJournal(journal)} />)
                  : visibleArticles.map((article) => {
                      const journal = journalById.get(article.journalId);
                      return journal ? <ArticleCard key={article.id} article={article} journal={journal} /> : null;
                    })}
              </div>
              {shown === 0 && (
                <div className="empty-state"><Search size={28} /><h3>Natija topilmadi</h3><p>Qidiruv yoki filtrlarni o‘zgartirib ko‘ring.</p><button onClick={resetFilters}>Filtrlarni tozalash</button></div>
              )}
              {shown > 0 && shown < totalResults && (
                <button className="load-more" onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? "Yuklanmoqda..." : `Yana ${number.format(Math.min(PAGE_SIZE, totalResults - shown))} ta ko‘rsatish`}
                  <ArrowRight size={17} />
                </button>
              )}
            </div>
          </div>
        </section>

        <section className="monitor-section" id="monitoring">
          <div className="monitor-copy">
            <span className="eyebrow light">AVTOMATIK YANGILANISH</span>
            <h2>Indeks har doim<br />yangilanib turadi.</h2>
            <p>Har bir jurnal alohida kuzatiladi. Yangi son chiqishi bilan maqolalar indeksga qo‘shiladi.</p>
            <div className="monitor-features">
              <span><CheckCircle2 size={17} /> Faqat o‘zgargan yozuvlar olinadi</span>
              <span><CheckCircle2 size={17} /> Takroriy yozuvlar aniqlanadi</span>
              <span><CheckCircle2 size={17} /> Har bir maydonning manbasi saqlanadi</span>
            </div>
          </div>
          <div className="monitor-console">
            <div className="console-head"><span><i /><i /><i /></span><strong>So‘nggi yangilanishlar</strong><Activity size={16} /></div>
            <div className="console-body">
              {recentUpdates.length === 0 && <p className="console-empty">Yangilanish ma’lumoti hali yo‘q.</p>}
              {recentUpdates.map((item) => (
                <p key={item.id}>
                  <time>{item.when}</time>
                  <span>{item.name}</span>
                  <small>{item.articles} maqola</small>
                </p>
              ))}
            </div>
          </div>
        </section>

        <section className="about-section" id="about">
          <div>
            <span className="eyebrow">LOYIHA TAMOYILI</span>
            <h2>Ochiq, tekshiriladigan va foydali ilmiy infratuzilma.</h2>
          </div>
          <div className="principles">
            <article><span>01</span><Globe2 size={22} /><h3>Ochiqlik</h3><p>Metama’lumotlar va qidiruv barcha foydalanuvchilar uchun ochiq.</p></article>
            <article><span>02</span><ShieldCheck size={22} /><h3>Manba aniqligi</h3><p>Har bir maydon qayerdan va qachon olingani qayd etiladi.</p></article>
            <article><span>03</span><CalendarDays size={22} /><h3>Doimiy yangilanish</h3><p>Faqat o‘zgargan yozuvlar muntazam olinadi, indeks eskirmaydi.</p></article>
          </div>
        </section>
      </main>

      <footer>
        <div className="footer-inner">
          <Brand />
          <p>O‘zbekiston ilmiy nashrlari uchun ochiq indeks prototipi.</p>
          <span>© 2026 IlmIz · MVP 0.1</span>
        </div>
      </footer>

      {selectedJournal && <JournalDrawer journal={selectedJournal} onClose={() => setSelectedJournal(null)} />}
      {picker}
      {accountOpen && <AccountPanel onClose={() => setAccountOpen(false)} />}
    </div>
  );
}

export default App;

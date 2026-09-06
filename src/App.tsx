import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  BookOpen,
  CalendarDays,
  Check,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  Globe2,
  Layers3,
  Loader2,
  Menu,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";

import {
  PAGE_SIZE,
  loadCatalog,
  loadJournal,
  loadJournalIndex,
  searchArticles,
  searchJournals,
  type Facets,
  type PlatformStats,
} from "@/api";
import { loadCurrentUser, type AuthUser } from "@/authApi";
import type { Article, Journal } from "@/types";

import AboutPage from "@/AboutPage";
import PrivacyPage from "@/PrivacyPage";
import TermsPage from "@/TermsPage";
import AccountPanel from "@/AccountPanel";
import AdminDashboard from "@/AdminDashboard";
import ArticlePage from "@/ArticlePage";
import ArchivePage from "@/ArchivePage";
import DirectoryPage from "@/DirectoryPage";
import FieldPicker from "@/FieldPicker";
import { navigate, useRoute } from "@/router";
import { AppLink } from "@/components/app-link";
import { ArticleCard } from "@/components/article-card";
import { Brand } from "@/components/brand";
import { JournalCard } from "@/components/journal-card";
import { JournalSheet } from "@/components/journal-sheet";
import { ModeToggle } from "@/components/mode-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { number, shortDate } from "@/lib/format";
import { clip, setHead, syncHead } from "@/lib/head";
import { cityPath, fieldPath, journalPath, slugify } from "@/lib/slug";
import { cn } from "@/lib/utils";

type View = "journals" | "articles";

const SHELL = "mx-auto w-full max-w-[1200px] px-4 sm:px-6";

function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "text-[11px] font-medium uppercase tracking-widest text-muted-foreground",
        className,
      )}
    >
      {children}
    </span>
  );
}

function App() {
  const [catalogJournals, setCatalogJournals] = useState<Journal[]>([]);
  const [catalogArticles, setCatalogArticles] = useState<Article[]>([]);
  const [platformStats, setPlatformStats] = useState<PlatformStats>({
    journals: 0,
    articles: 0,
    healthySources: 0,
  });
  const [apiState, setApiState] = useState<"loading" | "live" | "fallback">("loading");
  const [adminOpen, setAdminOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [account, setAccount] = useState<AuthUser | null>(null);
  // Maqola kartasi va drawer jurnal obyektini talab qiladi, sahifada esa
  // atigi PAGE_SIZE ta jurnal bo'ladi — shuning uchun to'liq indeks alohida.
  const [journalIndex, setJournalIndex] = useState<Journal[]>([]);
  const [journalTotal, setJournalTotal] = useState(0);
  const [articleTotal, setArticleTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  // Ko'rinish endi manzildan kelib chiqadi: `/jurnallar` va `/maqolalar` —
  // ikkita alohida indekslanadigan sahifa, holat emas.
  const route = useRoute();
  const isArchive = route.kind === 'recent' || ('page' in route && route.page > 1) || (route.kind === 'journal' && route.year !== null);
  useEffect(() => { void syncHead(); }, [route]);
  const view: View =
    route.kind === "articles" || route.kind === "search" ? "articles" : "journals";
  const setView = useCallback((next: View) => {
    navigate(next === "articles" ? "/maqolalar" : "/jurnallar");
  }, []);
  const [query, setQuery] = useState("");
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [facets, setFacets] = useState<Facets>({ fieldGroups: [], fieldCount: 0, cities: [] });
  const [pickerOpen, setPickerOpen] = useState(false);
  const [city, setCity] = useState("Barcha shaharlar");
  const [oaiOnly, setOaiOnly] = useState(false);
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
        void loadJournalIndex().then((items) => {
          if (active) setJournalIndex(items);
        });
        setApiState("live");
      })
      .catch(() => {
        if (active) setApiState("fallback");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    void loadCurrentUser()
      .then((value) => {
        if (active) setAccount(value);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [accountOpen]);

  const cities = ["Barcha shaharlar", ...facets.cities.map((item) => item.name)];
  const fieldSet = useMemo(() => new Set(selectedFields), [selectedFields]);

  // Jurnal drawer'i endi `/jurnal/{slug}` manzilida yashaydi — havolasini
  // ulashish va qidiruv tizimlariga ko'rsatish mumkin.
  const [fetchedJournal, setFetchedJournal] = useState<Journal | null>(null);
  const indexedJournal =
    route.kind === "journal" ? journalIndex.find((item) => item.id === route.slug) ?? null : null;
  const selectedJournal =
    route.kind === "journal" && !isArchive
      ? indexedJournal ?? (fetchedJournal?.id === route.slug ? fetchedJournal : null)
      : null;

  useEffect(() => {
    // Manzil to'g'ridan-to'g'ri ochilgan bo'lsa, indeks hali yuklanmagan
    // bo'lishi mumkin — jurnalni alohida olamiz.
    if (route.kind !== "journal" || indexedJournal) return;
    let active = true;
    void loadJournal(route.slug)
      .then((value) => {
        if (active) setFetchedJournal(value);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [indexedJournal, route]);

  useEffect(() => {
    if (route.kind !== "journal" || !selectedJournal) return;
    const issn = selectedJournal.issn && selectedJournal.issn !== "—" ? `, ISSN ${selectedJournal.issn}` : "";
    setHead({
      title: `${selectedJournal.name} — OAK jurnali${issn}`,
      description: clip(
        selectedJournal.description ||
          `${selectedJournal.name} — ${selectedJournal.city} shahrida ${selectedJournal.publisher} nashr etadigan OAK ro‘yxatidagi ilmiy jurnal.`,
      ),
      path: journalPath(selectedJournal.id),
    });
  }, [route, selectedJournal]);

  const closeJournal = useCallback(() => {
    if (window.history.length > 1) window.history.back();
    else navigate("/jurnallar");
  }, []);

  // `/soha/{slug}` va `/shahar/{slug}` — filtr emas, alohida qo'nish sahifasi.
  const routeField = useMemo(
    () =>
      route.kind === "field"
        ? facets.fieldGroups
            .flatMap((group) => group.fields)
            .find((item) => slugify(item.name) === route.slug)?.name ?? null
        : null,
    [facets, route],
  );
  const routeCity = useMemo(
    () =>
      route.kind === "city"
        ? facets.cities.find((item) => slugify(item.name) === route.slug)?.name ?? null
        : null,
    [facets, route],
  );

  useEffect(() => {
    setSelectedFields(routeField ? [routeField] : []);
  }, [routeField]);

  useEffect(() => {
    setCity(routeCity ?? "Barcha shaharlar");
  }, [routeCity]);

  // `/qidiruv?q=` — sayt qidiruvi. JSON-LD dagi `SearchAction` aynan shu
  // manzilga ishora qiladi, ya'ni Google uni chaqira olishi kerak.
  const routeQuery = route.kind === "search" ? route.query : null;
  useEffect(() => {
    if (routeQuery !== null) setQuery(routeQuery);
  }, [routeQuery]);
  // Ilgari bu joyda o'ylab topilgan "jonli konsol" turardi: soxta vaqtlar,
  // HTTP kodlari va yozuv sonlari. Endi haqiqiy yangilanish sanalari.
  const recentUpdates = useMemo(
    () =>
      journalIndex
        .filter((journal) => journal.oaiLastSync)
        .sort((left, right) => (right.oaiLastSync ?? "").localeCompare(left.oaiLastSync ?? ""))
        .slice(0, 5)
        .map((journal) => ({
          id: journal.id,
          name: journal.name.length > 40 ? `${journal.name.slice(0, 40)}…` : journal.name,
          when: shortDate(journal.oaiLastSync as string),
          articles: number.format(journal.articleCount),
        })),
    [journalIndex],
  );

  const topFields = useMemo(
    () =>
      facets.fieldGroups
        .flatMap((group) => group.fields)
        .sort((left, right) => right.articles - left.articles)
        .slice(0, 6)
        .map((item) => item.name),
    [facets],
  );
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
  const filtersActive =
    Boolean(query.trim()) || selectedFields.length > 0 || city !== "Barcha shaharlar" || oaiOnly;

  const resetFilters = () => {
    setQuery("");
    setSelectedFields([]);
    setCity("Barcha shaharlar");
    setOaiOnly(false);
    // Soha/shahar sahifasida turib filtrni tozalash manzilni yolg'onga
    // aylantirardi: URL "/soha/tibbiyot", ro'yxatda esa hamma jurnal.
    if (route.kind === "field" || route.kind === "city") navigate("/jurnallar");
  };

  // Har o'tishda sarlavha va kanonik havolani yangilaymiz. Birinchi
  // yuklashda ularni server qo'ygan — bu faqat keyingi o'tishlar uchun.
  useEffect(() => {
    if (route.kind === "article" || route.kind === "journal") return;
    const titles: Record<string, [string, string]> = {
      home: [
        "IlmIz — O‘zbekiston OAK jurnallari va ilmiy maqolalar indeksi",
        `OAK ro‘yxatidagi ${number.format(platformStats.journals)} ta ilmiy jurnal va ${number.format(platformStats.articles)} ta maqolaning ochiq indeksi.`,
      ],
      journals: [
        `OAK jurnallari ro‘yxati — ${number.format(journalTotal)} ta ilmiy nashr`,
        "O‘zbekiston OAK tasdiqlagan ilmiy jurnallar: ISSN, nashriyot, shahar va ilmiy soha bo‘yicha.",
      ],
      articles: [
        `Ilmiy maqolalar bazasi — ${number.format(articleTotal)} ta maqola`,
        "OAK jurnallaridan yig‘ilgan maqolalar: annotatsiya, kalit so‘zlar, DOI va tayyor iqtibos.",
      ],
      field: [
        routeField ? `${routeField} — OAK jurnallari va ilmiy maqolalar` : "Ilmiy soha",
        routeField ? `${routeField} sohasi bo‘yicha OAK ro‘yxatidagi ilmiy jurnallar va maqolalar.` : "",
      ],
      city: [
        routeCity ? `${routeCity} — OAK jurnallari va ilmiy nashrlari` : "Shahar",
        routeCity ? `${routeCity} shahrida nashr etiladigan OAK ro‘yxatidagi ilmiy jurnallar.` : "",
      ],
      notFound: ["Sahifa topilmadi", "So‘ralgan manzil indeksda yo‘q."],
    };
    const entry = titles[route.kind];
    if (!entry) return;
    setHead({
      title: entry[0],
      description: clip(entry[1]),
      noindex: route.kind === "notFound",
    });
  }, [articleTotal, journalTotal, platformStats, route, routeCity, routeField]);

  const activeCities = useMemo(() => (city === "Barcha shaharlar" ? [] : [city]), [city]);

  // `loadCatalog` filtrsiz ro'yxatni allaqachon olib bo'lgan. Bu effekt jonli
  // rejimga o'tgan zahoti ishga tushsa, aynan o'sha so'rovni takrorlardi.
  const skipFirstSearch = useRef(true);

  useEffect(() => {
    if (apiState !== "live") return;
    if (
      skipFirstSearch.current &&
      !query.trim() &&
      selectedFields.length === 0 &&
      activeCities.length === 0
    ) {
      skipFirstSearch.current = false;
      return;
    }
    skipFirstSearch.current = false;
    // Debounce faqat taymerni bekor qiladi, yuborilgan so‘rovni emas: "a"
    // so‘rovi "ab" dan keyin qaytsa, eski natija yangisini ustidan yozardi.
    // `active` bayrog‘i eskirgan javobni tashlab yuboradi.
    let active = true;
    const timer = window.setTimeout(() => {
      const request =
        view === "articles"
          ? searchArticles(query, selectedFields, activeCities).then((page) => {
              if (!active) return;
              setCatalogArticles(page.items);
              setArticleTotal(page.total);
            })
          : searchJournals(query, selectedFields, activeCities, 0, oaiOnly).then((page) => {
              if (!active) return;
              setCatalogJournals(page.items);
              setJournalTotal(page.total);
            });
      void request.catch(() => undefined);
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [activeCities, apiState, oaiOnly, query, selectedFields, view]);

  const loadMore = () => {
    if (loadingMore || apiState !== "live") return;
    setLoadingMore(true);
    const request =
      view === "articles"
        ? searchArticles(query, selectedFields, activeCities, visibleArticles.length).then((page) => {
            setCatalogArticles((current) => [...current, ...page.items]);
            setArticleTotal(page.total);
          })
        : searchJournals(query, selectedFields, activeCities, visibleJournals.length, oaiOnly).then(
            (page) => {
              setCatalogJournals((current) => [...current, ...page.items]);
              setJournalTotal(page.total);
            },
          );
    void request.catch(() => undefined).finally(() => setLoadingMore(false));
  };

  if (adminOpen) {
    return <AdminDashboard onClose={() => setAdminOpen(false)} />;
  }

  const hero: { eyebrow: string; title: React.ReactNode; lead: string } = (() => {
    const catalogue =
      "OAK tasdiqlagan jurnallar va ularda chop etilgan maqolalarning muntazam yangilanadigan ochiq katalogi.";
    if (routeField)
      return {
        eyebrow: `${routeField} yo‘nalishi`,
        title: `${routeField} sohasidagi OAK jurnallari`,
        lead: `${routeField} sohasi bo‘yicha OAK ro‘yxatidagi ilmiy jurnallar va ularning maqolalari.`,
      };
    if (routeCity)
      return {
        eyebrow: `${routeCity} shahri`,
        title: `${routeCity} shahridagi OAK jurnallari`,
        lead: `${routeCity} shahrida nashr etiladigan OAK ro‘yxatidagi ilmiy jurnallar.`,
      };
    if (selectedJournal)
      return {
        eyebrow: "OAK jurnali",
        title: selectedJournal.name,
        lead: selectedJournal.description || catalogue,
      };
    if (route.kind === "articles" || route.kind === "search")
      return {
        eyebrow: "Maqolalar bazasi",
        title: "O‘zbekiston ilmiy maqolalarini izlang.",
        lead: "OAK jurnallaridan yig‘ilgan maqolalar: annotatsiya, kalit so‘zlar, DOI va tayyor iqtibos.",
      };
    if (route.kind === "journals")
      return {
        eyebrow: "OAK ro‘yxati",
        title: "O‘zbekiston OAK jurnallari ro‘yxati",
        lead: catalogue,
      };
    return {
      eyebrow: "O‘zbekiston ilmiy nashrlari yagona indeksi",
      title: (
        <>
          Ilmiy manbani <span className="text-primary">bir joydan</span> toping.
        </>
      ),
      lead: catalogue,
    };
  })();

  // Navigatsiya haqiqiy `<a href>` lardan iborat: robot ular orqali indeksni
  // aylanib chiqadi, ilgari esa `onClick` ortidagi holat o'zgarishi edi.
  const navLinks = (
    <>
      {(
        [
          ["/jurnallar", "Jurnallar", route.kind === "journals" || route.kind === "home"],
          ["/maqolalar", "Maqolalar", route.kind === "articles"],
          ["/yangi-maqolalar", "Yangi maqolalar", route.kind === "recent"],
          ["/sohalar", "Sohalar", route.kind === "fields" || route.kind === "field"],
          ["/shaharlar", "Shaharlar", route.kind === "cities" || route.kind === "city"],
          ["/loyiha", "Loyiha haqida", route.kind === "about"],
        ] as const
      ).map(([href, label, active]) => (
        <Button
          key={href}
          variant="ghost"
          size="sm"
          className={cn(active && "bg-accent text-accent-foreground")}
          asChild
          onClick={() => setMobileNav(false)}
        >
          <AppLink to={href}>{label}</AppLink>
        </Button>
      ))}
    </>
  );

  const apiLabel =
    apiState === "live" ? "API ulangan" : apiState === "loading" ? "Ulanmoqda..." : "Ulanish xatosi";

  return (
    <div id="top" className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 w-full border-b bg-background/80 backdrop-blur-md">
        <div className={cn(SHELL, "flex h-14 items-center gap-4")}>
          <Brand />
          <nav className="hidden items-center gap-1 md:flex" aria-label="Asosiy navigatsiya">
            {navLinks}
          </nav>
          <div className="ml-auto flex items-center gap-1.5">
            <Badge
              variant="outline"
              className="hidden gap-1.5 font-normal text-muted-foreground sm:inline-flex"
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  apiState === "live" && "bg-success",
                  apiState === "loading" && "animate-pulse bg-warning",
                  apiState === "fallback" && "bg-muted-foreground",
                )}
              />
              {apiLabel}
            </Badge>
            <ModeToggle />
            <Button variant="outline" size="sm" onClick={() => setAccountOpen(true)}>
              {account ? account.displayName.split(" ")[0] : "Kirish"}
            </Button>
            {account?.isAdmin && (
              <Button
                variant="ghost"
                size="sm"
                className="hidden lg:inline-flex"
                onClick={() => setAdminOpen(true)}
              >
                Admin panel
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={() => setMobileNav(true)}
              aria-label="Menyuni ochish"
            >
              <Menu />
            </Button>
          </div>
        </div>
      </header>

      <Sheet open={mobileNav} onOpenChange={setMobileNav}>
        <SheetContent side="left" className="w-72 p-6">
          <SheetTitle className="sr-only">Navigatsiya</SheetTitle>
          <Brand />
          <nav className="mt-6 flex flex-col items-stretch gap-1 [&_button]:justify-start">
            {navLinks}
            {account?.isAdmin && (
              <>
                <Separator className="my-2" />
                <Button
                  variant="ghost"
                  size="sm"
                  className="justify-start"
                  onClick={() => {
                    setAdminOpen(true);
                    setMobileNav(false);
                  }}
                >
                  Admin panel
                </Button>
              </>
            )}
          </nav>
        </SheetContent>
      </Sheet>

      <main className="flex-1">
        {isArchive ? (
          <ArchivePage path={window.location.pathname + window.location.search} />
        ) : route.kind === "article" ? (
          <ArticlePage id={route.id} />
        ) : route.kind === "about" ? (
          <AboutPage stats={platformStats} />
        ) : route.kind === "privacy" ? (
          <PrivacyPage />
        ) : route.kind === "terms" ? (
          <TermsPage />
        ) : route.kind === "fields" || route.kind === "cities" ? (
          <DirectoryPage kind={route.kind} facets={facets} />
        ) : route.kind === "notFound" ? (
          <div className={cn(SHELL, "py-24 text-center")}>
            <h1 className="text-2xl font-semibold tracking-tight">Sahifa topilmadi</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              <code className="font-mono">{route.path}</code> manzili indeksda yo‘q.
            </p>
            <div className="mt-6 flex justify-center gap-2">
              <Button asChild>
                <AppLink to="/jurnallar">Jurnallar</AppLink>
              </Button>
              <Button variant="outline" asChild>
                <AppLink to="/maqolalar">Maqolalar</AppLink>
              </Button>
            </div>
          </div>
        ) : (
          <>
        <section className="relative overflow-hidden border-b">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 -z-10 opacity-70"
            style={{
              backgroundImage:
                "linear-gradient(to right, var(--border) 1px, transparent 1px), linear-gradient(to bottom, var(--border) 1px, transparent 1px)",
              backgroundSize: "56px 56px",
              maskImage: "radial-gradient(ellipse 65% 60% at 50% 0%, #000 55%, transparent 100%)",
              WebkitMaskImage:
                "radial-gradient(ellipse 65% 60% at 50% 0%, #000 55%, transparent 100%)",
            }}
          />
          <div className={cn(SHELL, "py-14 sm:py-20")}>
            <div className="mx-auto max-w-3xl text-center">
              <Badge variant="outline" className="mb-5 gap-1.5 bg-background/60 py-1 font-normal">
                <Database className="size-3.5" />
                {hero.eyebrow}
              </Badge>
              {/* H1 manzilga qarab o'zgaradi. Ilgari hamma sahifada bir xil
                  edi, ya'ni Googlebot render qilgach `/soha/tibbiyot` ham,
                  `/maqolalar` ham "Ilmiy manbani bir joydan toping" sarlavhasi
                  bilan indekslanardi — serverdagi H1 bilan mos kelmasdi. */}
              <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-5xl md:text-6xl">
                {hero.title}
              </h1>
              <p className="mx-auto mt-4 max-w-2xl text-pretty text-base leading-relaxed text-muted-foreground sm:text-lg">
                {hero.lead}
              </p>

              <div className="mx-auto mt-8 flex max-w-2xl flex-col gap-2 sm:flex-row">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder={
                      view === "journals"
                        ? "Jurnal nomi, ISSN, nashriyot yoki soha..."
                        : "Maqola, muallif yoki kalit so‘z..."
                    }
                    aria-label="Qidiruv"
                    className="h-11 bg-background pl-9 pr-9 text-base shadow-sm"
                  />
                  {query && (
                    <button
                      onClick={() => setQuery("")}
                      aria-label="Qidiruvni tozalash"
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 cursor-pointer rounded-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      <X className="size-4" />
                    </button>
                  )}
                </div>
                <Button
                  size="xl"
                  className="shrink-0"
                  onClick={() =>
                    document
                      .getElementById("catalog")
                      ?.scrollIntoView({ behavior: "smooth", block: "start" })
                  }
                >
                  Izlash <ArrowRight />
                </Button>
              </div>

              {topFields.length > 0 && (
                <div className="mt-5 flex flex-wrap items-center justify-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Ko‘p qidirilgan:</span>
                  {topFields.map((item) => (
                    <Button
                      key={item}
                      variant={fieldSet.has(item) ? "default" : "outline"}
                      size="sm"
                      className="h-7 rounded-full px-3 text-xs font-normal"
                      asChild
                    >
                      <AppLink to={fieldPath(item)}>{item}</AppLink>
                    </Button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>

        <section aria-label="Platforma ko‘rsatkichlari" className="border-b bg-muted/30">
          <div className={cn(SHELL, "grid gap-3 py-6 sm:grid-cols-2 lg:grid-cols-4")}>
            {[
              { icon: BookOpen, value: number.format(platformStats.journals), label: "OAK jurnallari" },
              { icon: FileText, value: number.format(platformStats.articles), label: "Maqolalar" },
              {
                icon: RefreshCw,
                value: number.format(platformStats.healthySources),
                label: "Yangilanadigan jurnallar",
              },
              { icon: Layers3, value: facets.fieldCount || "—", label: "Ilmiy sohalar" },
            ].map((item) => (
              <Card key={item.label} className="gap-0 py-0">
                <CardContent className="flex items-center gap-3 p-4">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted text-muted-foreground">
                    <item.icon className="size-4" />
                  </span>
                  <div className="min-w-0">
                    <div className="text-xl font-semibold tabular-nums tracking-tight">
                      {apiState === 'live' ? item.value : '—'}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">{item.label}</div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <div className={cn(SHELL, "flex justify-center pb-5")}>
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Check className="size-3.5 text-success" /> OAK ro‘yxati: 10-iyun, 2026
            </span>
          </div>
        </section>

        <section id="catalog" className={cn(SHELL, "py-12 sm:py-16")}>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-1.5">
              <Eyebrow>Ochiq katalog</Eyebrow>
              <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                {view === "journals" ? "OAK jurnallarini o‘rganing" : "Ilmiy maqolalarni izlang"}
              </h2>
              <p className="text-sm text-muted-foreground">
                {view === "journals"
                  ? "Tasdiqlangan nashrlar, yangilanish holati va arxiv ko‘rsatkichlari."
                  : "Barcha jurnallardan yig‘ilgan yagona maqolalar bazasi."}
              </p>
            </div>
            <Tabs value={view} onValueChange={(value) => setView(value as View)}>
              <TabsList>
                <TabsTrigger value="journals">
                  <BookOpen /> Jurnallar
                </TabsTrigger>
                <TabsTrigger value="articles">
                  <FileText /> Maqolalar
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
            <aside className="lg:sticky lg:top-20 lg:self-start">
              <Card className="gap-4 py-4">
                <CardContent className="space-y-4 px-4">
                  <div className="flex items-center gap-2">
                    <SlidersHorizontal className="size-4 text-muted-foreground" />
                    <strong className="text-sm font-semibold">Filtrlar</strong>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="ml-auto h-7 px-2 text-xs"
                      onClick={resetFilters}
                      disabled={!filtersActive}
                    >
                      Tozalash
                    </Button>
                  </div>

                  <Separator />

                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Ilmiy soha</Label>
                    <Button
                      variant="outline"
                      className="w-full justify-start font-normal"
                      onClick={() => setPickerOpen(true)}
                    >
                      <Layers3 className="text-muted-foreground" />
                      <span className="truncate">
                        {selectedFields.length === 0
                          ? facets.fieldCount
                            ? `Barcha sohalar (${facets.fieldCount})`
                            : "Barcha sohalar"
                          : `${selectedFields.length} ta soha tanlandi`}
                      </span>
                    </Button>
                    {selectedFields.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {selectedFields.map((item) => (
                          <button
                            key={item}
                            onClick={() =>
                              setSelectedFields((current) => current.filter((name) => name !== item))
                            }
                            className="inline-flex cursor-pointer items-center gap-1 rounded-md border bg-secondary px-2 py-0.5 text-xs text-secondary-foreground transition-colors hover:bg-secondary/70"
                          >
                            {item}
                            <X className="size-3" />
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Shahar</Label>
                    <Select value={city} onValueChange={setCity}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="max-h-72">
                        {cities.map((item) => (
                          <SelectItem key={item} value={item}>
                            {item}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex items-start gap-3 rounded-lg border p-3">
                    <div className="min-w-0 flex-1">
                      <Label htmlFor="oai-only" className="text-sm">
                        Avtomatik yangilanadigan
                      </Label>
                      <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
                        Maqolalari muntazam yig‘iladigan jurnallar
                      </p>
                    </div>
                    <Switch
                      id="oai-only"
                      checked={oaiOnly}
                      onCheckedChange={setOaiOnly}
                      className="mt-0.5"
                    />
                  </div>

                  <div className="flex gap-2.5 rounded-lg border bg-muted/40 p-3">
                    <ShieldCheck className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div>
                      <div className="text-xs font-medium">Ishonchli ma’lumot</div>
                      <p className="text-xs leading-snug text-muted-foreground">
                        Har bir yozuv manbasi va yangilangan vaqti bilan saqlanadi.
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </aside>

            <div className="min-w-0 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 pb-1">
                <p className="text-sm text-muted-foreground">
                  <strong className="font-semibold tabular-nums text-foreground">
                    {number.format(totalResults)}
                  </strong>{" "}
                  ta natija
                  {shown < totalResults ? ` · ${number.format(shown)} ta ko‘rsatilmoqda` : ""}
                </p>
                <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock3 className="size-3.5" />
                  {/* Qidiruv paytida maqolalar sanaga emas, mos kelishiga
                      qarab tartiblanadi (FTS5 BM25). */}
                  {view === "journals"
                    ? "Eng faol jurnallar birinchi"
                    : query.trim()
                      ? "Eng mos maqolalar birinchi"
                      : "Eng yangi maqolalar birinchi"}
                </span>
              </div>

              <div className="flex flex-col gap-3">
                {view === "journals"
                  ? visibleJournals.map((journal) => (
                      <JournalCard key={journal.id} journal={journal} />
                    ))
                  : visibleArticles.map((article) => {
                      const journal = journalById.get(article.journalId);
                      return journal ? (
                        <ArticleCard key={article.id} article={article} journal={journal} />
                      ) : null;
                    })}
              </div>

              {shown === 0 && (
                <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-16 text-center">
                  <span className="flex size-11 items-center justify-center rounded-full border bg-muted text-muted-foreground">
                    <Search className="size-5" />
                  </span>
                  <h3 className="text-base font-semibold tracking-tight">Natija topilmadi</h3>
                  <p className="max-w-sm text-sm text-muted-foreground">
                    Qidiruv yoki filtrlarni o‘zgartirib ko‘ring.
                  </p>
                  <Button variant="outline" size="sm" onClick={resetFilters}>
                    Filtrlarni tozalash
                  </Button>
                </div>
              )}

              {!filtersActive && totalResults > PAGE_SIZE && (
                <nav aria-label="Katalog sahifalari" className="flex justify-center gap-4 py-3 text-sm">
                  <span aria-current="page">1-sahifa</span>
                  <AppLink to={`${route.kind === 'home' ? '/jurnallar' : window.location.pathname}?sahifa=2`}>
                    Keyingi sahifa →
                  </AppLink>
                  <AppLink to={`${route.kind === 'home' ? '/jurnallar' : window.location.pathname}?sahifa=${Math.ceil(totalResults / PAGE_SIZE)}`}>
                    Oxirgi sahifa
                  </AppLink>
                </nav>
              )}
              {shown > 0 && shown < totalResults && (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={loadMore}
                  disabled={loadingMore}
                >
                  {loadingMore ? (
                    <>
                      <Loader2 className="animate-spin" /> Yuklanmoqda...
                    </>
                  ) : (
                    <>
                      Yana {number.format(Math.min(PAGE_SIZE, totalResults - shown))} ta ko‘rsatish
                      <ArrowRight />
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>
        </section>

        <section id="monitoring" className="border-y bg-muted/30">
          <div className={cn(SHELL, "grid gap-8 py-12 sm:py-16 lg:grid-cols-2 lg:items-center")}>
            <div className="space-y-4">
              <Eyebrow>Avtomatik yangilanish</Eyebrow>
              <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                Indeks har doim yangilanib turadi.
              </h2>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Har bir jurnal alohida kuzatiladi. Yangi son chiqishi bilan maqolalar indeksga
                qo‘shiladi.
              </p>
              <ul className="space-y-2">
                {[
                  "Faqat o‘zgargan yozuvlar olinadi",
                  "Takroriy yozuvlar aniqlanadi",
                  "Har bir maydonning manbasi saqlanadi",
                ].map((item) => (
                  <li key={item} className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="size-4 shrink-0 text-success" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <Card className="gap-0 overflow-hidden py-0">
              <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-3">
                <span className="flex gap-1.5">
                  <i className="size-2.5 rounded-full bg-destructive/60 not-italic" />
                  <i className="size-2.5 rounded-full bg-warning/70 not-italic" />
                  <i className="size-2.5 rounded-full bg-success/70 not-italic" />
                </span>
                <strong className="text-sm font-medium">So‘nggi yangilanishlar</strong>
                <Activity className="ml-auto size-4 text-muted-foreground" />
              </div>
              <div className="divide-y">
                {recentUpdates.length === 0 && (
                  <p className="p-6 text-center text-sm text-muted-foreground">
                    Yangilanish ma’lumoti hali yo‘q.
                  </p>
                )}
                {recentUpdates.map((item) => (
                  <div key={item.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                    <time className="w-16 shrink-0 font-mono text-xs text-muted-foreground">
                      {item.when}
                    </time>
                    <span className="min-w-0 flex-1 truncate">{item.name}</span>
                    <small className="shrink-0 tabular-nums text-xs text-muted-foreground">
                      {item.articles} maqola
                    </small>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </section>

        <section id="about" className={cn(SHELL, "py-12 sm:py-16")}>
          <div className="max-w-2xl space-y-2">
            <Eyebrow>Loyiha tamoyili</Eyebrow>
            <h2 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
              Ochiq, tekshiriladigan va foydali ilmiy infratuzilma.
            </h2>
          </div>
          <div className="mt-8 grid gap-3 md:grid-cols-3">
            {[
              {
                n: "01",
                icon: Globe2,
                title: "Ochiqlik",
                text: "Metama’lumotlar va qidiruv barcha foydalanuvchilar uchun ochiq.",
              },
              {
                n: "02",
                icon: ShieldCheck,
                title: "Manba aniqligi",
                text: "Har bir maydon qayerdan va qachon olingani qayd etiladi.",
              },
              {
                n: "03",
                icon: CalendarDays,
                title: "Doimiy yangilanish",
                text: "Faqat o‘zgargan yozuvlar muntazam olinadi, indeks eskirmaydi.",
              },
            ].map((item) => (
              <Card key={item.n} className="gap-3 py-5">
                <CardContent className="space-y-2.5 px-5">
                  <div className="flex items-center justify-between">
                    <span className="flex size-9 items-center justify-center rounded-md border bg-muted text-muted-foreground">
                      <item.icon className="size-4" />
                    </span>
                    <span className="font-mono text-xs text-muted-foreground">{item.n}</span>
                  </div>
                  <h3 className="text-base font-semibold tracking-tight">{item.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{item.text}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
          </>
        )}
      </main>

      <footer className="border-t">
        <div className={cn(SHELL, "grid gap-8 py-10 sm:grid-cols-2 lg:grid-cols-4")}>
          <div className="space-y-3">
            <Brand />
            <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
              O‘zbekiston OAK jurnallari va ilmiy maqolalarining ochiq indeksi.
            </p>
          </div>
          {/* Futer havolalari indeksni butun sayt bo‘ylab bog‘laydi: robot har
              qanday sahifadan asosiy bo‘limlarga bir qadamda o‘tadi. */}
          <nav aria-label="Katalog" className="space-y-2 text-sm">
            <strong className="block text-xs uppercase tracking-widest text-muted-foreground">
              Katalog
            </strong>
            <AppLink to="/jurnallar" className="block text-muted-foreground hover:text-foreground">
              OAK jurnallari
            </AppLink>
            <AppLink to="/maqolalar" className="block text-muted-foreground hover:text-foreground">
              Ilmiy maqolalar
            </AppLink>
            <AppLink to="/sohalar" className="block text-muted-foreground hover:text-foreground">
              Ilmiy sohalar
            </AppLink>
            <AppLink to="/shaharlar" className="block text-muted-foreground hover:text-foreground">
              Shaharlar
            </AppLink>
          </nav>
          <nav aria-label="Ommabop sohalar" className="space-y-2 text-sm">
            <strong className="block text-xs uppercase tracking-widest text-muted-foreground">
              Ommabop sohalar
            </strong>
            {topFields.slice(0, 5).map((item) => (
              <AppLink
                key={item}
                to={fieldPath(item)}
                className="block text-muted-foreground hover:text-foreground"
              >
                {item}
              </AppLink>
            ))}
          </nav>
          <nav aria-label="Shaharlar" className="space-y-2 text-sm">
            <strong className="block text-xs uppercase tracking-widest text-muted-foreground">
              Shaharlar
            </strong>
            {facets.cities.slice(0, 5).map((item) => (
              <AppLink
                key={item.name}
                to={cityPath(item.name)}
                className="block text-muted-foreground hover:text-foreground"
              >
                {item.name}
              </AppLink>
            ))}
          </nav>
        </div>
        <div className={cn(SHELL, "flex flex-col items-center gap-2 border-t py-5 sm:flex-row sm:justify-between")}>
          <nav className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
            <AppLink to="/loyiha" className="text-sm text-muted-foreground hover:text-foreground">
              Loyiha haqida
            </AppLink>
            <AppLink to="/maxfiylik" className="text-sm text-muted-foreground hover:text-foreground">
              Maxfiylik
            </AppLink>
            <AppLink to="/shartlar" className="text-sm text-muted-foreground hover:text-foreground">
              Shartlar
            </AppLink>
          </nav>
          <span className="text-xs text-muted-foreground">© 2026 IlmIz · MVP 0.1</span>
        </div>
      </footer>

      {selectedJournal && <JournalSheet journal={selectedJournal} onClose={closeJournal} />}
      {pickerOpen && (
        <FieldPicker
          groups={facets.fieldGroups}
          selected={selectedFields}
          onApply={(next) => {
            setSelectedFields(next);
            setPickerOpen(false);
          }}
          onClose={() => setPickerOpen(false)}
        />
      )}
      {accountOpen && <AccountPanel onClose={() => setAccountOpen(false)} />}
    </div>
  );
}

export default App;

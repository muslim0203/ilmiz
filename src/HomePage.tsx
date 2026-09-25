import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Atom,
  BookOpen,
  Check,
  ChevronRight,
  Globe2,
  GraduationCap,
  Landmark,
  Leaf,
  Microscope,
  Pause,
  Play,
  Search,
  ShieldCheck,
} from "lucide-react";
import type { Facets, PlatformStats } from "@/api";
import type { Article, Journal } from "@/types";
import { AppLink } from "@/components/app-link";
import { articlePath, fieldPath, journalPath } from "@/lib/slug";
import { number } from "@/lib/format";
import { navigate } from "@/router";

type Props = {
  journals: Journal[];
  articles: Article[];
  stats: PlatformStats;
  facets: Facets;
  state: "loading" | "live" | "fallback";
};

const fieldIcons: Record<string, typeof BookOpen> = {
  Pedagogika: GraduationCap,
  Filologiya: BookOpen,
  Iqtisodiyot: Landmark,
  Tarix: Landmark,
  Biologiya: Leaf,
  Kimyo: Atom,
  Tibbiyot: Microscope,
};

function Institutions({ journals }: { journals: Journal[] }) {
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(false);
  const [reduced, setReduced] = useState(false);
  const ref = useRef<HTMLElement>(null);
  const institutions = useMemo(
    () =>
      [
        ...new Set(journals.map((j) => j.publisher?.trim()).filter(Boolean)),
      ].slice(0, 8),
    [journals],
  );

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener("change", update);
    const observer = new IntersectionObserver(([entry]) =>
      setVisible(entry.isIntersecting),
    );
    if (ref.current) observer.observe(ref.current);
    return () => {
      observer.disconnect();
      media.removeEventListener("change", update);
    };
  }, [institutions.length]);

  if (institutions.length === 0) return null;
  return (
    <section
      ref={ref}
      className="institutions-section"
      aria-labelledby="institutions-title"
    >
      <div className="home-shell institutions-heading">
        <div>
          <p className="section-kicker">BILIM BIZNI BIRLASHTIRADI</p>
          <h2 id="institutions-title">Universitetlar va nashriyotlar</h2>
          <p>Jurnallari IlmIz indeksida mavjud bo‘lgan ilmiy tashkilotlar.</p>
        </div>
        {!reduced && (
          <button
            className="motion-control"
            onClick={() => setPaused((v) => !v)}
            aria-label={
              paused ? "Harakatni davom ettirish" : "Harakatni to‘xtatish"
            }
            aria-pressed={paused}
          >
            {paused ? <Play size={16} /> : <Pause size={16} />}
            <span>{paused ? "Davom ettirish" : "To‘xtatish"}</span>
          </button>
        )}
      </div>
      <div
        className="institution-window"
        tabIndex={0}
        aria-label="Tashkilotlar ro‘yxati"
        data-paused={paused || !visible}
      >
        <div className="institution-track">
          {[0, 1].map((copy) => (
            <div
              className="institution-group"
              key={copy}
              aria-hidden={copy === 1 ? true : undefined}
            >
              {institutions.map((name) => (
                <div className="institution-item" key={name}>
                  <Landmark size={30} strokeWidth={1.2} />
                  <span>{name}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function DataPlaceholder({ state }: { state: Props["state"] }) {
  return (
    <div className="home-data-state" role="status">
      {state === "loading" ? (
        <>
          <span className="loading-dot" />
          Ilmiy manbalar yuklanmoqda…
        </>
      ) : state === "fallback" ? (
        <>
          Ma’lumotlarni yuklab bo‘lmadi.{" "}
          <button onClick={() => window.location.reload()}>
            Qayta urinish <ArrowRight size={14} />
          </button>
        </>
      ) : (
        "Hozircha ma’lumot mavjud emas."
      )}
    </div>
  );
}

export default function HomePage({
  journals,
  articles,
  stats,
  facets,
  state,
}: Props) {
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState<"articles" | "journals">(
    "articles",
  );
  const rootRef = useRef<HTMLDivElement>(null);
  const fields = useMemo(
    () =>
      facets.fieldGroups
        .flatMap((group) => group.fields)
        .sort((a, b) => b.articles - a.articles)
        .slice(0, 6),
    [facets],
  );
  const featured = useMemo(
    () =>
      [...journals].sort((a, b) => b.articleCount - a.articleCount).slice(0, 3),
    [journals],
  );

  useEffect(() => {
    const root = rootRef.current;
    if (
      !root ||
      !("IntersectionObserver" in window) ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.08 },
    );
    root.querySelectorAll("[data-reveal]").forEach((element) => {
      element.classList.add("reveal-ready");
      observer.observe(element);
    });
    return () => observer.disconnect();
  }, []);

  function search(event: React.FormEvent) {
    event.preventDefault();
    const value = query.trim();
    navigate(
      searchType === "articles"
        ? value
          ? `/qidiruv?q=${encodeURIComponent(value)}`
          : "/maqolalar"
        : `/jurnallar${value ? `?q=${encodeURIComponent(value)}` : ""}`,
    );
  }

  return (
    <div className="home-page" ref={rootRef}>
      <section className="home-hero">
        <div className="home-shell hero-layout">
          <div className="hero-copy">
            <div className="hero-eyebrow">
              <span /> ILMIY MEROS. YANGI IZLANISH.
            </div>
            <h1>
              O‘zbekiston OAK jurnallari <span>va ilmiy maqolalar indeksi</span>
            </h1>
            <p className="hero-description">
              O‘zbekiston OAK ro‘yxatidagi ilmiy jurnallar,
              <br className="desktop-break" /> maqolalar va tadqiqotlar — bir ochiq indeksda.
            </p>
            <div className="hero-actions">
              <AppLink to="/jurnallar" className="primary-action">Jurnallarni ko‘rish <ArrowRight size={19} /></AppLink>
              <AppLink to="/loyiha" className="secondary-action">IlmIz haqida</AppLink>
            </div>
          </div>
          <div className="hero-photograph">
            <img src="/design/moturidiy/architecture.webp" alt="Registon maydoni, Samarqand" width="1184" height="666" fetchPriority="high" decoding="async" />
          </div>
        </div>
      </section>
      <section className="search-section" aria-label="Ilmiy manbalarni qidirish">
        <div className="home-shell search-layout">
          <div className="search-intro"><p className="section-kicker">OCHIQ ILMIY INDEKS</p><h2>Izlanish shu yerdan boshlanadi</h2></div>
          <div className="search-panel">
            <form className="hero-search" onSubmit={search} role="search">
              <fieldset className="search-type">
                <legend className="sr-only">Qidiruv turi</legend>
                {(
                  [
                    ["articles", "Maqolalar"],
                    ["journals", "Jurnallar"],
                  ] as const
                ).map(([value, label]) => (
                  <label
                    key={value}
                    className={searchType === value ? "selected" : ""}
                  >
                    <input
                      type="radio"
                      name="search-type"
                      value={value}
                      checked={searchType === value}
                      onChange={() => setSearchType(value)}
                    />
                    {value === "articles" ? (
                      <Search size={15} />
                    ) : (
                      <BookOpen size={15} />
                    )}
                    {label}
                  </label>
                ))}
              </fieldset>
              <div className="search-input-row">
                <Search className="search-symbol" size={21} strokeWidth={1.7} />
                <input
                  aria-label={
                    searchType === "articles"
                      ? "Maqola yoki muallif qidirish"
                      : "Jurnal yoki ISSN qidirish"
                  }
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={
                    searchType === "articles"
                      ? "Maqola, muallif yoki kalit so‘z…"
                      : "Jurnal nomi yoki ISSN…"
                  }
                />
                <button type="submit">
                  Qidirish <ArrowUpRight size={18} />
                </button>
              </div>
            </form>
            <div className="hero-suggestions">
              <span>Yo‘nalishlar:</span>
              {fields.slice(0, 3).map((field) => (
                <AppLink key={field.name} to={fieldPath(field.name)}>
                  {field.name}
                  <ArrowUpRight size={12} />
                </AppLink>
              ))}
            </div>
            <div className="hero-note">
              <ShieldCheck size={16} />
              <span>Ochiq manbalar. Bepul foydalanish. Cheksiz izlanish.</span>
            </div>
          </div>
        </div>
      </section>

      <section className="home-stats" aria-label="Platforma ko‘rsatkichlari">
        <div className="home-shell stats-grid">
          {[
            {
              value: stats.journals,
              label: "OAK jurnallari",
              detail: "Ilmiy nashrlar katalogi",
              icon: BookOpen,
            },
            {
              value: stats.articles,
              label: "Ilmiy maqolalar",
              detail: "Izlanishingiz uchun manbalar",
              icon: GraduationCap,
            },
            {
              value: facets.fieldCount,
              label: "Ilmiy yo‘nalish",
              detail: "Fanlararo bilimlar makoni",
              icon: Atom,
            },
            {
              value: facets.cities.length,
              label: "Shahar",
              detail: "Ilm geografiyasi",
              icon: Globe2,
            },
          ].map((item) => (
            <div className="stat-item" key={item.label}>
              <item.icon size={22} strokeWidth={1.4} />
              <div>
                <strong>
                  {state === "live" ? number.format(item.value) : "—"}
                </strong>
                <span>{item.label}</span>
                <small>{item.detail}</small>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section id="discover" className="home-shell home-section" data-reveal>
        <div className="section-heading">
          <div>
            <p className="section-kicker">ILMIY YO‘NALISHLAR</p>
            <h2>Fanlar bo‘yicha izlang</h2>
          </div>
          <AppLink className="section-link" to="/sohalar">
            Barcha yo‘nalishlar <ArrowUpRight size={17} />
          </AppLink>
        </div>
        <div className="fields-grid">
          {fields.map((field, index) => {
            const Icon = fieldIcons[field.name] ?? BookOpen;
            return (
              <AppLink
                key={field.name}
                to={fieldPath(field.name)}
                className={`field-tile field-tone-${index}`}
              >
                <span className="field-icon">
                  <Icon size={25} strokeWidth={1.4} />
                </span>
                <h3>{field.name}</h3>
                <span className="field-count">
                  {number.format(field.journals)} ta jurnal
                </span>
                <ArrowUpRight className="field-arrow" size={17} />
              </AppLink>
            );
          })}
        </div>
        {!fields.length && <DataPlaceholder state={state} />}
      </section>

      <section className="journals-section" data-reveal>
        <div className="home-shell home-section">
          <div className="section-heading">
            <div>
              <p className="section-kicker">
                JURNALLAR KATALOGI
              </p>
              <h2>O‘zbekiston ilmiy jurnallari</h2>
            </div>
            <AppLink className="section-link" to="/jurnallar">
              Barcha jurnallar <ArrowUpRight size={17} />
            </AppLink>
          </div>
          <div className="featured-grid">
            {featured.map((journal, index) => (
              <article
                className={`featured-journal journal-tone-${index}`}
                key={journal.id}
              >
                <div className="journal-category"><BookOpen size={22} strokeWidth={1.4} /><span>{journal.fields[0] || "Ilmiy jurnal"}</span><span className="journal-issn">{journal.issn ? `ISSN ${journal.issn}` : ""}</span></div>
                <div className="featured-body">
                  <div className="journal-meta">
                    <span>
                      <ShieldCheck size={13} />
                      {journal.oakStatus === "active"
                        ? "OAK ro‘yxatida"
                        : "OAK holati: tekshiruvda"}
                    </span>
                    <span>{journal.city}</span>
                  </div>
                  <h3>
                    <AppLink to={journalPath(journal.id)}>
                      {journal.name}
                    </AppLink>
                  </h3>
                  <p>{journal.publisher}</p>
                  <div className="featured-footer">
                    <span>
                      <strong>{number.format(journal.articleCount)}</strong>{" "}
                      maqola
                    </span>
                    <AppLink
                      to={journalPath(journal.id)}
                      aria-label={`${journal.name} jurnalini ochish`}
                    >
                      <ArrowUpRight size={20} />
                    </AppLink>
                  </div>
                </div>
              </article>
            ))}
          </div>
          {!featured.length && <DataPlaceholder state={state} />}
        </div>
      </section>

      <section className="home-shell home-section recent-section" data-reveal>
        <div className="recent-intro">
          <p className="section-kicker">SO‘NGGI MAQOLALAR</p>
          <h2>Ilmiy izlanishlar <br />bilan tanishing</h2>
          <p>
            Indeksga qo‘shilgan maqolalar bilan tanishing. Navbatdagi
            izlanishingiz uchun kerakli manbani toping.
          </p>
          <AppLink className="section-link" to="/yangi-maqolalar">
            Yangi maqolalar <ArrowUpRight size={17} />
          </AppLink>
        </div>
        <div className="home-articles">
          {articles.slice(0, 4).map((article, index) => (
            <article className="home-article" key={article.id}>
              <span className="article-number">0{index + 1}</span>
              <div>
                <div className="article-meta">
                  <span>{article.fields[0] || "Ilmiy maqola"}</span>
                  <span>{article.publicationDate || article.year || ""}</span>
                </div>
                <h3>
                  <AppLink to={articlePath(article.id, article.title)}>
                    {article.title}
                  </AppLink>
                </h3>
                <p>{article.authors.join(", ") || "Muallif ko‘rsatilmagan"}</p>
              </div>
              <AppLink
                className="article-arrow"
                to={articlePath(article.id, article.title)}
                aria-label={`${article.title} maqolasini o‘qish`}
              >
                <ArrowUpRight size={21} />
              </AppLink>
            </article>
          ))}
          {!articles.length && <DataPlaceholder state={state} />}
        </div>
      </section>

      <Institutions journals={journals} />

      <section className="home-shell home-section" data-reveal>
        <div className="research-banner">
          <div>
            <p className="section-kicker">ILM HAMMA UCHUN OCHIQ</p>
            <h2>
              Bir izlanish.
              <br />
              Minglab imkoniyat.
            </h2>
            <p>
              Kerakli maqolani toping, manbasini tekshiring
              <br className="desktop-break" /> va tayyor iqtibosdan foydalaning.
            </p>
            <AppLink to="/maqolalar" className="banner-button">
              Izlanishni boshlash <ArrowUpRight size={18} />
            </AppLink>
          </div>
          <div className="banner-steps">
            {[
              {
                icon: Search,
                title: "Izlang",
                text: "Mavzu, muallif yoki kalit so‘z bo‘yicha",
              },
              {
                icon: ShieldCheck,
                title: "O‘rganing",
                text: "Asl manba va jurnal ma’lumotlari bilan",
              },
              {
                icon: Check,
                title: "Iqtibos oling",
                text: "APA, GOST, MLA va boshqa formatlarda",
              },
            ].map((step, index) => (
              <div key={step.title}>
                <span className="step-icon">
                  <step.icon size={20} />
                </span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.text}</p>
                </div>
                <span className="step-number">0{index + 1}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="home-colophon">
          <span>Milliy ilmiy meros. Umumiy kelajak.</span>
          <AppLink to="/loyiha">
            IlmIz haqida <ChevronRight size={15} />
          </AppLink>
        </div>
      </section>
    </div>
  );
}

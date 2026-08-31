import { useEffect, useState } from 'react';
import { loadSeoPage, type SeoPage } from '@/lib/head';

/** Identical crawlable archive content before and after JavaScript renders. */
export default function ArchivePage({ path }: { path: string }) {
  const [page, setPage] = useState<SeoPage | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setPage(null);
    setFailed(false);
    loadSeoPage(path).then(value => { if (active) setPage(value); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [path]);
  // Only our escaped renderer provides this HTML, never raw harvested HTML.
  if (page) return <section className="seo-shell" dangerouslySetInnerHTML={{ __html: page.body }} />;
  return <section className="mx-auto max-w-4xl px-6 py-16" aria-live="polite">
    {failed ? 'Arxivni yuklab bo‘lmadi. Sahifani qayta ochib ko‘ring.' : 'Arxiv yuklanmoqda…'}
  </section>;
}

import { useEffect, useRef, useState } from 'react';
import { loadSeoPage, type SeoPage } from '@/lib/head';
import { initialShell } from '@/lib/ssr';

/** Identical crawlable archive content before and after JavaScript renders. */
export default function ArchivePage({ path }: { path: string }) {
  // Birinchi yuklashda server allaqachon shu HTML'ni bergan — uni qayta
  // so'ramaymiz (miltillash yo'q, `/api/seo` ga qo'shimcha so'rov yo'q).
  const [page, setPage] = useState<SeoPage | null>(() => {
    const body = initialShell(path);
    return body ? { head: '', body, status: 200, path } : null;
  });
  const seededPath = useRef<string | null>(page?.path ?? null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (seededPath.current === path) {
      seededPath.current = null;
      return;
    }
    let active = true;
    setFailed(false);
    setPage(null);
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

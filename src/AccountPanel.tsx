import { useEffect, useState } from "react";
import { CheckCircle2, LogOut, ShieldCheck, UserRound, X } from "lucide-react";
import {
  PROVIDER_LABELS,
  loadCurrentUser,
  loadProviders,
  logout,
  startLogin,
  updateProfile,
  type AuthUser,
} from "./authApi";

const ORCID_HELP = "ORCID — tadqiqotchining xalqaro identifikatori. orcid.org da bepul olinadi.";

export default function AccountPanel({ onClose }: { onClose: () => void }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [providers, setProviders] = useState<string[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState({ displayName: "", affiliation: "", scholarUrl: "" });

  useEffect(() => {
    let active = true;
    Promise.all([loadCurrentUser(), loadProviders()])
      .then(([currentUser, available]) => {
        if (!active) return;
        setUser(currentUser);
        setProviders(available);
        if (currentUser) {
          setDraft({
            displayName: currentUser.displayName,
            affiliation: currentUser.affiliation ?? "",
            scholarUrl: currentUser.scholarUrl ?? "",
          });
        }
        setState("ready");
      })
      .catch(() => { if (active) setState("error"); });
    return () => { active = false; };
  }, []);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const saved = await updateProfile({
        display_name: draft.displayName.trim(),
        affiliation: draft.affiliation.trim(),
        // Bo'sh havola yuborilsa validatsiya yiqiladi, shuning uchun faqat to'lganini yuboramiz.
        ...(draft.scholarUrl.trim() ? { scholar_url: draft.scholarUrl.trim() } : {}),
      });
      setUser(saved);
      setMessage("Profil saqlandi.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Saqlanmadi");
    } finally {
      setSaving(false);
    }
  };

  const signOut = async () => {
    await logout().catch(() => undefined);
    setUser(null);
  };

  return (
    <div className="picker-backdrop" role="dialog" aria-modal="true" aria-label="Hisob" onMouseDown={onClose}>
      <div className="account-panel" onMouseDown={(event) => event.stopPropagation()}>
        <header className="picker-head">
          <h2>{user ? "Mening profilim" : "Tizimga kirish"}</h2>
          <button className="picker-close" onClick={onClose} aria-label="Yopish"><X size={18} /></button>
        </header>

        {state === "loading" && <p className="account-note">Yuklanmoqda...</p>}
        {state === "error" && <p className="account-note error">Hisob ma’lumotlari olinmadi.</p>}

        {state === "ready" && !user && (
          <div className="account-login">
            <UserRound size={30} />
            <p>Profil ochish uchun quyidagi xizmatlardan biri orqali kiring. Parol talab qilinmaydi.</p>
            {providers.length === 0 ? (
              <p className="account-note error">
                Hech bir provayder sozlanmagan. Server tomonida <code>ORCID_CLIENT_ID</code> yoki
                {" "}<code>GOOGLE_CLIENT_ID</code> muhit o‘zgaruvchilari kerak.
              </p>
            ) : (
              <div className="account-providers">
                {providers.map((provider) => (
                  <button key={provider} className={`provider-button provider-${provider}`} onClick={() => startLogin(provider)}>
                    {PROVIDER_LABELS[provider] ?? provider}
                  </button>
                ))}
              </div>
            )}
            {providers.includes("orcid") && <small className="account-hint">{ORCID_HELP}</small>}
          </div>
        )}

        {state === "ready" && user && (
          <form className="account-form" onSubmit={save}>
            <div className="account-identity">
              <span className="account-avatar">{user.displayName.slice(0, 2).toUpperCase()}</span>
              <div>
                <strong>{user.displayName}</strong>
                <span>{user.email ?? "e-pochta ko‘rsatilmagan"}</span>
                <span className="account-provider">
                  <ShieldCheck size={13} /> {user.provider === "orcid" ? "ORCID" : "Google"} orqali kirgan
                </span>
              </div>
            </div>

            {user.orcid && (
              <p className="account-orcid">
                <CheckCircle2 size={14} /> ORCID:{" "}
                <a href={`https://orcid.org/${user.orcid}`} target="_blank" rel="noreferrer">{user.orcid}</a>
              </p>
            )}

            <label>
              <span>Ism va familiya</span>
              <input value={draft.displayName} onChange={(event) => setDraft({ ...draft, displayName: event.target.value })} />
            </label>
            <label>
              <span>Ish joyi</span>
              <input
                value={draft.affiliation}
                onChange={(event) => setDraft({ ...draft, affiliation: event.target.value })}
                placeholder="Masalan: Toshkent davlat universiteti"
              />
            </label>
            <label>
              <span>Google Scholar profili</span>
              <input
                value={draft.scholarUrl}
                onChange={(event) => setDraft({ ...draft, scholarUrl: event.target.value })}
                placeholder="https://scholar.google.com/citations?user=..."
              />
              <small>Google Scholar’da kirish xizmati yo‘q, shuning uchun havolani o‘zingiz kiritasiz.</small>
            </label>

            {message && <p className="account-note success">{message}</p>}
            {error && <p className="account-note error">{error}</p>}

            <div className="account-actions">
              <button type="button" className="account-signout" onClick={() => void signOut()}>
                <LogOut size={15} /> Chiqish
              </button>
              <button type="submit" className="picker-ok" disabled={saving || !draft.displayName.trim()}>
                {saving ? "Saqlanmoqda..." : "Saqlash"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

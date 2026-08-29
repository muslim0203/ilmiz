import { useEffect, useState } from "react";
import { CheckCircle2, LogOut, ShieldCheck, UserRound } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  PROVIDER_LABELS,
  loadCurrentUser,
  loadProviders,
  logout,
  startLogin,
  updateProfile,
  type AuthUser,
} from "@/authApi";
import { monogram } from "@/lib/format";
import MyArticles from "@/MyArticles";

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
      .catch(() => {
        if (active) setState("error");
      });
    return () => {
      active = false;
    };
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
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{user ? "Mening profilim" : "Tizimga kirish"}</DialogTitle>
          <DialogDescription>
            {user
              ? "Profil ma’lumotlaringiz maqola mualliflari bilan bog‘lanadi."
              : "Parolsiz kirish — ORCID yoki Google hisobi orqali."}
          </DialogDescription>
        </DialogHeader>

        {state === "loading" && (
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-2/3" />
          </div>
        )}

        {state === "error" && (
          <Alert variant="destructive">
            <AlertDescription>Hisob ma’lumotlari olinmadi.</AlertDescription>
          </Alert>
        )}

        {state === "ready" && !user && (
          <div className="space-y-4">
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-6 text-center">
              <span className="flex size-11 items-center justify-center rounded-full border bg-muted text-muted-foreground">
                <UserRound className="size-5" />
              </span>
              <p className="text-sm text-muted-foreground">
                Profil ochish uchun quyidagi xizmatlardan biri orqali kiring. Parol talab
                qilinmaydi.
              </p>
            </div>

            {providers.length === 0 ? (
              <Alert variant="destructive">
                <AlertDescription>
                  Hech bir provayder sozlanmagan. Server tomonida{" "}
                  <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                    ORCID_CLIENT_ID
                  </code>{" "}
                  yoki{" "}
                  <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                    GOOGLE_CLIENT_ID
                  </code>{" "}
                  muhit o‘zgaruvchilari kerak.
                </AlertDescription>
              </Alert>
            ) : (
              <div className="grid gap-2">
                {providers.map((provider) => (
                  <Button
                    key={provider}
                    variant={provider === "orcid" ? "default" : "outline"}
                    size="lg"
                    onClick={() => startLogin(provider)}
                  >
                    {PROVIDER_LABELS[provider] ?? provider}
                  </Button>
                ))}
              </div>
            )}

            {providers.includes("orcid") && (
              <p className="text-xs leading-relaxed text-muted-foreground">{ORCID_HELP}</p>
            )}
          </div>
        )}

        {state === "ready" && user && (
          <form className="space-y-4" onSubmit={save}>
            <div className="flex items-center gap-3 rounded-lg border p-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                {monogram(user.displayName)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold">{user.displayName}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {user.email ?? "e-pochta ko‘rsatilmagan"}
                </div>
              </div>
              <Badge variant="outline" className="gap-1 font-normal">
                <ShieldCheck />
                {user.provider === "orcid" ? "ORCID" : "Google"}
              </Badge>
            </div>

            {user.orcid && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <CheckCircle2 className="size-3.5 text-success" /> ORCID:{" "}
                <a
                  href={`https://orcid.org/${user.orcid}`}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-foreground underline-offset-4 hover:underline"
                >
                  {user.orcid}
                </a>
              </p>
            )}

            <Separator />

            <div className="space-y-2">
              <Label htmlFor="display-name">Ism va familiya</Label>
              <Input
                id="display-name"
                value={draft.displayName}
                onChange={(event) => setDraft({ ...draft, displayName: event.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="affiliation">Ish joyi</Label>
              <Input
                id="affiliation"
                value={draft.affiliation}
                onChange={(event) => setDraft({ ...draft, affiliation: event.target.value })}
                placeholder="Masalan: Toshkent davlat universiteti"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="scholar-url">Google Scholar profili</Label>
              <Input
                id="scholar-url"
                value={draft.scholarUrl}
                onChange={(event) => setDraft({ ...draft, scholarUrl: event.target.value })}
                placeholder="https://scholar.google.com/citations?user=..."
              />
              <p className="text-xs text-muted-foreground">
                Google Scholar’da kirish xizmati yo‘q, shuning uchun havolani o‘zingiz kiritasiz.
              </p>
            </div>

            {message && (
              <Alert variant="success">
                <CheckCircle2 />
                <AlertDescription>{message}</AlertDescription>
              </Alert>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="flex items-center justify-between gap-2 pt-1">
              <Button type="button" variant="ghost" onClick={() => void signOut()}>
                <LogOut /> Chiqish
              </Button>
              <Button type="submit" disabled={saving || !draft.displayName.trim()}>
                {saving ? "Saqlanmoqda..." : "Saqlash"}
              </Button>
            </div>
          </form>
        )}

        {state === "ready" && user && (
          <>
            <Separator />
            {/* Saqlangan ism bo'yicha qidiriladi, tahrirdagi qoralama bo'yicha emas. */}
            <MyArticles displayName={user.displayName} />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

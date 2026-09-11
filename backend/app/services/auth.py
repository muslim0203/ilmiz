"""ORCID va Google orqali kirish.

Nega aynan shu ikkitasi:

- **ORCID** ilmiy muhitning standart identifikatori va to'liq OAuth 2.0
  provayderi. Tadqiqotchi uchun eng to'g'ri variant.
- **Google** oddiy OAuth provayderi.
- **Google Scholar** provayder emas: unda na OAuth, na ochiq API bor.
  Shuning uchun Scholar profili faqat havola sifatida saqlanadi va
  foydalanuvchi uni o'zi kiritadi.

Parol saqlanmaydi. Sessiya tokeni serverda faqat SHA-256 hash ko'rinishida
turadi.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from ..models import OAuthState, User, UserArticle, UserIdentity, UserSession
from . import orcid_profile

logger = logging.getLogger(__name__)

SESSION_COOKIE = "ilmiz_session"
SESSION_TTL = timedelta(days=30)
STATE_TTL = timedelta(minutes=15)
ORCID_RE_LENGTH = 19  # 0000-0000-0000-0000


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    authorize_url: str
    token_url: str
    scope: str
    client_id: str
    client_secret: str
    userinfo_url: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


@dataclass
class ProviderIdentity:
    """Provayderdan kelgan, bizga kerak bo'lgan minimal ma'lumot."""

    subject: str
    display_name: str
    email: str | None = None
    orcid: str | None = None
    affiliation: str | None = None
    affiliation_ror: str | None = None


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def orcid_config() -> ProviderConfig:
    # Sandbox bilan ishlash uchun bazani almashtirish mumkin.
    base = _env("ORCID_BASE_URL") or "https://orcid.org"
    return ProviderConfig(
        name="orcid",
        authorize_url=f"{base}/oauth/authorize",
        token_url=f"{base}/oauth/token",
        scope="/authenticate",
        client_id=_env("ORCID_CLIENT_ID"),
        client_secret=_env("ORCID_CLIENT_SECRET"),
    )


def google_config() -> ProviderConfig:
    return ProviderConfig(
        name="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
        scope="openid email profile",
        client_id=_env("GOOGLE_CLIENT_ID"),
        client_secret=_env("GOOGLE_CLIENT_SECRET"),
    )


def provider_config(name: str) -> ProviderConfig:
    if name == "orcid":
        return orcid_config()
    if name == "google":
        return google_config()
    raise ValueError(f"noma'lum provayder: {name}")


def public_base_url() -> str:
    return (_env("ILMIZ_PUBLIC_URL") or "http://127.0.0.1:5173").rstrip("/")


def redirect_uri(provider: str) -> str:
    return f"{public_base_url()}/api/auth/{provider}/callback"


# `redirect_to` uchun oqilona chegara; frontend `window.location.href` yuboradi.
MAX_REDIRECT_LENGTH = 2048


def safe_redirect(value: str | None) -> str | None:
    """Kirishdan keyin qaytish manzilini faqat o'z saytimiz bilan cheklaydi.

    Ilgari `?redirect_to=https://evil.example` tekshirilmasdan saqlanib,
    muvaffaqiyatli kirishdan so'ng aynan o'sha manzilga 307 qaytarilardi —
    ochiq yo'naltirish (fishing havolasi ilmiz.uz nomidan ko'rinardi).

    Ruxsat: `/` bilan boshlanuvchi nisbiy yo'l (`//host` emas) yoki sxema va
    hosti `ILMIZ_PUBLIC_URL` ga teng absolyut URL. Qolgani `None` — bosh sahifa.
    """
    if not value:
        return None
    value = value.strip()
    if not value or len(value) > MAX_REDIRECT_LENGTH or not value.isprintable() or "\\" in value:
        return None
    if value.startswith("/"):
        return None if value.startswith("//") else value
    parsed = urlsplit(value)
    base = urlsplit(public_base_url())
    if parsed.scheme == base.scheme and parsed.netloc.casefold() == base.netloc.casefold():
        return value
    return None


def available_providers() -> list[str]:
    return [name for name in ("orcid", "google") if provider_config(name).configured]


# --- state ---------------------------------------------------------------

def create_state(
    db: Session, provider: str, redirect_to: str | None, *, link_user_id: int | None = None
) -> str:
    db.execute(delete(OAuthState).where(OAuthState.created_at < datetime.now(timezone.utc) - STATE_TTL))
    state = secrets.token_urlsafe(32)
    db.add(OAuthState(state=state, provider=provider, redirect_to=redirect_to, link_user_id=link_user_id))
    db.commit()
    return state


def consume_state(db: Session, provider: str, state: str) -> str | None:
    return consume_state_link(db, provider, state)[0]


def consume_state_link(db: Session, provider: str, state: str) -> tuple[str | None, int | None]:
    """State'ni bir marta ishlatadi va o'chiradi; `redirect_to` ni qaytaradi.

    Noto'g'ri yoki muddati o'tgan state — `LookupError`. Ilgari bu holat ham
    `None` bilan bildirilardi, `redirect_to` bo'sh bo'lgan haqiqiy state ham
    `None` qaytarardi; `main.py` ikkalasini ajrata olmay, qator allaqachon
    o'chirilgani uchun `redirect_to`siz kirishni doim 400 bilan rad etardi.
    """
    row = db.scalar(select(OAuthState).where(OAuthState.state == state, OAuthState.provider == provider))
    if row is None:
        raise LookupError("state topilmadi")
    fresh = row.created_at.replace(tzinfo=timezone.utc) >= datetime.now(timezone.utc) - STATE_TTL
    redirect_to, link_user_id = row.redirect_to, row.link_user_id
    db.delete(row)
    db.commit()
    if not fresh:
        raise LookupError("state muddati o'tgan")
    return redirect_to, link_user_id


def authorize_url(provider: str, state: str) -> str:
    config = provider_config(provider)
    params = {
        "client_id": config.client_id,
        "response_type": "code",
        "scope": config.scope,
        "redirect_uri": redirect_uri(provider),
        "state": state,
    }
    return f"{config.authorize_url}?{urlencode(params)}"


# --- token almashish -----------------------------------------------------

def _normalise_orcid(value: str) -> str | None:
    value = (value or "").strip()
    return value if len(value) == ORCID_RE_LENGTH else None


def exchange_code(provider: str, code: str, *, timeout: int = 20) -> ProviderIdentity:
    """Kodni tokenga almashtiradi va provayder identifikatorini qaytaradi."""
    config = provider_config(provider)
    if not config.configured:
        raise RuntimeError(f"{provider} sozlanmagan")
    payload = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(provider),
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(config.token_url, data=payload, headers={"Accept": "application/json"})
        response.raise_for_status()
        token = response.json()

        if provider == "orcid":
            # ORCID token javobining o'zida iD va ism bo'ladi. Ish joyi
            # alohida so'rov bilan olinadi; u yiqilsa kirish davom etadi.
            orcid = _normalise_orcid(str(token.get("orcid") or ""))
            if not orcid:
                raise RuntimeError("ORCID javobida iD yo'q")
            affiliation = orcid_profile.fetch_current(client, orcid, str(token.get("access_token") or ""))
            return ProviderIdentity(
                subject=orcid,
                display_name=str(token.get("name") or orcid),
                orcid=orcid,
                affiliation=affiliation.name if affiliation else None,
                affiliation_ror=affiliation.ror_id if affiliation else None,
            )

        access_token = token.get("access_token")
        if not access_token:
            raise RuntimeError("Google javobida access_token yo'q")
        info = client.get(
            config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info.raise_for_status()
        data = info.json()
        subject = str(data.get("sub") or "")
        if not subject:
            raise RuntimeError("Google javobida sub yo'q")
        # Tasdiqlanmagan pochta saqlanmaydi: `grant-admin` pochta bo'yicha
        # huquq beradi, tasdiqlanmagan pochta bilan begona odam o'sha
        # manzilni "egallashi" mumkin edi.
        email = data.get("email") if data.get("email_verified") is True else None
        return ProviderIdentity(
            subject=subject,
            display_name=str(data.get("name") or email or subject),
            email=email,
        )


# --- foydalanuvchi va sessiya --------------------------------------------

def _find_identity(db: Session, provider: str, subject: str) -> UserIdentity | None:
    return db.scalar(
        select(UserIdentity).where(UserIdentity.provider == provider, UserIdentity.subject == subject)
    )


def _apply_identity(user: User, provider: str, identity: ProviderIdentity) -> None:
    """Provayder bergan ma'lumotni profilga yozadi (ism bundan mustasno).

    Ism faqat profil ochilganda olinadi: ilgari har kirishda provayderdagi ism
    foydalanuvchi tahririni ustidan yozardi, ulangan ikki provayder esa uni
    har kirishda almashtirib turgan bo'lardi.
    """
    if identity.email:
        user.email = identity.email
    if identity.orcid and not user.orcid:
        user.orcid = identity.orcid
    # Provayderdan kelgan ish joyi faqat bo'sh joyni yoki avval ham shu yo'l
    # bilan to'ldirilganini yangilaydi — foydalanuvchi yozganini emas.
    autofilled = user.affiliation_source == provider
    if identity.affiliation and (autofilled or (user.affiliation_source is None and not user.affiliation)):
        user.affiliation = identity.affiliation
        user.affiliation_ror = identity.affiliation_ror
        user.affiliation_source = provider


def upsert_user(db: Session, provider: str, identity: ProviderIdentity) -> User:
    now = datetime.now(timezone.utc)
    link = _find_identity(db, provider, identity.subject)
    user = link.user if link is not None else None
    if user is None and identity.orcid:
        user = db.scalar(select(User).where(User.orcid == identity.orcid))
    if user is None:
        user = User(provider=provider, provider_subject=identity.subject, display_name=identity.display_name)
        db.add(user)
    if link is None:
        link = UserIdentity(user=user, provider=provider, subject=identity.subject)
        db.add(link)
    link.last_login_at = now
    _apply_identity(user, provider, identity)
    user.last_login_at = now
    db.commit()
    db.refresh(user)
    return user


# --- hisoblarni bog'lash -------------------------------------------------

class LinkError(Exception):
    """Ulash rad etildi; `code` frontend'ga `?hisob=` sifatida qaytadi."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def merge_users(db: Session, *, keep: User, drop: User) -> None:
    """`drop` profilini `keep` ga qo'shib o'chiradi. Commit qilmaydi.

    Ko'chiriladi: kirish usullari, tasdiqlangan maqolalar (ikkalasida bor
    bo'lsa bittasi qoladi), sessiyalar. `keep` dagi bo'sh maydonlar
    (ORCID iD, e-pochta, Scholar, ish joyi) `drop` dan to'ldiriladi,
    to'lganlariga tegilmaydi. Admin huquqi ikkalasidan birida bo'lsa qoladi.
    """
    if keep.id == drop.id:
        raise ValueError("bir xil profilni o'zi bilan birlashtirib bo'lmaydi")
    db.flush()
    carried = {
        "orcid": drop.orcid, "email": drop.email, "scholar_url": drop.scholar_url,
        "affiliation": drop.affiliation, "affiliation_ror": drop.affiliation_ror,
        "affiliation_source": drop.affiliation_source, "is_admin": drop.is_admin,
        "created_at": drop.created_at, "last_login_at": drop.last_login_at,
    }
    no_sync = {"synchronize_session": False}
    kept_articles = select(UserArticle.article_id).where(UserArticle.user_id == keep.id)
    db.execute(
        update(UserArticle)
        .where(UserArticle.user_id == drop.id, UserArticle.article_id.not_in(kept_articles))
        .values(user_id=keep.id)
        .execution_options(**no_sync)
    )
    db.execute(delete(UserArticle).where(UserArticle.user_id == drop.id).execution_options(**no_sync))
    db.execute(update(UserIdentity).where(UserIdentity.user_id == drop.id).values(user_id=keep.id).execution_options(**no_sync))
    db.execute(update(UserSession).where(UserSession.user_id == drop.id).values(user_id=keep.id).execution_options(**no_sync))
    db.execute(delete(OAuthState).where(OAuthState.link_user_id == drop.id).execution_options(**no_sync))
    db.execute(delete(User).where(User.id == drop.id).execution_options(**no_sync))
    db.expunge(drop)
    db.expire_all()

    for field in ("orcid", "email", "scholar_url"):
        if not getattr(keep, field) and carried[field]:
            setattr(keep, field, carried[field])
    if not keep.affiliation and carried["affiliation"]:
        keep.affiliation = carried["affiliation"]
        keep.affiliation_ror = carried["affiliation_ror"]
        keep.affiliation_source = carried["affiliation_source"]
    keep.is_admin = bool(keep.is_admin or carried["is_admin"])
    if carried["created_at"] and (keep.created_at is None or carried["created_at"] < keep.created_at):
        keep.created_at = carried["created_at"]
    if carried["last_login_at"] and (keep.last_login_at is None or carried["last_login_at"] > keep.last_login_at):
        keep.last_login_at = carried["last_login_at"]
    db.flush()


def link_identity(db: Session, user: User, provider: str, identity: ProviderIdentity) -> str:
    """Kirgan foydalanuvchiga yana bir kirish usulini ulaydi.

    Natija: `ulandi`, `birlashtirildi` (usul boshqa profilga tegishli edi —
    foydalanuvchi ikkalasini ham boshqarishini provayder orqali isbotladi)
    yoki `allaqachon`. Rad etilsa `LinkError`.
    """
    now = datetime.now(timezone.utc)
    link = _find_identity(db, provider, identity.subject)
    if link is not None and link.user_id == user.id:
        link.last_login_at = now
        db.commit()
        return "allaqachon"
    mine = {item.provider for item in user.identities}
    if provider in mine:
        raise LinkError("provayder-band")
    other = link.user if link is not None else None
    if other is None and identity.orcid:
        other = db.scalar(select(User).where(User.orcid == identity.orcid, User.id != user.id))
    if identity.orcid and user.orcid and identity.orcid != user.orcid:
        raise LinkError("boshqa-orcid")
    outcome = "ulandi"
    if other is not None:
        if {item.provider for item in other.identities} & mine:
            raise LinkError("birlashtirib-bolmaydi")
        if other.orcid and user.orcid and other.orcid != user.orcid:
            raise LinkError("boshqa-orcid")
        merge_users(db, keep=user, drop=other)
        outcome = "birlashtirildi"
        link = _find_identity(db, provider, identity.subject)
    if link is None:
        link = UserIdentity(user_id=user.id, provider=provider, subject=identity.subject)
        db.add(link)
    link.last_login_at = now
    _apply_identity(user, provider, identity)
    db.commit()
    db.refresh(user)
    return outcome


def with_query(url: str, **params: str) -> str:
    """Manzilga querystring parametrlarini qo'shadi (borini almashtiradi)."""
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key not in params]
    query += list(params.items())
    return urlunsplit(parts._replace(query=urlencode(query)))


def account_summary(db: Session, user: User) -> dict[str, object]:
    """CLI uchun profilning qisqa tavsifi (sirlarsiz)."""
    return {
        "id": user.id,
        "ism": user.display_name,
        "kirish_usullari": sorted({item.provider for item in user.identities}),
        "orcid_bor": bool(user.orcid),
        "email_bor": bool(user.email),
        "ish_joyi": user.affiliation,
        "is_admin": user.is_admin,
        "maqolalar": db.scalar(select(func.count()).select_from(UserArticle).where(UserArticle.user_id == user.id)),
        "sessiyalar": db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)),
        "yaratilgan": user.created_at.isoformat() if user.created_at else None,
    }


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# Bir foydalanuvchida shuncha faol sessiyadan ortig'i (eng eskilari) o'chiriladi.
MAX_SESSIONS_PER_USER = 10


def _prune_sessions(db: Session, user: User) -> None:
    """Muddati o'tganlarni va foydalanuvchining ortiqcha sessiyalarini o'chiradi.

    Ilgari muddati o'tgan sessiya faqat o'sha token bilan qayta kelinganda
    o'chirilardi — qaytmagan foydalanuvchilarniki abadiy qolardi, soni ham
    cheklanmagan edi.
    """
    now = datetime.now(timezone.utc)
    db.execute(delete(UserSession).where(UserSession.expires_at < now))
    extra = list(
        db.scalars(
            select(UserSession.id)
            .where(UserSession.user_id == user.id)
            .order_by(UserSession.created_at.desc())
            .offset(MAX_SESSIONS_PER_USER - 1)
        )
    )
    if extra:
        db.execute(delete(UserSession).where(UserSession.id.in_(extra)))


def create_session(db: Session, user: User, *, user_agent: str | None = None) -> str:
    """Sessiya yaratadi va TOKENNI qaytaradi. Bazada faqat hash saqlanadi."""
    _prune_sessions(db, user)
    token = secrets.token_urlsafe(48)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(timezone.utc) + SESSION_TTL,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    db.commit()
    return token


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == _hash_token(token)))
    if session is None:
        return None
    if session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        return None
    return session.user if session.user and session.user.is_active else None


def revoke_session(db: Session, token: str | None) -> bool:
    if not token:
        return False
    session = db.scalar(select(UserSession).where(UserSession.token_hash == _hash_token(token)))
    if session is None:
        return False
    db.delete(session)
    db.commit()
    return True


def any_admin_exists(db: Session) -> bool:
    return db.scalar(select(User.id).where(User.is_admin.is_(True), User.is_active.is_(True))) is not None


def grant_admin(db: Session, identifier: str, *, revoke: bool = False) -> User | None:
    """ORCID iD yoki e-pochta bo'yicha admin huquqini beradi/oladi."""
    needle = identifier.strip()
    matches = list(db.scalars(select(User).where(or_(User.orcid == needle, User.email == needle))))
    if not matches:
        return None
    if len(matches) > 1:
        # `users.email` unique emas (ORCID va Google hisoblari bir pochtani
        # ko'rsatishi mumkin); birinchisiga berish noto'g'ri odamga tushardi.
        described = ", ".join(f"#{item.id} ({item.provider})" for item in matches)
        raise ValueError(f"Bir nechta foydalanuvchi mos keladi: {described}. Aniq ORCID iD bering.")
    user = matches[0]
    user.is_admin = not revoke
    db.commit()
    db.refresh(user)
    return user


def user_payload(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "provider": user.provider,
        "providers": sorted({item.provider for item in user.identities}) or [user.provider],
        "isAdmin": user.is_admin,
        "displayName": user.display_name,
        "email": user.email,
        "orcid": user.orcid,
        "affiliation": user.affiliation,
        "affiliationRor": user.affiliation_ror,
        "affiliationSource": user.affiliation_source,
        "scholarUrl": user.scholar_url,
        "createdAt": user.created_at.isoformat(),
        "lastLoginAt": user.last_login_at.isoformat() if user.last_login_at else None,
    }

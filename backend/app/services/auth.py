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
from urllib.parse import urlencode, urlsplit

import httpx
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..models import OAuthState, User, UserSession

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

def create_state(db: Session, provider: str, redirect_to: str | None) -> str:
    db.execute(delete(OAuthState).where(OAuthState.created_at < datetime.now(timezone.utc) - STATE_TTL))
    state = secrets.token_urlsafe(32)
    db.add(OAuthState(state=state, provider=provider, redirect_to=redirect_to))
    db.commit()
    return state


def consume_state(db: Session, provider: str, state: str) -> str | None:
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
    redirect_to = row.redirect_to
    db.delete(row)
    db.commit()
    if not fresh:
        raise LookupError("state muddati o'tgan")
    return redirect_to


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
            # ORCID token javobining o'zida iD va ism bo'ladi — qo'shimcha
            # so'rov shart emas.
            orcid = _normalise_orcid(str(token.get("orcid") or ""))
            if not orcid:
                raise RuntimeError("ORCID javobida iD yo'q")
            return ProviderIdentity(
                subject=orcid,
                display_name=str(token.get("name") or orcid),
                orcid=orcid,
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

def upsert_user(db: Session, provider: str, identity: ProviderIdentity) -> User:
    user = db.scalar(
        select(User).where(User.provider == provider, User.provider_subject == identity.subject)
    )
    if user is None and identity.orcid:
        # Bir odam avval Google bilan kirgan bo'lsa ham, ORCID bir xil bo'lsa
        # yangi hisob ochmaymiz.
        user = db.scalar(select(User).where(User.orcid == identity.orcid))
    if user is None:
        user = User(provider=provider, provider_subject=identity.subject, display_name=identity.display_name)
        db.add(user)
    user.display_name = identity.display_name or user.display_name
    if identity.email:
        user.email = identity.email
    if identity.orcid:
        user.orcid = identity.orcid
    if identity.affiliation and identity.affiliation != user.affiliation:
        user.affiliation = identity.affiliation
        # Eski ROR bog'lanishi boshqa tashkilotga tegishli bo'lib qolardi.
        user.affiliation_ror = None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


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
        "isAdmin": user.is_admin,
        "displayName": user.display_name,
        "email": user.email,
        "orcid": user.orcid,
        "affiliation": user.affiliation,
        "affiliationRor": user.affiliation_ror,
        "scholarUrl": user.scholar_url,
        "createdAt": user.created_at.isoformat(),
        "lastLoginAt": user.last_login_at.isoformat() if user.last_login_at else None,
    }

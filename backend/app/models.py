from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Journal(Base):
    __tablename__ = "journals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500))
    short_name: Mapped[str] = mapped_column(String(120))
    publisher: Mapped[str] = mapped_column(String(500))
    city: Mapped[str] = mapped_column(String(120), index=True)
    fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    issn: Mapped[str | None] = mapped_column(String(9), nullable=True, index=True)
    eissn: Mapped[str | None] = mapped_column(String(9), nullable=True, index=True)
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    oak_status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    access: Mapped[str] = mapped_column(String(20), default="unknown")
    founded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    articles: Mapped[list[Article]] = relationship(back_populates="journal", cascade="all, delete-orphan")
    harvest_sources: Mapped[list[HarvestSource]] = relationship(back_populates="journal", cascade="all, delete-orphan")
    profile: Mapped[JournalProfile | None] = relationship(back_populates="journal", cascade="all, delete-orphan", uselist=False)
    contacts: Mapped[list[JournalContact]] = relationship(back_populates="journal", cascade="all, delete-orphan")
    editorial_members: Mapped[list[EditorialMember]] = relationship(back_populates="journal", cascade="all, delete-orphan")
    policies: Mapped[list[JournalPolicy]] = relationship(back_populates="journal", cascade="all, delete-orphan")
    sections: Mapped[list[JournalSection]] = relationship(back_populates="journal", cascade="all, delete-orphan")
    indexing_claims: Mapped[list[JournalIndexingClaim]] = relationship(back_populates="journal", cascade="all, delete-orphan")
    links: Mapped[list[JournalLink]] = relationship(back_populates="journal", cascade="all, delete-orphan")
    profile_fields: Mapped[list[JournalProfileField]] = relationship(back_populates="journal", cascade="all, delete-orphan")


class JournalProfile(Base):
    __tablename__ = "journal_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), unique=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    aims_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    peer_review: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_frequency: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    completeness_score: Mapped[float] = mapped_column(Float, default=0)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    journal: Mapped[Journal] = relationship(back_populates="profile")


class JournalContact(Base):
    __tablename__ = "journal_contacts"
    __table_args__ = (UniqueConstraint("journal_id", "kind", "value", name="journal_contact_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    journal: Mapped[Journal] = relationship(back_populates="contacts")


class EditorialMember(Base):
    __tablename__ = "editorial_members"
    __table_args__ = (UniqueConstraint("journal_id", "name", "role", name="editorial_member_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(500))
    role: Mapped[str | None] = mapped_column(String(300), nullable=True)
    affiliation: Mapped[str | None] = mapped_column(Text, nullable=True)
    orcid: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    journal: Mapped[Journal] = relationship(back_populates="editorial_members")


class JournalPolicy(Base):
    __tablename__ = "journal_policies"
    __table_args__ = (UniqueConstraint("journal_id", "policy_type", name="journal_policy_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    policy_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    journal: Mapped[Journal] = relationship(back_populates="policies")


class JournalSection(Base):
    __tablename__ = "journal_sections"
    __table_args__ = (UniqueConstraint("journal_id", "name", name="journal_section_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    journal: Mapped[Journal] = relationship(back_populates="sections")


class JournalIndexingClaim(Base):
    __tablename__ = "journal_indexing_claims"
    __table_args__ = (UniqueConstraint("journal_id", "provider", name="journal_indexing_claim_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(30), default="claimed")
    claim_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    journal: Mapped[Journal] = relationship(back_populates="indexing_claims")


class JournalLink(Base):
    __tablename__ = "journal_links"
    __table_args__ = (UniqueConstraint("journal_id", "kind", "url", name="journal_link_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    journal: Mapped[Journal] = relationship(back_populates="links")


class JournalProfileField(Base):
    __tablename__ = "journal_profile_fields"
    __table_args__ = (UniqueConstraint("journal_id", "field_name", name="journal_profile_field_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    field_name: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[object] = mapped_column(JSON)
    source_url: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    verification_status: Mapped[str] = mapped_column(String(30), default="collected")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    journal: Mapped[Journal] = relationship(back_populates="profile_fields")


class Article(Base):
    __tablename__ = "articles"

    # Ro'yxat va SEO sahifalarining asosiy so'rovi: o'chirilmaganlar, yangi
    # nashrdan eskisiga. Kompozit indekssiz SQLite 104 000 qatorni har safar
    # vaqtinchalik B-daraxtda saralab, javobni ~180 ms ga cho'zardi.
    __table_args__ = (
        Index(
            "ix_articles_feed",
            "is_deleted",
            text("publication_year DESC"),
            text("id DESC"),
        ),
        # Jurnal sahifasi va yillik arxivlar. `ix_articles_feed` qo'shilgach
        # SQLite jurnal bo'yicha so'rovlarda ham o'shani tanlab, butun
        # jadvalni skanerlay boshlagandi.
        Index(
            "ix_articles_journal_feed",
            "journal_id",
            "is_deleted",
            text("publication_year DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text)
    normalized_title: Mapped[str] = mapped_column(Text, index=True)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    publication_date: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    volume: Mapped[str | None] = mapped_column(String(80), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pages: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(300), nullable=True, unique=True, index=True)
    landing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sarlavha + annotatsiya + mualliflar, kichik harf va lotinlashtirilgan.
    # Qidiruv shu ustunda ishlaydi: `ilike` va JSON cast'siz.
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    harvested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    journal: Mapped[Journal] = relationship(back_populates="articles")
    source_records: Mapped[list[SourceRecord]] = relationship(back_populates="article")


class HarvestSource(Base):
    __tablename__ = "harvest_sources"
    __table_args__ = (UniqueConstraint("journal_id", "base_url", "metadata_prefix", name="source_identity_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    base_url: Mapped[str] = mapped_column(Text)
    metadata_prefix: Mapped[str] = mapped_column(String(80), default="oai_dc")
    repository_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    protocol_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    datestamp_granularity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    deleted_record_policy: Mapped[str | None] = mapped_column(String(30), nullable=True)
    available_formats: Mapped[list[dict[str, str | None]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # Ayrim universitet saytlarida sertifikat muddati o‘tgan yoki hostga mos
    # emas, OAI esa to‘g‘ri ishlaydi. Bayroq bazada saqlanadi, chunki audit va
    # harvest alohida jarayonlarda ishlaydi.
    insecure_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    journal: Mapped[Journal] = relationship(back_populates="harvest_sources")
    records: Mapped[list[SourceRecord]] = relationship(back_populates="source", cascade="all, delete-orphan")
    runs: Mapped[list[HarvestRun]] = relationship(back_populates="source", cascade="all, delete-orphan")


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("source_id", "oai_identifier", name="source_record_identifier_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("harvest_sources.id", ondelete="CASCADE"), index=True)
    # Indekssiz har bir maqola o‘chirilishida SQLite butun jadvalni skanlaydi:
    # 9 192 ta maqolani o‘chirish 5 daqiqadan oshib ketgan edi, indeks bilan 0.6 s.
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    oai_identifier: Mapped[str] = mapped_column(Text)
    oai_datestamp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    set_specs: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # oai_dc metama'lumoti alohida saqlanmaydi — u `raw_xml` dan
    # `metadata_from_xml()` orqali aynan tiklanadi (118 666 yozuvda tekshirilgan).
    raw_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source: Mapped[HarvestSource] = relationship(back_populates="records")
    article: Mapped[Article | None] = relationship(back_populates="source_records")


class HarvestRun(Base):
    __tablename__ = "harvest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("harvest_sources.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    mode: Mapped[str] = mapped_column(String(20), default="incremental")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_deleted: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[HarvestSource] = relationship(back_populates="runs")


class OakImportRun(Base):
    __tablename__ = "oak_import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    registry_created: Mapped[int] = mapped_column(Integer, default=0)
    journals_created: Mapped[int] = mapped_column(Integer, default=0)
    journals_updated: Mapped[int] = mapped_column(Integer, default=0)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    entries: Mapped[list[OakRegistryEntry]] = relationship(back_populates="import_run")
    snapshot_entries: Mapped[list[OakRegistrySnapshotEntry]] = relationship(back_populates="import_run", cascade="all, delete-orphan")
    snapshot_meta: Mapped[OakRegistrySnapshotMeta | None] = relationship(back_populates="import_run", cascade="all, delete-orphan", uselist=False)


class OakRegistryEntry(Base):
    __tablename__ = "oak_registry_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("oak_import_runs.id", ondelete="CASCADE"), index=True)
    journal_id: Mapped[int | None] = mapped_column(ForeignKey("journals.id", ondelete="SET NULL"), nullable=True, index=True)
    source_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(Text)
    place: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialty_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    area: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    added: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[str | None] = mapped_column(Text, nullable=True)
    removed: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    import_run: Mapped[OakImportRun] = relationship(back_populates="entries")
    journal: Mapped[Journal | None] = relationship()
    snapshots: Mapped[list[OakRegistrySnapshotEntry]] = relationship(back_populates="registry_entry", cascade="all, delete-orphan")


class OakRegistrySnapshotEntry(Base):
    __tablename__ = "oak_registry_snapshot_entries"
    __table_args__ = (UniqueConstraint("import_run_id", "registry_entry_id", name="oak_snapshot_entry_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("oak_import_runs.id", ondelete="CASCADE"), index=True)
    registry_entry_id: Mapped[int] = mapped_column(ForeignKey("oak_registry_entries.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    import_run: Mapped[OakImportRun] = relationship(back_populates="snapshot_entries")
    registry_entry: Mapped[OakRegistryEntry] = relationship(back_populates="snapshots")


class OakRegistrySnapshotMeta(Base):
    __tablename__ = "oak_registry_snapshot_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("oak_import_runs.id", ondelete="CASCADE"), unique=True, index=True)
    publication_count: Mapped[int] = mapped_column(Integer)
    raw_row_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    import_run: Mapped[OakImportRun] = relationship(back_populates="snapshot_meta")


class AuditJob(Base):
    __tablename__ = "audit_jobs"
    __table_args__ = (UniqueConstraint("journal_id", "candidate_url", name="audit_job_candidate_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    candidate_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    discovered_base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    journal: Mapped[Journal] = relationship()


class ProfileJob(Base):
    __tablename__ = "profile_jobs"
    __table_args__ = (UniqueConstraint("journal_id", name="profile_job_journal_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    journal: Mapped[Journal] = relationship()


class User(Base):
    """Tashqi provayder (ORCID yoki Google) orqali kirgan foydalanuvchi.

    Parol saqlanmaydi — autentifikatsiya butunlay provayder tomonida.
    ORCID iD ilmiy muhitda barqaror identifikator, shuning uchun asosiy
    bog'lovchi sifatida ishlatiladi.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="user_provider_uq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), index=True)
    provider_subject: Mapped[str] = mapped_column(String(200))
    orcid: Mapped[str | None] = mapped_column(String(19), nullable=True, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    affiliation: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Google Scholar'da OAuth yo'q, shuning uchun profil havolasi qo'lda kiritiladi.
    scholar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Admin panelga kirish huquqi. Birinchi adminni `grant-admin` CLI bilan
    # yoki ILMIZ_ADMIN_TOKEN orqali tayinlash mumkin.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list[UserSession]] = relationship(back_populates="user", cascade="all, delete-orphan")
    claimed_articles: Mapped[list["UserArticle"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserArticle(Base):
    """Foydalanuvchi o'ziniki deb tasdiqlagan maqola.

    Mualliflik nomlar bo'yicha taxmin qilinadi, shuning uchun avtomatik
    bog'lamaymiz: tizim faqat nomzodlarni topadi, qaysi biri o'ziniki
    ekanini foydalanuvchining o'zi tasdiqlaydi (Google Scholar singari).
    """

    __tablename__ = "user_articles"
    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="user_article_uq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="claimed_articles")
    article: Mapped[Article] = relationship()


class UserSession(Base):
    """Serverda saqlanadigan sessiya.

    Token o'rniga uning SHA-256 hash'i saqlanadi: baza o'qilib qolsa ham
    tayyor sessiya tokenlari qo'lga tushmaydi.
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class OAuthState(Base):
    """OAuth `state` qiymati — CSRF va qayta ishlatishga qarshi.

    Bir marta ishlatiladi va callback'da o'chiriladi.
    """

    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(20))
    redirect_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

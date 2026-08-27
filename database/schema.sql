-- IlmIz MVP database schema (PostgreSQL 15+)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE oak_status AS ENUM ('active', 'removed', 'review');
CREATE TYPE source_status AS ENUM ('pending', 'healthy', 'warning', 'failed', 'disabled');
CREATE TYPE access_model AS ENUM ('open', 'mixed', 'closed', 'unknown');
CREATE TYPE harvest_run_status AS ENUM ('running', 'succeeded', 'partial', 'failed');

CREATE TABLE publishers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  normalized_name text NOT NULL,
  website_url text,
  city text,
  country_code char(2) NOT NULL DEFAULT 'UZ',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX publishers_normalized_name_uq ON publishers (normalized_name);

CREATE TABLE journals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE,
  title text NOT NULL,
  short_title text,
  alternate_titles text[] NOT NULL DEFAULT '{}',
  publisher_id uuid REFERENCES publishers(id),
  issn_print varchar(9),
  issn_online varchar(9),
  city text,
  languages text[] NOT NULL DEFAULT '{}',
  founded_year smallint,
  website_url text,
  description text,
  oak_status oak_status NOT NULL DEFAULT 'review',
  oak_decision_number text,
  oak_decision_date date,
  oak_source_url text,
  access access_model NOT NULL DEFAULT 'unknown',
  verified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (issn_print IS NULL OR issn_print ~ '^[0-9]{4}-[0-9X]{4}$'),
  CHECK (issn_online IS NULL OR issn_online ~ '^[0-9]{4}-[0-9X]{4}$')
);

CREATE TABLE disciplines (
  id smallserial PRIMARY KEY,
  slug text NOT NULL UNIQUE,
  name_uz text NOT NULL,
  oak_code text
);

CREATE TABLE journal_disciplines (
  journal_id uuid NOT NULL REFERENCES journals(id) ON DELETE CASCADE,
  discipline_id smallint NOT NULL REFERENCES disciplines(id),
  PRIMARY KEY (journal_id, discipline_id)
);

CREATE TABLE harvest_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  journal_id uuid NOT NULL REFERENCES journals(id) ON DELETE CASCADE,
  base_url text NOT NULL,
  metadata_prefix text NOT NULL DEFAULT 'oai_dc',
  set_spec text,
  repository_name text,
  protocol_version text,
  datestamp_granularity text,
  deleted_record_policy text,
  status source_status NOT NULL DEFAULT 'pending',
  consecutive_failures integer NOT NULL DEFAULT 0,
  last_cursor_datestamp timestamptz,
  last_attempt_at timestamptz,
  last_success_at timestamptz,
  next_run_at timestamptz,
  last_error_code text,
  last_error_message text,
  identify_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (journal_id, base_url, metadata_prefix, set_spec)
);

CREATE INDEX harvest_sources_due_idx ON harvest_sources (next_run_at)
  WHERE status IN ('pending', 'healthy', 'warning', 'failed');

CREATE TABLE issues (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  journal_id uuid NOT NULL REFERENCES journals(id) ON DELETE CASCADE,
  volume text,
  issue_number text,
  publication_year smallint,
  published_at date,
  title text,
  landing_url text,
  cover_url text,
  source_key text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (journal_id, volume, issue_number, publication_year)
);

CREATE TABLE articles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  journal_id uuid NOT NULL REFERENCES journals(id) ON DELETE CASCADE,
  issue_id uuid REFERENCES issues(id) ON DELETE SET NULL,
  title text NOT NULL,
  normalized_title text NOT NULL,
  alternate_titles jsonb NOT NULL DEFAULT '[]',
  abstract text,
  keywords text[] NOT NULL DEFAULT '{}',
  language text,
  publication_date date,
  publication_year smallint,
  volume text,
  issue_number text,
  first_page text,
  last_page text,
  doi text,
  landing_url text,
  pdf_url text,
  license_url text,
  is_deleted boolean NOT NULL DEFAULT false,
  metadata_quality smallint NOT NULL DEFAULT 0 CHECK (metadata_quality BETWEEN 0 AND 100),
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX articles_doi_uq ON articles (lower(doi)) WHERE doi IS NOT NULL;
CREATE INDEX articles_journal_year_idx ON articles (journal_id, publication_year DESC);
CREATE INDEX articles_title_search_idx ON articles USING gin (to_tsvector('simple', title));

CREATE TABLE authors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name text NOT NULL,
  normalized_name text NOT NULL,
  orcid varchar(19),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (orcid IS NULL OR orcid ~ '^0000-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$')
);

CREATE UNIQUE INDEX authors_orcid_uq ON authors (orcid) WHERE orcid IS NOT NULL;
CREATE INDEX authors_normalized_name_idx ON authors (normalized_name);

CREATE TABLE article_authors (
  article_id uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  author_id uuid NOT NULL REFERENCES authors(id),
  ordinal smallint NOT NULL,
  raw_name text NOT NULL,
  affiliation text,
  corresponding boolean NOT NULL DEFAULT false,
  PRIMARY KEY (article_id, ordinal),
  UNIQUE (article_id, author_id)
);

CREATE TABLE harvest_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES harvest_sources(id) ON DELETE CASCADE,
  status harvest_run_status NOT NULL DEFAULT 'running',
  mode text NOT NULL CHECK (mode IN ('identify', 'full', 'incremental')),
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  requested_from timestamptz,
  records_seen integer NOT NULL DEFAULT 0,
  records_created integer NOT NULL DEFAULT 0,
  records_updated integer NOT NULL DEFAULT 0,
  records_deleted integer NOT NULL DEFAULT 0,
  pages_fetched integer NOT NULL DEFAULT 0,
  error_summary text
);

CREATE TABLE source_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES harvest_sources(id) ON DELETE CASCADE,
  article_id uuid REFERENCES articles(id) ON DELETE SET NULL,
  oai_identifier text NOT NULL,
  oai_datestamp timestamptz,
  set_specs text[] NOT NULL DEFAULT '{}',
  is_deleted boolean NOT NULL DEFAULT false,
  metadata_hash char(64),
  raw_metadata jsonb,
  raw_xml text,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, oai_identifier)
);

CREATE INDEX source_records_article_idx ON source_records (article_id);
CREATE INDEX source_records_datestamp_idx ON source_records (source_id, oai_datestamp);

CREATE TABLE article_merge_candidates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  left_article_id uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  right_article_id uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  match_method text NOT NULL,
  confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'merged', 'rejected')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (left_article_id, right_article_id),
  CHECK (left_article_id <> right_article_id)
);

COMMENT ON TABLE source_records IS 'Har bir OAI yozuvining provenance va raw nusxasi; normalizatsiyani qayta ishga tushirish imkonini beradi.';
COMMENT ON COLUMN harvest_sources.last_cursor_datestamp IS 'Keyingi incremental harvest boshlanadigan cursor; overlap window bilan ishlatiladi.';

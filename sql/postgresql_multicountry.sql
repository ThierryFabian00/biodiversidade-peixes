-- Modelo PostgreSQL multiespécies e multípaís (Etapa 5).
-- O marcador __SCHEMA__ é substituído por src.load após validação do nome.

-- statement
CREATE SCHEMA IF NOT EXISTS __SCHEMA__

-- statement
DROP VIEW IF EXISTS __SCHEMA__.vw_occurrence_details,
                    __SCHEMA__.vw_occurrences_by_year,
                    __SCHEMA__.vw_species_ranking

-- statement
DO $$
BEGIN
    IF to_regclass('__SCHEMA__.species') IS NOT NULL
       AND to_regclass('__SCHEMA__.taxa') IS NULL THEN
        ALTER TABLE __SCHEMA__.species RENAME TO taxa;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = '__SCHEMA__'
          AND table_name = 'taxa'
          AND column_name = 'species_key'
    ) THEN
        ALTER TABLE __SCHEMA__.taxa RENAME COLUMN species_key TO taxon_key;
    END IF;
END
$$

-- statement
CREATE TABLE IF NOT EXISTS __SCHEMA__.countries (
    id BIGSERIAL PRIMARY KEY,
    iso_code CHAR(2) NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (iso_code ~ '^[A-Z]{2}$')
)

-- statement
CREATE TABLE IF NOT EXISTS __SCHEMA__.taxa (
    taxon_key TEXT PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    accepted_scientific_name TEXT,
    taxonomic_status TEXT,
    kingdom TEXT,
    phylum TEXT,
    class_name TEXT,
    order_name TEXT,
    family TEXT,
    genus TEXT,
    species TEXT,
    canonical_name TEXT NOT NULL,
    fish_group TEXT,
    iucn_category TEXT,
    source_occurrence_count INTEGER NOT NULL DEFAULT 0
        CHECK (source_occurrence_count >= 0),
    first_year SMALLINT,
    last_year SMALLINT,
    origin_status TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (origin_status IN ('NATIVE', 'INTRODUCED', 'CONFLICTING', 'UNKNOWN')),
    origin_evidence TEXT,
    origin_source TEXT,
    origin_source_url TEXT,
    origin_scope TEXT,
    taxonomic_issue_count INTEGER NOT NULL DEFAULT 0
        CHECK (taxonomic_issue_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (first_year IS NULL OR first_year BETWEEN 1600 AND 2200),
    CHECK (last_year IS NULL OR last_year BETWEEN 1600 AND 2200),
    CHECK (first_year IS NULL OR last_year IS NULL OR first_year <= last_year)
)

-- statement
ALTER TABLE __SCHEMA__.taxa
    ADD COLUMN IF NOT EXISTS scientific_name TEXT,
    ADD COLUMN IF NOT EXISTS accepted_scientific_name TEXT,
    ADD COLUMN IF NOT EXISTS taxonomic_status TEXT,
    ADD COLUMN IF NOT EXISTS kingdom TEXT,
    ADD COLUMN IF NOT EXISTS phylum TEXT,
    ADD COLUMN IF NOT EXISTS class_name TEXT,
    ADD COLUMN IF NOT EXISTS order_name TEXT,
    ADD COLUMN IF NOT EXISTS family TEXT,
    ADD COLUMN IF NOT EXISTS genus TEXT,
    ADD COLUMN IF NOT EXISTS species TEXT,
    ADD COLUMN IF NOT EXISTS canonical_name TEXT,
    ADD COLUMN IF NOT EXISTS fish_group TEXT,
    ADD COLUMN IF NOT EXISTS iucn_category TEXT,
    ADD COLUMN IF NOT EXISTS source_occurrence_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS first_year SMALLINT,
    ADD COLUMN IF NOT EXISTS last_year SMALLINT,
    ADD COLUMN IF NOT EXISTS origin_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS origin_evidence TEXT,
    ADD COLUMN IF NOT EXISTS origin_source TEXT,
    ADD COLUMN IF NOT EXISTS origin_source_url TEXT,
    ADD COLUMN IF NOT EXISTS origin_scope TEXT,
    ADD COLUMN IF NOT EXISTS taxonomic_issue_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP

-- statement
UPDATE __SCHEMA__.taxa
SET scientific_name = COALESCE(scientific_name, accepted_scientific_name, canonical_name),
    accepted_scientific_name = COALESCE(accepted_scientific_name, scientific_name),
    canonical_name = COALESCE(canonical_name, scientific_name),
    species = COALESCE(species, canonical_name)
WHERE scientific_name IS NULL
   OR accepted_scientific_name IS NULL
   OR canonical_name IS NULL
   OR species IS NULL

-- statement
ALTER TABLE __SCHEMA__.taxa
    ALTER COLUMN scientific_name SET NOT NULL,
    ALTER COLUMN canonical_name SET NOT NULL

-- statement
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = '__SCHEMA__'
          AND table_name = 'occurrences'
          AND column_name = 'gbif_id'
    ) THEN
        ALTER TABLE __SCHEMA__.occurrences RENAME COLUMN gbif_id TO gbif_key;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = '__SCHEMA__'
          AND table_name = 'occurrences'
          AND column_name = 'species_key'
    ) THEN
        ALTER TABLE __SCHEMA__.occurrences RENAME COLUMN species_key TO taxon_key;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = '__SCHEMA__'
          AND table_name = 'occurrences'
          AND column_name = 'decimal_latitude'
    ) THEN
        ALTER TABLE __SCHEMA__.occurrences RENAME COLUMN decimal_latitude TO latitude;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = '__SCHEMA__'
          AND table_name = 'occurrences'
          AND column_name = 'decimal_longitude'
    ) THEN
        ALTER TABLE __SCHEMA__.occurrences RENAME COLUMN decimal_longitude TO longitude;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = '__SCHEMA__'
          AND table_name = 'occurrences'
          AND column_name = 'event_year'
    ) THEN
        ALTER TABLE __SCHEMA__.occurrences RENAME COLUMN event_year TO year;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = '__SCHEMA__'
          AND table_name = 'occurrences'
          AND column_name = 'event_month'
    ) THEN
        ALTER TABLE __SCHEMA__.occurrences RENAME COLUMN event_month TO month;
    END IF;
END
$$

-- statement
CREATE TABLE IF NOT EXISTS __SCHEMA__.occurrences (
    gbif_key BIGINT PRIMARY KEY,
    taxon_key TEXT NOT NULL REFERENCES __SCHEMA__.taxa(taxon_key)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    country_code CHAR(2) NOT NULL REFERENCES __SCHEMA__.countries(iso_code)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    scientific_name TEXT,
    taxonomic_status TEXT,
    latitude DOUBLE PRECISION CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION CHECK (longitude BETWEEN -180 AND 180),
    event_date TIMESTAMPTZ,
    event_date_original TEXT,
    date_precision TEXT,
    year SMALLINT CHECK (year IS NULL OR year BETWEEN 1600 AND 2200),
    month SMALLINT CHECK (month IS NULL OR month BETWEEN 1 AND 12),
    state_province TEXT,
    locality TEXT,
    basis_of_record TEXT,
    dataset_key TEXT,
    dataset_name TEXT,
    publishing_org_key TEXT,
    institution_code TEXT,
    license TEXT,
    references_url TEXT,
    occurrence_status TEXT,
    establishment_means TEXT,
    degree_of_establishment TEXT,
    taxonomic_issues TEXT,
    occurrence_issues TEXT,
    inside_basin BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)

-- statement
ALTER TABLE __SCHEMA__.occurrences
    ADD COLUMN IF NOT EXISTS country_code CHAR(2),
    ADD COLUMN IF NOT EXISTS date_precision TEXT,
    ADD COLUMN IF NOT EXISTS dataset_name TEXT,
    ADD COLUMN IF NOT EXISTS publishing_org_key TEXT,
    ADD COLUMN IF NOT EXISTS institution_code TEXT,
    ADD COLUMN IF NOT EXISTS license TEXT,
    ADD COLUMN IF NOT EXISTS references_url TEXT

-- statement
ALTER TABLE __SCHEMA__.occurrences
    ALTER COLUMN latitude DROP NOT NULL,
    ALTER COLUMN longitude DROP NOT NULL

-- statement
INSERT INTO __SCHEMA__.countries (iso_code, name)
VALUES ('BR', 'Brasil'), ('CH', 'Suíça'), ('DE', 'Alemanha'), ('FR', 'França'),
       ('AR', 'Argentina'), ('PY', 'Paraguai')
ON CONFLICT (iso_code) DO UPDATE
SET name = EXCLUDED.name, updated_at = CURRENT_TIMESTAMP

-- statement
UPDATE __SCHEMA__.occurrences
SET country_code = 'BR'
WHERE country_code IS NULL

-- statement
ALTER TABLE __SCHEMA__.occurrences
    ALTER COLUMN country_code SET NOT NULL

-- statement
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = '__SCHEMA__.occurrences'::regclass
          AND contype = 'f'
          AND pg_get_constraintdef(oid) LIKE '%(country_code)%'
    ) THEN
        ALTER TABLE __SCHEMA__.occurrences
            ADD CONSTRAINT occurrences_country_code_fkey
            FOREIGN KEY (country_code)
            REFERENCES __SCHEMA__.countries(iso_code)
            ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
END
$$

-- statement
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = '__SCHEMA__.occurrences'::regclass
          AND contype = 'f'
          AND pg_get_constraintdef(oid) LIKE '%(taxon_key)%'
    ) THEN
        ALTER TABLE __SCHEMA__.occurrences
            ADD CONSTRAINT occurrences_taxon_key_fkey
            FOREIGN KEY (taxon_key)
            REFERENCES __SCHEMA__.taxa(taxon_key)
            ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
END
$$

-- statement
CREATE TABLE IF NOT EXISTS __SCHEMA__.data_imports (
    id BIGSERIAL PRIMARY KEY,
    country_code CHAR(2) NOT NULL REFERENCES __SCHEMA__.countries(iso_code)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    taxon_key TEXT REFERENCES __SCHEMA__.taxa(taxon_key)
        ON UPDATE CASCADE ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    records_received INTEGER NOT NULL CHECK (records_received >= 0),
    records_saved INTEGER NOT NULL DEFAULT 0 CHECK (records_saved >= 0),
    status TEXT NOT NULL CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED')),
    taxa_file TEXT NOT NULL,
    occurrences_file TEXT NOT NULL,
    source_checksum CHAR(64) NOT NULL
)

-- statement
CREATE INDEX IF NOT EXISTS idx_occurrences_country
ON __SCHEMA__.occurrences(country_code)

-- statement
CREATE INDEX IF NOT EXISTS idx_occurrences_taxon
ON __SCHEMA__.occurrences(taxon_key)

-- statement
CREATE INDEX IF NOT EXISTS idx_occurrences_year
ON __SCHEMA__.occurrences(year)

-- statement
CREATE INDEX IF NOT EXISTS idx_occurrences_country_taxon_year
ON __SCHEMA__.occurrences(country_code, taxon_key, year)

-- statement
CREATE INDEX IF NOT EXISTS idx_data_imports_country_started
ON __SCHEMA__.data_imports(country_code, started_at DESC)

-- statement
CREATE OR REPLACE VIEW __SCHEMA__.vw_species_ranking AS
SELECT
    t.taxon_key,
    t.canonical_name,
    t.origin_status,
    o.country_code,
    COUNT(o.gbif_key)::BIGINT AS occurrence_count,
    MIN(o.year) AS first_year,
    MAX(o.year) AS last_year
FROM __SCHEMA__.taxa t
LEFT JOIN __SCHEMA__.occurrences o ON o.taxon_key = t.taxon_key
GROUP BY t.taxon_key, t.canonical_name, t.origin_status, o.country_code

-- statement
CREATE OR REPLACE VIEW __SCHEMA__.vw_occurrences_by_year AS
SELECT country_code, year, COUNT(*)::BIGINT AS occurrence_count
FROM __SCHEMA__.occurrences
WHERE year IS NOT NULL
GROUP BY country_code, year

-- statement
CREATE OR REPLACE VIEW __SCHEMA__.vw_occurrence_details AS
SELECT
    o.gbif_key,
    o.taxon_key,
    o.country_code,
    t.canonical_name,
    t.family,
    t.order_name,
    t.origin_status,
    t.iucn_category,
    o.event_date,
    o.year,
    o.month,
    o.latitude,
    o.longitude,
    o.state_province,
    o.locality,
    o.basis_of_record,
    o.taxonomic_issues,
    o.occurrence_issues
FROM __SCHEMA__.occurrences o
JOIN __SCHEMA__.taxa t ON t.taxon_key = o.taxon_key

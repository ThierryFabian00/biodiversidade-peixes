-- Resumo geral
SELECT
    (SELECT COUNT(*) FROM biodiversity.occurrences) AS occurrence_count,
    (SELECT COUNT(*) FROM biodiversity.taxa) AS species_count,
    MIN(year) AS first_year,
    MAX(year) AS last_year
FROM biodiversity.occurrences;

-- Especies mais registradas
SELECT country_code, taxon_key, canonical_name, origin_status, occurrence_count
FROM biodiversity.vw_species_ranking
ORDER BY occurrence_count DESC, canonical_name
LIMIT 20;

-- Registros por ano
SELECT country_code, year, occurrence_count
FROM biodiversity.vw_occurrences_by_year
ORDER BY country_code, year;

-- Registros por mes
SELECT country_code, month, COUNT(*) AS occurrence_count
FROM biodiversity.occurrences
WHERE month IS NOT NULL
GROUP BY country_code, month
ORDER BY country_code, month;

-- Especies por origem
SELECT origin_status, COUNT(*) AS species_count
FROM biodiversity.taxa
GROUP BY origin_status
ORDER BY species_count DESC;

-- Ocorrencias de uma especie
SELECT
    gbif_key,
    canonical_name,
    event_date,
    latitude,
    longitude,
    state_province,
    basis_of_record
FROM biodiversity.vw_occurrence_details
WHERE canonical_name ILIKE '%Oreochromis niloticus%'
ORDER BY event_date DESC NULLS LAST;

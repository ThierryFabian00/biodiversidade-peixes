-- Resumo geral
SELECT
    (SELECT COUNT(*) FROM biodiversity.occurrences) AS occurrence_count,
    (SELECT COUNT(*) FROM biodiversity.species) AS species_count,
    MIN(event_year) AS first_year,
    MAX(event_year) AS last_year
FROM biodiversity.occurrences;

-- Especies mais registradas
SELECT canonical_name, origin_status, occurrence_count
FROM biodiversity.vw_species_ranking
ORDER BY occurrence_count DESC, canonical_name
LIMIT 20;

-- Registros por ano
SELECT event_year, occurrence_count
FROM biodiversity.vw_occurrences_by_year
ORDER BY event_year;

-- Registros por mes
SELECT event_month, COUNT(*) AS occurrence_count
FROM biodiversity.occurrences
WHERE event_month IS NOT NULL
GROUP BY event_month
ORDER BY event_month;

-- Especies por origem
SELECT origin_status, COUNT(*) AS species_count
FROM biodiversity.species
GROUP BY origin_status
ORDER BY species_count DESC;

-- Ocorrencias de uma especie
SELECT
    gbif_id,
    canonical_name,
    event_date,
    decimal_latitude,
    decimal_longitude,
    state_province,
    basis_of_record
FROM biodiversity.vw_occurrence_details
WHERE canonical_name ILIKE '%Oreochromis niloticus%'
ORDER BY event_date DESC NULLS LAST;

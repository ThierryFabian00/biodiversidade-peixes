import argparse
import hashlib
import os
import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from dotenv import load_dotenv

from src.transform_fish import ARQUIVO_ESPECIES, ARQUIVO_OCORRENCIAS

PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_ENV = PASTA_PROJETO / ".env"
SCHEMA_PADRAO = "biodiversity"
TAMANHO_LOTE_PADRAO = 500

COLUNAS_ESPECIES = {
    "speciesKey",
    "acceptedScientificName",
    "canonicalName",
    "occurrenceCount",
    "originStatus",
}
COLUNAS_OCORRENCIAS = {
    "gbifID",
    "speciesKey",
    "decimalLatitude",
    "decimalLongitude",
    "insideBasin",
}

SQL_UPSERT_ESPECIES = """
INSERT INTO {schema}.species (
    species_key, accepted_scientific_name, canonical_name, fish_group,
    class_name, order_name, family, genus, iucn_category,
    source_occurrence_count, first_year, last_year, origin_status,
    origin_evidence, origin_source, origin_source_url, origin_scope,
    taxonomic_issue_count
) VALUES (
    %(species_key)s, %(accepted_scientific_name)s, %(canonical_name)s,
    %(fish_group)s, %(class_name)s, %(order_name)s, %(family)s, %(genus)s,
    %(iucn_category)s, %(source_occurrence_count)s, %(first_year)s,
    %(last_year)s, %(origin_status)s, %(origin_evidence)s,
    %(origin_source)s, %(origin_source_url)s, %(origin_scope)s,
    %(taxonomic_issue_count)s
)
ON CONFLICT (species_key) DO UPDATE SET
    accepted_scientific_name = EXCLUDED.accepted_scientific_name,
    canonical_name = EXCLUDED.canonical_name,
    fish_group = EXCLUDED.fish_group,
    class_name = EXCLUDED.class_name,
    order_name = EXCLUDED.order_name,
    family = EXCLUDED.family,
    genus = EXCLUDED.genus,
    iucn_category = EXCLUDED.iucn_category,
    source_occurrence_count = EXCLUDED.source_occurrence_count,
    first_year = EXCLUDED.first_year,
    last_year = EXCLUDED.last_year,
    origin_status = EXCLUDED.origin_status,
    origin_evidence = EXCLUDED.origin_evidence,
    origin_source = EXCLUDED.origin_source,
    origin_source_url = EXCLUDED.origin_source_url,
    origin_scope = EXCLUDED.origin_scope,
    taxonomic_issue_count = EXCLUDED.taxonomic_issue_count,
    updated_at = CURRENT_TIMESTAMP
"""

SQL_UPSERT_OCORRENCIAS = """
INSERT INTO {schema}.occurrences (
    gbif_id, species_key, scientific_name, taxonomic_status,
    decimal_latitude, decimal_longitude, event_date, event_date_original,
    event_year, event_month, state_province, locality, basis_of_record,
    dataset_key, occurrence_status, establishment_means,
    degree_of_establishment, taxonomic_issues, occurrence_issues,
    inside_basin
) VALUES (
    %(gbif_id)s, %(species_key)s, %(scientific_name)s,
    %(taxonomic_status)s, %(decimal_latitude)s, %(decimal_longitude)s,
    %(event_date)s, %(event_date_original)s, %(event_year)s,
    %(event_month)s, %(state_province)s, %(locality)s,
    %(basis_of_record)s, %(dataset_key)s, %(occurrence_status)s,
    %(establishment_means)s, %(degree_of_establishment)s,
    %(taxonomic_issues)s, %(occurrence_issues)s, %(inside_basin)s
)
ON CONFLICT (gbif_id) DO UPDATE SET
    species_key = EXCLUDED.species_key,
    scientific_name = EXCLUDED.scientific_name,
    taxonomic_status = EXCLUDED.taxonomic_status,
    decimal_latitude = EXCLUDED.decimal_latitude,
    decimal_longitude = EXCLUDED.decimal_longitude,
    event_date = EXCLUDED.event_date,
    event_date_original = EXCLUDED.event_date_original,
    event_year = EXCLUDED.event_year,
    event_month = EXCLUDED.event_month,
    state_province = EXCLUDED.state_province,
    locality = EXCLUDED.locality,
    basis_of_record = EXCLUDED.basis_of_record,
    dataset_key = EXCLUDED.dataset_key,
    occurrence_status = EXCLUDED.occurrence_status,
    establishment_means = EXCLUDED.establishment_means,
    degree_of_establishment = EXCLUDED.degree_of_establishment,
    taxonomic_issues = EXCLUDED.taxonomic_issues,
    occurrence_issues = EXCLUDED.occurrence_issues,
    inside_basin = EXCLUDED.inside_basin,
    updated_at = CURRENT_TIMESTAMP
"""


def validar_schema(schema: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise ValueError(
            "Schema invalido. Use apenas letras minusculas, numeros e underscore."
        )
    return schema


def criar_comandos_schema(schema: str) -> list[str]:
    schema = validar_schema(schema)
    return [
        f"CREATE SCHEMA IF NOT EXISTS {schema}",
        f"""
        CREATE TABLE IF NOT EXISTS {schema}.species (
            species_key TEXT PRIMARY KEY,
            accepted_scientific_name TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            fish_group TEXT,
            class_name TEXT,
            order_name TEXT,
            family TEXT,
            genus TEXT,
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
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {schema}.occurrences (
            gbif_id BIGINT PRIMARY KEY,
            species_key TEXT NOT NULL REFERENCES {schema}.species(species_key)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            scientific_name TEXT,
            taxonomic_status TEXT,
            decimal_latitude DOUBLE PRECISION NOT NULL
                CHECK (decimal_latitude BETWEEN -90 AND 90),
            decimal_longitude DOUBLE PRECISION NOT NULL
                CHECK (decimal_longitude BETWEEN -180 AND 180),
            event_date TIMESTAMPTZ,
            event_date_original TEXT,
            event_year SMALLINT CHECK (event_year IS NULL OR event_year BETWEEN 1600 AND 2200),
            event_month SMALLINT CHECK (event_month IS NULL OR event_month BETWEEN 1 AND 12),
            state_province TEXT,
            locality TEXT,
            basis_of_record TEXT,
            dataset_key TEXT,
            occurrence_status TEXT,
            establishment_means TEXT,
            degree_of_establishment TEXT,
            taxonomic_issues TEXT,
            occurrence_issues TEXT,
            inside_basin BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {schema}.load_runs (
            load_id BIGSERIAL PRIMARY KEY,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            species_file TEXT NOT NULL,
            occurrences_file TEXT NOT NULL,
            source_checksum CHAR(64) NOT NULL,
            species_rows INTEGER NOT NULL CHECK (species_rows >= 0),
            occurrence_rows INTEGER NOT NULL CHECK (occurrence_rows >= 0),
            status TEXT NOT NULL DEFAULT 'COMPLETED'
                CHECK (status IN ('COMPLETED', 'FAILED'))
        )
        """,
        f"CREATE INDEX IF NOT EXISTS idx_occurrences_species ON {schema}.occurrences(species_key)",
        f"CREATE INDEX IF NOT EXISTS idx_occurrences_year_month ON {schema}.occurrences(event_year, event_month)",
        f"CREATE INDEX IF NOT EXISTS idx_occurrences_state ON {schema}.occurrences(state_province)",
        f"CREATE INDEX IF NOT EXISTS idx_occurrences_basis ON {schema}.occurrences(basis_of_record)",
        f"CREATE INDEX IF NOT EXISTS idx_occurrences_coordinates ON {schema}.occurrences(decimal_longitude, decimal_latitude)",
        f"""
        CREATE OR REPLACE VIEW {schema}.vw_species_ranking AS
        SELECT
            s.species_key,
            s.canonical_name,
            s.origin_status,
            COUNT(o.gbif_id)::BIGINT AS occurrence_count,
            MIN(o.event_year) AS first_year,
            MAX(o.event_year) AS last_year
        FROM {schema}.species s
        LEFT JOIN {schema}.occurrences o ON o.species_key = s.species_key
        GROUP BY s.species_key, s.canonical_name, s.origin_status
        """,
        f"""
        CREATE OR REPLACE VIEW {schema}.vw_occurrences_by_year AS
        SELECT event_year, COUNT(*)::BIGINT AS occurrence_count
        FROM {schema}.occurrences
        WHERE event_year IS NOT NULL
        GROUP BY event_year
        """,
        f"""
        CREATE OR REPLACE VIEW {schema}.vw_occurrence_details AS
        SELECT
            o.gbif_id,
            o.species_key,
            s.canonical_name,
            s.family,
            s.origin_status,
            o.event_date,
            o.event_year,
            o.event_month,
            o.decimal_latitude,
            o.decimal_longitude,
            o.state_province,
            o.locality,
            o.basis_of_record,
            o.taxonomic_issues,
            o.occurrence_issues
        FROM {schema}.occurrences o
        JOIN {schema}.species s ON s.species_key = o.species_key
        """,
    ]


def _limpar_valor(valor: Any) -> Any:
    if valor is None or pd.isna(valor):
        return None
    if hasattr(valor, "item"):
        return valor.item()
    return valor


def _inteiro(valor: Any) -> int | None:
    valor = _limpar_valor(valor)
    return int(valor) if valor is not None else None


def _texto(valor: Any) -> str | None:
    valor = _limpar_valor(valor)
    return str(valor) if valor is not None else None


def _texto_obrigatorio(valor: Any, campo: str) -> str:
    texto = _texto(valor)
    if texto is None or not texto.strip():
        raise ValueError(f"Valor obrigatorio ausente: {campo}")
    return texto


def _numero_obrigatorio(valor: Any, campo: str) -> float:
    valor = _limpar_valor(valor)
    if valor is None:
        raise ValueError(f"Valor obrigatorio ausente: {campo}")
    numero = float(valor)
    if pd.isna(numero):
        raise ValueError(f"Valor obrigatorio ausente: {campo}")
    return numero


def _booleano(valor: Any) -> bool:
    valor = _limpar_valor(valor)
    if isinstance(valor, str):
        if valor.strip().casefold() in {"true", "1", "yes", "sim"}:
            return True
        if valor.strip().casefold() in {"false", "0", "no", "nao"}:
            return False
        raise ValueError(f"Valor booleano invalido: {valor}")
    return bool(valor)


def _data_utc(valor: Any) -> datetime | None:
    valor = _limpar_valor(valor)
    if valor is None:
        return None
    data = pd.to_datetime(valor, errors="coerce", utc=True)
    if pd.isna(data):
        return None
    return data.to_pydatetime()


def validar_tabela(
    dados: pd.DataFrame, colunas: set[str], nome: str
) -> None:
    ausentes = colunas.difference(dados.columns)
    if ausentes:
        raise ValueError(
            f"Colunas obrigatorias ausentes em {nome}: {', '.join(sorted(ausentes))}"
        )


def preparar_especies(dados: pd.DataFrame) -> list[dict[str, Any]]:
    validar_tabela(dados, COLUNAS_ESPECIES, "especies")
    registros: list[dict[str, Any]] = []
    for linha in dados.to_dict("records"):
        registros.append(
            {
                "species_key": _texto_obrigatorio(linha["speciesKey"], "speciesKey"),
                "accepted_scientific_name": _texto_obrigatorio(
                    linha.get("acceptedScientificName"), "acceptedScientificName"
                ),
                "canonical_name": _texto_obrigatorio(
                    linha.get("canonicalName"), "canonicalName"
                ),
                "fish_group": _limpar_valor(linha.get("fishGroup")),
                "class_name": _limpar_valor(linha.get("class")),
                "order_name": _limpar_valor(linha.get("order")),
                "family": _limpar_valor(linha.get("family")),
                "genus": _limpar_valor(linha.get("genus")),
                "iucn_category": _limpar_valor(linha.get("iucnCategory")),
                "source_occurrence_count": _inteiro(linha.get("occurrenceCount")) or 0,
                "first_year": _inteiro(linha.get("firstYear")),
                "last_year": _inteiro(linha.get("lastYear")),
                "origin_status": _limpar_valor(linha.get("originStatus")) or "UNKNOWN",
                "origin_evidence": _limpar_valor(linha.get("originEvidence")),
                "origin_source": _limpar_valor(linha.get("originSource")),
                "origin_source_url": _limpar_valor(linha.get("originSourceUrl")),
                "origin_scope": _limpar_valor(linha.get("originScope")),
                "taxonomic_issue_count": _inteiro(
                    linha.get("taxonomicIssueCount")
                )
                or 0,
            }
        )
    return registros


def preparar_ocorrencias(dados: pd.DataFrame) -> list[dict[str, Any]]:
    validar_tabela(dados, COLUNAS_OCORRENCIAS, "ocorrencias")
    registros: list[dict[str, Any]] = []
    for linha in dados.to_dict("records"):
        registros.append(
            {
                "gbif_id": int(_numero_obrigatorio(linha["gbifID"], "gbifID")),
                "species_key": _texto_obrigatorio(linha["speciesKey"], "speciesKey"),
                "scientific_name": _limpar_valor(linha.get("scientificName")),
                "taxonomic_status": _limpar_valor(linha.get("taxonomicStatus")),
                "decimal_latitude": _numero_obrigatorio(
                    linha["decimalLatitude"], "decimalLatitude"
                ),
                "decimal_longitude": _numero_obrigatorio(
                    linha["decimalLongitude"], "decimalLongitude"
                ),
                "event_date": _data_utc(linha.get("eventDate")),
                "event_date_original": _limpar_valor(
                    linha.get("eventDateOriginal")
                ),
                "event_year": _inteiro(linha.get("year")),
                "event_month": _inteiro(linha.get("month")),
                "state_province": _limpar_valor(linha.get("stateProvince")),
                "locality": _limpar_valor(linha.get("locality")),
                "basis_of_record": _limpar_valor(linha.get("basisOfRecord")),
                "dataset_key": _limpar_valor(linha.get("datasetKey")),
                "occurrence_status": _limpar_valor(
                    linha.get("occurrenceStatus")
                ),
                "establishment_means": _limpar_valor(
                    linha.get("establishmentMeans")
                ),
                "degree_of_establishment": _texto(
                    linha.get("degreeOfEstablishment")
                ),
                "taxonomic_issues": _limpar_valor(
                    linha.get("taxonomicIssues")
                ),
                "occurrence_issues": _limpar_valor(
                    linha.get("occurrenceIssues")
                ),
                "inside_basin": _booleano(linha["insideBasin"]),
            }
        )
    return registros


def validar_referencias(
    especies: Sequence[dict[str, Any]],
    ocorrencias: Sequence[dict[str, Any]],
) -> None:
    chaves_especies = {registro["species_key"] for registro in especies}
    chaves_ocorrencias = {registro["species_key"] for registro in ocorrencias}
    orfas = sorted(chaves_ocorrencias.difference(chaves_especies))
    if orfas:
        amostra = ", ".join(orfas[:5])
        raise ValueError(f"Ocorrencias referenciam especies ausentes: {amostra}")


def calcular_checksum(caminhos: Iterable[Path]) -> str:
    resumo = hashlib.sha256()
    for caminho in caminhos:
        with caminho.open("rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                resumo.update(bloco)
    return resumo.hexdigest()


def _lotes(registros: Sequence[dict[str, Any]], tamanho: int):
    if tamanho <= 0:
        raise ValueError("O tamanho do lote deve ser positivo.")
    for inicio in range(0, len(registros), tamanho):
        yield registros[inicio : inicio + tamanho]


def criar_estrutura(conexao: Any, schema: str) -> None:
    with conexao.cursor() as cursor:
        for comando in criar_comandos_schema(schema):
            cursor.execute(comando)


def carregar_registros(
    conexao: Any,
    especies: Sequence[dict[str, Any]],
    ocorrencias: Sequence[dict[str, Any]],
    schema: str,
    tamanho_lote: int,
    caminho_especies: Path,
    caminho_ocorrencias: Path,
) -> dict[str, int]:
    schema = validar_schema(schema)
    validar_referencias(especies, ocorrencias)
    criar_estrutura(conexao, schema)
    with conexao.cursor() as cursor:
        sql_especies = SQL_UPSERT_ESPECIES.format(schema=schema)
        sql_ocorrencias = SQL_UPSERT_OCORRENCIAS.format(schema=schema)
        for lote in _lotes(especies, tamanho_lote):
            cursor.executemany(sql_especies, lote)
        for lote in _lotes(ocorrencias, tamanho_lote):
            cursor.executemany(sql_ocorrencias, lote)
        cursor.execute(
            f"""
            INSERT INTO {schema}.load_runs (
                species_file, occurrences_file, source_checksum,
                species_rows, occurrence_rows
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                str(caminho_especies),
                str(caminho_ocorrencias),
                calcular_checksum([caminho_especies, caminho_ocorrencias]),
                len(especies),
                len(ocorrencias),
            ),
        )
    return {"species": len(especies), "occurrences": len(ocorrencias)}


def verificar_carga(conexao: Any, schema: str) -> dict[str, int]:
    schema = validar_schema(schema)
    with conexao.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {schema}.species")
        especies = int(cursor.fetchone()[0])
        cursor.execute(f"SELECT COUNT(*) FROM {schema}.occurrences")
        ocorrencias = int(cursor.fetchone()[0])
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM {schema}.occurrences o
            LEFT JOIN {schema}.species s ON s.species_key = o.species_key
            WHERE s.species_key IS NULL
            """
        )
        orfas = int(cursor.fetchone()[0])
    return {"species": especies, "occurrences": ocorrencias, "orphans": orfas}


def carregar_csv(caminho: Path, colunas: set[str], nome: str) -> pd.DataFrame:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de {nome} nao encontrado: {caminho}")
    dados = pd.read_csv(caminho, dtype={"speciesKey": "string"})
    validar_tabela(dados, colunas, nome)
    return dados


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Carrega especies e ocorrencias no PostgreSQL."
    )
    parser.add_argument("--especies", type=Path, default=ARQUIVO_ESPECIES)
    parser.add_argument("--ocorrencias", type=Path, default=ARQUIVO_OCORRENCIAS)
    parser.add_argument("--env-file", type=Path, default=ARQUIVO_ENV)
    parser.add_argument("--schema", default=None)
    parser.add_argument("--tamanho-lote", type=int, default=TAMANHO_LOTE_PADRAO)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida e prepara os dados sem conectar ao banco.",
    )
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    load_dotenv(argumentos.env_file)
    schema = validar_schema(
        argumentos.schema or os.getenv("DB_SCHEMA", SCHEMA_PADRAO)
    )
    dados_especies = carregar_csv(
        argumentos.especies, COLUNAS_ESPECIES, "especies"
    )
    dados_ocorrencias = carregar_csv(
        argumentos.ocorrencias, COLUNAS_OCORRENCIAS, "ocorrencias"
    )
    especies = preparar_especies(dados_especies)
    ocorrencias = preparar_ocorrencias(dados_ocorrencias)
    validar_referencias(especies, ocorrencias)

    if argumentos.dry_run:
        print(f"Especies validadas: {len(especies)}")
        print(f"Ocorrencias validadas: {len(ocorrencias)}")
        print("Dry-run concluido; nenhuma conexao foi aberta.")
        return

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL nao definida. Crie .env a partir de .env.example."
        )

    try:
        with psycopg.connect(database_url) as conexao:
            resultado = carregar_registros(
                conexao,
                especies,
                ocorrencias,
                schema,
                argumentos.tamanho_lote,
                argumentos.especies,
                argumentos.ocorrencias,
            )
            verificacao = verificar_carga(conexao, schema)
    except psycopg.Error as erro:
        raise SystemExit(f"Falha na carga PostgreSQL: {erro}") from erro

    print(f"Especies processadas: {resultado['species']}")
    print(f"Ocorrencias processadas: {resultado['occurrences']}")
    print(f"Especies no banco: {verificacao['species']}")
    print(f"Ocorrencias no banco: {verificacao['occurrences']}")
    print(f"Referencias orfas: {verificacao['orphans']}")


if __name__ == "__main__":
    main()

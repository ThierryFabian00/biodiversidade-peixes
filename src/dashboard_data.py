from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from src.analysis import ESTADOS_ESPERADOS, normalizar_estado
from src.load import validar_schema
from src.transform_fish import ARQUIVO_ESPECIES, ARQUIVO_OCORRENCIAS


@dataclass(frozen=True)
class ResultadoFonte:
    dados: pd.DataFrame
    fonte: str
    aviso: str | None = None


COLUNAS_DASHBOARD = [
    "gbif_id",
    "species_key",
    "canonical_name",
    "family",
    "order_name",
    "origin_status",
    "iucn_category",
    "event_date",
    "event_year",
    "event_month",
    "decimal_latitude",
    "decimal_longitude",
    "state_province",
    "locality",
    "basis_of_record",
    "taxonomic_issues",
    "occurrence_issues",
]


def consulta_dashboard(schema: str) -> str:
    schema = validar_schema(schema)
    return f"""
        SELECT
            o.gbif_id,
            o.species_key,
            s.canonical_name,
            s.family,
            s.order_name,
            s.origin_status,
            s.iucn_category,
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
        ORDER BY o.gbif_id
    """


def carregar_postgresql(database_url: str, schema: str) -> pd.DataFrame:
    with psycopg.connect(database_url, row_factory=dict_row) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(consulta_dashboard(schema))
            return pd.DataFrame(cursor.fetchall(), columns=COLUNAS_DASHBOARD)


def carregar_csv(
    caminho_ocorrencias: Path = ARQUIVO_OCORRENCIAS,
    caminho_especies: Path = ARQUIVO_ESPECIES,
) -> pd.DataFrame:
    if not caminho_ocorrencias.exists() or not caminho_especies.exists():
        raise FileNotFoundError(
            "Tabelas processadas nao encontradas para o fallback CSV."
        )
    ocorrencias = pd.read_csv(caminho_ocorrencias)
    especies = pd.read_csv(caminho_especies)
    especies = especies[
        [
            "speciesKey",
            "family",
            "order",
            "originStatus",
            "iucnCategory",
        ]
    ].drop_duplicates("speciesKey")
    dados = ocorrencias.merge(especies, on="speciesKey", how="left")
    return dados.rename(
        columns={
            "gbifID": "gbif_id",
            "speciesKey": "species_key",
            "canonicalName": "canonical_name",
            "order": "order_name",
            "originStatus": "origin_status",
            "iucnCategory": "iucn_category",
            "eventDate": "event_date",
            "year": "event_year",
            "month": "event_month",
            "decimalLatitude": "decimal_latitude",
            "decimalLongitude": "decimal_longitude",
            "stateProvince": "state_province",
            "basisOfRecord": "basis_of_record",
            "taxonomicIssues": "taxonomic_issues",
            "occurrenceIssues": "occurrence_issues",
        }
    )[COLUNAS_DASHBOARD]


def normalizar_dados(dados: pd.DataFrame) -> pd.DataFrame:
    ausentes = set(COLUNAS_DASHBOARD).difference(dados.columns)
    if ausentes:
        raise ValueError(
            f"Colunas ausentes para o dashboard: {', '.join(sorted(ausentes))}"
        )
    resultado = dados.copy()
    resultado["event_date"] = pd.to_datetime(
        resultado["event_date"], errors="coerce", utc=True, format="mixed"
    )
    resultado["event_year"] = pd.to_numeric(
        resultado["event_year"], errors="coerce"
    ).astype("Int64")
    resultado["event_month"] = pd.to_numeric(
        resultado["event_month"], errors="coerce"
    ).astype("Int64")
    resultado["decimal_latitude"] = pd.to_numeric(
        resultado["decimal_latitude"], errors="coerce"
    )
    resultado["decimal_longitude"] = pd.to_numeric(
        resultado["decimal_longitude"], errors="coerce"
    )
    resultado["origin_status"] = resultado["origin_status"].fillna("UNKNOWN")
    resultado["state_normalized"] = resultado["state_province"].map(normalizar_estado)
    resultado["has_taxonomic_issue"] = resultado["taxonomic_issues"].fillna("").ne("")
    resultado["has_occurrence_issue"] = resultado["occurrence_issues"].fillna("").ne("")
    resultado["missing_locality"] = resultado["locality"].isna()
    resultado["unexpected_state"] = ~resultado["state_normalized"].isin(
        ESTADOS_ESPERADOS | {"Nao informado"}
    )
    return resultado


def carregar_dados_dashboard(
    database_url: str | None,
    schema: str,
    caminho_ocorrencias: Path = ARQUIVO_OCORRENCIAS,
    caminho_especies: Path = ARQUIVO_ESPECIES,
) -> ResultadoFonte:
    if database_url:
        try:
            dados = carregar_postgresql(database_url, schema)
            return ResultadoFonte(normalizar_dados(dados), "PostgreSQL")
        except psycopg.Error:
            aviso = "PostgreSQL indisponivel; exibindo os CSVs processados."
    else:
        aviso = "DATABASE_URL ausente; exibindo os CSVs processados."
    dados = carregar_csv(caminho_ocorrencias, caminho_especies)
    return ResultadoFonte(normalizar_dados(dados), "CSV", aviso)


def filtrar_ocorrencias(
    dados: pd.DataFrame,
    especies: Sequence[str] | None = None,
    origens: Sequence[str] | None = None,
    intervalo_anos: tuple[int, int] | None = None,
    tipos: Sequence[str] | None = None,
    estados: Sequence[str] | None = None,
) -> pd.DataFrame:
    mascara = pd.Series(True, index=dados.index)
    if especies:
        mascara &= dados["canonical_name"].isin(especies)
    if origens:
        mascara &= dados["origin_status"].isin(origens)
    if intervalo_anos:
        inicio, fim = intervalo_anos
        mascara &= dados["event_year"].between(inicio, fim, inclusive="both")
    if tipos:
        mascara &= dados["basis_of_record"].isin(tipos)
    if estados:
        mascara &= dados["state_normalized"].isin(estados)
    return dados.loc[mascara].copy()


def calcular_indicadores(dados: pd.DataFrame) -> dict[str, Any]:
    anos = dados["event_year"].dropna()
    return {
        "occurrences": len(dados),
        "species": int(dados["species_key"].nunique()),
        "introduced_species": int(
            dados.loc[dados["origin_status"].eq("INTRODUCED"), "species_key"].nunique()
        ),
        "states": int(
            dados.loc[
                ~dados["state_normalized"].eq("Nao informado"),
                "state_normalized",
            ].nunique()
        ),
        "period": (
            f"{int(anos.min())}-{int(anos.max())}" if not anos.empty else "Sem data"
        ),
    }


def ranking_especies(dados: pd.DataFrame, limite: int = 15) -> pd.DataFrame:
    return (
        dados.groupby("canonical_name", as_index=False)
        .agg(
            occurrence_count=("gbif_id", "size"),
            origin_status=("origin_status", "first"),
        )
        .sort_values(["occurrence_count", "canonical_name"], ascending=[False, True])
        .head(limite)
    )


def serie_temporal(dados: pd.DataFrame) -> pd.DataFrame:
    validos = dados.dropna(subset=["event_year", "event_month"])
    if validos.empty:
        return pd.DataFrame(columns=["period", "occurrence_count"])
    tabela = (
        validos.groupby(["event_year", "event_month"], as_index=False)
        .size()
        .rename(columns={"size": "occurrence_count"})
    )
    tabela["period"] = pd.to_datetime(
        {
            "year": tabela["event_year"].astype(int),
            "month": tabela["event_month"].astype(int),
            "day": 1,
        }
    )
    return tabela.sort_values("period")


def distribuicao_origem(dados: pd.DataFrame) -> pd.DataFrame:
    especies = dados[["species_key", "origin_status"]].drop_duplicates("species_key")
    return (
        especies.groupby("origin_status", as_index=False)
        .size()
        .rename(columns={"size": "species_count"})
        .sort_values("species_count", ascending=False)
    )


def distribuicao_tipo(dados: pd.DataFrame) -> pd.DataFrame:
    return (
        dados["basis_of_record"]
        .fillna("Nao informado")
        .value_counts()
        .rename_axis("basis_of_record")
        .reset_index(name="occurrence_count")
    )


def indicadores_qualidade(dados: pd.DataFrame) -> dict[str, int]:
    return {
        "missing_locality": int(dados["missing_locality"].sum()),
        "taxonomic_issue": int(dados["has_taxonomic_issue"].sum()),
        "occurrence_issue": int(dados["has_occurrence_issue"].sum()),
        "unexpected_state": int(dados["unexpected_state"].sum()),
    }


def frequencia_alertas(dados: pd.DataFrame, coluna: str) -> pd.DataFrame:
    if coluna not in {"taxonomic_issues", "occurrence_issues"}:
        raise ValueError("Coluna de alertas invalida.")
    alertas = dados[coluna].fillna("").str.split("|").explode()
    alertas = alertas[alertas.ne("")]
    return alertas.value_counts().rename_axis("issue").reset_index(name="record_count")

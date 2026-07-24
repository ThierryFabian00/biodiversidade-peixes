from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from src.analysis import ESTADOS_ESPERADOS, normalizar_estado
from src.config import PAIS_PADRAO
from src.database import validar_schema
from src.services.country_service import normalizar_codigo_pais, obter_pais
from src.transform_fish import (
    ARQUIVO_ESPECIES,
    ARQUIVO_OCORRENCIAS,
    caminhos_processados_pais,
)


@dataclass(frozen=True)
class ResumoImportacao:
    registros_recebidos: int
    registros_salvos: int
    registros_descartados: int
    sem_nivel_especie: int
    atualizado_em: Any | None = None

    @property
    def percentual_aproveitado(self) -> float:
        if not self.registros_recebidos:
            return 0.0
        return 100 * self.registros_salvos / self.registros_recebidos


@dataclass(frozen=True)
class ResultadoFonte:
    dados: pd.DataFrame
    fonte: str
    aviso: str | None = None
    pais_codigo: str = PAIS_PADRAO
    pais_nome: str = "Brasil"
    resumo_importacao: ResumoImportacao | None = None


COLUNAS_DASHBOARD = [
    "gbif_id",
    "species_key",
    "canonical_name",
    "family",
    "order_name",
    "origin_status",
    "iucn_category",
    "event_date",
    "date_precision",
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
            o.gbif_key AS gbif_id,
            o.taxon_key AS species_key,
            t.canonical_name,
            t.family,
            t.order_name,
            t.origin_status,
            t.iucn_category,
            o.event_date,
            o.date_precision,
            o.year AS event_year,
            o.month AS event_month,
            o.latitude AS decimal_latitude,
            o.longitude AS decimal_longitude,
            o.state_province,
            o.locality,
            o.basis_of_record,
            o.taxonomic_issues,
            o.occurrence_issues
        FROM {schema}.occurrences o
        JOIN {schema}.taxa t ON t.taxon_key = o.taxon_key
        WHERE o.country_code = %s
        ORDER BY o.gbif_key
    """


def carregar_postgresql(
    database_url: str, schema: str, codigo_pais: str
) -> pd.DataFrame:
    with psycopg.connect(database_url, row_factory=dict_row) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(consulta_dashboard(schema), (codigo_pais,))
            return pd.DataFrame(cursor.fetchall(), columns=COLUNAS_DASHBOARD)


def carregar_resumo_importacao(
    database_url: str, schema: str, codigo_pais: str
) -> ResumoImportacao | None:
    schema = validar_schema(schema)
    with psycopg.connect(database_url, row_factory=dict_row) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT records_received, records_saved, records_rejected,
                       records_rejected_taxonomy, quality_stats_complete,
                       finished_at
                FROM {schema}.data_imports
                WHERE country_code = %s AND status = 'COMPLETED'
                ORDER BY finished_at DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                (codigo_pais,),
            )
            linha = cursor.fetchone()
    if not linha or not linha["quality_stats_complete"]:
        return None
    return ResumoImportacao(
        registros_recebidos=int(linha["records_received"]),
        registros_salvos=int(linha["records_saved"]),
        registros_descartados=int(linha["records_rejected"]),
        sem_nivel_especie=int(linha["records_rejected_taxonomy"]),
        atualizado_em=linha["finished_at"],
    )


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
    # Occurrence rows also preserve taxonomy; the species catalog is authoritative.
    ocorrencias = ocorrencias.drop(
        columns=["family", "order", "iucnCategory"], errors="ignore"
    )

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
    if "datePrecision" not in dados:
        original = dados.get("eventDateOriginal", dados.get("eventDate"))
        if original is None:
            dados["datePrecision"] = pd.NA
        else:
            texto = original.astype("string").str.strip()
            dados["datePrecision"] = "UNKNOWN"
            dados.loc[texto.str.fullmatch(r"\d{4}", na=False), "datePrecision"] = "YEAR"
            dados.loc[
                texto.str.fullmatch(r"\d{4}-\d{2}", na=False), "datePrecision"
            ] = "MONTH"
            dados.loc[
                texto.str.match(r"^\d{4}-\d{2}-\d{2}", na=False), "datePrecision"
            ] = "DAY"
            dados.loc[texto.isna(), "datePrecision"] = pd.NA
    return dados.rename(
        columns={
            "gbifID": "gbif_id",
            "speciesKey": "species_key",
            "canonicalName": "canonical_name",
            "order": "order_name",
            "originStatus": "origin_status",
            "iucnCategory": "iucn_category",
            "eventDate": "event_date",
            "datePrecision": "date_precision",
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


def normalizar_dados(
    dados: pd.DataFrame, codigo_pais_fonte: str = PAIS_PADRAO
) -> pd.DataFrame:
    dados = dados.copy()
    if "date_precision" not in dados:
        dados["date_precision"] = pd.NA
    ausentes = set(COLUNAS_DASHBOARD).difference(dados.columns)
    if ausentes:
        raise ValueError(
            f"Colunas ausentes para o dashboard: {', '.join(sorted(ausentes))}"
        )
    pais_fonte = obter_pais(codigo_pais_fonte)
    resultado = dados
    if "country_code" not in resultado:
        resultado["country_code"] = pais_fonte.codigo_iso
    resultado["country_code"] = resultado["country_code"].map(normalizar_codigo_pais)
    resultado["country_name"] = resultado["country_code"].map(
        lambda codigo: obter_pais(codigo).nome
    )
    resultado["species_key"] = resultado["species_key"].astype("string")
    resultado["event_date"] = pd.to_datetime(
        resultado["event_date"], errors="coerce", utc=True, format="mixed"
    )
    resultado["date_precision"] = (
        resultado["date_precision"].astype("string").str.strip().str.upper()
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
    resultado["has_gbif_issue"] = (
        resultado["has_taxonomic_issue"] | resultado["has_occurrence_issue"]
    )
    resultado["missing_locality"] = resultado["locality"].isna()
    resultado["missing_date"] = resultado["event_date"].isna()
    resultado["monthly_date"] = resultado["date_precision"].eq("MONTH").fillna(False)
    latitude = resultado["decimal_latitude"]
    longitude = resultado["decimal_longitude"]
    resultado["invalid_coordinates"] = (
        latitude.isna()
        | longitude.isna()
        | ~latitude.between(-90, 90)
        | ~longitude.between(-180, 180)
    )
    assinatura_duplicidade = [
        "species_key",
        "decimal_latitude",
        "decimal_longitude",
        "event_date",
    ]
    completos = resultado[assinatura_duplicidade].notna().all(axis=1)
    resultado["potential_duplicate"] = completos & resultado.duplicated(
        assinatura_duplicidade, keep=False
    )
    resultado["potential_outside_country"] = (
        resultado["occurrence_issues"]
        .fillna("")
        .str.contains(r"(?:^|\|)COUNTRY_COORDINATE_MISMATCH(?:\||$)", regex=True)
    )
    resultado["unexpected_state"] = ~resultado["state_normalized"].isin(
        ESTADOS_ESPERADOS | {"Nao informado"}
    )
    return resultado


def carregar_dados_dashboard(
    database_url: str | None,
    schema: str,
    caminho_ocorrencias: Path | None = None,
    caminho_especies: Path | None = None,
    codigo_pais: str = PAIS_PADRAO,
) -> ResultadoFonte:
    pais = obter_pais(codigo_pais)
    caminhos_automaticos = caminho_ocorrencias is None and caminho_especies is None
    if (caminho_ocorrencias is None) != (caminho_especies is None):
        raise ValueError("Informe os dois caminhos CSV ou nenhum deles.")
    if caminhos_automaticos:
        caminho_ocorrencias, caminho_especies, _ = caminhos_processados_pais(
            pais.codigo_iso
        )
    assert caminho_ocorrencias is not None
    assert caminho_especies is not None
    arquivos_do_pais_disponiveis = (
        caminhos_automaticos
        and pais.codigo_iso != PAIS_PADRAO
        and caminho_ocorrencias.exists()
        and caminho_especies.exists()
    )
    aviso_fonte = None
    resumo_importacao = None
    if arquivos_do_pais_disponiveis and not database_url:
        dados = carregar_csv(caminho_ocorrencias, caminho_especies)
        fonte = "CSV"
    elif database_url:
        try:
            dados = carregar_postgresql(database_url, schema, pais.codigo_iso)
            resumo_importacao = carregar_resumo_importacao(
                database_url, schema, pais.codigo_iso
            )
            fonte = "PostgreSQL"
        except psycopg.Error:
            aviso_fonte = "PostgreSQL indisponivel; exibindo os CSVs processados."
            if caminhos_automaticos and not (
                caminho_ocorrencias.exists() and caminho_especies.exists()
            ):
                caminho_ocorrencias = ARQUIVO_OCORRENCIAS
                caminho_especies = ARQUIVO_ESPECIES
            dados = carregar_csv(caminho_ocorrencias, caminho_especies)
            fonte = "CSV"
    else:
        aviso_fonte = "DATABASE_URL ausente; exibindo os CSVs processados."
        if caminhos_automaticos and not (
            caminho_ocorrencias.exists() and caminho_especies.exists()
        ):
            caminho_ocorrencias = ARQUIVO_OCORRENCIAS
            caminho_especies = ARQUIVO_ESPECIES
        dados = carregar_csv(caminho_ocorrencias, caminho_especies)
        fonte = "CSV"

    codigo_pais_fonte = (
        pais.codigo_iso
        if arquivos_do_pais_disponiveis or fonte == "PostgreSQL"
        else PAIS_PADRAO
    )
    dados = normalizar_dados(dados, codigo_pais_fonte)
    dados = dados.loc[dados["country_code"].eq(pais.codigo_iso)].copy()
    avisos = [aviso_fonte] if aviso_fonte else []
    if pais.codigo_iso != PAIS_PADRAO and dados.empty:
        avisos.append(
            f"Ainda não há dados importados para {pais.nome} ({pais.codigo_iso})."
        )
    return ResultadoFonte(
        dados,
        fonte,
        " ".join(avisos) or None,
        pais.codigo_iso,
        pais.nome,
        resumo_importacao,
    )


def filtrar_ocorrencias(
    dados: pd.DataFrame,
    especies: Sequence[str] | None = None,
    chaves_especies: Sequence[str] | None = None,
    origens: Sequence[str] | None = None,
    intervalo_anos: tuple[int, int] | None = None,
    tipos: Sequence[str] | None = None,
    estados: Sequence[str] | None = None,
) -> pd.DataFrame:
    mascara = pd.Series(True, index=dados.index)
    if especies:
        mascara &= dados["canonical_name"].isin(especies)
    if chaves_especies:
        mascara &= dados["species_key"].isin(chaves_especies)
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
        "missing_date": int(dados["missing_date"].sum()),
        "monthly_date": int(dados["monthly_date"].sum()),
        "invalid_coordinates": int(dados["invalid_coordinates"].sum()),
        "potential_duplicate": int(dados["potential_duplicate"].sum()),
        "potential_outside_country": int(dados["potential_outside_country"].sum()),
        "gbif_issue": int(dados["has_gbif_issue"].sum()),
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

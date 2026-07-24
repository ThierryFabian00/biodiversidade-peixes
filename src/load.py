import argparse
import hashlib
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg

from src.config import ARQUIVO_ENV, PAIS_PADRAO, TAMANHO_LOTE_PADRAO
from src.config import SCHEMA_PADRAO as SCHEMA_PADRAO
from src.database import ConfiguracaoBanco, validar_schema
from src.logging_config import configurar_logging
from src.services.country_service import normalizar_codigo_pais, obter_pais
from src.transform_fish import ARQUIVO_ESPECIES, ARQUIVO_OCORRENCIAS

LOGGER = logging.getLogger(__name__)
ARQUIVO_SCHEMA = (
    Path(__file__).resolve().parent.parent / "sql" / "postgresql_multicountry.sql"
)

COLUNAS_TAXA = {
    "speciesKey",
    "acceptedScientificName",
    "canonicalName",
    "occurrenceCount",
    "originStatus",
}
COLUNAS_ESPECIES = COLUNAS_TAXA
COLUNAS_OCORRENCIAS = {
    "gbifID",
    "speciesKey",
    "decimalLatitude",
    "decimalLongitude",
    "insideBasin",
}

SQL_UPSERT_PAISES = """
INSERT INTO {schema}.countries (iso_code, name)
VALUES (%(iso_code)s, %(name)s)
ON CONFLICT (iso_code) DO UPDATE SET
    name = EXCLUDED.name,
    updated_at = CURRENT_TIMESTAMP
"""

SQL_UPSERT_TAXA = """
INSERT INTO {schema}.taxa (
    taxon_key, scientific_name, accepted_scientific_name, taxonomic_status,
    kingdom, phylum, class_name, order_name, family, genus, species,
    canonical_name, fish_group, iucn_category, source_occurrence_count,
    first_year, last_year, origin_status, origin_evidence, origin_source,
    origin_source_url, origin_scope, taxonomic_issue_count
) VALUES (
    %(taxon_key)s, %(scientific_name)s, %(accepted_scientific_name)s,
    %(taxonomic_status)s, %(kingdom)s, %(phylum)s, %(class_name)s,
    %(order_name)s, %(family)s, %(genus)s, %(species)s, %(canonical_name)s,
    %(fish_group)s, %(iucn_category)s, %(source_occurrence_count)s,
    %(first_year)s, %(last_year)s, %(origin_status)s, %(origin_evidence)s,
    %(origin_source)s, %(origin_source_url)s, %(origin_scope)s,
    %(taxonomic_issue_count)s
)
ON CONFLICT (taxon_key) DO UPDATE SET
    scientific_name = EXCLUDED.scientific_name,
    accepted_scientific_name = EXCLUDED.accepted_scientific_name,
    taxonomic_status = EXCLUDED.taxonomic_status,
    kingdom = EXCLUDED.kingdom,
    phylum = EXCLUDED.phylum,
    class_name = EXCLUDED.class_name,
    order_name = EXCLUDED.order_name,
    family = EXCLUDED.family,
    genus = EXCLUDED.genus,
    species = EXCLUDED.species,
    canonical_name = EXCLUDED.canonical_name,
    fish_group = EXCLUDED.fish_group,
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
    gbif_key, taxon_key, country_code, scientific_name, taxonomic_status,
    latitude, longitude, event_date, event_date_original, date_precision,
    year, month, state_province, locality, basis_of_record, dataset_key,
    dataset_name, publishing_org_key, institution_code, license,
    references_url, occurrence_status, establishment_means,
    degree_of_establishment, taxonomic_issues, occurrence_issues, inside_basin
) VALUES (
    %(gbif_key)s, %(taxon_key)s, %(country_code)s, %(scientific_name)s,
    %(taxonomic_status)s, %(latitude)s, %(longitude)s, %(event_date)s,
    %(event_date_original)s, %(date_precision)s, %(year)s, %(month)s,
    %(state_province)s, %(locality)s, %(basis_of_record)s, %(dataset_key)s,
    %(dataset_name)s, %(publishing_org_key)s, %(institution_code)s,
    %(license)s, %(references_url)s, %(occurrence_status)s,
    %(establishment_means)s, %(degree_of_establishment)s,
    %(taxonomic_issues)s, %(occurrence_issues)s, %(inside_basin)s
)
ON CONFLICT (gbif_key) DO UPDATE SET
    taxon_key = EXCLUDED.taxon_key,
    country_code = EXCLUDED.country_code,
    scientific_name = EXCLUDED.scientific_name,
    taxonomic_status = EXCLUDED.taxonomic_status,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    event_date = EXCLUDED.event_date,
    event_date_original = EXCLUDED.event_date_original,
    date_precision = EXCLUDED.date_precision,
    year = EXCLUDED.year,
    month = EXCLUDED.month,
    state_province = EXCLUDED.state_province,
    locality = EXCLUDED.locality,
    basis_of_record = EXCLUDED.basis_of_record,
    dataset_key = EXCLUDED.dataset_key,
    dataset_name = EXCLUDED.dataset_name,
    publishing_org_key = EXCLUDED.publishing_org_key,
    institution_code = EXCLUDED.institution_code,
    license = EXCLUDED.license,
    references_url = EXCLUDED.references_url,
    occurrence_status = EXCLUDED.occurrence_status,
    establishment_means = EXCLUDED.establishment_means,
    degree_of_establishment = EXCLUDED.degree_of_establishment,
    taxonomic_issues = EXCLUDED.taxonomic_issues,
    occurrence_issues = EXCLUDED.occurrence_issues,
    inside_basin = EXCLUDED.inside_basin,
    updated_at = CURRENT_TIMESTAMP
"""

SQL_REGISTRAR_IMPORTACOES = """
INSERT INTO {schema}.data_imports (
    country_code, taxon_key, started_at, finished_at, records_received,
    records_saved, records_rejected, records_rejected_taxonomy, status,
    quality_stats_complete, taxa_file, occurrences_file, source_checksum
) VALUES (
    %(country_code)s, %(taxon_key)s, %(started_at)s, %(finished_at)s,
    %(records_received)s, %(records_saved)s, %(records_rejected)s,
    %(records_rejected_taxonomy)s, %(status)s, %(quality_stats_complete)s,
    %(taxa_file)s, %(occurrences_file)s, %(source_checksum)s
)
"""


def criar_comandos_schema(schema: str) -> list[str]:
    schema = validar_schema(schema)
    conteudo = ARQUIVO_SCHEMA.read_text(encoding="utf-8")
    comandos = [
        trecho.strip()
        for trecho in conteudo.split("-- statement")
        if trecho.strip() and not trecho.lstrip().startswith("-- Modelo")
    ]
    return [comando.replace("__SCHEMA__", schema) for comando in comandos]


def _limpar_valor(valor: Any) -> Any:
    if valor is None or pd.isna(valor):
        return None
    if hasattr(valor, "item"):
        return valor.item()
    return valor


def _inteiro(valor: Any) -> int | None:
    valor = _limpar_valor(valor)
    return int(valor) if valor is not None else None


def _numero(valor: Any) -> float | None:
    valor = _limpar_valor(valor)
    if valor is None:
        return None
    numero = float(valor)
    return None if pd.isna(numero) else numero


def _texto(valor: Any) -> str | None:
    valor = _limpar_valor(valor)
    return str(valor) if valor is not None else None


def _texto_obrigatorio(valor: Any, campo: str) -> str:
    texto = _texto(valor)
    if texto is None or not texto.strip():
        raise ValueError(f"Valor obrigatorio ausente: {campo}")
    return texto.strip()


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
        normalizado = valor.strip().casefold()
        if normalizado in {"true", "1", "yes", "sim"}:
            return True
        if normalizado in {"false", "0", "no", "nao"}:
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


def _precisao_data(linha: dict[str, Any]) -> str | None:
    explicita = _texto(linha.get("datePrecision"))
    if explicita:
        return explicita.strip().upper()
    original = _texto(linha.get("eventDateOriginal"))
    if not original:
        return None
    original = original.strip()
    if re.fullmatch(r"\d{4}", original):
        return "YEAR"
    if re.fullmatch(r"\d{4}-\d{2}", original):
        return "MONTH"
    if re.match(r"^\d{4}-\d{2}-\d{2}", original):
        return "DAY"
    return "UNKNOWN"


def validar_tabela(dados: pd.DataFrame, colunas: set[str], nome: str) -> None:
    ausentes = colunas.difference(dados.columns)
    if ausentes:
        raise ValueError(
            f"Colunas obrigatorias ausentes em {nome}: {', '.join(sorted(ausentes))}"
        )


def preparar_taxa(dados: pd.DataFrame) -> list[dict[str, Any]]:
    validar_tabela(dados, COLUNAS_TAXA, "taxa")
    registros: list[dict[str, Any]] = []
    for linha in dados.to_dict("records"):
        nome_aceito = _texto_obrigatorio(
            linha.get("acceptedScientificName"), "acceptedScientificName"
        )
        nome_canonico = _texto_obrigatorio(linha.get("canonicalName"), "canonicalName")
        registros.append(
            {
                "taxon_key": _texto_obrigatorio(linha["speciesKey"], "speciesKey"),
                "scientific_name": _texto(linha.get("scientificName")) or nome_aceito,
                "accepted_scientific_name": nome_aceito,
                "taxonomic_status": _texto(linha.get("taxonomicStatus")),
                "kingdom": _texto(linha.get("kingdom")),
                "phylum": _texto(linha.get("phylum")),
                "class_name": _texto(linha.get("class")),
                "order_name": _texto(linha.get("order")),
                "family": _texto(linha.get("family")),
                "genus": _texto(linha.get("genus")),
                "species": _texto(linha.get("species")) or nome_canonico,
                "canonical_name": nome_canonico,
                "fish_group": _texto(linha.get("fishGroup")),
                "iucn_category": _texto(linha.get("iucnCategory")),
                "source_occurrence_count": _inteiro(linha.get("occurrenceCount")) or 0,
                "first_year": _inteiro(linha.get("firstYear")),
                "last_year": _inteiro(linha.get("lastYear")),
                "origin_status": _texto(linha.get("originStatus")) or "UNKNOWN",
                "origin_evidence": _texto(linha.get("originEvidence")),
                "origin_source": _texto(linha.get("originSource")),
                "origin_source_url": _texto(linha.get("originSourceUrl")),
                "origin_scope": _texto(linha.get("originScope")),
                "taxonomic_issue_count": _inteiro(linha.get("taxonomicIssueCount"))
                or 0,
            }
        )
    return registros


preparar_especies = preparar_taxa


def preparar_ocorrencias(dados: pd.DataFrame) -> list[dict[str, Any]]:
    validar_tabela(dados, COLUNAS_OCORRENCIAS, "ocorrencias")
    registros: list[dict[str, Any]] = []
    for linha in dados.to_dict("records"):
        registros.append(
            {
                "gbif_key": int(_numero_obrigatorio(linha["gbifID"], "gbifID")),
                "taxon_key": _texto_obrigatorio(linha["speciesKey"], "speciesKey"),
                "country_code": normalizar_codigo_pais(
                    _texto(linha.get("countryCode")) or PAIS_PADRAO
                ),
                "scientific_name": _texto(linha.get("scientificName")),
                "taxonomic_status": _texto(linha.get("taxonomicStatus")),
                "latitude": _numero(linha["decimalLatitude"]),
                "longitude": _numero(linha["decimalLongitude"]),
                "event_date": _data_utc(linha.get("eventDate")),
                "event_date_original": _texto(linha.get("eventDateOriginal")),
                "date_precision": _precisao_data(linha),
                "year": _inteiro(linha.get("year")),
                "month": _inteiro(linha.get("month")),
                "state_province": _texto(linha.get("stateProvince")),
                "locality": _texto(linha.get("locality")),
                "basis_of_record": _texto(linha.get("basisOfRecord")),
                "dataset_key": _texto(linha.get("datasetKey")),
                "dataset_name": _texto(linha.get("datasetName")),
                "publishing_org_key": _texto(linha.get("publishingOrgKey")),
                "institution_code": _texto(linha.get("institutionCode")),
                "license": _texto(linha.get("license")),
                "references_url": _texto(linha.get("references")),
                "occurrence_status": _texto(linha.get("occurrenceStatus")),
                "establishment_means": _texto(linha.get("establishmentMeans")),
                "degree_of_establishment": _texto(linha.get("degreeOfEstablishment")),
                "taxonomic_issues": _texto(linha.get("taxonomicIssues")),
                "occurrence_issues": _texto(linha.get("occurrenceIssues")),
                "inside_basin": _booleano(linha["insideBasin"]),
            }
        )
    gbif_keys = [registro["gbif_key"] for registro in registros]
    duplicadas = sorted(chave for chave in set(gbif_keys) if gbif_keys.count(chave) > 1)
    if duplicadas:
        amostra = ", ".join(str(chave) for chave in duplicadas[:5])
        raise ValueError(f"gbif_key duplicada na importacao: {amostra}")
    return registros


def preparar_paises(
    ocorrencias: Sequence[dict[str, Any]],
) -> list[dict[str, str]]:
    codigos = sorted({registro["country_code"] for registro in ocorrencias})
    return [
        {
            "iso_code": pais.codigo_iso,
            "name": pais.nome,
        }
        for pais in (obter_pais(codigo) for codigo in codigos)
    ]


def validar_referencias(
    taxa: Sequence[dict[str, Any]],
    ocorrencias: Sequence[dict[str, Any]],
) -> None:
    chaves_taxa = {registro["taxon_key"] for registro in taxa}
    chaves_ocorrencias = {registro["taxon_key"] for registro in ocorrencias}
    orfas = sorted(chaves_ocorrencias.difference(chaves_taxa))
    if orfas:
        amostra = ", ".join(orfas[:5])
        raise ValueError(f"Ocorrencias referenciam taxa ausentes: {amostra}")


def calcular_checksum(caminhos: Iterable[Path]) -> str:
    resumo = hashlib.sha256()
    for caminho in caminhos:
        with caminho.open("rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                resumo.update(bloco)
    return resumo.hexdigest()


def _lotes(
    registros: Sequence[dict[str, Any]], tamanho: int
) -> Iterable[Sequence[dict[str, Any]]]:
    if tamanho <= 0:
        raise ValueError("O tamanho do lote deve ser positivo.")
    for inicio in range(0, len(registros), tamanho):
        yield registros[inicio : inicio + tamanho]


def criar_estrutura(conexao: Any, schema: str) -> None:
    with conexao.cursor() as cursor:
        for comando in criar_comandos_schema(schema):
            cursor.execute(comando)


def _registros_importacao(
    ocorrencias: Sequence[dict[str, Any]],
    inicio: datetime,
    caminho_taxa: Path,
    caminho_ocorrencias: Path,
    estatisticas: Mapping[str, Mapping[str, int]] | None = None,
) -> list[dict[str, Any]]:
    checksum = calcular_checksum([caminho_taxa, caminho_ocorrencias])
    fim = datetime.now(timezone.utc)
    importacoes = []
    for pais in preparar_paises(ocorrencias):
        registros_pais = [
            registro
            for registro in ocorrencias
            if registro["country_code"] == pais["iso_code"]
        ]
        chaves = {registro["taxon_key"] for registro in registros_pais}
        estatistica_completa = bool(estatisticas and pais["iso_code"] in estatisticas)
        estatistica = (estatisticas or {}).get(pais["iso_code"], {})
        recebidos = int(estatistica.get("records_received", len(registros_pais)))
        rejeitados_taxonomia = int(estatistica.get("records_rejected_taxonomy", 0))
        descartados = int(
            estatistica.get("records_rejected", recebidos - len(registros_pais))
        )
        if min(recebidos, descartados, rejeitados_taxonomia) < 0:
            raise ValueError("As estatísticas da importação não podem ser negativas.")
        if recebidos < len(registros_pais):
            raise ValueError(
                "Registros recebidos não pode ser menor que registros salvos."
            )
        if descartados != recebidos - len(registros_pais):
            raise ValueError(
                "Registros descartados deve ser a diferença entre recebidos e salvos."
            )
        if rejeitados_taxonomia > descartados:
            raise ValueError(
                "Rejeições taxonômicas não pode exceder registros descartados."
            )
        importacoes.append(
            {
                "country_code": pais["iso_code"],
                "taxon_key": next(iter(chaves)) if len(chaves) == 1 else None,
                "started_at": inicio,
                "finished_at": fim,
                "records_received": recebidos,
                "records_saved": len(registros_pais),
                "records_rejected": descartados,
                "records_rejected_taxonomy": rejeitados_taxonomia,
                "quality_stats_complete": estatistica_completa,
                "status": "COMPLETED",
                "taxa_file": str(caminho_taxa),
                "occurrences_file": str(caminho_ocorrencias),
                "source_checksum": checksum,
            }
        )
    return importacoes


def carregar_registros(
    conexao: Any,
    taxa: Sequence[dict[str, Any]],
    ocorrencias: Sequence[dict[str, Any]],
    schema: str,
    tamanho_lote: int,
    caminho_taxa: Path,
    caminho_ocorrencias: Path,
    estatisticas_importacao: Mapping[str, Mapping[str, int]] | None = None,
    *,
    substituir_paises: bool = False,
) -> dict[str, int]:
    schema = validar_schema(schema)
    validar_referencias(taxa, ocorrencias)
    inicio = datetime.now(timezone.utc)
    criar_estrutura(conexao, schema)
    paises = preparar_paises(ocorrencias)
    importacoes = _registros_importacao(
        ocorrencias,
        inicio,
        caminho_taxa,
        caminho_ocorrencias,
        estatisticas_importacao,
    )
    with conexao.cursor() as cursor:
        cursor.executemany(SQL_UPSERT_PAISES.format(schema=schema), paises)
        if substituir_paises and paises:
            cursor.execute(
                f"DELETE FROM {schema}.occurrences WHERE country_code = ANY(%s)",
                ([pais["iso_code"] for pais in paises],),
            )
        for lote in _lotes(taxa, tamanho_lote):
            cursor.executemany(SQL_UPSERT_TAXA.format(schema=schema), lote)
        for lote in _lotes(ocorrencias, tamanho_lote):
            cursor.executemany(SQL_UPSERT_OCORRENCIAS.format(schema=schema), lote)
        cursor.executemany(SQL_REGISTRAR_IMPORTACOES.format(schema=schema), importacoes)
    return {
        "countries": len(paises),
        "taxa": len(taxa),
        "occurrences": len(ocorrencias),
        "imports": len(importacoes),
    }


def verificar_carga(conexao: Any, schema: str) -> dict[str, int]:
    schema = validar_schema(schema)
    with conexao.cursor() as cursor:
        contagens = {}
        for chave, tabela in (
            ("countries", "countries"),
            ("taxa", "taxa"),
            ("occurrences", "occurrences"),
            ("imports", "data_imports"),
        ):
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.{tabela}")
            contagens[chave] = int(cursor.fetchone()[0])
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM {schema}.occurrences o
            LEFT JOIN {schema}.taxa t ON t.taxon_key = o.taxon_key
            LEFT JOIN {schema}.countries c ON c.iso_code = o.country_code
            WHERE t.taxon_key IS NULL OR c.iso_code IS NULL
            """
        )
        contagens["orphans"] = int(cursor.fetchone()[0])
    return contagens


def carregar_csv(caminho: Path, colunas: set[str], nome: str) -> pd.DataFrame:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de {nome} nao encontrado: {caminho}")
    dados = pd.read_csv(
        caminho,
        dtype={"speciesKey": "string", "countryCode": "string"},
    )
    validar_tabela(dados, colunas, nome)
    return dados


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Carrega países, táxons e ocorrências no PostgreSQL."
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
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    configurar_logging(argumentos.verbose)
    configuracao_banco = ConfiguracaoBanco.do_ambiente(
        argumentos.env_file, argumentos.schema
    )
    schema = configuracao_banco.schema
    dados_taxa = carregar_csv(argumentos.especies, COLUNAS_TAXA, "taxa")
    dados_ocorrencias = carregar_csv(
        argumentos.ocorrencias, COLUNAS_OCORRENCIAS, "ocorrencias"
    )
    taxa = preparar_taxa(dados_taxa)
    ocorrencias = preparar_ocorrencias(dados_ocorrencias)
    validar_referencias(taxa, ocorrencias)

    if argumentos.dry_run:
        LOGGER.info("Táxons validados: %s", len(taxa))
        LOGGER.info("Ocorrências validadas: %s", len(ocorrencias))
        LOGGER.info("Países encontrados: %s", len(preparar_paises(ocorrencias)))
        LOGGER.info("Dry-run concluído; nenhuma conexão foi aberta.")
        return

    try:
        database_url = configuracao_banco.exigir_url()
    except ValueError as erro:
        raise SystemExit(str(erro)) from erro

    try:
        with psycopg.connect(database_url) as conexao:
            resultado = carregar_registros(
                conexao,
                taxa,
                ocorrencias,
                schema,
                argumentos.tamanho_lote,
                argumentos.especies,
                argumentos.ocorrencias,
            )
            verificacao = verificar_carga(conexao, schema)
    except psycopg.Error as erro:
        raise SystemExit(f"Falha na carga PostgreSQL: {erro}") from erro

    LOGGER.info("Países processados: %s", resultado["countries"])
    LOGGER.info("Táxons processados: %s", resultado["taxa"])
    LOGGER.info("Ocorrências processadas: %s", resultado["occurrences"])
    LOGGER.info("Importações registradas: %s", resultado["imports"])
    LOGGER.info("Países no banco: %s", verificacao["countries"])
    LOGGER.info("Táxons no banco: %s", verificacao["taxa"])
    LOGGER.info("Ocorrências no banco: %s", verificacao["occurrences"])
    LOGGER.info("Referências órfãs: %s", verificacao["orphans"])


if __name__ == "__main__":
    main()

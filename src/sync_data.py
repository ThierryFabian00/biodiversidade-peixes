"""Sincronização controlada entre cache PostgreSQL e API do GBIF."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
import requests

from src.config import (
    GBIF_API,
    GRUPOS_PEIXES,
    LIMITE_AMOSTRA_PEIXES,
    PASTA_PROJETO,
    TAMANHO_LOTE_PADRAO,
    TAMANHO_MAXIMO_PAGINA,
)
from src.database import validar_schema
from src.extract_fish import (
    ResultadoPeixes,
    buscar_ocorrencias_peixes,
    salvar_resultado,
)
from src.load import (
    carregar_registros,
    criar_estrutura,
    preparar_ocorrencias,
    preparar_taxa,
)
from src.services.country_service import normalizar_codigo_pais
from src.transform_fish import (
    ARQUIVO_REFERENCIA_ORIGEM,
    salvar_tabelas,
    transformar_registros,
)


@dataclass(frozen=True)
class StatusCache:
    codigo_pais: str
    registros: int
    taxa: int
    atualizado_em: datetime | None
    registros_descartados: int = 0
    estatisticas_completas: bool = False

    @property
    def disponivel(self) -> bool:
        return self.registros > 0


@dataclass(frozen=True)
class ProgressoSincronizacao:
    etapa: str
    mensagem: str
    coletados: int = 0
    total: int = 0
    paginas: int = 0


@dataclass(frozen=True)
class ResultadoSincronizacao:
    fonte: str
    status_cache: StatusCache
    paginas_consultadas: int = 0
    registros_recebidos: int = 0
    registros_salvos: int = 0


CallbackProgresso = Callable[[ProgressoSincronizacao], None]


def consultar_status_cache(
    conexao: Any,
    schema: str,
    codigo_pais: str,
    grupos_taxonomicos: Mapping[str, str] = GRUPOS_PEIXES,
) -> StatusCache:
    schema = validar_schema(schema)
    codigo_pais = normalizar_codigo_pais(codigo_pais)
    grupos = list(grupos_taxonomicos)
    if not grupos:
        raise ValueError("Informe ao menos um grupo taxonômico.")

    with conexao.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                COUNT(o.gbif_key),
                COUNT(DISTINCT o.taxon_key),
                (
                    SELECT MAX(i.finished_at)
                    FROM {schema}.data_imports i
                    WHERE i.country_code = %s
                      AND i.status = 'COMPLETED'
                ),
                COALESCE((
                    SELECT i.records_rejected
                    FROM {schema}.data_imports i
                    WHERE i.country_code = %s
                    ORDER BY i.finished_at DESC NULLS LAST, i.id DESC
                    LIMIT 1
                ), 0),
                COALESCE((
                    SELECT i.quality_stats_complete
                    FROM {schema}.data_imports i
                    WHERE i.country_code = %s
                    ORDER BY i.finished_at DESC NULLS LAST, i.id DESC
                    LIMIT 1
                ), FALSE)
            FROM {schema}.occurrences o
            JOIN {schema}.taxa t ON t.taxon_key = o.taxon_key
            WHERE o.country_code = %s
              AND t.fish_group = ANY(%s)
            """,
            (codigo_pais, codigo_pais, codigo_pais, codigo_pais, grupos),
        )
        linha = cursor.fetchone()
    return StatusCache(
        codigo_pais=codigo_pais,
        registros=int(linha[0]),
        taxa=int(linha[1]),
        atualizado_em=linha[2],
        registros_descartados=int(linha[3]),
        estatisticas_completas=bool(linha[4]),
    )


def _consultar_cache_com_estrutura(
    conexao: Any,
    schema: str,
    codigo_pais: str,
    grupos_taxonomicos: Mapping[str, str],
) -> StatusCache:
    try:
        return consultar_status_cache(conexao, schema, codigo_pais, grupos_taxonomicos)
    except (
        psycopg.errors.UndefinedColumn,
        psycopg.errors.UndefinedTable,
        psycopg.errors.InvalidSchemaName,
    ):
        conexao.rollback()
        criar_estrutura(conexao, schema)
        return consultar_status_cache(conexao, schema, codigo_pais, grupos_taxonomicos)


def consultar_status_cache_url(
    database_url: str,
    schema: str,
    codigo_pais: str,
    grupos_taxonomicos: Mapping[str, str] = GRUPOS_PEIXES,
) -> StatusCache:
    with psycopg.connect(database_url) as conexao:
        return _consultar_cache_com_estrutura(
            conexao, schema, codigo_pais, grupos_taxonomicos
        )


def _emitir(
    callback: CallbackProgresso | None,
    etapa: str,
    mensagem: str,
    coletados: int = 0,
    total: int = 0,
    paginas: int = 0,
) -> None:
    if callback:
        callback(
            ProgressoSincronizacao(
                etapa=etapa,
                mensagem=mensagem,
                coletados=coletados,
                total=total,
                paginas=paginas,
            )
        )


def _caminhos_pais(codigo_pais: str) -> tuple[Path, Path, Path, Path]:
    sufixo = codigo_pais.lower()
    pasta_bruta = PASTA_PROJETO / "data" / "raw"
    pasta_processada = PASTA_PROJETO / "data" / "processed"
    return (
        pasta_bruta / f"ocorrencias_peixes_{sufixo}.jsonl",
        pasta_processada / f"ocorrencias_peixes_{sufixo}.csv",
        pasta_processada / f"especies_peixes_{sufixo}.csv",
        pasta_processada / f"problemas_taxonomicos_{sufixo}.csv",
    )


def _carregar_referencia(caminho: Path) -> pd.DataFrame | None:
    return pd.read_csv(caminho) if caminho.exists() else None


def sincronizar_dados_pais(
    database_url: str,
    schema: str,
    codigo_pais: str,
    *,
    forcar_atualizacao: bool = False,
    max_registros: int = LIMITE_AMOSTRA_PEIXES,
    tamanho_pagina: int = TAMANHO_MAXIMO_PAGINA,
    grupos_taxonomicos: Mapping[str, str] = GRUPOS_PEIXES,
    gbif_api: str = GBIF_API,
    sessao: requests.Session | None = None,
    callback: CallbackProgresso | None = None,
    caminho_referencia: Path = ARQUIVO_REFERENCIA_ORIGEM,
) -> ResultadoSincronizacao:
    schema = validar_schema(schema)
    codigo_pais = normalizar_codigo_pais(codigo_pais)

    _emitir(callback, "cache", "Consultando o cache PostgreSQL.")
    with psycopg.connect(database_url) as conexao:
        status = _consultar_cache_com_estrutura(
            conexao, schema, codigo_pais, grupos_taxonomicos
        )
    if status.disponivel and not forcar_atualizacao:
        return ResultadoSincronizacao("PostgreSQL", status)

    _emitir(callback, "gbif", "Consultando ocorrências no GBIF.")

    def progresso_gbif(coletados: int, total: int, paginas: int) -> None:
        _emitir(
            callback,
            "gbif",
            f"Coletando ocorrências: {coletados}/{total}.",
            coletados,
            total,
            paginas,
        )

    resultado: ResultadoPeixes = buscar_ocorrencias_peixes(
        max_registros=max_registros,
        tamanho_pagina=tamanho_pagina,
        sessao=sessao,
        grupos_taxonomicos=grupos_taxonomicos,
        progresso=progresso_gbif,
        gbif_api=gbif_api,
        pais=codigo_pais,
    )
    if not resultado.registros:
        raise ValueError(f"O GBIF não retornou ocorrências para {codigo_pais}.")

    caminho_bruto, caminho_ocorrencias, caminho_taxa, caminho_problemas = (
        _caminhos_pais(codigo_pais)
    )
    salvar_resultado(
        resultado,
        caminho_bruto,
        None,
        max_registros,
        grupos_taxonomicos,
        gbif_api,
        codigo_pais,
    )

    _emitir(callback, "transformacao", "Normalizando táxons e ocorrências.")
    referencia = _carregar_referencia(caminho_referencia)
    ocorrencias, taxa, problemas, resumo = transformar_registros(
        resultado.registros,
        None,
        referencia,
    )
    if ocorrencias.empty or taxa.empty:
        raise ValueError("Nenhuma ocorrência válida permaneceu após a normalização.")

    caminho_metadados = caminho_bruto.with_name(f"{caminho_bruto.stem}_metadata.json")
    metadados = json.loads(caminho_metadados.read_text(encoding="utf-8"))
    salvar_tabelas(
        ocorrencias,
        taxa,
        problemas,
        resumo,
        (caminho_ocorrencias, caminho_taxa, caminho_problemas),
        metadados,
    )

    _emitir(callback, "postgresql", "Atualizando o cache PostgreSQL.")
    taxa_preparada = preparar_taxa(taxa)
    ocorrencias_preparadas = preparar_ocorrencias(ocorrencias)
    with psycopg.connect(database_url) as conexao:
        carregar_registros(
            conexao,
            taxa_preparada,
            ocorrencias_preparadas,
            schema,
            TAMANHO_LOTE_PADRAO,
            caminho_taxa,
            caminho_ocorrencias,
            {
                codigo_pais: {
                    "records_received": len(resultado.registros),
                    "records_rejected": len(resultado.registros)
                    - len(ocorrencias_preparadas),
                    "records_rejected_taxonomy": len(problemas),
                }
            },
            substituir_paises=True,
        )
        status = consultar_status_cache(
            conexao, schema, codigo_pais, grupos_taxonomicos
        )

    _emitir(
        callback,
        "concluido",
        f"Atualização concluída: {len(ocorrencias_preparadas)} registros salvos.",
        len(ocorrencias_preparadas),
        len(ocorrencias_preparadas),
        resultado.paginas_consultadas,
    )
    return ResultadoSincronizacao(
        fonte="GBIF",
        status_cache=status,
        paginas_consultadas=resultado.paginas_consultadas,
        registros_recebidos=len(resultado.registros),
        registros_salvos=len(ocorrencias_preparadas),
    )

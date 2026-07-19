import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import geopandas as gpd
import requests
from shapely import orient_polygons

from src.config import (
    CHECKLIST_GBIF,
    GBIF_API,
    GRUPOS_PEIXES,
    LIMITE_AMOSTRA_PEIXES,
    LIMITE_BUSCA_GBIF,
    TAMANHO_MAXIMO_PAGINA,
    ConfiguracaoAplicacao,
)
from src.filter_basin import ARQUIVO_LIMITE, carregar_limite
from src.gbif_client import criar_sessao, requisitar_json
from src.logging_config import configurar_logging

LOGGER = logging.getLogger(__name__)

PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_SAIDA = PASTA_PROJETO / "data" / "raw" / "ocorrencias_peixes_amostra.jsonl"
CHECKLIST_COL = CHECKLIST_GBIF
MAX_REGISTROS_PADRAO = LIMITE_AMOSTRA_PEIXES


def selecionar_grupo_taxonomico(nome: str) -> dict[str, str]:
    nome_normalizado = nome.strip().casefold()
    for grupo, chave in GRUPOS_PEIXES.items():
        if grupo.casefold() == nome_normalizado:
            return {grupo: chave}
    opcoes = ", ".join(sorted(GRUPOS_PEIXES))
    raise ValueError(f"Grupo taxonômico desconhecido: {nome}. Opções: {opcoes}")


@dataclass(frozen=True)
class ResultadoPeixes:
    registros: list[dict[str, Any]]
    paginas_consultadas: int
    total_disponivel: int


def criar_prefiltro_wkt(limite: gpd.GeoDataFrame) -> str:
    if limite.empty or limite.crs is None:
        raise ValueError("O limite geográfico deve possuir geometria e CRS.")

    poligono = limite.to_crs("EPSG:4326").geometry.union_all()
    prefiltro = orient_polygons(poligono.convex_hull, exterior_cw=False)
    if not prefiltro.covers(poligono):
        raise ValueError("O pré-filtro não cobre integralmente o limite da bacia.")
    return prefiltro.wkt


def requisitar_pagina(
    sessao: requests.Session,
    parametros: list[tuple[str, Any]],
    gbif_api: str = GBIF_API,
) -> dict[str, Any]:
    dados = requisitar_json(
        sessao,
        f"{gbif_api}/occurrence/search",
        parametros,
        timeout=60,
    )
    if not isinstance(dados.get("results"), list):
        raise ValueError("A API do GBIF retornou uma página inválida.")
    return dados


def buscar_ocorrencias_peixes(
    geometria_wkt: str,
    max_registros: int = MAX_REGISTROS_PADRAO,
    tamanho_pagina: int = TAMANHO_MAXIMO_PAGINA,
    sessao: requests.Session | None = None,
    grupos_taxonomicos: Mapping[str, str] = GRUPOS_PEIXES,
    gbif_api: str = GBIF_API,
) -> ResultadoPeixes:
    if not 1 <= tamanho_pagina <= TAMANHO_MAXIMO_PAGINA:
        raise ValueError(
            f"O tamanho da página deve estar entre 1 e {TAMANHO_MAXIMO_PAGINA}."
        )
    if not 1 <= max_registros <= LIMITE_BUSCA_GBIF:
        raise ValueError(
            f"A amostra deve conter entre 1 e {LIMITE_BUSCA_GBIF} registros."
        )
    if not grupos_taxonomicos:
        raise ValueError("Informe ao menos um grupo taxonômico.")

    sessao = sessao or criar_sessao()
    registros: list[dict[str, Any]] = []
    offset = 0
    paginas = 0
    total_disponivel = 0

    while len(registros) < max_registros:
        limite = min(tamanho_pagina, max_registros - len(registros))
        parametros = [
            *(("taxonKey", chave) for chave in grupos_taxonomicos.values()),
            ("checklistKey", CHECKLIST_COL),
            ("geometry", geometria_wkt),
            ("hasCoordinate", "true"),
            ("occurrenceStatus", "PRESENT"),
            ("limit", limite),
            ("offset", offset),
        ]
        dados = requisitar_pagina(sessao, parametros, gbif_api)
        pagina = dados["results"]
        paginas += 1
        if isinstance(dados.get("count"), int):
            total_disponivel = dados["count"]

        registros.extend(pagina)
        if dados.get("endOfRecords") or not pagina:
            break
        offset += len(pagina)

    return ResultadoPeixes(registros, paginas, total_disponivel)


def salvar_resultado(
    resultado: ResultadoPeixes,
    caminho_saida: Path,
    caminho_limite: Path,
    max_registros: int,
    grupos_taxonomicos: Mapping[str, str] = GRUPOS_PEIXES,
    gbif_api: str = GBIF_API,
) -> None:
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    with caminho_saida.open("w", encoding="utf-8") as arquivo:
        for registro in resultado.registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False))
            arquivo.write("\n")

    metadados = {
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "source": f"{gbif_api}/occurrence/search",
        "checklistKey": CHECKLIST_COL,
        "taxonGroups": dict(grupos_taxonomicos),
        "spatialPrefilter": "convex hull of the basin boundary",
        "exactBoundaryFile": str(caminho_limite),
        "occurrenceStatus": "PRESENT",
        "hasCoordinate": True,
        "sampleLimit": max_registros,
        "recordsCollected": len(resultado.registros),
        "recordsAvailableInPrefilter": resultado.total_disponivel,
        "pagesRequested": resultado.paginas_consultadas,
        "isComplete": len(resultado.registros) >= resultado.total_disponivel,
        "warning": (
            "A consulta excede o limite da API de busca. Este arquivo é uma "
            "amostra; uma base completa exige GBIF Occurrence Download com DOI."
        ),
    }
    caminho_metadados = caminho_saida.with_name(f"{caminho_saida.stem}_metadata.json")
    caminho_metadados.write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def criar_parser(
    configuracao: ConfiguracaoAplicacao | None = None,
) -> argparse.ArgumentParser:
    configuracao = configuracao or ConfiguracaoAplicacao.do_ambiente()
    parser = argparse.ArgumentParser(
        description="Extrai uma amostra multiespécies de peixes no GBIF."
    )
    parser.add_argument("--limite", type=Path, default=ARQUIVO_LIMITE)
    parser.add_argument(
        "--grupo-taxonomico",
        default=configuracao.grupo_taxonomico,
        help="Grupo de peixes consultado no GBIF.",
    )
    parser.add_argument("--saida", type=Path, default=ARQUIVO_SAIDA)
    parser.add_argument(
        "--max-registros",
        type=int,
        default=MAX_REGISTROS_PADRAO,
    )
    parser.add_argument(
        "--tamanho-pagina",
        type=int,
        default=configuracao.tamanho_pagina_padrao,
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    configuracao = ConfiguracaoAplicacao.do_ambiente()
    argumentos = criar_parser(configuracao).parse_args()
    configurar_logging(argumentos.verbose)
    limite = carregar_limite(argumentos.limite)
    geometria_wkt = criar_prefiltro_wkt(limite)
    grupos_taxonomicos = selecionar_grupo_taxonomico(argumentos.grupo_taxonomico)
    resultado = buscar_ocorrencias_peixes(
        geometria_wkt,
        max_registros=argumentos.max_registros,
        tamanho_pagina=argumentos.tamanho_pagina,
        grupos_taxonomicos=grupos_taxonomicos,
        gbif_api=configuracao.gbif_api,
    )
    salvar_resultado(
        resultado,
        argumentos.saida,
        argumentos.limite,
        argumentos.max_registros,
        grupos_taxonomicos=grupos_taxonomicos,
        gbif_api=configuracao.gbif_api,
    )

    LOGGER.info("Grupo taxonômico: %s", argumentos.grupo_taxonomico)
    LOGGER.info("Registros disponíveis no pré-filtro: %s", resultado.total_disponivel)
    LOGGER.info("Registros coletados na amostra: %s", len(resultado.registros))
    LOGGER.info("Páginas consultadas: %s", resultado.paginas_consultadas)
    LOGGER.info("JSONL bruto salvo em: %s", argumentos.saida)


if __name__ == "__main__":
    main()

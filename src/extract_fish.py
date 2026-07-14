import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests
from shapely import orient_polygons

from src.extract import (
    GBIF_API,
    LIMITE_BUSCA_GBIF,
    TAMANHO_MAXIMO_PAGINA,
    criar_sessao,
)
from src.filter_basin import ARQUIVO_LIMITE, carregar_limite

PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_SAIDA = (
    PASTA_PROJETO / "data" / "raw" / "ocorrencias_peixes_amostra.jsonl"
)
CHECKLIST_COL = "7ddf754f-d193-4cc9-b351-99906754a03b"
MAX_REGISTROS_PADRAO = 5_000

GRUPOS_PEIXES = {
    "Actinopterygii": "8VR36",
    "Elasmobranchii": "LB",
    "Dipneusti": "8V4VF",
    "Myxini": "6225G",
    "Petromyzonti": "8VJWX",
}


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
) -> dict[str, Any]:
    resposta = sessao.get(
        f"{GBIF_API}/occurrence/search",
        params=parametros,
        timeout=60,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    if not isinstance(dados, dict) or not isinstance(dados.get("results"), list):
        raise ValueError("A API do GBIF retornou uma página inválida.")
    return dados


def buscar_ocorrencias_peixes(
    geometria_wkt: str,
    max_registros: int = MAX_REGISTROS_PADRAO,
    tamanho_pagina: int = TAMANHO_MAXIMO_PAGINA,
    sessao: requests.Session | None = None,
) -> ResultadoPeixes:
    if not 1 <= tamanho_pagina <= TAMANHO_MAXIMO_PAGINA:
        raise ValueError("O tamanho da página deve estar entre 1 e 300.")
    if not 1 <= max_registros <= LIMITE_BUSCA_GBIF:
        raise ValueError("A amostra deve conter entre 1 e 100000 registros.")

    sessao = sessao or criar_sessao()
    registros: list[dict[str, Any]] = []
    offset = 0
    paginas = 0
    total_disponivel = 0

    while len(registros) < max_registros:
        limite = min(tamanho_pagina, max_registros - len(registros))
        parametros = [
            *(('taxonKey', chave) for chave in GRUPOS_PEIXES.values()),
            ("checklistKey", CHECKLIST_COL),
            ("geometry", geometria_wkt),
            ("hasCoordinate", "true"),
            ("occurrenceStatus", "PRESENT"),
            ("limit", limite),
            ("offset", offset),
        ]
        dados = requisitar_pagina(sessao, parametros)
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
) -> None:
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    with caminho_saida.open("w", encoding="utf-8") as arquivo:
        for registro in resultado.registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False))
            arquivo.write("\n")

    metadados = {
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "source": f"{GBIF_API}/occurrence/search",
        "checklistKey": CHECKLIST_COL,
        "taxonGroups": GRUPOS_PEIXES,
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
    caminho_metadados = caminho_saida.with_name(
        f"{caminho_saida.stem}_metadata.json"
    )
    caminho_metadados.write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrai uma amostra multiespécies de peixes no GBIF."
    )
    parser.add_argument("--limite", type=Path, default=ARQUIVO_LIMITE)
    parser.add_argument("--saida", type=Path, default=ARQUIVO_SAIDA)
    parser.add_argument(
        "--max-registros",
        type=int,
        default=MAX_REGISTROS_PADRAO,
    )
    parser.add_argument(
        "--tamanho-pagina",
        type=int,
        default=TAMANHO_MAXIMO_PAGINA,
    )
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    limite = carregar_limite(argumentos.limite)
    geometria_wkt = criar_prefiltro_wkt(limite)
    resultado = buscar_ocorrencias_peixes(
        geometria_wkt,
        max_registros=argumentos.max_registros,
        tamanho_pagina=argumentos.tamanho_pagina,
    )
    salvar_resultado(
        resultado,
        argumentos.saida,
        argumentos.limite,
        argumentos.max_registros,
    )

    print(f"Registros disponíveis no pré-filtro: {resultado.total_disponivel}")
    print(f"Registros coletados na amostra: {len(resultado.registros)}")
    print(f"Páginas consultadas: {resultado.paginas_consultadas}")
    print(f"JSONL bruto salvo em: {argumentos.saida}")


if __name__ == "__main__":
    main()

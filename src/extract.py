import argparse
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from src.config import (
    ESPECIE_PADRAO,
    GBIF_API,
    LIMITE_BUSCA_GBIF,
    PAIS_PADRAO,
    TAMANHO_MAXIMO_PAGINA,
    ConfiguracaoAplicacao,
)
from src.gbif_client import criar_sessao, requisitar_json
from src.logging_config import configurar_logging
from src.services.occurrence_service import ParametrosConsultaOcorrencia

LOGGER = logging.getLogger(__name__)
COLUNAS = [
    "key",
    "scientificName",
    "decimalLatitude",
    "decimalLongitude",
    "eventDate",
    "stateProvince",
    "locality",
    "basisOfRecord",
]


@dataclass(frozen=True)
class ResultadoExtracao:
    registros: list[dict[str, Any]]
    paginas_consultadas: int
    total_disponivel: int | None


def buscar_especie(
    nome_cientifico: str,
    sessao: requests.Session | None = None,
    gbif_api: str = GBIF_API,
) -> dict[str, Any]:
    sessao = sessao or criar_sessao()
    dados = requisitar_json(
        sessao,
        f"{gbif_api}/species/match",
        {"name": nome_cientifico},
    )

    if "usageKey" not in dados:
        raise ValueError(f"Espécie não encontrada no GBIF: {nome_cientifico}")

    return dados


def buscar_ocorrencias(
    taxon_key: int,
    pais: str = PAIS_PADRAO,
    tamanho_pagina: int = TAMANHO_MAXIMO_PAGINA,
    max_registros: int | None = None,
    sessao: requests.Session | None = None,
    gbif_api: str = GBIF_API,
) -> ResultadoExtracao:
    consulta = ParametrosConsultaOcorrencia(
        taxon_key, pais, tamanho_pagina, max_registros
    )

    sessao = sessao or criar_sessao()
    url = f"{gbif_api}/occurrence/search"
    registros: list[dict[str, Any]] = []
    offset = 0
    paginas_consultadas = 0
    total_disponivel: int | None = None

    while True:
        limite = tamanho_pagina
        if max_registros is not None:
            limite = min(limite, max_registros - len(registros))

        parametros = consulta.parametros_api(offset, limite)
        dados = requisitar_json(sessao, url, parametros)
        pagina = dados.get("results")

        if not isinstance(pagina, list):
            raise ValueError("Resposta do GBIF sem uma lista valida em 'results'.")

        paginas_consultadas += 1
        total = dados.get("count")
        if isinstance(total, int):
            total_disponivel = total
            if total > LIMITE_BUSCA_GBIF and max_registros is None:
                raise ValueError(
                    f"A consulta possui {total} registros, acima do limite de "
                    "100000 da API de busca. Informe --max-registros ou use o "
                    "serviço de download do GBIF."
                )

        registros.extend(pagina)

        atingiu_limite = max_registros is not None and len(registros) >= max_registros
        fim_dos_registros = bool(dados.get("endOfRecords"))
        if atingiu_limite or fim_dos_registros or not pagina:
            break

        offset += len(pagina)

    return ResultadoExtracao(
        registros=registros,
        paginas_consultadas=paginas_consultadas,
        total_disponivel=total_disponivel,
    )


def criar_nome_arquivo(nome_cientifico: str) -> str:
    nome_normalizado = unicodedata.normalize("NFKD", nome_cientifico)
    nome_ascii = nome_normalizado.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", nome_ascii.lower()).strip("_")
    return f"ocorrencias_{slug}.csv"


def salvar_resultados(
    resultado: ResultadoExtracao,
    especie: dict[str, Any],
    nome_consultado: str,
    pais: str,
    caminho_saida: Path,
    gbif_api: str = GBIF_API,
) -> None:
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    tabela = pd.DataFrame(resultado.registros).reindex(columns=COLUNAS)
    tabela.to_csv(caminho_saida, index=False, encoding="utf-8")

    metadados = {
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "source": f"{gbif_api}/occurrence/search",
        "query": {
            "scientificName": nome_consultado,
            "taxonKey": especie["usageKey"],
            "country": pais,
            "hasCoordinate": True,
        },
        "matchedScientificName": especie.get("scientificName"),
        "recordsCollected": len(tabela),
        "recordsAvailable": resultado.total_disponivel,
        "pagesRequested": resultado.paginas_consultadas,
        "dataFile": caminho_saida.name,
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
        description="Extrai ocorrências paginadas da API do GBIF."
    )
    parser.add_argument(
        "--especie",
        default=configuracao.especie_padrao,
        help="Nome científico consultado no GBIF.",
    )
    parser.add_argument(
        "--pais",
        default=configuracao.pais_padrao,
        help=f"Código ISO de duas letras (padrão: {configuracao.pais_padrao}).",
    )
    parser.add_argument(
        "--max-registros",
        type=int,
        default=configuracao.limite_padrao,
        help="Quantidade máxima de registros da consulta.",
    )
    parser.add_argument(
        "--tamanho-pagina",
        type=int,
        default=configuracao.tamanho_pagina_padrao,
        help=f"Registros por requisição, de 1 a {TAMANHO_MAXIMO_PAGINA}.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=None,
        help="Caminho do CSV bruto de saida.",
    )
    return parser


def main() -> None:
    configuracao = ConfiguracaoAplicacao.do_ambiente()
    argumentos = criar_parser(configuracao).parse_args()
    configurar_logging()
    sessao = criar_sessao()
    especie = buscar_especie(argumentos.especie, sessao, configuracao.gbif_api)
    if argumentos.saida:
        caminho_saida = argumentos.saida
    elif argumentos.especie.casefold() == ESPECIE_PADRAO.casefold():
        caminho_saida = Path("data/raw/ocorrencias_tilapia.csv")
    else:
        caminho_saida = Path("data/raw") / criar_nome_arquivo(argumentos.especie)

    LOGGER.info("Espécie encontrada: %s", especie.get("scientificName"))
    LOGGER.info("Taxon key: %s", especie["usageKey"])

    resultado = buscar_ocorrencias(
        taxon_key=especie["usageKey"],
        pais=argumentos.pais.upper(),
        tamanho_pagina=argumentos.tamanho_pagina,
        max_registros=argumentos.max_registros,
        sessao=sessao,
        gbif_api=configuracao.gbif_api,
    )
    salvar_resultados(
        resultado,
        especie,
        argumentos.especie,
        argumentos.pais.upper(),
        caminho_saida,
        gbif_api=configuracao.gbif_api,
    )

    LOGGER.info("Foram coletados %s registros.", len(resultado.registros))
    LOGGER.info("Páginas consultadas: %s", resultado.paginas_consultadas)
    LOGGER.info("CSV salvo em: %s", caminho_saida)


if __name__ == "__main__":
    main()

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import truststore
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

truststore.inject_into_ssl()

GBIF_API = "https://api.gbif.org/v1"
TAMANHO_MAXIMO_PAGINA = 300
LIMITE_BUSCA_GBIF = 100_000
ESPECIE_PADRAO = "Oreochromis niloticus"
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


def criar_sessao() -> requests.Session:
    retentativas = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adaptador = HTTPAdapter(max_retries=retentativas)
    sessao = requests.Session()
    sessao.mount("https://", adaptador)
    return sessao


def requisitar_json(
    sessao: requests.Session,
    url: str,
    parametros: dict[str, Any],
) -> dict[str, Any]:
    resposta = sessao.get(url, params=parametros, timeout=30)
    resposta.raise_for_status()

    try:
        dados = resposta.json()
    except requests.exceptions.JSONDecodeError as erro:
        raise ValueError("A API do GBIF retornou uma resposta JSON inválida.") from erro

    if not isinstance(dados, dict):
        raise ValueError("A API do GBIF retornou um formato inesperado.")

    return dados


def buscar_especie(
    nome_cientifico: str,
    sessao: requests.Session | None = None,
) -> dict[str, Any]:
    sessao = sessao or criar_sessao()
    dados = requisitar_json(
        sessao,
        f"{GBIF_API}/species/match",
        {"name": nome_cientifico},
    )

    if "usageKey" not in dados:
        raise ValueError(f"Espécie não encontrada no GBIF: {nome_cientifico}")

    return dados


def buscar_ocorrencias(
    taxon_key: int,
    pais: str = "BR",
    tamanho_pagina: int = TAMANHO_MAXIMO_PAGINA,
    max_registros: int | None = None,
    sessao: requests.Session | None = None,
) -> ResultadoExtracao:
    if not 1 <= tamanho_pagina <= TAMANHO_MAXIMO_PAGINA:
        raise ValueError(
            f"O tamanho da página deve estar entre 1 e {TAMANHO_MAXIMO_PAGINA}."
        )
    if max_registros is not None and max_registros < 1:
        raise ValueError("O limite total de registros deve ser maior que zero.")
    if max_registros is not None and max_registros > LIMITE_BUSCA_GBIF:
        raise ValueError(
            "A API de busca do GBIF permite no máximo 100000 registros. "
            "Para volumes maiores, use o serviço de download do GBIF."
        )

    sessao = sessao or criar_sessao()
    url = f"{GBIF_API}/occurrence/search"
    registros: list[dict[str, Any]] = []
    offset = 0
    paginas_consultadas = 0
    total_disponivel: int | None = None

    while True:
        limite = tamanho_pagina
        if max_registros is not None:
            limite = min(limite, max_registros - len(registros))

        parametros = {
            "taxon_key": taxon_key,
            "country": pais,
            "has_coordinate": "true",
            "limit": limite,
            "offset": offset,
        }
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
) -> None:
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    tabela = pd.DataFrame(resultado.registros).reindex(columns=COLUNAS)
    tabela.to_csv(caminho_saida, index=False, encoding="utf-8")

    metadados = {
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "source": f"{GBIF_API}/occurrence/search",
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


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrai ocorrências paginadas da API do GBIF."
    )
    parser.add_argument(
        "--especie",
        default=ESPECIE_PADRAO,
        help="Nome científico consultado no GBIF.",
    )
    parser.add_argument(
        "--pais",
        default="BR",
        help="Código de duas letras do país (padrão: BR).",
    )
    parser.add_argument(
        "--max-registros",
        type=int,
        default=None,
        help="Quantidade máxima a coletar; sem este argumento, coleta todos.",
    )
    parser.add_argument(
        "--tamanho-pagina",
        type=int,
        default=TAMANHO_MAXIMO_PAGINA,
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
    argumentos = criar_parser().parse_args()
    sessao = criar_sessao()
    especie = buscar_especie(argumentos.especie, sessao)
    if argumentos.saida:
        caminho_saida = argumentos.saida
    elif argumentos.especie.casefold() == ESPECIE_PADRAO.casefold():
        caminho_saida = Path("data/raw/ocorrencias_tilapia.csv")
    else:
        caminho_saida = Path("data/raw") / criar_nome_arquivo(argumentos.especie)

    print("Espécie encontrada:", especie.get("scientificName"))
    print("Taxon key:", especie["usageKey"])

    resultado = buscar_ocorrencias(
        taxon_key=especie["usageKey"],
        pais=argumentos.pais.upper(),
        tamanho_pagina=argumentos.tamanho_pagina,
        max_registros=argumentos.max_registros,
        sessao=sessao,
    )
    salvar_resultados(
        resultado,
        especie,
        argumentos.especie,
        argumentos.pais.upper(),
        caminho_saida,
    )

    print(f"\nForam coletados {len(resultado.registros)} registros.")
    print(f"Páginas consultadas: {resultado.paginas_consultadas}")
    print(f"CSV salvo em: {caminho_saida}")


if __name__ == "__main__":
    main()

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.logging_config import configurar_logging
from src.transform_fish import ARQUIVO_OCORRENCIAS

LOGGER = logging.getLogger(__name__)

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_AMOSTRA = PASTA_PROJETO / "data" / "sample"
ARQUIVO_AMOSTRA = PASTA_AMOSTRA / "occurrences_sample.csv"
ARQUIVO_METADADOS = PASTA_AMOSTRA / "metadata.json"

LICENCAS_PUBLICAVEIS = {
    "http://creativecommons.org/publicdomain/zero/1.0/legalcode": "CC0 1.0",
    "http://creativecommons.org/licenses/by/4.0/legalcode": "CC BY 4.0",
}

COLUNAS_OBRIGATORIAS = {
    "gbifID",
    "canonicalName",
    "datasetKey",
    "datasetName",
    "license",
}

COLUNAS_AMOSTRA = [
    "gbifID",
    "canonicalName",
    "eventDate",
    "stateProvince",
    "basisOfRecord",
    "decimalLatitude",
    "decimalLongitude",
    "datasetKey",
    "datasetName",
    "publishingOrgKey",
    "institutionCode",
    "licenseName",
    "license",
    "gbifUrl",
    "originalReferences",
]


def selecionar_amostra(
    dados: pd.DataFrame,
    limite: int = 100,
    maximo_por_dataset: int = 10,
) -> pd.DataFrame:
    ausentes = COLUNAS_OBRIGATORIAS.difference(dados.columns)
    if ausentes:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(ausentes))}")
    if limite <= 0 or maximo_por_dataset <= 0:
        raise ValueError("Os limites da amostra devem ser positivos.")

    elegiveis = dados[dados["license"].isin(LICENCAS_PUBLICAVEIS)].copy()
    elegiveis = elegiveis.dropna(
        subset=["gbifID", "canonicalName", "datasetKey", "license"]
    )
    elegiveis = elegiveis.sort_values(
        ["canonicalName", "datasetKey", "gbifID"], kind="stable"
    )
    elegiveis = elegiveis.drop_duplicates("canonicalName", keep="first")
    elegiveis = elegiveis.groupby("datasetKey", group_keys=False).head(
        maximo_por_dataset
    )
    elegiveis = elegiveis.sort_values(["canonicalName", "gbifID"], kind="stable").head(
        limite
    )

    elegiveis["licenseName"] = elegiveis["license"].map(LICENCAS_PUBLICAVEIS)
    elegiveis["gbifUrl"] = elegiveis["gbifID"].map(
        lambda valor: f"https://www.gbif.org/occurrence/{int(valor)}"
    )
    elegiveis["originalReferences"] = elegiveis.get(
        "references", pd.Series(pd.NA, index=elegiveis.index)
    )
    for coluna in COLUNAS_AMOSTRA:
        if coluna not in elegiveis:
            elegiveis[coluna] = pd.NA
    return elegiveis[COLUNAS_AMOSTRA].reset_index(drop=True)


def criar_metadados(
    amostra: pd.DataFrame,
    caminho_entrada: Path,
) -> dict[str, Any]:
    datasets = (
        amostra.groupby(
            ["datasetKey", "datasetName", "institutionCode", "licenseName"],
            dropna=False,
        )
        .size()
        .reset_index(name="recordCount")
        .fillna("")
        .to_dict("records")
    )
    return {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourceFile": str(caminho_entrada),
        "recordCount": len(amostra),
        "selection": (
            "Deterministic sample with one occurrence per species, up to ten "
            "records per dataset, restricted to CC0 1.0 and CC BY 4.0."
        ),
        "citationWarning": (
            "This sample does not replace a citable GBIF Occurrence Download "
            "with DOI. Retain dataset, institution, license and GBIF IDs."
        ),
        "datasets": datasets,
    }


def exportar_amostra(
    caminho_entrada: Path = ARQUIVO_OCORRENCIAS,
    caminho_saida: Path = ARQUIVO_AMOSTRA,
    caminho_metadados: Path = ARQUIVO_METADADOS,
    limite: int = 100,
) -> pd.DataFrame:
    if not caminho_entrada.exists():
        raise FileNotFoundError(f"Arquivo processado não encontrado: {caminho_entrada}")
    dados = pd.read_csv(caminho_entrada)
    amostra = selecionar_amostra(dados, limite=limite)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    amostra.to_csv(caminho_saida, index=False, encoding="utf-8")
    caminho_metadados.write_text(
        json.dumps(
            criar_metadados(amostra, caminho_entrada),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return amostra


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exporta uma amostra publicável de ocorrências."
    )
    parser.add_argument("--entrada", type=Path, default=ARQUIVO_OCORRENCIAS)
    parser.add_argument("--saida", type=Path, default=ARQUIVO_AMOSTRA)
    parser.add_argument("--metadados", type=Path, default=ARQUIVO_METADADOS)
    parser.add_argument("--limite", type=int, default=100)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    configurar_logging(argumentos.verbose)
    amostra = exportar_amostra(
        argumentos.entrada,
        argumentos.saida,
        argumentos.metadados,
        argumentos.limite,
    )
    LOGGER.info("Amostra exportada: %s registros em %s", len(amostra), argumentos.saida)


if __name__ == "__main__":
    main()

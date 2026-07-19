"""Configuração central da aplicação e dos serviços externos."""

import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from dotenv import load_dotenv

PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_ENV = PASTA_PROJETO / ".env"

GBIF_API = "https://api.gbif.org/v1"
TAMANHO_MAXIMO_PAGINA = 300
TAMANHO_PAGINA_PADRAO = 300
LIMITE_BUSCA_GBIF = 100_000

PAIS_PADRAO = "BR"
ESPECIE_PADRAO = "Oreochromis niloticus"
LIMITE_CONSULTA_PADRAO = 10_000
LIMITE_PADRAO = LIMITE_CONSULTA_PADRAO  # Compatibilidade com a configuração inicial.
GRUPO_TAXONOMICO = "Actinopterygii"
LIMITE_AMOSTRA_PEIXES = 5_000

CHECKLIST_GBIF = "7ddf754f-d193-4cc9-b351-99906754a03b"
GRUPOS_PEIXES: Mapping[str, str] = MappingProxyType(
    {
        "Actinopterygii": "8VR36",
        "Elasmobranchii": "LB",
        "Dipneusti": "8V4VF",
        "Myxini": "6225G",
        "Petromyzonti": "8VJWX",
    }
)

SCHEMA_PADRAO = "biodiversity"
TAMANHO_LOTE_PADRAO = 500


def carregar_ambiente(caminho: Path = ARQUIVO_ENV) -> None:
    """Carrega variáveis locais sem sobrescrever valores já definidos."""
    load_dotenv(caminho, override=False)


def _inteiro_positivo(nome: str, padrao: int) -> int:
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    try:
        numero = int(valor)
    except ValueError as erro:
        raise ValueError(f"{nome} deve ser um número inteiro.") from erro
    if numero <= 0:
        raise ValueError(f"{nome} deve ser maior que zero.")
    return numero


def _limite_consulta_padrao() -> int:
    if os.getenv("LIMITE_CONSULTA_PADRAO") is not None:
        return _inteiro_positivo("LIMITE_CONSULTA_PADRAO", LIMITE_CONSULTA_PADRAO)
    return _inteiro_positivo("LIMITE_PADRAO", LIMITE_CONSULTA_PADRAO)


@dataclass(frozen=True)
class ConfiguracaoAplicacao:
    pais_padrao: str = PAIS_PADRAO
    especie_padrao: str = ESPECIE_PADRAO
    limite_padrao: int = LIMITE_CONSULTA_PADRAO
    tamanho_pagina_padrao: int = TAMANHO_PAGINA_PADRAO
    grupo_taxonomico: str = GRUPO_TAXONOMICO
    gbif_api: str = GBIF_API

    @classmethod
    def do_ambiente(cls, caminho: Path = ARQUIVO_ENV) -> "ConfiguracaoAplicacao":
        carregar_ambiente(caminho)
        return cls(
            pais_padrao=os.getenv("PAIS_PADRAO", PAIS_PADRAO),
            especie_padrao=os.getenv("ESPECIE_PADRAO", ESPECIE_PADRAO),
            limite_padrao=_limite_consulta_padrao(),
            tamanho_pagina_padrao=_inteiro_positivo(
                "TAMANHO_PAGINA_PADRAO", TAMANHO_PAGINA_PADRAO
            ),
            grupo_taxonomico=os.getenv("GRUPO_TAXONOMICO", GRUPO_TAXONOMICO),
            gbif_api=os.getenv("GBIF_API", GBIF_API).rstrip("/"),
        )

"""Cliente HTTP compartilhado para a API do GBIF."""

from typing import Any

import requests
import truststore
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import (
    BACKOFF_GBIF_SEGUNDOS,
    TENTATIVAS_GBIF,
    TIMEOUT_GBIF_SEGUNDOS,
)


class ErroGBIF(RuntimeError):
    """Falha controlada de comunicação com a API do GBIF."""


truststore.inject_into_ssl()


def criar_sessao(
    tentativas: int = TENTATIVAS_GBIF,
    backoff: float = BACKOFF_GBIF_SEGUNDOS,
) -> requests.Session:
    retentativas = Retry(
        total=tentativas,
        connect=tentativas,
        read=tentativas,
        status=tentativas,
        backoff_factor=backoff,
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
    parametros: dict[str, Any] | list[tuple[str, Any]],
    timeout: int = TIMEOUT_GBIF_SEGUNDOS,
) -> dict[str, Any]:
    try:
        resposta = sessao.get(url, params=parametros, timeout=timeout)
        resposta.raise_for_status()
    except requests.Timeout as erro:
        raise ErroGBIF("A consulta ao GBIF excedeu o tempo limite.") from erro
    except requests.ConnectionError as erro:
        raise ErroGBIF("Não foi possível conectar à API do GBIF.") from erro
    except requests.HTTPError as erro:
        codigo = erro.response.status_code if erro.response is not None else "?"
        raise ErroGBIF(f"A API do GBIF respondeu com erro HTTP {codigo}.") from erro

    try:
        dados = resposta.json()
    except requests.exceptions.JSONDecodeError as erro:
        raise ValueError("A API do GBIF retornou uma resposta JSON inválida.") from erro

    if not isinstance(dados, dict):
        raise ValueError("A API do GBIF retornou um formato inesperado.")
    return dados

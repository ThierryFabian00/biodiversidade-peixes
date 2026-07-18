"""Cliente HTTP compartilhado para a API do GBIF."""

from typing import Any

import requests
import truststore
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

truststore.inject_into_ssl()


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
    parametros: dict[str, Any] | list[tuple[str, Any]],
    timeout: int = 30,
) -> dict[str, Any]:
    resposta = sessao.get(url, params=parametros, timeout=timeout)
    resposta.raise_for_status()

    try:
        dados = resposta.json()
    except requests.exceptions.JSONDecodeError as erro:
        raise ValueError("A API do GBIF retornou uma resposta JSON inválida.") from erro

    if not isinstance(dados, dict):
        raise ValueError("A API do GBIF retornou um formato inesperado.")
    return dados

"""Parâmetros e regras de uma consulta de ocorrências."""

from dataclasses import dataclass
from typing import Any

from src.config import (
    LIMITE_BUSCA_GBIF,
    PAIS_PADRAO,
    TAMANHO_MAXIMO_PAGINA,
)
from src.services.country_service import normalizar_codigo_pais


@dataclass(frozen=True)
class ParametrosConsultaOcorrencia:
    taxon_key: int
    pais: str = PAIS_PADRAO
    tamanho_pagina: int = TAMANHO_MAXIMO_PAGINA
    max_registros: int | None = None
    com_coordenadas: bool = True

    def __post_init__(self) -> None:
        if self.taxon_key <= 0:
            raise ValueError("A chave taxonômica deve ser maior que zero.")
        if not 1 <= self.tamanho_pagina <= TAMANHO_MAXIMO_PAGINA:
            raise ValueError(
                f"O tamanho da página deve estar entre 1 e {TAMANHO_MAXIMO_PAGINA}."
            )
        if self.max_registros is not None and self.max_registros < 1:
            raise ValueError("O limite total de registros deve ser maior que zero.")
        if self.max_registros is not None and self.max_registros > LIMITE_BUSCA_GBIF:
            raise ValueError(
                "A API de busca do GBIF permite no máximo 100000 registros. "
                "Para volumes maiores, use o serviço de download do GBIF."
            )
        object.__setattr__(self, "pais", normalizar_codigo_pais(self.pais))

    def parametros_api(self, offset: int, limite: int) -> dict[str, Any]:
        return {
            "taxon_key": self.taxon_key,
            "country": self.pais,
            "has_coordinate": str(self.com_coordenadas).lower(),
            "limit": limite,
            "offset": offset,
        }

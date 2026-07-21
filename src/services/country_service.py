"""Catálogo e validação de países usados nas consultas externas."""

import re
from dataclasses import dataclass

from src.config import PAIS_PADRAO, PAISES


@dataclass(frozen=True)
class Pais:
    nome: str
    codigo_iso: str


def listar_paises() -> tuple[Pais, ...]:
    """Retorna o catálogo na ordem apresentada pela interface."""
    return tuple(Pais(nome, codigo) for nome, codigo in PAISES.items())


def normalizar_codigo_pais(codigo: str = PAIS_PADRAO) -> str:
    codigo_normalizado = codigo.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", codigo_normalizado):
        raise ValueError("O país deve ser informado por um código ISO de duas letras.")
    if codigo_normalizado not in PAISES.values():
        codigos = ", ".join(PAISES.values())
        raise ValueError(f"Código de país não suportado. Use um de: {codigos}.")
    return codigo_normalizado


def obter_pais(codigo: str = PAIS_PADRAO) -> Pais:
    codigo_normalizado = normalizar_codigo_pais(codigo)
    nome = next(nome for nome, valor in PAISES.items() if valor == codigo_normalizado)
    return Pais(nome, codigo_normalizado)

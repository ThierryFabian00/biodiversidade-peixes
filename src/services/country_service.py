"""Validação de países usados nas consultas externas."""

import re

from src.config import PAIS_PADRAO


def normalizar_codigo_pais(codigo: str = PAIS_PADRAO) -> str:
    codigo_normalizado = codigo.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", codigo_normalizado):
        raise ValueError("O país deve ser informado por um código ISO de duas letras.")
    return codigo_normalizado

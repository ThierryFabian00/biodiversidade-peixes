import argparse
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from src.config import ARQUIVO_ENV
from src.database import ConfiguracaoBanco, validar_schema

CONSULTAS = ("resumo", "ranking", "anos", "meses", "origens", "especie")


def criar_consultas(schema: str) -> dict[str, str]:
    schema = validar_schema(schema)
    return {
        "resumo": f"""
            SELECT
                (SELECT COUNT(*) FROM {schema}.occurrences) AS occurrence_count,
                (SELECT COUNT(*) FROM {schema}.taxa) AS species_count,
                MIN(year) AS first_year,
                MAX(year) AS last_year
            FROM {schema}.occurrences
        """,
        "ranking": f"""
            SELECT country_code, taxon_key, canonical_name, origin_status, occurrence_count
            FROM {schema}.vw_species_ranking
            ORDER BY occurrence_count DESC, country_code, canonical_name
            LIMIT %s
        """,
        "anos": f"""
            SELECT country_code, year, occurrence_count
            FROM {schema}.vw_occurrences_by_year
            ORDER BY country_code, year
        """,
        "meses": f"""
            SELECT country_code, month, COUNT(*)::BIGINT AS occurrence_count
            FROM {schema}.occurrences
            WHERE month IS NOT NULL
            GROUP BY country_code, month
            ORDER BY country_code, month
        """,
        "origens": f"""
            SELECT origin_status, COUNT(*)::BIGINT AS species_count
            FROM {schema}.taxa
            GROUP BY origin_status
            ORDER BY species_count DESC, origin_status
        """,
        "especie": f"""
            SELECT
                gbif_key, taxon_key, canonical_name, event_date,
                latitude, longitude, state_province,
                basis_of_record
            FROM {schema}.vw_occurrence_details
            WHERE canonical_name ILIKE %s
            ORDER BY event_date DESC NULLS LAST, gbif_key
            LIMIT %s
        """,
    }


def executar_consulta(
    cursor: Any,
    consulta: str,
    schema: str,
    limite: int = 20,
    termo: str | None = None,
) -> list[dict[str, Any]]:
    if limite <= 0:
        raise ValueError("O limite deve ser positivo.")
    consultas = criar_consultas(schema)
    if consulta not in consultas:
        raise ValueError(f"Consulta desconhecida: {consulta}")
    parametros: tuple[Any, ...] | None = None
    if consulta == "ranking":
        parametros = (limite,)
    elif consulta == "especie":
        if not termo or not termo.strip():
            raise ValueError("Informe --termo para consultar uma especie.")
        parametros = (f"%{termo.strip()}%", limite)
    cursor.execute(consultas[consulta], parametros)
    return list(cursor.fetchall())


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa consultas analiticas no PostgreSQL."
    )
    parser.add_argument("--consulta", choices=CONSULTAS, default="resumo")
    parser.add_argument(
        "--termo", help="Parte do nome cientifico para a consulta especie."
    )
    parser.add_argument("--limite", type=int, default=20)
    parser.add_argument("--schema", default=None)
    parser.add_argument("--env-file", type=Path, default=ARQUIVO_ENV)
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    configuracao_banco = ConfiguracaoBanco.do_ambiente(
        argumentos.env_file, argumentos.schema
    )
    schema = configuracao_banco.schema
    try:
        database_url = configuracao_banco.exigir_url()
    except ValueError as erro:
        raise SystemExit(str(erro)) from erro
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conexao:
            with conexao.cursor() as cursor:
                resultado = executar_consulta(
                    cursor,
                    argumentos.consulta,
                    schema,
                    argumentos.limite,
                    argumentos.termo,
                )
    except (psycopg.Error, ValueError) as erro:
        raise SystemExit(f"Falha na consulta PostgreSQL: {erro}") from erro
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

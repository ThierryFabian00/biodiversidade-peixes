import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from src.load import ARQUIVO_ENV, SCHEMA_PADRAO, validar_schema

CONSULTAS = ("resumo", "ranking", "anos", "meses", "origens", "especie")


def criar_consultas(schema: str) -> dict[str, str]:
    schema = validar_schema(schema)
    return {
        "resumo": f"""
            SELECT
                (SELECT COUNT(*) FROM {schema}.occurrences) AS occurrence_count,
                (SELECT COUNT(*) FROM {schema}.species) AS species_count,
                MIN(event_year) AS first_year,
                MAX(event_year) AS last_year
            FROM {schema}.occurrences
        """,
        "ranking": f"""
            SELECT species_key, canonical_name, origin_status, occurrence_count
            FROM {schema}.vw_species_ranking
            ORDER BY occurrence_count DESC, canonical_name
            LIMIT %s
        """,
        "anos": f"""
            SELECT event_year, occurrence_count
            FROM {schema}.vw_occurrences_by_year
            ORDER BY event_year
        """,
        "meses": f"""
            SELECT event_month, COUNT(*)::BIGINT AS occurrence_count
            FROM {schema}.occurrences
            WHERE event_month IS NOT NULL
            GROUP BY event_month
            ORDER BY event_month
        """,
        "origens": f"""
            SELECT origin_status, COUNT(*)::BIGINT AS species_count
            FROM {schema}.species
            GROUP BY origin_status
            ORDER BY species_count DESC, origin_status
        """,
        "especie": f"""
            SELECT
                gbif_id, species_key, canonical_name, event_date,
                decimal_latitude, decimal_longitude, state_province,
                basis_of_record
            FROM {schema}.vw_occurrence_details
            WHERE canonical_name ILIKE %s
            ORDER BY event_date DESC NULLS LAST, gbif_id
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
    load_dotenv(argumentos.env_file)
    schema = validar_schema(argumentos.schema or os.getenv("DB_SCHEMA", SCHEMA_PADRAO))
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL nao definida. Crie .env a partir de .env.example."
        )
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

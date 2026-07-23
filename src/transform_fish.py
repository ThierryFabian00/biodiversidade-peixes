import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import pandas as pd

from src.extract_fish import ARQUIVO_SAIDA as ARQUIVO_ENTRADA
from src.extract_fish import CHECKLIST_COL, GRUPOS_PEIXES
from src.filter_basin import ARQUIVO_LIMITE, carregar_limite, classificar_ocorrencias
from src.logging_config import configurar_logging
from src.services.country_service import normalizar_codigo_pais

LOGGER = logging.getLogger(__name__)

PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_OCORRENCIAS = (
    PASTA_PROJETO / "data" / "processed" / "ocorrencias_peixes_bacia_parana.csv"
)
ARQUIVO_ESPECIES = PASTA_PROJETO / "data" / "processed" / "especies_bacia_parana.csv"
ARQUIVO_PROBLEMAS = (
    PASTA_PROJETO / "data" / "processed" / "problemas_taxonomicos_peixes.csv"
)
ARQUIVO_REFERENCIA_ORIGEM = (
    PASTA_PROJETO / "data" / "reference" / "introduced_fish_brazil.csv"
)

COLUNAS_PROBLEMAS = ["gbifID", "scientificName", "problem"]


def caminhos_processados_pais(codigo_pais: str) -> tuple[Path, Path, Path]:
    """Resolve os CSVs reconhecidos automaticamente pelo dashboard."""
    codigo = normalizar_codigo_pais(codigo_pais)
    if codigo == "BR":
        return ARQUIVO_OCORRENCIAS, ARQUIVO_ESPECIES, ARQUIVO_PROBLEMAS
    sufixo = codigo.casefold()
    pasta = PASTA_PROJETO / "data" / "processed"
    return (
        pasta / f"ocorrencias_peixes_{sufixo}.csv",
        pasta / f"especies_peixes_{sufixo}.csv",
        pasta / f"problemas_taxonomicos_{sufixo}.csv",
    )


def carregar_jsonl(caminho: Path) -> list[dict[str, Any]]:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo bruto não encontrado: {caminho}")
    with caminho.open(encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo if linha.strip()]


def valor_vocabulario(valor: Any) -> str | None:
    if isinstance(valor, str):
        return valor
    if isinstance(valor, dict):
        return valor.get("concept") or valor.get("value")
    return None


def normalizar_nome_cientifico(valor: Any) -> str | None:
    """Remove espaços redundantes sem descartar autoria ou epítetos."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    return " ".join(valor.split())


def extrair_hierarquia(classificacao: dict[str, Any]) -> dict[str, Any]:
    hierarquia: dict[str, Any] = {}
    for taxon in classificacao.get("classification", []):
        rank = str(taxon.get("rank", "")).upper()
        if rank in {
            "KINGDOM",
            "PHYLUM",
            "CLASS",
            "ORDER",
            "FAMILY",
            "GENUS",
            "SPECIES",
        }:
            hierarquia[rank] = taxon
    return hierarquia


def identificar_grupo(classificacao: dict[str, Any]) -> str | None:
    chaves = {
        str(taxon.get("key")) for taxon in classificacao.get("classification", [])
    }
    chaves.add(str(classificacao.get("usage", {}).get("key")))
    for nome, chave in GRUPOS_PEIXES.items():
        if chave in chaves:
            return nome
    return None


def normalizar_registro(
    registro: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    classificacao = registro.get("classifications", {}).get(CHECKLIST_COL)
    if not isinstance(classificacao, dict):
        return None, "NO_COL_CLASSIFICATION"

    uso = classificacao.get("usage") or {}
    aceito = classificacao.get("acceptedUsage") or uso
    if uso.get("rank") != "SPECIES":
        return None, f"NOT_SPECIES_LEVEL:{uso.get('rank', 'UNKNOWN')}"
    if aceito.get("rank") != "SPECIES" or not aceito.get("key"):
        return None, "NO_ACCEPTED_SPECIES"

    hierarquia = extrair_hierarquia(classificacao)
    especie_hierarquia = hierarquia.get("SPECIES", {})
    problemas_col = classificacao.get("issues") or []
    problemas_ocorrencia = registro.get("issues") or []
    nome_original = normalizar_nome_cientifico(
        registro.get("verbatimScientificName") or registro.get("scientificName")
    )
    nome_interpretado = normalizar_nome_cientifico(
        uso.get("name") or registro.get("scientificName")
    )
    nome_aceito = normalizar_nome_cientifico(aceito.get("name"))
    nome_canonico = normalizar_nome_cientifico(
        aceito.get("canonicalName") or especie_hierarquia.get("name")
    )
    status_taxonomico = classificacao.get("taxonomicStatus") or uso.get("status")
    status_normalizado = str(status_taxonomico or "UNKNOWN").upper()
    sinonimo = str(uso.get("key")) != str(aceito.get("key")) or status_normalizado in {
        "SYNONYM",
        "HETEROTYPIC_SYNONYM",
        "HOMOTYPIC_SYNONYM",
        "PROPARTE_SYNONYM",
    }

    normalizado = {
        "gbifID": registro.get("key"),
        "speciesKey": str(aceito["key"]),
        "originalScientificName": nome_original,
        "scientificName": nome_interpretado,
        "acceptedScientificName": nome_aceito,
        "canonicalName": nome_canonico,
        "taxonomicStatus": status_normalizado,
        "isSynonym": sinonimo,
        "countryCode": str(registro.get("countryCode") or "").upper() or None,
        "fishGroup": identificar_grupo(classificacao),
        "kingdom": hierarquia.get("KINGDOM", {}).get("name"),
        "phylum": hierarquia.get("PHYLUM", {}).get("name"),
        "class": hierarquia.get("CLASS", {}).get("name"),
        "order": hierarquia.get("ORDER", {}).get("name"),
        "family": hierarquia.get("FAMILY", {}).get("name"),
        "genus": hierarquia.get("GENUS", {}).get("name"),
        "species": especie_hierarquia.get("name") or nome_canonico,
        "iucnCategory": classificacao.get("iucnRedListCategoryCode"),
        "decimalLatitude": registro.get("decimalLatitude"),
        "decimalLongitude": registro.get("decimalLongitude"),
        "eventDate": registro.get("eventDate"),
        "stateProvince": registro.get("stateProvince"),
        "locality": registro.get("locality"),
        "basisOfRecord": registro.get("basisOfRecord"),
        "datasetKey": registro.get("datasetKey"),
        "datasetName": registro.get("datasetName"),
        "publishingOrgKey": registro.get("publishingOrgKey"),
        "institutionCode": registro.get("institutionCode"),
        "license": registro.get("license"),
        "references": registro.get("references"),
        "occurrenceStatus": registro.get("occurrenceStatus"),
        "establishmentMeans": valor_vocabulario(registro.get("establishmentMeans")),
        "degreeOfEstablishment": valor_vocabulario(
            registro.get("degreeOfEstablishment")
        ),
        "taxonomicIssues": "|".join(sorted(set(problemas_col))),
        "occurrenceIssues": "|".join(sorted(set(problemas_ocorrencia))),
    }
    return normalizado, None


def classificar_origem(valores: Iterable[str]) -> str:
    termos = {str(valor).upper() for valor in valores if pd.notna(valor)}
    introduzida = any(
        termo in {"INTRODUCED", "INVASIVE", "NATURALISED", "EXOTIC"} for termo in termos
    )
    nativa = "NATIVE" in termos
    if introduzida and nativa:
        return "CONFLICTING"
    if introduzida:
        return "INTRODUCED"
    if nativa:
        return "NATIVE"
    return "UNKNOWN"


def aplicar_referencia_origem(
    especies: pd.DataFrame,
    referencia: pd.DataFrame | None,
) -> pd.DataFrame:
    if referencia is None or referencia.empty:
        return especies

    resultado = especies.copy()
    referencia = referencia.drop_duplicates("canonicalName", keep="first")
    por_nome = referencia.set_index("canonicalName")
    for indice, especie in resultado.iterrows():
        nome = especie["canonicalName"]
        if nome not in por_nome.index:
            continue
        evidencia = por_nome.loc[nome]
        nota = evidencia.get("note")
        resultado.at[indice, "originStatus"] = evidencia["originStatus"]
        resultado.at[indice, "originEvidence"] = (
            str(nota).strip() if pd.notna(nota) and str(nota).strip() else nome
        )
        resultado.at[indice, "originSource"] = evidencia["source"]
        resultado.at[indice, "originSourceUrl"] = evidencia["sourceUrl"]
        resultado.at[indice, "originScope"] = evidencia["scope"]
    return resultado


def criar_tabela_especies(
    ocorrencias: pd.DataFrame,
    referencia_origem: pd.DataFrame | None = None,
) -> pd.DataFrame:
    linhas: list[dict[str, Any]] = []
    campos_taxonomicos = [
        "speciesKey",
        "originalScientificName",
        "scientificName",
        "acceptedScientificName",
        "canonicalName",
        "taxonomicStatus",
        "kingdom",
        "phylum",
        "fishGroup",
        "class",
        "order",
        "family",
        "genus",
        "species",
        "iucnCategory",
    ]
    for _, grupo in ocorrencias.groupby("speciesKey", sort=True):
        primeira = grupo.iloc[0]
        meios = sorted(
            {
                str(valor)
                for valor in grupo["establishmentMeans"].dropna()
                if str(valor).strip()
            }
        )
        linha = {campo: primeira.get(campo) for campo in campos_taxonomicos}
        nomes_originais = sorted(
            {str(valor) for valor in grupo["originalScientificName"].dropna()}
        )
        nomes_interpretados = sorted(
            {str(valor) for valor in grupo["scientificName"].dropna()}
        )
        status_taxonomicos = sorted(
            {str(valor) for valor in grupo["taxonomicStatus"].dropna()}
        )
        sinonimos = sorted(
            {
                str(valor)
                for valor in grupo.loc[grupo["isSynonym"], "scientificName"].dropna()
            }
        )
        linha.update(
            {
                "originalScientificNames": "|".join(nomes_originais),
                "scientificNames": "|".join(nomes_interpretados),
                "taxonomicStatuses": "|".join(status_taxonomicos),
                "synonymNames": "|".join(sinonimos),
                "hasSynonyms": bool(sinonimos),
                "occurrenceCount": len(grupo),
                "firstYear": grupo["year"].min(),
                "lastYear": grupo["year"].max(),
                "originStatus": classificar_origem(meios),
                "originEvidence": "|".join(meios),
                "originSource": (
                    "GBIF occurrence establishmentMeans" if meios else pd.NA
                ),
                "originSourceUrl": pd.NA,
                "originScope": "occurrence record" if meios else pd.NA,
                "taxonomicIssueCount": int(
                    grupo["taxonomicIssues"].fillna("").ne("").sum()
                ),
            }
        )
        linhas.append(linha)
    return aplicar_referencia_origem(pd.DataFrame(linhas), referencia_origem)


def transformar_registros(
    registros: list[dict[str, Any]],
    limite: gpd.GeoDataFrame | None,
    referencia_origem: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    normalizados: list[dict[str, Any]] = []
    problemas: list[dict[str, Any]] = []
    for registro in registros:
        normalizado, problema = normalizar_registro(registro)
        if problema:
            problemas.append(
                {
                    "gbifID": registro.get("key"),
                    "scientificName": registro.get("scientificName"),
                    "problem": problema,
                }
            )
        elif normalizado:
            normalizados.append(normalizado)

    ocorrencias = pd.DataFrame(normalizados)
    if ocorrencias.empty:
        return (
            ocorrencias,
            pd.DataFrame(),
            pd.DataFrame(problemas, columns=COLUNAS_PROBLEMAS),
            {"normalized": 0, "inside": 0, "outside": 0},
        )

    ocorrencias = ocorrencias.drop_duplicates(subset="gbifID", keep="first")
    ocorrencias["eventDateOriginal"] = ocorrencias["eventDate"]
    ocorrencias["eventDate"] = pd.to_datetime(
        ocorrencias["eventDate"], errors="coerce", utc=True, format="mixed"
    )
    ocorrencias["year"] = ocorrencias["eventDate"].dt.year.astype("Int64")
    ocorrencias["month"] = ocorrencias["eventDate"].dt.month.astype("Int64")

    if limite is None:
        classificadas = ocorrencias.copy()
        classificadas["insideBasin"] = True
        dentro = classificadas.reset_index(drop=True)
    else:
        classificadas = classificar_ocorrencias(ocorrencias, limite)
        dentro = classificadas[classificadas["insideBasin"]].copy()
        dentro = dentro.drop(columns="geometry").reset_index(drop=True)
    especies = criar_tabela_especies(pd.DataFrame(dentro), referencia_origem)
    tabela_problemas = pd.DataFrame(problemas, columns=COLUNAS_PROBLEMAS)
    resumo = {
        "normalized": len(classificadas),
        "inside": len(dentro),
        "outside": len(classificadas) - len(dentro),
    }
    return pd.DataFrame(dentro), especies, tabela_problemas, resumo


def salvar_tabelas(
    ocorrencias: pd.DataFrame,
    especies: pd.DataFrame,
    problemas: pd.DataFrame,
    resumo: dict[str, int],
    caminhos: tuple[Path, Path, Path],
    metadados_extracao: dict[str, Any] | None = None,
) -> None:
    caminho_ocorrencias, caminho_especies, caminho_problemas = caminhos
    for caminho in caminhos:
        caminho.parent.mkdir(parents=True, exist_ok=True)

    ocorrencias.to_csv(caminho_ocorrencias, index=False, encoding="utf-8")
    especies.to_csv(caminho_especies, index=False, encoding="utf-8")
    problemas.to_csv(caminho_problemas, index=False, encoding="utf-8")

    metadados = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "checklistKey": CHECKLIST_COL,
        "recordsNormalized": resumo["normalized"],
        "recordsInsideBasin": resumo["inside"],
        "recordsOutsideBasin": resumo["outside"],
        "speciesCount": len(especies),
        "taxonomicProblems": len(problemas),
        "originStatusNote": (
            "NATIVE/INTRODUCED deriva de establishmentMeans publicado nos "
            "registros GBIF ou da referência oficial de espécies introduzidas "
            "do MAPA; UNKNOWN não deve ser interpretado como nativo."
        ),
    }
    if metadados_extracao:
        metadados.update(
            {
                "sourceRecordsCollected": metadados_extracao.get("recordsCollected"),
                "sourceRecordsAvailable": metadados_extracao.get(
                    "recordsAvailableInPrefilter"
                ),
                "sourceIsComplete": metadados_extracao.get("isComplete"),
                "sourceWarning": metadados_extracao.get("warning"),
            }
        )
    caminho_metadados = caminho_ocorrencias.with_name(
        "pipeline_multiespecies_metadata.json"
    )
    caminho_metadados.write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normaliza e filtra a amostra multiespécies de peixes."
    )
    parser.add_argument("--entrada", type=Path, default=ARQUIVO_ENTRADA)
    parser.add_argument("--limite", type=Path, default=ARQUIVO_LIMITE)
    parser.add_argument(
        "--sem-recorte-bacia",
        action="store_true",
        help="Mantém todas as ocorrências do país informado na extração.",
    )
    parser.add_argument("--ocorrencias", type=Path, default=ARQUIVO_OCORRENCIAS)
    parser.add_argument("--especies", type=Path, default=ARQUIVO_ESPECIES)
    parser.add_argument("--problemas", type=Path, default=ARQUIVO_PROBLEMAS)
    parser.add_argument(
        "--referencia-origem",
        type=Path,
        default=ARQUIVO_REFERENCIA_ORIGEM,
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    configurar_logging(argumentos.verbose)
    registros = carregar_jsonl(argumentos.entrada)
    caminho_metadados_entrada = argumentos.entrada.with_name(
        f"{argumentos.entrada.stem}_metadata.json"
    )
    metadados_extracao = (
        json.loads(caminho_metadados_entrada.read_text(encoding="utf-8"))
        if caminho_metadados_entrada.exists()
        else None
    )
    limite = (
        None if argumentos.sem_recorte_bacia else carregar_limite(argumentos.limite)
    )
    referencia_origem = pd.read_csv(argumentos.referencia_origem)
    ocorrencias, especies, problemas, resumo = transformar_registros(
        registros, limite, referencia_origem
    )
    salvar_tabelas(
        ocorrencias,
        especies,
        problemas,
        resumo,
        (argumentos.ocorrencias, argumentos.especies, argumentos.problemas),
        metadados_extracao,
    )

    LOGGER.info("Registros brutos: %s", len(registros))
    LOGGER.info("Registros normalizados: %s", resumo["normalized"])
    LOGGER.info("Registros dentro da bacia: %s", resumo["inside"])
    LOGGER.info("Espécies distintas: %s", len(especies))
    LOGGER.info("Problemas taxonômicos: %s", len(problemas))
    LOGGER.info("Tabela de ocorrências: %s", argumentos.ocorrencias)
    LOGGER.info("Tabela de espécies: %s", argumentos.especies)


if __name__ == "__main__":
    main()

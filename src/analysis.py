import argparse
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
from shapely.geometry import box

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from src.filter_basin import ARQUIVO_LIMITE, carregar_limite
from src.logging_config import configurar_logging
from src.transform_fish import ARQUIVO_ESPECIES, ARQUIVO_OCORRENCIAS

PASTA_PROJETO = Path(__file__).resolve().parent.parent
LOGGER = logging.getLogger(__name__)
PASTA_SAIDA = PASTA_PROJETO / "data" / "analysis"
ARQUIVO_METADADOS_PIPELINE = (
    PASTA_PROJETO / "data" / "processed" / "pipeline_multiespecies_metadata.json"
)

COLUNAS_OBRIGATORIAS = {
    "gbifID",
    "speciesKey",
    "canonicalName",
    "decimalLatitude",
    "decimalLongitude",
    "year",
    "month",
    "stateProvince",
    "basisOfRecord",
}

MESES = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}

ALIASES_ESTADOS = {
    "sp": "Sao Paulo",
    "sao paulo": "Sao Paulo",
    "estado de sao paulo": "Sao Paulo",
    "pr": "Parana",
    "parana": "Parana",
    "mg": "Minas Gerais",
    "minas gerais": "Minas Gerais",
    "ms": "Mato Grosso do Sul",
    "mato grosso do sul": "Mato Grosso do Sul",
    "go": "Goias",
    "goias": "Goias",
    "sc": "Santa Catarina",
    "santa catarina": "Santa Catarina",
    "santa catarina state": "Santa Catarina",
    "df": "Distrito Federal",
    "distrito federal": "Distrito Federal",
}

ESTADOS_ESPERADOS = {
    "Sao Paulo",
    "Parana",
    "Minas Gerais",
    "Mato Grosso do Sul",
    "Goias",
    "Santa Catarina",
    "Distrito Federal",
}


def carregar_tabela(caminho: Path, colunas: set[str] | None = None) -> pd.DataFrame:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")
    dados = pd.read_csv(caminho)
    ausentes = (colunas or set()).difference(dados.columns)
    if ausentes:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(ausentes))}")
    return dados


def corrigir_mojibake(valor: Any) -> Any:
    if pd.isna(valor):
        return pd.NA
    texto = str(valor).strip()
    if "Ã" in texto or "Â" in texto:
        try:
            return texto.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return texto


def normalizar_estado(valor: Any) -> str:
    texto = corrigir_mojibake(valor)
    if pd.isna(texto) or not str(texto).strip():
        return "Nao informado"
    texto = str(texto).strip()
    chave = (
        texto.casefold()
        .replace("ã", "a")
        .replace("á", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )
    return ALIASES_ESTADOS.get(chave, texto)


def contar_por_coluna(
    dados: pd.DataFrame, coluna: str, nome_categoria: str
) -> pd.DataFrame:
    valores = dados[coluna].fillna("Nao informado")
    tabela = (
        valores.value_counts(dropna=False)
        .rename_axis(nome_categoria)
        .reset_index(name="occurrenceCount")
    )
    tabela["percentage"] = (100 * tabela["occurrenceCount"] / len(dados)).round(2)
    return tabela


def contar_issues(dados: pd.DataFrame, coluna: str, nome: str) -> pd.DataFrame:
    if coluna not in dados:
        return pd.DataFrame(columns=[nome, "recordCount", "percentage"])
    valores = dados[coluna].fillna("").str.split("|").explode()
    valores = valores[valores.ne("")]
    tabela = valores.value_counts().rename_axis(nome).reset_index(name="recordCount")
    tabela["percentage"] = (100 * tabela["recordCount"] / len(dados)).round(2)
    return tabela


def criar_resumos(
    ocorrencias: pd.DataFrame, especies: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    ranking = especies.sort_values(
        ["occurrenceCount", "canonicalName"], ascending=[False, True]
    ).reset_index(drop=True)

    anos_validos = pd.to_numeric(ocorrencias["year"], errors="coerce").dropna()
    if anos_validos.empty:
        por_ano = pd.DataFrame(columns=["year", "occurrenceCount", "percentage"])
    else:
        intervalo = range(int(anos_validos.min()), int(anos_validos.max()) + 1)
        contagens = (
            anos_validos.astype(int).value_counts().reindex(intervalo, fill_value=0)
        )
        por_ano = contagens.rename_axis("year").reset_index(name="occurrenceCount")
        por_ano["percentage"] = (
            100 * por_ano["occurrenceCount"] / len(ocorrencias)
        ).round(2)

    meses = (
        pd.to_numeric(ocorrencias["month"], errors="coerce")
        .dropna()
        .astype(int)
        .value_counts()
        .reindex(range(1, 13), fill_value=0)
    )
    por_mes = meses.rename_axis("month").reset_index(name="occurrenceCount")
    por_mes["monthName"] = por_mes["month"].map(MESES)
    por_mes["percentage"] = (100 * por_mes["occurrenceCount"] / len(ocorrencias)).round(
        2
    )

    estados = ocorrencias["stateProvince"].map(normalizar_estado)
    por_estado = contar_por_coluna(
        ocorrencias.assign(stateNormalized=estados),
        "stateNormalized",
        "stateProvince",
    )

    return {
        "ranking_especies": ranking,
        "registros_por_ano": por_ano,
        "registros_por_mes": por_mes,
        "registros_por_estado": por_estado,
        "registros_por_tipo": contar_por_coluna(
            ocorrencias, "basisOfRecord", "basisOfRecord"
        ),
        "alertas_ocorrencia": contar_issues(ocorrencias, "occurrenceIssues", "issue"),
        "alertas_taxonomicos": contar_issues(ocorrencias, "taxonomicIssues", "issue"),
    }


def identificar_duplicados_potenciais(ocorrencias: pd.DataFrame) -> pd.DataFrame:
    colunas = [
        "speciesKey",
        "decimalLatitude",
        "decimalLongitude",
        "eventDateOriginal",
    ]
    if "eventDateOriginal" not in ocorrencias:
        colunas[-1] = "eventDate"
    completos = ocorrencias.dropna(subset=colunas).copy()
    mascara = completos.duplicated(subset=colunas, keep=False)
    duplicados = completos.loc[mascara].sort_values(colunas + ["gbifID"]).copy()
    if duplicados.empty:
        duplicados["duplicateGroup"] = pd.Series(dtype="Int64")
        return duplicados
    assinaturas = pd.MultiIndex.from_frame(duplicados[colunas])
    duplicados["duplicateGroup"] = pd.factorize(assinaturas)[0] + 1
    return duplicados


def resumir_qualidade(ocorrencias: pd.DataFrame) -> pd.DataFrame:
    total = len(ocorrencias)
    duplicados = identificar_duplicados_potenciais(ocorrencias)
    estados = ocorrencias["stateProvince"].map(normalizar_estado)
    metricas = {
        "missingScientificName": ocorrencias["canonicalName"].isna().sum(),
        "missingCoordinates": ocorrencias[["decimalLatitude", "decimalLongitude"]]
        .isna()
        .any(axis=1)
        .sum(),
        "missingEventDate": pd.to_numeric(ocorrencias["year"], errors="coerce")
        .isna()
        .sum(),
        "missingStateProvince": ocorrencias["stateProvince"].isna().sum(),
        "unexpectedStateProvince": (
            ~estados.isin(ESTADOS_ESPERADOS | {"Nao informado"})
        ).sum(),
        "missingLocality": ocorrencias.get(
            "locality", pd.Series(pd.NA, index=ocorrencias.index)
        )
        .isna()
        .sum(),
        "taxonomicIssue": ocorrencias.get(
            "taxonomicIssues", pd.Series("", index=ocorrencias.index)
        )
        .fillna("")
        .ne("")
        .sum(),
        "occurrenceIssue": ocorrencias.get(
            "occurrenceIssues", pd.Series("", index=ocorrencias.index)
        )
        .fillna("")
        .ne("")
        .sum(),
        "duplicateGbifId": ocorrencias.duplicated("gbifID", keep=False).sum(),
        "potentialDuplicate": len(duplicados),
    }
    tabela = pd.DataFrame(
        [
            {"metric": nome, "recordCount": int(valor)}
            for nome, valor in metricas.items()
        ]
    )
    tabela["percentage"] = (100 * tabela["recordCount"] / total if total else 0).round(
        2
    )
    return tabela


def criar_grade_espacial(
    ocorrencias: pd.DataFrame,
    limite: gpd.GeoDataFrame,
    tamanho_grau: float = 1.0,
) -> gpd.GeoDataFrame:
    if tamanho_grau <= 0:
        raise ValueError("O tamanho da celula deve ser positivo.")
    limite = limite.to_crs("EPSG:4326")
    bacia = limite.geometry.union_all()
    min_x, min_y, max_x, max_y = bacia.bounds
    inicio_x = math.floor(min_x / tamanho_grau) * tamanho_grau
    inicio_y = math.floor(min_y / tamanho_grau) * tamanho_grau
    fim_x = math.ceil(max_x / tamanho_grau) * tamanho_grau
    fim_y = math.ceil(max_y / tamanho_grau) * tamanho_grau

    celulas: list[dict[str, Any]] = []
    for x in np.arange(inicio_x, fim_x, tamanho_grau):
        for y in np.arange(inicio_y, fim_y, tamanho_grau):
            id_grade = f"{x:.2f}_{y:.2f}"
            geometria = box(x, y, x + tamanho_grau, y + tamanho_grau).intersection(
                bacia
            )
            if not geometria.is_empty:
                celulas.append({"gridId": id_grade, "geometry": geometria})

    grade = gpd.GeoDataFrame(celulas, crs="EPSG:4326")
    pontos = ocorrencias.dropna(subset=["decimalLongitude", "decimalLatitude"]).copy()
    pontos["gridId"] = pontos.apply(
        lambda linha: (
            f"{math.floor(float(linha['decimalLongitude']) / tamanho_grau) * tamanho_grau:.2f}_"
            f"{math.floor(float(linha['decimalLatitude']) / tamanho_grau) * tamanho_grau:.2f}"
        ),
        axis=1,
    )
    contagens = pontos.groupby("gridId").agg(
        occurrenceCount=("gbifID", "size"),
        speciesCount=("speciesKey", "nunique"),
    )
    grade = grade.merge(contagens, how="left", left_on="gridId", right_index=True)
    grade[["occurrenceCount", "speciesCount"]] = (
        grade[["occurrenceCount", "speciesCount"]].fillna(0).astype(int)
    )
    grade["sampled"] = grade["occurrenceCount"].gt(0)
    grade["areaKm2"] = (grade.to_crs("EPSG:5880").area / 1_000_000).round(2)
    return grade


def _configurar_estilo() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "#f7f8fa",
            "axes.edgecolor": "#6b7280",
            "axes.grid": True,
            "grid.alpha": 0.22,
            "font.size": 10,
        }
    )


def _salvar_figura(figura: plt.Figure, caminho: Path) -> None:
    figura.tight_layout()
    figura.savefig(caminho, dpi=180, bbox_inches="tight")
    plt.close(figura)


def gerar_graficos(
    ocorrencias: pd.DataFrame,
    resumos: dict[str, pd.DataFrame],
    limite: gpd.GeoDataFrame,
    grade: gpd.GeoDataFrame,
    pasta_saida: Path,
) -> None:
    _configurar_estilo()

    top = resumos["ranking_especies"].head(15).sort_values("occurrenceCount")
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(top["canonicalName"], top["occurrenceCount"], color="#1b6ca8")
    ax.set(title="Especies com mais registros", xlabel="Ocorrencias", ylabel="")
    _salvar_figura(fig, pasta_saida / "especies_mais_registradas.png")

    anos = resumos["registros_por_ano"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(anos["year"], anos["occurrenceCount"], marker="o", color="#2f855a")
    ax.set(title="Registros por ano", xlabel="Ano", ylabel="Ocorrencias")
    ax.set_xticks(anos["year"])
    _salvar_figura(fig, pasta_saida / "registros_por_ano.png")

    meses = resumos["registros_por_mes"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(meses["monthName"], meses["occurrenceCount"], color="#d97706")
    ax.set(title="Registros por mes", xlabel="Mes", ylabel="Ocorrencias")
    _salvar_figura(fig, pasta_saida / "registros_por_mes.png")

    tipos = resumos["registros_por_tipo"].sort_values("occurrenceCount")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(tipos["basisOfRecord"], tipos["occurrenceCount"], color="#7c3f58")
    ax.set(title="Distribuicao por tipo de registro", xlabel="Ocorrencias", ylabel="")
    _salvar_figura(fig, pasta_saida / "registros_por_tipo.png")

    estados = resumos["registros_por_estado"].head(10).sort_values("occurrenceCount")
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(estados["stateProvince"], estados["occurrenceCount"], color="#4f772d")
    ax.set(
        title="Registros por unidade administrativa informada",
        xlabel="Ocorrencias",
        ylabel="",
    )
    _salvar_figura(fig, pasta_saida / "registros_por_estado.png")

    limite_4326 = limite.to_crs("EPSG:4326")
    pontos = gpd.GeoDataFrame(
        ocorrencias.copy(),
        geometry=gpd.points_from_xy(
            ocorrencias["decimalLongitude"], ocorrencias["decimalLatitude"]
        ),
        crs="EPSG:4326",
    )
    nomes_top = resumos["ranking_especies"].head(5)["canonicalName"].tolist()
    cores = ["#1b6ca8", "#d97706", "#2f855a", "#b23a48", "#6d597a"]
    fig, ax = plt.subplots(figsize=(9, 9))
    limite_4326.plot(ax=ax, color="#edf2f4", edgecolor="#36454f", linewidth=0.8)
    pontos[~pontos["canonicalName"].isin(nomes_top)].plot(
        ax=ax, color="#9ca3af", markersize=4, alpha=0.22, label="Outras especies"
    )
    for nome, cor in zip(nomes_top, cores, strict=True):
        pontos[pontos["canonicalName"].eq(nome)].plot(
            ax=ax, color=cor, markersize=12, alpha=0.65, label=nome
        )
    ax.set(
        title="Distribuicao das cinco especies mais registradas",
        xlabel="Longitude",
        ylabel="Latitude",
    )
    ax.legend(loc="lower left", fontsize=8, frameon=True)
    ax.set_aspect("equal")
    _salvar_figura(fig, pasta_saida / "mapa_ocorrencias.png")

    grade_mapa = grade.copy()
    grade_mapa["logOccurrences"] = np.log1p(grade_mapa["occurrenceCount"])
    fig, ax = plt.subplots(figsize=(9, 9))
    grade_mapa.plot(
        ax=ax,
        column="logOccurrences",
        cmap="YlGnBu",
        edgecolor="white",
        linewidth=0.35,
        legend=True,
        legend_kwds={"label": "log(1 + ocorrencias)"},
    )
    limite_4326.boundary.plot(ax=ax, color="#263238", linewidth=0.8)
    ax.set(
        title="Esforco amostral e lacunas espaciais (grade de 1 grau)",
        xlabel="Longitude",
        ylabel="Latitude",
    )
    ax.set_aspect("equal")
    _salvar_figura(fig, pasta_saida / "lacunas_espaciais.png")


def criar_relatorio(
    ocorrencias: pd.DataFrame,
    especies: pd.DataFrame,
    resumos: dict[str, pd.DataFrame],
    qualidade: pd.DataFrame,
    grade: gpd.GeoDataFrame,
    metadados_pipeline: dict[str, Any],
) -> str:
    top = resumos["ranking_especies"].iloc[0]
    tipo = resumos["registros_por_tipo"].iloc[0]
    estado = resumos["registros_por_estado"].iloc[0]
    ano_min = int(pd.to_numeric(ocorrencias["year"], errors="coerce").min())
    ano_max = int(pd.to_numeric(ocorrencias["year"], errors="coerce").max())
    celulas_vazias = int((~grade["sampled"]).sum())
    duplicados = int(
        qualidade.loc[qualidade["metric"].eq("potentialDuplicate"), "recordCount"].iloc[
            0
        ]
    )
    estado_inesperado = int(
        qualidade.loc[
            qualidade["metric"].eq("unexpectedStateProvince"), "recordCount"
        ].iloc[0]
    )
    principal_alerta = resumos["alertas_ocorrencia"].iloc[0]
    incompleta = metadados_pipeline.get("sourceIsComplete") is False
    aviso_amostra = (
        "A fonte processada e uma amostra incompleta da consulta ao GBIF. "
        if incompleta
        else ""
    )

    return f"""# Analise exploratoria - Etapa 6

## Indicadores gerais

- Ocorrencias analisadas: {len(ocorrencias):,}
- Especies distintas: {especies["speciesKey"].nunique():,}
- Intervalo temporal observado: {ano_min} a {ano_max}
- Especie mais registrada: *{top["canonicalName"]}* ({int(top["occurrenceCount"])} registros)
- Tipo de registro predominante: {tipo["basisOfRecord"]} ({tipo["percentage"]:.2f}%)
- Unidade administrativa mais informada: {estado["stateProvince"]} ({estado["percentage"]:.2f}%)

## Qualidade e lacunas

- Registros candidatos a duplicidade: {duplicados:,}. Eles compartilham especie, coordenadas e data, mas nao sao removidos automaticamente porque podem representar individuos ou eventos distintos.
- Rotulos administrativos inesperados: {estado_inesperado}. O recorte usa as coordenadas; por isso divergencias no texto de estado/provincia sao mantidas como alerta de qualidade.
- Celulas da grade sem ocorrencias: {celulas_vazias} de {len(grade)}. Celulas vazias indicam ausencia de registros publicados na amostra, nao ausencia de peixes.
- Todos os pontos desta tabela possuem coordenadas e passaram pelo recorte espacial exato da Regiao Hidrografica do Parana.
- O alerta GBIF mais frequente e {principal_alerta["issue"]} ({int(principal_alerta["recordCount"])} registros). Alertas de interpretacao nao significam necessariamente que o registro seja inutilizavel.

## Interpretacao inicial

{aviso_amostra}As contagens representam atividade de coleta e publicacao, nao abundancia biologica. Concentracoes por especie, estado, periodo ou celula podem refletir acesso, projetos de pesquisa, colecoes e digitalizacao. A ordem da amostra e o recorte recente observado impedem interpretar a serie anual como tendencia populacional.

Os mapas devem ser usados para reconhecer concentracoes e areas pouco representadas. Uma comparacao robusta de riqueza ou ocupacao exige a base completa, controle do esforco amostral e avaliacao dos protocolos de coleta.
"""


def executar_analise(
    caminho_ocorrencias: Path = ARQUIVO_OCORRENCIAS,
    caminho_especies: Path = ARQUIVO_ESPECIES,
    caminho_limite: Path = ARQUIVO_LIMITE,
    pasta_saida: Path = PASTA_SAIDA,
) -> dict[str, Any]:
    ocorrencias = carregar_tabela(caminho_ocorrencias, COLUNAS_OBRIGATORIAS)
    especies = carregar_tabela(
        caminho_especies, {"speciesKey", "canonicalName", "occurrenceCount"}
    )
    limite = carregar_limite(caminho_limite)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    resumos = criar_resumos(ocorrencias, especies)
    qualidade = resumir_qualidade(ocorrencias)
    duplicados = identificar_duplicados_potenciais(ocorrencias)
    grade = criar_grade_espacial(ocorrencias, limite)

    for nome, tabela in resumos.items():
        tabela.to_csv(pasta_saida / f"{nome}.csv", index=False, encoding="utf-8")
    qualidade.to_csv(pasta_saida / "qualidade_dados.csv", index=False, encoding="utf-8")
    duplicados.to_csv(
        pasta_saida / "duplicados_potenciais.csv", index=False, encoding="utf-8"
    )
    grade.drop(columns="geometry").to_csv(
        pasta_saida / "grade_lacunas_espaciais.csv", index=False, encoding="utf-8"
    )

    gerar_graficos(ocorrencias, resumos, limite, grade, pasta_saida)
    metadados_pipeline = {}
    if ARQUIVO_METADADOS_PIPELINE.exists():
        metadados_pipeline = json.loads(
            ARQUIVO_METADADOS_PIPELINE.read_text(encoding="utf-8")
        )
    relatorio = criar_relatorio(
        ocorrencias, especies, resumos, qualidade, grade, metadados_pipeline
    )
    (pasta_saida / "relatorio_exploratorio.md").write_text(relatorio, encoding="utf-8")

    metadados = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "inputOccurrences": str(caminho_ocorrencias),
        "inputSpecies": str(caminho_especies),
        "boundaryFile": str(caminho_limite),
        "occurrenceCount": len(ocorrencias),
        "speciesCount": int(especies["speciesKey"].nunique()),
        "spatialGridDegrees": 1.0,
        "sourceIsComplete": metadados_pipeline.get("sourceIsComplete"),
        "interpretationWarning": (
            "Registros GBIF refletem coleta e publicacao, nao abundancia."
        ),
    }
    (pasta_saida / "analise_metadata.json").write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadados


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa a analise exploratoria multiespecies da Etapa 6."
    )
    parser.add_argument("--ocorrencias", type=Path, default=ARQUIVO_OCORRENCIAS)
    parser.add_argument("--especies", type=Path, default=ARQUIVO_ESPECIES)
    parser.add_argument("--limite", type=Path, default=ARQUIVO_LIMITE)
    parser.add_argument("--saida", type=Path, default=PASTA_SAIDA)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    configurar_logging(argumentos.verbose)
    metadados = executar_analise(
        argumentos.ocorrencias,
        argumentos.especies,
        argumentos.limite,
        argumentos.saida,
    )
    LOGGER.info("Ocorrências analisadas: %s", metadados["occurrenceCount"])
    LOGGER.info("Espécies distintas: %s", metadados["speciesCount"])
    LOGGER.info("Resultados salvos em: %s", argumentos.saida)


if __name__ == "__main__":
    main()

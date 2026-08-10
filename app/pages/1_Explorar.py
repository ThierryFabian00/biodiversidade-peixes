import colorsys
import hashlib
import logging
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import plotly.express as px
import psycopg
import pydeck as pdk
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    APP_NAME,
    LIMITE_PONTOS_MAPA,
    LIMITE_RESULTADOS_SQL,
    PAIS_PADRAO,
    PROJECT_SLUG,
)
from src.dashboard_data import (  # noqa: E402
    ResultadoFonte,
    calcular_indicadores,
    carregar_dados_dashboard,
    catalogo_taxonomico,
    comparar_paises,
    distribuicao_origem,
    distribuicao_tipo,
    filtrar_ocorrencias,
    frequencia_alertas,
    indicadores_qualidade,
    preparar_pontos_mapa,
    ranking_especies,
    serie_anual,
    serie_temporal,
    serie_temporal_especies,
)
from src.database import ConfiguracaoBanco  # noqa: E402
from src.filter_basin import ARQUIVO_LIMITE  # noqa: E402
from src.gbif_client import ErroGBIF  # noqa: E402
from src.i18n import (  # noqa: E402
    format_integer,
    t,
    translate_error,
    translate_notice,
    translate_progress,
    translate_source,
)
from src.report import gerar_relatorio_pdf  # noqa: E402
from src.security import mensagem_erro_segura  # noqa: E402
from src.services.country_service import listar_paises, obter_pais  # noqa: E402
from src.sync_data import (  # noqa: E402
    ProgressoSincronizacao,
    sincronizar_dados_pais,
)

CONFIGURACAO_BANCO = ConfiguracaoBanco.do_ambiente()
LOGGER = logging.getLogger(__name__)

CORES_ORIGEM = {
    "NATIVE": [15, 118, 110, 190],
    "INTRODUCED": [194, 65, 59, 200],
    "CONFLICTING": [217, 119, 6, 200],
    "UNKNOWN": [100, 116, 139, 160],
}
CORES_PLOTLY = {
    "NATIVE": "#0f766e",
    "INTRODUCED": "#c2413b",
    "CONFLICTING": "#d97706",
    "UNKNOWN": "#64748b",
}
ROTULOS_ORIGEM = {
    "NATIVE": t("native"),
    "INTRODUCED": t("introduced"),
    "CONFLICTING": t("conflicting"),
    "UNKNOWN": t("unknown"),
}
ROTULOS_ESTADO = {
    "Parana": "Paraná",
    "Sao Paulo": "São Paulo",
    "Goias": "Goiás",
    "Nao informado": t("not_informed"),
}

CHAVES_FILTROS_DEPENDENTES = (
    "explore_species",
    "explore_period",
    "explore_record_types",
    "explore_origins",
    "explore_states",
)
CHAVE_FILTRO_PAIS = "explore_country"


def limpar_filtros_dependentes() -> None:
    """Descarta seleções que não são válidas ao trocar o país."""
    for chave in CHAVES_FILTROS_DEPENDENTES:
        st.session_state.pop(chave, None)


def limpar_todos_os_filtros() -> None:
    """Restaura a página Explorar ao estado inicial neutro."""
    st.session_state.pop(CHAVE_FILTRO_PAIS, None)
    limpar_filtros_dependentes()


def aplicar_estilo() -> None:
    st.html(
        """
        <style>
        :root { --ink: #17211d; --muted: #5f6f67; --line: #d7dfdb; }
        * { letter-spacing: 0 !important; }
        .stApp { background: #f5f7f6; color: var(--ink); }
        .block-container { max-width: 1480px; padding-top: 3.8rem; padding-bottom: 3rem; }
        h1 { font-size: 2.15rem !important; line-height: 1.12 !important; margin-bottom: .2rem !important; }
        h2 { font-size: 1.25rem !important; }
        h3 { font-size: 1.05rem !important; }
        [data-testid="stSidebar"] { background: #edf2ef; border-right: 1px solid var(--line); }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid var(--line);
            border-left: 4px solid #0f766e;
            border-radius: 6px;
            min-height: 106px;
            padding: 1rem 1.05rem;
        }
        [data-testid="stMetricLabel"] { color: var(--muted); }
        [data-testid="stMetricValue"] { color: var(--ink); font-size: 1.4rem; }
        .source-row { display: flex; align-items: center; gap: .55rem; color: var(--muted); margin: .2rem 0 1.1rem; }
        .source-badge {
            display: inline-flex; align-items: center; min-height: 26px;
            padding: 2px 9px; border: 1px solid #9bb8aa; border-radius: 999px;
            background: #e4f0ea; color: #245b43; font-size: .78rem; font-weight: 650;
        }
        .stTabs [data-baseweb="tab-list"] { gap: .3rem; border-bottom: 1px solid var(--line); }
        .stTabs [data-baseweb="tab"] { border-radius: 4px 4px 0 0; padding: .65rem 1rem; }
        [data-testid="stDataFrame"], [data-testid="stPlotlyChart"], [data-testid="stPydeckChart"] {
            background: #ffffff; border: 1px solid var(--line); border-radius: 6px;
        }
        .quality-note {
            border-left: 4px solid #d97706; background: #fff8eb; padding: .85rem 1rem;
            border-radius: 4px; color: #5f481b; margin-top: .75rem;
        }
        button { border-radius: 4px !important; }
        [data-testid="stAppDeployButton"], [data-testid="stMainMenu"], [data-testid="stStatusWidget"] { display: none; }
        @media (max-width: 760px) {
            .block-container { padding: 3.5rem .8rem 2rem; }
            h1 { font-size: 1.7rem !important; }
            [data-testid="stMetric"] { min-height: 92px; }
            .source-row { align-items: flex-start; flex-direction: column; }
        }
        </style>
        """
    )


@st.cache_data(ttl=300, max_entries=12, show_spinner=False)
def obter_dados(schema: str, codigo_pais: str) -> ResultadoFonte:
    return carregar_dados_dashboard(
        CONFIGURACAO_BANCO.database_url, schema, codigo_pais=codigo_pais
    )


@st.cache_data(max_entries=2, show_spinner=False)
def obter_limite_geojson() -> dict[str, Any] | None:
    if not ARQUIVO_LIMITE.exists():
        return None
    limite = gpd.read_file(ARQUIVO_LIMITE, engine="fiona").to_crs("EPSG:4326")
    limite["geometry"] = limite.geometry.simplify(0.01, preserve_topology=True)
    return limite.__geo_interface__


@st.cache_data(ttl=300, max_entries=20, show_spinner=False)
def obter_relatorio_pdf(
    dados: pd.DataFrame,
    pais_nome: str,
    pais_codigo: str,
    fonte: str,
    filtros: tuple[tuple[str, str], ...],
) -> bytes:
    return gerar_relatorio_pdf(
        dados,
        pais_nome=pais_nome,
        pais_codigo=pais_codigo,
        fonte=fonte,
        filtros=dict(filtros),
    )


def formatar_numero(valor: int) -> str:
    return format_integer(valor)


def rotulo_estado(valor: str) -> str:
    return ROTULOS_ESTADO.get(valor, valor)


def layout_grafico(figura: Any, altura: int = 390) -> Any:
    figura.update_layout(
        height=altura,
        margin=dict(l=16, r=16, t=52, b=20),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(color="#17211d", size=12),
        title_font=dict(size=16),
        hoverlabel=dict(bgcolor="#ffffff", font_size=12),
    )
    figura.update_xaxes(showgrid=True, gridcolor="#e8eeeb", zeroline=False)
    figura.update_yaxes(showgrid=False, zeroline=False)
    return figura


def cor_especie(chave: Any) -> list[int]:
    resumo = hashlib.sha256(str(chave).encode("utf-8")).digest()
    matiz = int.from_bytes(resumo[:2], "big") / 65535
    vermelho, verde, azul = colorsys.hsv_to_rgb(matiz, 0.68, 0.78)
    return [int(vermelho * 255), int(verde * 255), int(azul * 255), 190]


def criar_mapa(
    dados: pd.DataFrame,
    exibir_limite: bool = True,
    modo: str = "Pontos por espécie",
) -> pdk.Deck | None:
    pontos, agregado = preparar_pontos_mapa(dados)
    if pontos.empty:
        return None
    modos = {"Pontos por espécie", "Mapa de calor", "Agrupamento espacial"}
    if modo not in modos:
        raise ValueError(f"Modo de mapa inválido: {modo}")
    pontos["point_color"] = (
        [[15, 118, 110, 190]] * len(pontos)
        if agregado
        else pontos["species_key"].map(cor_especie)
    )
    pontos["origin_display"] = pontos["origin_status"].map(ROTULOS_ORIGEM)
    pontos["state_display"] = pontos["state_normalized"].map(rotulo_estado)
    pontos["point_color"] = pontos["point_color"].apply(
        lambda cor: cor if isinstance(cor, list) else CORES_ORIGEM["UNKNOWN"]
    )
    pontos["point_radius"] = (
        2600 * (1 + pontos["map_occurrence_count"].pow(0.5).clip(upper=5))
        if agregado
        else 2600
    )
    camadas = []
    limite = obter_limite_geojson() if exibir_limite else None
    if limite:
        camadas.append(
            pdk.Layer(
                "GeoJsonLayer",
                limite,
                stroked=True,
                filled=True,
                get_fill_color=[15, 118, 110, 16],
                get_line_color=[39, 73, 58, 180],
                line_width_min_pixels=1,
                pickable=False,
            )
        )
    if modo == "Pontos por espécie":
        camadas.append(
            pdk.Layer(
                "ScatterplotLayer",
                pontos,
                get_position="[decimal_longitude, decimal_latitude]",
                get_fill_color="point_color",
                get_radius="point_radius",
                radius_min_pixels=3,
                radius_max_pixels=11,
                stroked=True,
                get_line_color=[255, 255, 255, 130],
                line_width_min_pixels=0.4,
                opacity=0.75,
                pickable=True,
                auto_highlight=True,
            )
        )
    elif modo == "Mapa de calor":
        camadas.append(
            pdk.Layer(
                "HeatmapLayer",
                pontos,
                get_position="[decimal_longitude, decimal_latitude]",
                get_weight="map_occurrence_count",
                radius_pixels=45,
                intensity=1,
                threshold=0.03,
            )
        )
    else:
        tipo_camada = "ColumnLayer" if agregado else "HexagonLayer"
        argumentos_camada = {
            "get_position": "[decimal_longitude, decimal_latitude]",
            "radius": 12000,
            "elevation_scale": 20,
            "extruded": True,
            "pickable": True,
            "auto_highlight": True,
            "coverage": 0.88,
        }
        if agregado:
            argumentos_camada.update(
                get_elevation="map_occurrence_count",
                get_fill_color=[15, 118, 110, 190],
            )
        else:
            argumentos_camada["elevation_range"] = [0, 1000]
        camadas.append(pdk.Layer(tipo_camada, pontos, **argumentos_camada))
    zoom = 5.0 if len(pontos) >= 50 else 6.2
    vista = pdk.ViewState(
        latitude=float(pontos["decimal_latitude"].mean()),
        longitude=float(pontos["decimal_longitude"].mean()),
        zoom=zoom,
        pitch=35 if modo == "Agrupamento espacial" else 0,
    )
    return pdk.Deck(
        layers=camadas,
        initial_view_state=vista,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip=(
            {
                "html": "<b>{canonical_name}</b><br/>{state_display}<br/>{event_year} · {basis_of_record}<br/>GBIF {gbif_id}",
                "style": {"backgroundColor": "#17211d", "color": "white"},
            }
            if modo == "Pontos por espécie" and not agregado
            else {
                "html": (t("map_aggregated")),
                "style": {"backgroundColor": "#17211d", "color": "white"},
            }
            if agregado
            else {
                "html": t("map_nearby"),
                "style": {"backgroundColor": "#17211d", "color": "white"},
            }
        ),
    )


aplicar_estilo()

st.title(APP_NAME)
st.caption(t("app_caption"))

paises_disponiveis = listar_paises()
nomes_por_codigo = {pais.codigo_iso: pais.nome for pais in paises_disponiveis}
codigos_paises = [pais.codigo_iso for pais in paises_disponiveis]
with st.sidebar:
    st.markdown(f"### {APP_NAME}")
    st.header(t("filters"))
    codigo_pais = st.selectbox(
        t("country"),
        [None, *codigos_paises],
        index=0,
        format_func=lambda codigo: (
            t("select_country")
            if codigo is None
            else f"{nomes_por_codigo[codigo]} ({codigo})"
        ),
        key=CHAVE_FILTRO_PAIS,
        on_change=limpar_filtros_dependentes,
    )

if codigo_pais is None:
    st.info(t("select_country_to_begin"))
    st.stop()

pais = obter_pais(codigo_pais)
schema = CONFIGURACAO_BANCO.schema
sincronizacao = None
widget_progresso: dict[str, Any] = {"valor": None}


def atualizar_progresso(evento: ProgressoSincronizacao) -> None:
    valor = (
        min(evento.coletados / evento.total, 1.0)
        if evento.total
        else (1.0 if evento.etapa == "concluido" else 0.0)
    )
    if widget_progresso["valor"] is None:
        widget_progresso["valor"] = st.sidebar.progress(
            valor, text=translate_progress(evento.mensagem)
        )
    else:
        widget_progresso["valor"].progress(
            valor, text=translate_progress(evento.mensagem)
        )


try:
    resultado = obter_dados(schema, pais.codigo_iso)
except (FileNotFoundError, ValueError) as erro:
    mensagem = mensagem_erro_segura(erro, t("source_unavailable_error"))
    LOGGER.error("Falha controlada ao carregar dados: %s", mensagem)
    st.error(
        t(
            "data_unavailable",
            message=translate_error(mensagem, "source_unavailable_error"),
        )
    )
    st.stop()

dados = resultado.dados

with st.sidebar:
    catalogo_especies = (
        dados[["species_key", "canonical_name"]]
        .dropna()
        .drop_duplicates("species_key")
        .sort_values(["canonical_name", "species_key"])
    )
    nomes_especies = dict(
        zip(
            catalogo_especies["species_key"],
            catalogo_especies["canonical_name"],
            strict=True,
        )
    )
    anos = dados["event_year"].dropna().astype(int)
    limites_anos = (int(anos.min()), int(anos.max())) if not anos.empty else None
    tipos_disponiveis = sorted(dados["basis_of_record"].dropna().unique())

    with st.form("explore_primary_filters", border=False):
        especies = st.multiselect(
            t("species"),
            catalogo_especies["species_key"].tolist(),
            placeholder=t("all_species"),
            format_func=lambda chave: nomes_especies.get(chave, chave),
            key="explore_species",
        )
        intervalo_anos = None
        if limites_anos is not None:
            intervalo_anos = st.slider(
                t("period"),
                min_value=limites_anos[0],
                max_value=limites_anos[1],
                value=limites_anos,
                key="explore_period",
            )
        tipos = st.multiselect(
            t("record_type"),
            tipos_disponiveis,
            placeholder=t("all_record_types"),
            key="explore_record_types",
        )
        st.form_submit_button(
            t("apply_filters"),
            type="primary",
            width="stretch",
        )

    st.button(
        t("clear_filters"),
        on_click=limpar_todos_os_filtros,
        width="stretch",
    )

    with st.expander(t("advanced_filters")):
        origens_disponiveis = sorted(dados["origin_status"].dropna().unique())
        origens = st.multiselect(
            t("origin"),
            origens_disponiveis,
            placeholder=t("all_classifications"),
            format_func=lambda valor: ROTULOS_ORIGEM.get(valor, valor),
            key="explore_origins",
        )
        estados_disponiveis = sorted(dados["state_normalized"].dropna().unique())
        estados = st.multiselect(
            t("administrative_unit"),
            estados_disponiveis,
            placeholder=t("all_units"),
            format_func=rotulo_estado,
            key="explore_states",
        )

    database_write_url = CONFIGURACAO_BANCO.database_write_url
    with st.expander(t("data_administration")):
        forcar_atualizacao = st.button(
            t("update_gbif"),
            icon=":material/refresh:",
            width="stretch",
            disabled=database_write_url is None,
            help=t("update_help") if database_write_url is None else None,
        )
        if database_write_url is None:
            st.caption(t("update_disabled"))

    st.divider()
    st.caption("GBIF · DHN250/IBGE · Catalogue of Life")

if forcar_atualizacao and database_write_url:
    try:
        sincronizacao = sincronizar_dados_pais(
            database_write_url,
            schema,
            pais.codigo_iso,
            forcar_atualizacao=forcar_atualizacao,
            callback=atualizar_progresso,
        )
        if sincronizacao.fonte == "GBIF":
            obter_dados.clear()
            st.sidebar.success(
                t(
                    "update_complete",
                    count=formatar_numero(sincronizacao.registros_salvos),
                )
            )
            st.rerun()
    except (ErroGBIF, psycopg.Error, ValueError) as erro:
        mensagem = mensagem_erro_segura(erro, t("unexpected_update_error"))
        LOGGER.error("Falha controlada na atualização: %s", mensagem)
        st.sidebar.error(
            t(
                "update_failed",
                message=translate_error(mensagem, "unexpected_update_error"),
            )
        )
    finally:
        if widget_progresso["valor"] is not None:
            widget_progresso["valor"].empty()
elif forcar_atualizacao:
    st.sidebar.warning(t("update_unavailable"))

filtrados = filtrar_ocorrencias(
    dados,
    chaves_especies=especies,
    origens=origens,
    intervalo_anos=intervalo_anos,
    tipos=tipos,
    estados=estados,
)

descricao_pais = (
    t("parana_region_description")
    if pais.codigo_iso == PAIS_PADRAO
    else t("selected_country", name=pais.nome, code=pais.codigo_iso)
)
fonte_traduzida = translate_source(resultado.fonte)
st.html(
    f"""
    <div class="source-row">
      <span>{descricao_pais}</span>
      <span class="source-badge">{t("active_source", source=fonte_traduzida)}</span>
    </div>
    """
)
st.caption(t("selected_country", name=pais.nome, code=pais.codigo_iso))
if resultado.aviso:
    st.warning(translate_notice(resultado.aviso))

indicadores = calcular_indicadores(filtrados)
rotulo_especies = (
    nomes_especies.get(especies[0], especies[0])
    if len(especies) == 1
    else t("selected_species_count", count=len(especies))
    if especies
    else t("all_species")
)
rotulo_periodo = (
    t("all_available_period")
    if intervalo_anos is None or intervalo_anos == limites_anos
    else f"{intervalo_anos[0]}–{intervalo_anos[1]}"
)
rotulo_tipos = (
    tipos[0]
    if len(tipos) == 1
    else t("selected_record_types_count", count=len(tipos))
    if tipos
    else t("all_record_types")
)
st.markdown(
    f"**{t('active_filters')}:** "
    + " • ".join([pais.nome, rotulo_especies, rotulo_periodo, rotulo_tipos])
)
st.caption(t("records_found", count=formatar_numero(indicadores["occurrences"])))

ultima_atualizacao = (
    pd.Timestamp(resultado.resumo_importacao.atualizado_em).strftime("%d/%m/%Y")
    if resultado.resumo_importacao
    and resultado.resumo_importacao.atualizado_em is not None
    else None
)
metricas = [
    (t("occurrences"), formatar_numero(indicadores["occurrences"])),
    (t("species"), formatar_numero(indicadores["species"])),
    (t("covered_period"), indicadores["period"]),
]
if ultima_atualizacao is not None:
    metricas.append((t("last_update"), ultima_atualizacao))
colunas_metricas = st.columns(len(metricas))
for coluna, (rotulo, valor) in zip(colunas_metricas, metricas, strict=True):
    coluna.metric(rotulo, valor)

if filtrados.empty:
    st.info(t("empty_filters", name=pais.nome, code=pais.codigo_iso))
    st.stop()

aba_visao, aba_mapa, aba_temporal, aba_qualidade = st.tabs(
    [
        t("overview"),
        t("map"),
        t("temporal_analysis"),
        t("data_quality"),
    ]
)

with aba_visao:
    ranking = ranking_especies(filtrados)
    origens_tabela = distribuicao_origem(filtrados)
    ranking["origin_label"] = ranking["origin_status"].map(ROTULOS_ORIGEM)
    origens_tabela["origin_label"] = origens_tabela["origin_status"].map(ROTULOS_ORIGEM)
    coluna_ranking, coluna_origem = st.columns([1.65, 1])
    with coluna_ranking:
        ranking_plot = ranking.sort_values("occurrence_count")
        figura = px.bar(
            ranking_plot,
            x="occurrence_count",
            y="canonical_name",
            color="origin_label",
            orientation="h",
            color_discrete_map={
                ROTULOS_ORIGEM[chave]: cor for chave, cor in CORES_PLOTLY.items()
            },
            labels={
                "occurrence_count": t("occurrences"),
                "canonical_name": "",
                "origin_label": t("origin"),
            },
            title=t("most_recorded_species"),
        )
        figura.update_layout(legend_title_text=t("origin"))
        st.plotly_chart(
            layout_grafico(figura, 470),
            width="stretch",
            config={"displayModeBar": False},
        )

    secao_especies = st.expander(t("species"))
    secao_comparacao = st.expander(t("comparison"))
    secao_relatorio = st.expander(t("report"))
    secao_dados = st.expander(t("data"))
    with coluna_origem:
        figura = px.bar(
            origens_tabela,
            x="origin_label",
            y="species_count",
            color="origin_label",
            color_discrete_map={
                ROTULOS_ORIGEM[chave]: cor for chave, cor in CORES_PLOTLY.items()
            },
            labels={"origin_label": t("origin"), "species_count": t("species")},
            title=t("species_by_origin"),
        )
        figura.update_layout(showlegend=False)
        st.plotly_chart(
            layout_grafico(figura, 470),
            width="stretch",
            config={"displayModeBar": False},
        )

with aba_mapa:
    modo_mapa = st.radio(
        t("map_view"),
        ["Pontos por espécie", "Mapa de calor", "Agrupamento espacial"],
        format_func=lambda modo: {
            "Pontos por espécie": t("map_points"),
            "Mapa de calor": t("map_heat"),
            "Agrupamento espacial": t("map_clusters"),
        }[modo],
        horizontal=True,
    )
    mapa = criar_mapa(
        filtrados,
        exibir_limite=pais.codigo_iso == PAIS_PADRAO,
        modo=modo_mapa,
    )
    registros_mapa = filtrados.dropna(subset=["decimal_latitude", "decimal_longitude"])
    if len(registros_mapa) > LIMITE_PONTOS_MAPA:
        st.caption(
            t(
                "map_responsive",
                records=formatar_numero(len(registros_mapa)),
                cells=formatar_numero(LIMITE_PONTOS_MAPA),
            )
        )
    if mapa:
        st.pydeck_chart(mapa, width="stretch", height=610)
    else:
        st.info(t("no_coordinates"))

    registros_detalhe = registros_mapa.head(LIMITE_RESULTADOS_SQL)
    if len(registros_mapa) > len(registros_detalhe):
        st.caption(t("details_limited", count=formatar_numero(len(registros_detalhe))))
    ids_mapa = registros_detalhe["gbif_id"].tolist()
    nomes_ids = registros_detalhe.set_index("gbif_id")["canonical_name"].to_dict()
    ocorrencia_selecionada = st.selectbox(
        t("occurrence_details"),
        [None, *ids_mapa],
        key=f"ocorrencia_mapa_{pais.codigo_iso}",
        format_func=lambda chave: (
            t("select_occurrence")
            if chave is None
            else f"GBIF {chave} — {nomes_ids.get(chave, t('species_not_informed'))}"
        ),
    )
    if ocorrencia_selecionada is not None:
        detalhe = registros_detalhe.loc[
            registros_detalhe["gbif_id"].eq(ocorrencia_selecionada),
            [
                "gbif_id",
                "canonical_name",
                "family",
                "order_name",
                "event_date",
                "basis_of_record",
                "state_normalized",
                "locality",
                "decimal_latitude",
                "decimal_longitude",
            ],
        ].rename(
            columns={
                "gbif_id": "GBIF ID",
                "canonical_name": t("species"),
                "family": t("family"),
                "order_name": t("order"),
                "event_date": t("date"),
                "basis_of_record": t("type"),
                "state_normalized": t("unit"),
                "locality": t("locality"),
                "decimal_latitude": "Latitude",
                "decimal_longitude": "Longitude",
            }
        )
        st.dataframe(detalhe, hide_index=True, width="stretch")

    tipo_tabela = distribuicao_tipo(filtrados).head(10)
    estado_tabela = (
        filtrados["state_normalized"]
        .value_counts()
        .rename_axis("state")
        .reset_index(name="occurrence_count")
        .head(10)
    )
    estado_tabela["state_display"] = estado_tabela["state"].map(rotulo_estado)
    coluna_tipo, coluna_estado = st.columns(2)
    with coluna_tipo:
        figura = px.bar(
            tipo_tabela.sort_values("occurrence_count"),
            x="occurrence_count",
            y="basis_of_record",
            orientation="h",
            labels={"occurrence_count": t("occurrences"), "basis_of_record": ""},
            title=t("record_type"),
            color_discrete_sequence=["#7c3f58"],
        )
        st.plotly_chart(
            layout_grafico(figura),
            width="stretch",
            config={"displayModeBar": False},
        )
    with coluna_estado:
        figura = px.bar(
            estado_tabela.sort_values("occurrence_count"),
            x="occurrence_count",
            y="state_display",
            orientation="h",
            labels={"occurrence_count": t("occurrences"), "state_display": ""},
            title=t("informed_administrative_unit"),
            color_discrete_sequence=["#4f772d"],
        )
        st.plotly_chart(
            layout_grafico(figura),
            width="stretch",
            config={"displayModeBar": False},
        )

with aba_temporal:
    anual = serie_anual(filtrados)
    mensal = serie_temporal(filtrados)
    coluna_anual, coluna_mensal = st.columns(2)
    with coluna_anual:
        figura = px.bar(
            anual,
            x="event_year",
            y="occurrence_count",
            labels={"event_year": t("year"), "occurrence_count": t("occurrences")},
            title=t("occurrences_by_year"),
            color_discrete_sequence=["#0f766e"],
        )
        st.plotly_chart(
            layout_grafico(figura, 400),
            width="stretch",
            config={"displayModeBar": False},
        )
    with coluna_mensal:
        figura = px.line(
            mensal,
            x="period",
            y="occurrence_count",
            labels={"period": t("month"), "occurrence_count": t("occurrences")},
            title=t("occurrences_by_month"),
        )
        figura.update_traces(line_color="#2563eb")
        st.plotly_chart(
            layout_grafico(figura, 400),
            width="stretch",
            config={"displayModeBar": False},
        )

    comparacao = serie_temporal_especies(filtrados)
    figura = px.line(
        comparacao,
        x="event_year",
        y="occurrence_count",
        color="canonical_name",
        markers=True,
        labels={
            "event_year": t("year"),
            "occurrence_count": t("occurrences"),
            "canonical_name": t("species"),
        },
        title=t("species_temporal_comparison"),
    )
    st.plotly_chart(
        layout_grafico(figura, 430),
        width="stretch",
        config={"displayModeBar": False},
    )

with secao_especies:
    st.subheader(t("taxonomic_catalog"))
    busca_taxonomica = st.text_input(
        t("search_scientific_name"),
        placeholder=t("scientific_name_placeholder"),
        key="busca_taxonomica",
    )
    taxonomia = catalogo_taxonomico(filtrados)
    if busca_taxonomica.strip():
        taxonomia = taxonomia.loc[
            taxonomia["canonical_name"]
            .fillna("")
            .str.contains(busca_taxonomica.strip(), case=False, regex=False)
        ]
    taxonomia["origin_status"] = taxonomia["origin_status"].map(ROTULOS_ORIGEM)
    st.dataframe(
        taxonomia.rename(
            columns={
                "species_key": t("taxonomic_key"),
                "canonical_name": t("scientific_name"),
                "family": t("family"),
                "order_name": t("order"),
                "occurrence_count": t("occurrences"),
                "origin_status": t("origin"),
                "iucn_category": "IUCN",
            }
        ),
        hide_index=True,
        width="stretch",
        height=520,
    )

with secao_comparacao:
    st.subheader(t("country_comparison"))
    coluna_pais_a, coluna_pais_b = st.columns(2)
    with coluna_pais_a:
        codigo_comparacao_a = st.selectbox(
            t("first_country"),
            codigos_paises,
            index=codigos_paises.index("BR"),
            format_func=lambda codigo: f"{nomes_por_codigo[codigo]} ({codigo})",
            key="pais_comparacao_a",
        )
    with coluna_pais_b:
        codigo_comparacao_b = st.selectbox(
            t("second_country"),
            codigos_paises,
            index=codigos_paises.index("CH"),
            format_func=lambda codigo: f"{nomes_por_codigo[codigo]} ({codigo})",
            key="pais_comparacao_b",
        )

    if codigo_comparacao_a == codigo_comparacao_b:
        st.warning(t("different_countries"))
    else:
        fonte_a = obter_dados(schema, codigo_comparacao_a)
        fonte_b = obter_dados(schema, codigo_comparacao_b)
        dados_a = fonte_a.dados
        dados_b = fonte_b.dados
        if dados_a.empty or dados_b.empty:
            sem_dados = [
                nomes_por_codigo[codigo]
                for codigo, tabela in (
                    (codigo_comparacao_a, dados_a),
                    (codigo_comparacao_b, dados_b),
                )
                if tabela.empty
            ]
            st.warning(t("countries_without_data", countries=", ".join(sem_dados)))
        else:
            anos_comparacao = pd.concat(
                [dados_a["event_year"], dados_b["event_year"]]
            ).dropna()
            if not anos_comparacao.empty:
                limites_comparacao = (
                    int(anos_comparacao.min()),
                    int(anos_comparacao.max()),
                )
                intervalo_comparacao = st.slider(
                    t("comparison_period"),
                    min_value=limites_comparacao[0],
                    max_value=limites_comparacao[1],
                    value=limites_comparacao,
                    key="periodo_comparacao",
                )
                dados_a = filtrar_ocorrencias(
                    dados_a, intervalo_anos=intervalo_comparacao
                )
                dados_b = filtrar_ocorrencias(
                    dados_b, intervalo_anos=intervalo_comparacao
                )

            comparacao = comparar_paises(
                dados_a,
                codigo_comparacao_a,
                nomes_por_codigo[codigo_comparacao_a],
                dados_b,
                codigo_comparacao_b,
                nomes_por_codigo[codigo_comparacao_b],
            )
            resumo_a = comparacao.resumo.iloc[0]
            resumo_b = comparacao.resumo.iloc[1]
            metricas_comparacao = st.columns(4)
            metricas_comparacao[0].metric(
                t("species_code", code=codigo_comparacao_a),
                formatar_numero(int(resumo_a["species"])),
            )
            metricas_comparacao[1].metric(
                t("species_code", code=codigo_comparacao_b),
                formatar_numero(int(resumo_b["species"])),
            )
            metricas_comparacao[2].metric(
                t("occurrences_code", code=codigo_comparacao_a),
                formatar_numero(int(resumo_a["occurrences"])),
            )
            metricas_comparacao[3].metric(
                t("occurrences_code", code=codigo_comparacao_b),
                formatar_numero(int(resumo_b["occurrences"])),
            )

            st.subheader(t("temporal_distribution"))
            coluna_bruta, coluna_normalizada = st.columns(2)
            with coluna_bruta:
                figura = px.line(
                    comparacao.temporal,
                    x="event_year",
                    y="occurrence_count",
                    color="country_name",
                    markers=True,
                    labels={
                        "event_year": t("year"),
                        "occurrence_count": t("occurrences"),
                        "country_name": t("country"),
                    },
                    title=t("annual_counts"),
                )
                st.plotly_chart(
                    layout_grafico(figura, 410),
                    width="stretch",
                    config={"displayModeBar": False},
                )
            with coluna_normalizada:
                figura = px.line(
                    comparacao.temporal,
                    x="event_year",
                    y="sample_percentage",
                    color="country_name",
                    markers=True,
                    labels={
                        "event_year": t("year"),
                        "sample_percentage": t("country_sample_pct"),
                        "country_name": t("country"),
                    },
                    title=t("normalized_annual_distribution"),
                )
                st.plotly_chart(
                    layout_grafico(figura, 410),
                    width="stretch",
                    config={"displayModeBar": False},
                )

            st.subheader(t("normalized_metrics"))
            tabela_normalizada = comparacao.resumo[
                [
                    "country_name",
                    "occurrences_per_species",
                    "years_with_records",
                    "period",
                    "records_with_date_pct",
                    "records_with_coordinates_pct",
                ]
            ].rename(
                columns={
                    "country_name": t("country"),
                    "occurrences_per_species": t("records_per_species"),
                    "years_with_records": t("years_with_records"),
                    "period": t("period"),
                    "records_with_date_pct": t("with_date_pct"),
                    "records_with_coordinates_pct": t("with_coordinates_pct"),
                }
            )
            st.dataframe(
                tabela_normalizada,
                hide_index=True,
                width="stretch",
                column_config={
                    t("records_per_species"): st.column_config.NumberColumn(
                        format="%.1f"
                    ),
                    t("with_date_pct"): st.column_config.NumberColumn(format="%.1f%%"),
                    t("with_coordinates_pct"): st.column_config.NumberColumn(
                        format="%.1f%%"
                    ),
                },
            )

            st.subheader(t("shared_exclusive_species"))
            colunas_sobreposicao = st.columns(4)
            colunas_sobreposicao[0].metric(
                t("shared"),
                formatar_numero(len(comparacao.especies_compartilhadas)),
            )
            colunas_sobreposicao[1].metric(
                t("exclusive_code", code=codigo_comparacao_a),
                formatar_numero(len(comparacao.especies_exclusivas_a)),
            )
            colunas_sobreposicao[2].metric(
                t("exclusive_code", code=codigo_comparacao_b),
                formatar_numero(len(comparacao.especies_exclusivas_b)),
            )
            colunas_sobreposicao[3].metric(
                t("jaccard_similarity"),
                f"{comparacao.similaridade_jaccard:.1f}%",
            )

            tabela_compartilhadas = comparacao.especies_compartilhadas.rename(
                columns={
                    "species_key": t("taxonomic_key"),
                    "canonical_name": t("scientific_name"),
                    "occurrences_a": t("occurrences_code", code=codigo_comparacao_a),
                    "occurrences_b": t("occurrences_code", code=codigo_comparacao_b),
                }
            )
            coluna_compartilhadas, coluna_exclusivas = st.columns([1.25, 1])
            with coluna_compartilhadas:
                st.caption(t("species_in_both"))
                st.dataframe(
                    tabela_compartilhadas,
                    hide_index=True,
                    width="stretch",
                    height=360,
                )
            with coluna_exclusivas:
                st.caption(t("exclusive_by_set"))
                exclusivas_a = comparacao.especies_exclusivas_a.assign(
                    country=codigo_comparacao_a
                ).rename(columns={"occurrences_a": "occurrence_count"})
                exclusivas_b = comparacao.especies_exclusivas_b.assign(
                    country=codigo_comparacao_b
                ).rename(columns={"occurrences_b": "occurrence_count"})
                exclusivas = pd.concat(
                    [exclusivas_a, exclusivas_b], ignore_index=True
                ).rename(
                    columns={
                        "species_key": t("taxonomic_key"),
                        "canonical_name": t("scientific_name"),
                        "occurrence_count": t("occurrences"),
                        "country": t("country"),
                    }
                )
                st.dataframe(
                    exclusivas,
                    hide_index=True,
                    width="stretch",
                    height=360,
                )

            recebidos_a = (
                fonte_a.resumo_importacao.registros_recebidos
                if fonte_a.resumo_importacao
                else len(fonte_a.dados)
            )
            recebidos_b = (
                fonte_b.resumo_importacao.registros_recebidos
                if fonte_b.resumo_importacao
                else len(fonte_b.dados)
            )
            st.html(
                '<div class="quality-note">'
                + t(
                    "methodological_caution",
                    records_a=formatar_numero(recebidos_a),
                    country_a=nomes_por_codigo[codigo_comparacao_a],
                    records_b=formatar_numero(recebidos_b),
                    country_b=nomes_por_codigo[codigo_comparacao_b],
                )
                + "</div>"
            )

with secao_relatorio:
    st.subheader(t("automatic_report"))
    st.caption(t("report_description"))
    nomes_selecionados = [nomes_especies[chave] for chave in especies]
    periodo_relatorio = (
        f"{intervalo_anos[0]}–{intervalo_anos[1]}"
        if intervalo_anos
        else t("all_available_years")
    )
    filtros_relatorio = {
        t("country"): f"{pais.nome} ({pais.codigo_iso})",
        t("species"): ", ".join(nomes_selecionados) or t("all_species"),
        t("period"): periodo_relatorio,
        t("origin"): ", ".join(ROTULOS_ORIGEM.get(item, item) for item in origens)
        or t("all_classifications"),
        t("record_type"): ", ".join(tipos) or t("all_record_types"),
        t("administrative_unit"): ", ".join(rotulo_estado(item) for item in estados)
        or t("all_units"),
        t("source_update"): ultima_atualizacao or t("not_available"),
    }
    st.markdown(
        t(
            "query_summary",
            country=pais.nome,
            period=periodo_relatorio,
            occurrences=formatar_numero(indicadores["occurrences"]),
            species=formatar_numero(indicadores["species"]),
        )
    )
    with st.spinner(t("preparing_report")):
        relatorio_pdf = obter_relatorio_pdf(
            filtrados,
            pais.nome,
            pais.codigo_iso,
            f"GBIF via {resultado.fonte}",
            tuple(filtros_relatorio.items()),
        )
    sufixo_periodo = periodo_relatorio.replace("–", "-").replace(" ", "_")
    st.download_button(
        t("download_report"),
        data=relatorio_pdf,
        file_name=(
            f"{PROJECT_SLUG}_relatorio_{pais.codigo_iso.lower()}_{sufixo_periodo}.pdf"
        ),
        mime="application/pdf",
        icon=":material/picture_as_pdf:",
        type="primary",
    )
    st.caption(t("report_signature"))

with aba_qualidade:
    qualidade = indicadores_qualidade(filtrados)
    total = max(len(filtrados), 1)

    st.subheader(t("last_load_usage"))
    resumo_importacao = resultado.resumo_importacao
    if resumo_importacao:
        colunas_funil = st.columns(4)
        colunas_funil[0].metric(
            t("received"), formatar_numero(resumo_importacao.registros_recebidos)
        )
        colunas_funil[1].metric(
            t("used"), formatar_numero(resumo_importacao.registros_salvos)
        )
        colunas_funil[2].metric(
            t("discarded"), formatar_numero(resumo_importacao.registros_descartados)
        )
        colunas_funil[3].metric(
            t("usage"), f"{resumo_importacao.percentual_aproveitado:.1f}%"
        )
        st.caption(
            t(
                "without_species_level",
                count=formatar_numero(resumo_importacao.sem_nivel_especie),
            )
        )
    else:
        st.caption(t("summary_unavailable"))

    st.subheader(t("used_record_indicators"))
    colunas_qualidade = st.columns(4)
    itens_qualidade = [
        (t("missing_date"), qualidade["missing_date"]),
        (t("monthly_date"), qualidade["monthly_date"]),
        (t("invalid_coordinates"), qualidade["invalid_coordinates"]),
        (t("potential_duplicate"), qualidade["potential_duplicate"]),
    ]
    for coluna, (rotulo, valor) in zip(colunas_qualidade, itens_qualidade, strict=True):
        coluna.metric(rotulo, formatar_numero(valor), f"{100 * valor / total:.1f}%")

    colunas_qualidade = st.columns(4)
    itens_qualidade = [
        (t("gbif_issue"), qualidade["gbif_issue"]),
        (t("potential_outside_country"), qualidade["potential_outside_country"]),
        (t("missing_locality"), qualidade["missing_locality"]),
        (t("unexpected_unit"), qualidade["unexpected_state"]),
    ]
    for coluna, (rotulo, valor) in zip(colunas_qualidade, itens_qualidade, strict=True):
        coluna.metric(rotulo, formatar_numero(valor), f"{100 * valor / total:.1f}%")

    evidencia = distribuicao_tipo(filtrados).head(12)
    precisao = (
        filtrados["date_precision"]
        .fillna("MISSING")
        .value_counts()
        .rename_axis("date_precision")
        .reset_index(name="record_count")
    )
    rotulos_precisao = {
        "DAY": t("day"),
        "MONTH": t("month"),
        "YEAR": t("year"),
        "UNKNOWN": t("unknown"),
        "MISSING": t("missing_date"),
    }
    precisao["precision_display"] = precisao["date_precision"].map(
        lambda valor: rotulos_precisao.get(valor, valor)
    )
    figura_evidencia = px.bar(
        evidencia.sort_values("occurrence_count"),
        x="occurrence_count",
        y="basis_of_record",
        orientation="h",
        labels={"occurrence_count": t("records"), "basis_of_record": ""},
        title=t("evidence_distribution"),
        color_discrete_sequence=["#4f772d"],
    )
    figura_precisao = px.bar(
        precisao,
        x="precision_display",
        y="record_count",
        labels={"precision_display": t("precision"), "record_count": t("records")},
        title=t("date_precision"),
        color_discrete_sequence=["#7c3f58"],
    )
    coluna_evidencia, coluna_precisao = st.columns(2)
    with coluna_evidencia:
        st.plotly_chart(
            layout_grafico(figura_evidencia, 420),
            width="stretch",
            config={"displayModeBar": False},
        )
    with coluna_precisao:
        st.plotly_chart(
            layout_grafico(figura_precisao, 420),
            width="stretch",
            config={"displayModeBar": False},
        )

    alertas_ocorrencia = frequencia_alertas(filtrados, "occurrence_issues").head(12)
    alertas_taxonomicos = frequencia_alertas(filtrados, "taxonomic_issues").head(12)
    coluna_ocorrencia, coluna_taxonomia = st.columns(2)
    with coluna_ocorrencia:
        figura = px.bar(
            alertas_ocorrencia.sort_values("record_count"),
            x="record_count",
            y="issue",
            orientation="h",
            labels={"record_count": t("records"), "issue": ""},
            title=t("occurrence_alerts"),
            color_discrete_sequence=["#2563eb"],
        )
        st.plotly_chart(
            layout_grafico(figura, 440),
            width="stretch",
            config={"displayModeBar": False},
        )
    with coluna_taxonomia:
        figura = px.bar(
            alertas_taxonomicos.sort_values("record_count"),
            x="record_count",
            y="issue",
            orientation="h",
            labels={"record_count": t("records"), "issue": ""},
            title=t("taxonomic_alerts"),
            color_discrete_sequence=["#c2413b"],
        )
        st.plotly_chart(
            layout_grafico(figura, 440),
            width="stretch",
            config={"displayModeBar": False},
        )
    st.html(f'<div class="quality-note">{t("gbif_alert_note")}</div>')

with secao_dados:
    busca = st.text_input(
        t("search_records"),
        placeholder=t("search_records_placeholder"),
    )
    tabela = filtrados.copy()
    if len(busca.strip()) > 200:
        st.warning(t("search_too_long"))
        tabela = tabela.iloc[0:0]
    elif busca.strip():
        termo = busca.strip()
        mascara_busca = (
            tabela["canonical_name"]
            .fillna("")
            .str.contains(termo, case=False, regex=False)
            | tabela["locality"].fillna("").str.contains(termo, case=False, regex=False)
            | tabela["state_normalized"]
            .fillna("")
            .str.contains(termo, case=False, regex=False)
        )
        tabela = tabela.loc[mascara_busca]
    coluna_origem_tabela = t("origin")
    coluna_unidade_tabela = t("unit")
    coluna_data_tabela = t("date")
    coluna_latitude = "Latitude"
    coluna_longitude = "Longitude"
    tabela_exibicao = tabela[
        [
            "gbif_id",
            "country_name",
            "canonical_name",
            "origin_status",
            "event_date",
            "state_normalized",
            "locality",
            "basis_of_record",
            "decimal_latitude",
            "decimal_longitude",
        ]
    ].rename(
        columns={
            "gbif_id": "GBIF ID",
            "country_name": t("country"),
            "canonical_name": t("species"),
            "origin_status": coluna_origem_tabela,
            "event_date": coluna_data_tabela,
            "state_normalized": coluna_unidade_tabela,
            "locality": t("locality"),
            "basis_of_record": t("type"),
            "decimal_latitude": coluna_latitude,
            "decimal_longitude": coluna_longitude,
        }
    )
    tabela_exibicao[coluna_origem_tabela] = tabela_exibicao[coluna_origem_tabela].map(
        ROTULOS_ORIGEM
    )
    tabela_exibicao[coluna_unidade_tabela] = tabela_exibicao[coluna_unidade_tabela].map(
        rotulo_estado
    )
    tabela_navegador = tabela_exibicao.head(LIMITE_RESULTADOS_SQL)
    st.caption(t("record_count", count=formatar_numero(len(tabela_exibicao))))
    if len(tabela_exibicao) > len(tabela_navegador):
        st.caption(
            t(
                "table_limited",
                shown=formatar_numero(len(tabela_navegador)),
            )
        )
    st.dataframe(
        tabela_navegador,
        hide_index=True,
        width="stretch",
        height=540,
        column_config={
            coluna_data_tabela: st.column_config.DatetimeColumn(
                format="DD/MM/YYYY HH:mm"
            ),
            coluna_latitude: st.column_config.NumberColumn(format="%.5f"),
            coluna_longitude: st.column_config.NumberColumn(format="%.5f"),
        },
    )
    st.download_button(
        t("download_csv"),
        data=tabela_exibicao.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{PROJECT_SLUG}_ocorrencias_filtradas.csv",
        mime="text/csv",
        icon=":material/download:",
    )

with st.expander(t("methodology_limitations")):
    st.markdown(t("methodology_text"))

st.caption(t("footer"))

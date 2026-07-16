import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.dashboard_data import (  # noqa: E402
    calcular_indicadores,
    carregar_dados_dashboard,
    distribuicao_origem,
    distribuicao_tipo,
    filtrar_ocorrencias,
    frequencia_alertas,
    indicadores_qualidade,
    ranking_especies,
    serie_temporal,
)
from src.filter_basin import ARQUIVO_LIMITE  # noqa: E402
from src.load import SCHEMA_PADRAO, validar_schema  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

st.set_page_config(
    page_title="Peixes da Bacia do Paraná",
    layout="wide",
    initial_sidebar_state="auto",
)

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
    "NATIVE": "Nativa",
    "INTRODUCED": "Introduzida",
    "CONFLICTING": "Conflitante",
    "UNKNOWN": "Desconhecida",
}
ROTULOS_ESTADO = {
    "Parana": "Paraná",
    "Sao Paulo": "São Paulo",
    "Goias": "Goiás",
    "Nao informado": "Não informado",
}


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
        [data-testid="stMetricValue"] { color: var(--ink); font-size: 1.6rem; }
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


@st.cache_data(ttl=300, show_spinner=False)
def obter_dados(schema: str):
    return carregar_dados_dashboard(os.getenv("DATABASE_URL"), schema)


@st.cache_data(show_spinner=False)
def obter_limite_geojson():
    if not ARQUIVO_LIMITE.exists():
        return None
    limite = gpd.read_file(ARQUIVO_LIMITE, engine="fiona").to_crs("EPSG:4326")
    limite["geometry"] = limite.geometry.simplify(0.01, preserve_topology=True)
    return limite.__geo_interface__


def formatar_numero(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def rotulo_estado(valor: str) -> str:
    return ROTULOS_ESTADO.get(valor, valor)


def layout_grafico(figura, altura: int = 390):
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


def criar_mapa(dados: pd.DataFrame):
    pontos = dados.dropna(subset=["decimal_latitude", "decimal_longitude"]).copy()
    if pontos.empty:
        return None
    pontos["point_color"] = pontos["origin_status"].map(CORES_ORIGEM)
    pontos["origin_display"] = pontos["origin_status"].map(ROTULOS_ORIGEM)
    pontos["state_display"] = pontos["state_normalized"].map(rotulo_estado)
    pontos["point_color"] = pontos["point_color"].apply(
        lambda cor: cor if isinstance(cor, list) else CORES_ORIGEM["UNKNOWN"]
    )
    camadas = []
    limite = obter_limite_geojson()
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
    camadas.append(
        pdk.Layer(
            "ScatterplotLayer",
            pontos,
            get_position="[decimal_longitude, decimal_latitude]",
            get_fill_color="point_color",
            get_radius=2600,
            radius_min_pixels=3,
            radius_max_pixels=11,
            stroked=True,
            get_line_color=[255, 255, 255, 130],
            line_width_min_pixels=0.4,
            opacity=0.75,
            pickable=True,
        )
    )
    zoom = 5.0 if len(pontos) >= 50 else 6.2
    vista = pdk.ViewState(
        latitude=float(pontos["decimal_latitude"].mean()),
        longitude=float(pontos["decimal_longitude"].mean()),
        zoom=zoom,
        pitch=0,
    )
    return pdk.Deck(
        layers=camadas,
        initial_view_state=vista,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={
            "html": "<b>{canonical_name}</b><br/>{origin_display} · {state_display}<br/>{event_year} · {basis_of_record}",
            "style": {"backgroundColor": "#17211d", "color": "white"},
        },
    )


aplicar_estilo()

schema = validar_schema(os.getenv("DB_SCHEMA", SCHEMA_PADRAO))
try:
    resultado = obter_dados(schema)
except (FileNotFoundError, ValueError) as erro:
    st.error(f"Dados indisponiveis: {erro}")
    st.stop()

dados = resultado.dados

with st.sidebar:
    st.header("Filtros")
    if st.button("Atualizar dados", icon=":material/refresh:", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    especies_disponiveis = sorted(dados["canonical_name"].dropna().unique())
    especies = st.multiselect(
        "Espécies",
        especies_disponiveis,
        placeholder="Todas as espécies",
    )
    origens_disponiveis = sorted(dados["origin_status"].dropna().unique())
    origens = st.multiselect(
        "Origem",
        origens_disponiveis,
        placeholder="Todas as classificações",
        format_func=lambda valor: ROTULOS_ORIGEM.get(valor, valor),
    )
    anos = dados["event_year"].dropna().astype(int)
    intervalo_anos = None
    if not anos.empty:
        limites_anos = (int(anos.min()), int(anos.max()))
        intervalo_anos = st.slider(
            "Período",
            min_value=limites_anos[0],
            max_value=limites_anos[1],
            value=limites_anos,
        )
    tipos_disponiveis = sorted(dados["basis_of_record"].dropna().unique())
    tipos = st.multiselect(
        "Tipo de registro",
        tipos_disponiveis,
        placeholder="Todos os tipos",
    )
    estados_disponiveis = sorted(dados["state_normalized"].dropna().unique())
    estados = st.multiselect(
        "Unidade administrativa",
        estados_disponiveis,
        placeholder="Todas as unidades",
        format_func=rotulo_estado,
    )
    st.divider()
    st.caption("GBIF · DHN250/IBGE · Catalogue of Life")

filtrados = filtrar_ocorrencias(
    dados,
    especies=especies,
    origens=origens,
    intervalo_anos=intervalo_anos,
    tipos=tipos,
    estados=estados,
)

st.title("Peixes da Bacia do Paraná")
st.html(
    f"""
    <div class="source-row">
      <span>Ocorrências publicadas na porção brasileira da Região Hidrográfica do Paraná</span>
      <span class="source-badge">Fonte ativa: {resultado.fonte}</span>
    </div>
    """
)
if resultado.aviso:
    st.warning(resultado.aviso)

indicadores = calcular_indicadores(filtrados)
colunas_metricas = st.columns(5)
metricas = [
    ("Ocorrências", formatar_numero(indicadores["occurrences"])),
    ("Espécies", formatar_numero(indicadores["species"])),
    ("Introduzidas", formatar_numero(indicadores["introduced_species"])),
    ("Unidades", formatar_numero(indicadores["states"])),
    ("Período", indicadores["period"]),
]
for coluna, (rotulo, valor) in zip(colunas_metricas, metricas, strict=True):
    coluna.metric(rotulo, valor)

if filtrados.empty:
    st.info("Nenhuma ocorrência corresponde aos filtros selecionados.")
    st.stop()

aba_visao, aba_distribuicao, aba_qualidade, aba_dados = st.tabs(
    ["Visão geral", "Distribuição", "Qualidade", "Dados"]
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
                "occurrence_count": "Ocorrências",
                "canonical_name": "",
                "origin_label": "Origem",
            },
            title="Espécies mais registradas",
        )
        figura.update_layout(legend_title_text="Origem")
        st.plotly_chart(
            layout_grafico(figura, 470),
            width="stretch",
            config={"displayModeBar": False},
        )
    with coluna_origem:
        figura = px.bar(
            origens_tabela,
            x="origin_label",
            y="species_count",
            color="origin_label",
            color_discrete_map={
                ROTULOS_ORIGEM[chave]: cor for chave, cor in CORES_PLOTLY.items()
            },
            labels={"origin_label": "Origem", "species_count": "Espécies"},
            title="Espécies por origem",
        )
        figura.update_layout(showlegend=False)
        st.plotly_chart(
            layout_grafico(figura, 470),
            width="stretch",
            config={"displayModeBar": False},
        )

    temporal = serie_temporal(filtrados)
    figura = px.line(
        temporal,
        x="period",
        y="occurrence_count",
        markers=True,
        labels={"period": "Período", "occurrence_count": "Ocorrências"},
        title="Registros ao longo do tempo",
    )
    figura.update_traces(line_color="#2563eb", marker_color="#d97706")
    st.plotly_chart(
        layout_grafico(figura, 360),
        width="stretch",
        config={"displayModeBar": False},
    )

with aba_distribuicao:
    mapa = criar_mapa(filtrados)
    if mapa:
        st.pydeck_chart(mapa, width="stretch", height=610)
    else:
        st.info("O recorte atual não possui coordenadas válidas.")

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
            labels={"occurrence_count": "Ocorrências", "basis_of_record": ""},
            title="Tipo de registro",
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
            labels={"occurrence_count": "Ocorrências", "state_display": ""},
            title="Unidade administrativa informada",
            color_discrete_sequence=["#4f772d"],
        )
        st.plotly_chart(
            layout_grafico(figura),
            width="stretch",
            config={"displayModeBar": False},
        )

with aba_qualidade:
    qualidade = indicadores_qualidade(filtrados)
    total = max(len(filtrados), 1)
    colunas_qualidade = st.columns(4)
    itens_qualidade = [
        ("Sem localidade", qualidade["missing_locality"]),
        ("Alerta taxonômico", qualidade["taxonomic_issue"]),
        ("Alerta de ocorrência", qualidade["occurrence_issue"]),
        ("Unidade inesperada", qualidade["unexpected_state"]),
    ]
    for coluna, (rotulo, valor) in zip(colunas_qualidade, itens_qualidade, strict=True):
        coluna.metric(rotulo, formatar_numero(valor), f"{100 * valor / total:.1f}%")

    alertas_ocorrencia = frequencia_alertas(filtrados, "occurrence_issues").head(12)
    alertas_taxonomicos = frequencia_alertas(filtrados, "taxonomic_issues").head(12)
    coluna_ocorrencia, coluna_taxonomia = st.columns(2)
    with coluna_ocorrencia:
        figura = px.bar(
            alertas_ocorrencia.sort_values("record_count"),
            x="record_count",
            y="issue",
            orientation="h",
            labels={"record_count": "Registros", "issue": ""},
            title="Alertas de ocorrência",
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
            labels={"record_count": "Registros", "issue": ""},
            title="Alertas taxonômicos",
            color_discrete_sequence=["#c2413b"],
        )
        st.plotly_chart(
            layout_grafico(figura, 440),
            width="stretch",
            config={"displayModeBar": False},
        )
    st.html(
        """
        <div class="quality-note">
        Alertas do GBIF registram interpretações e inconsistências potenciais. Eles não invalidam automaticamente uma ocorrência. Registros candidatos a duplicidade exigem revisão do evento de coleta antes de qualquer remoção.
        </div>
        """
    )

with aba_dados:
    busca = st.text_input(
        "Buscar nos registros",
        placeholder="Espécie, localidade ou unidade administrativa",
    )
    tabela = filtrados.copy()
    if busca.strip():
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
    tabela_exibicao = tabela[
        [
            "gbif_id",
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
            "canonical_name": "Espécie",
            "origin_status": "Origem",
            "event_date": "Data",
            "state_normalized": "Unidade",
            "locality": "Localidade",
            "basis_of_record": "Tipo",
            "decimal_latitude": "Latitude",
            "decimal_longitude": "Longitude",
        }
    )
    tabela_exibicao["Origem"] = tabela_exibicao["Origem"].map(ROTULOS_ORIGEM)
    tabela_exibicao["Unidade"] = tabela_exibicao["Unidade"].map(rotulo_estado)
    st.caption(f"{formatar_numero(len(tabela_exibicao))} registros")
    st.dataframe(
        tabela_exibicao,
        hide_index=True,
        width="stretch",
        height=540,
        column_config={
            "Data": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
            "Latitude": st.column_config.NumberColumn(format="%.5f"),
            "Longitude": st.column_config.NumberColumn(format="%.5f"),
        },
    )
    st.download_button(
        "Baixar CSV",
        data=tabela_exibicao.to_csv(index=False).encode("utf-8-sig"),
        file_name="ocorrencias_filtradas.csv",
        mime="text/csv",
        icon=":material/download:",
    )

with st.expander("Metodologia e limitações"):
    st.markdown(
        """
        Os pontos representam ocorrências publicadas no GBIF e filtradas pelo limite oficial da porção brasileira da Região Hidrográfica do Paraná. As contagens refletem coleta e publicação, não abundância biológica. A fonte atual é uma amostra de 5.000 registros do pré-filtro; comparações ecológicas exigem a base integral e controle do esforço amostral.
        """
    )

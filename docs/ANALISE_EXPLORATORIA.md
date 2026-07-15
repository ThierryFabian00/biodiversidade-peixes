# Análise exploratória

## Escopo

A Etapa 6 analisa a amostra multiespécies produzida pelas etapas anteriores. A execução atual contém 3.792 ocorrências dentro da porção brasileira da Região Hidrográfica do Paraná e 356 espécies aceitas.

O módulo `src.analysis` gera tabelas, gráficos, mapas, indicadores de qualidade e um relatório interpretativo em `data/analysis/`. O notebook `notebooks/01_analise_exploratoria.ipynb` reproduz a mesma execução.

## Resultados iniciais

- *Hypostomus ancistroides* possui a maior quantidade de registros: 153.
- O período observado vai de 2020 a 2026; 2022 concentra 1.282 registros (33,81%).
- Agosto é o mês mais representado, com 716 registros (18,88%).
- Espécimes preservados representam 2.878 registros (75,90%).
- Paraná e São Paulo concentram, respectivamente, 50,21% e 36,45% dos registros após a consolidação dos rótulos equivalentes.
- A grade de 1 grau possui 104 células que intersectam a bacia; 27 não têm ocorrências na amostra.

Essas contagens medem registros publicados e não abundância, riqueza real ou tamanho das populações.

## Qualidade dos dados

- Não existem IDs GBIF repetidos na tabela processada.
- 1.299 registros são candidatos a duplicidade por compartilharem espécie, coordenadas e data. Eles são apenas sinalizados, pois vários indivíduos ou lotes podem ter sido coletados no mesmo evento.
- 956 registros (25,21%) não informam localidade textual.
- 959 registros (25,29%) possuem algum alerta taxonômico do GBIF.
- Todos os registros possuem ao menos um alerta de interpretação de ocorrência. O mais comum, `CONTINENT_DERIVED_FROM_COORDINATES`, apenas informa que o continente foi derivado das coordenadas e não invalida sozinho o ponto.
- Existem rótulos administrativos incompatíveis com o recorte brasileiro, como Misiones e Alto Paraná. O filtro espacial usa as coordenadas e mantém esses textos como alerta de qualidade.

O campo de município não está disponível de forma consistente na tabela atual. Por isso, a agregação administrativa usa `stateProvince`, com correção de codificação e consolidação de abreviações conhecidas.

## Limitações e vieses

A consulta disponível tem 126.688 registros no pré-filtro, mas a API de busca forneceu uma amostra de 5.000. A análise não representa a base completa e o intervalo temporal recente observado pode refletir a composição e a ordem dessa amostra.

Áreas com mais pontos podem ter recebido mais coletas, projetos ou digitalização. Células vazias significam ausência de registros publicados na amostra, não ausência de peixes. Comparações ecológicas robustas exigem o download integral com DOI, controle do esforço amostral e avaliação dos protocolos de coleta.

## Artefatos gerados

- `ranking_especies.csv`
- `registros_por_ano.csv` e `registros_por_mes.csv`
- `registros_por_estado.csv` e `registros_por_tipo.csv`
- `alertas_ocorrencia.csv` e `alertas_taxonomicos.csv`
- `qualidade_dados.csv` e `duplicados_potenciais.csv`
- `grade_lacunas_espaciais.csv`
- gráficos temporais, taxonômicos e administrativos em PNG
- `mapa_ocorrencias.png` e `lacunas_espaciais.png`
- `relatorio_exploratorio.md` e `analise_metadata.json`

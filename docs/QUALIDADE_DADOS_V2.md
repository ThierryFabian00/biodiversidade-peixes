# Qualidade dos dados

## Objetivo

A Etapa 7 torna explícito o que foi recebido, descartado e aproveitado em cada
atualização e apresenta indicadores que ajudam a avaliar se um registro é
adequado para uma análise. Os alertas são sinais para revisão; não causam
remoção automática, exceto quando o registro não possui identificação válida no
nível de espécie ou está fora do recorte espacial solicitado.

## Funil da última carga

Cada atualização iniciada pelo dashboard registra em `data_imports`:

- registros recebidos do GBIF;
- registros salvos após normalização e recorte;
- registros descartados;
- rejeições por classificação ausente, identificação acima de espécie ou
  ausência de uma espécie aceita;
- percentual aproveitado, calculado como `salvos / recebidos * 100`.

A coluna `quality_stats_complete` evita apresentar como completas as cargas
legadas que não preservavam essas contagens. Uma nova atualização pelo GBIF
passa a registrar o funil integralmente.

## Indicadores

Os indicadores da aba **Qualidade** respeitam os filtros do dashboard:

| Indicador | Definição |
| --- | --- |
| Sem data | `event_date` não pôde ser interpretada |
| Data apenas mensal | `date_precision` é `MONTH` |
| Coordenada ausente ou inválida | latitude/longitude ausente ou fora dos intervalos geográficos válidos |
| Duplicidade potencial | mesma espécie, coordenadas e data em mais de um GBIF ID |
| Sem nível de espécie | rejeição taxonômica registrada no funil da carga |
| Problema indicado pelo GBIF | presença de ao menos um alerta taxonômico ou de ocorrência |
| Possivelmente fora do país | alerta `COUNTRY_COORDINATE_MISMATCH` do GBIF |
| Tipo de evidência | distribuição de `basis_of_record` |

Localidade ausente e unidade administrativa inesperada continuam disponíveis
como indicadores auxiliares. Duplicidades potenciais não são apagadas, pois
registros diferentes podem representar indivíduos ou lotes do mesmo evento.

## Limitações

Os alertas publicados pelo GBIF podem refletir normalizações legítimas. A
ausência de alerta também não garante correção taxonômica ou geográfica. A
qualidade deve ser avaliada em função da pergunta científica, da documentação
do conjunto de origem e do esforço amostral.

## Testes

Os testes cobrem precisão mensal, data ausente, coordenadas inválidas,
duplicidades potenciais, incompatibilidade país/coordenada, alertas do GBIF,
percentual aproveitado e persistência das contagens da importação.

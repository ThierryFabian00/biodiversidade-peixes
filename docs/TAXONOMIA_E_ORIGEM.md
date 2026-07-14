# Taxonomia e origem das espécies

## Escopo taxonômico

A coleta multiespécies usa a taxonomia Catalogue of Life eXtended Release disponibilizada pelo GBIF, identificada por `checklistKey=7ddf754f-d193-4cc9-b351-99906754a03b`.

Foram selecionados cinco grupos que, em conjunto, representam os principais grupos atuais de peixes sem incluir tetrápodes:

- Actinopterygii (`8VR36`);
- Elasmobranchii (`LB`);
- Dipneusti (`8V4VF`);
- Myxini (`6225G`);
- Petromyzonti (`8VJWX`).

Somente ocorrências cuja classificação no Catalogue of Life chega ao nível `SPECIES` entram na base final. Nomes sinônimos são ligados ao `acceptedUsage`; registros identificados somente no nível de gênero ou sem rank são preservados na tabela de problemas taxonômicos.

## Status de origem

O status `originStatus` não é inferido pela ausência de informação.

1. Espécies presentes na lista oficial de animais aquáticos introduzidos do Ministério da Agricultura e Pecuária recebem `INTRODUCED`.
2. Para as demais, valores explícitos de `establishmentMeans` publicados nos registros do GBIF podem produzir `NATIVE`, `INTRODUCED` ou `CONFLICTING`.
3. Sem evidência explícita, o valor permanece `UNKNOWN`.

Fonte oficial complementar: [MAPA, lista de espécies aquáticas introduzidas](https://www.gov.br/agricultura/pt-br/assuntos/sustentabilidade/recursos-geneticos/lista-de-especies-introduzidas/aquaticos), baseada na Instrução Normativa nº 16, de 4 de junho de 2019.

A lista do MAPA informa introdução no Brasil, não necessariamente o histórico específico de cada sub-bacia. Espécies brasileiras translocadas entre bacias ainda exigem uma referência regional especializada e permanecem sem classificação automática.

## Limite da amostra

O pré-filtro espacial contém mais de 100 mil ocorrências, limite máximo da API de busca do GBIF. A execução padrão coleta uma amostra de 5.000 registros e registra `isComplete=false` nos metadados. Uma base completa deve ser solicitada pelo GBIF Occurrence Download, com autenticação e DOI.

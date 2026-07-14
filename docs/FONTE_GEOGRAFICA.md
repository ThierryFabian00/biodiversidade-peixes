# Fonte geográfica

## Recorte adotado

A primeira delimitação do projeto corresponde à porção brasileira da Região Hidrográfica do Paraná. Essa decisão mantém coerência com a extração atual do GBIF, que usa o filtro `country=BR`.

O recorte não representa toda a bacia internacional do rio Paraná. Uma ampliação futura deverá incorporar territórios de Argentina, Paraguai e Bolívia a partir de uma fonte transfronteiriça compatível.

## Fonte

- Instituição: Instituto Brasileiro de Geografia e Estatística (IBGE).
- Produto: Divisão Hidrográfica Nacional DHN250.
- Versão: 2021.
- Camada: Macrorregiões Hidrográficas (`macro_RH`).
- Região selecionada: código `111`, nome `PARANÁ`.
- Escala: 1:250.000.
- Área informada na camada: aproximadamente 878.347 km².
- Arquivo: `macro_RH.zip`.
- Download: https://geoftp.ibge.gov.br/informacoes_ambientais/estudos_ambientais/bacias_e_divisoes_hidrograficas_do_brasil/2021/Divisao_Hidrografica_Nacional_DHN250/vetores/macro_RH.zip
- Documentação técnica: https://geoftp.ibge.gov.br/informacoes_ambientais/estudos_ambientais/bacias_e_divisoes_hidrograficas_do_brasil/2021/Divisao_Hidrografica_Nacional_DHN250/vetores/Documentacao_Tecnica_DHN250.pdf

## Licença e atribuição

O conjunto integra os dados abertos do IBGE, disponibilizados conforme a Política de Dados Abertos do Poder Executivo Federal. A reutilização deve atribuir a fonte ao IBGE. O diretório do produto não informa um identificador de licença padronizado, como SPDX ou Creative Commons; por isso o projeto não atribui uma licença mais específica sem confirmação da instituição.

Citação usada no projeto: `Fonte: IBGE, Divisão Hidrográfica Nacional DHN250, versão 2021.`

## Sistemas de coordenadas

A camada original usa SIRGAS 2000 (`EPSG:4674`), conforme a documentação técnica do IBGE. O arquivo derivado é convertido para WGS 84 (`EPSG:4326`), o mesmo sistema usado para interpretar as coordenadas de ocorrência do GBIF.

O filtro reprojeta o limite para o CRS dos pontos antes da operação espacial. A relação usada é `intersects`, de modo que registros exatamente sobre a linha do limite sejam preservados.

## Reprodução

```powershell
.\.venv\Scripts\python.exe src\prepare_boundary.py
.\.venv\Scripts\python.exe src\transform.py
.\.venv\Scripts\python.exe src\filter_basin.py
```

Os arquivos geográficos e os resultados processados são gerados localmente e permanecem fora do Git.

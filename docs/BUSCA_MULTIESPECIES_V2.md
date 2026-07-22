# Busca multiespécies por país

## Objetivo

A etapa 4 consulta ocorrências do grupo taxonômico de peixes no país escolhido,
mantém somente identificações no nível de espécie e produz um catálogo de
espécies distintas pela chave aceita do Catalogue of Life usada pelo GBIF.

## Consulta

O extrator envia ao endpoint `occurrence/search`:

- `country`: código ISO validado, como `BR` ou `CH`;
- `taxonKey`: chave do grupo configurado, inicialmente `Actinopterygii`;
- `checklistKey`: Catalogue of Life;
- `occurrenceStatus=PRESENT`;
- paginação de até 300 registros e teto configurável.

A consulta padrão considera o país inteiro. O argumento `--recorte-bacia`
adiciona o polígono da Bacia do Paraná e exige coordenadas.

Exemplo para a Suíça:

```powershell
python -m src.extract_fish `
  --pais CH `
  --grupo-taxonomico Actinopterygii `
  --saida data/raw/ocorrencias_peixes_ch.jsonl

python -m src.transform_fish `
  --entrada data/raw/ocorrencias_peixes_ch.jsonl `
  --sem-recorte-bacia `
  --ocorrencias data/processed/ocorrencias_peixes_ch.csv `
  --especies data/processed/especies_peixes_ch.csv `
  --problemas data/processed/problemas_taxonomicos_ch.csv
```

Para reproduzir o recorte brasileiro legado, use `--pais BR --recorte-bacia` no
extrator e mantenha o recorte padrão na transformação. Os nomes de arquivo do
exemplo (`ocorrencias_peixes_ch.csv` e `especies_peixes_ch.csv`) são reconhecidos
automaticamente pelo dashboard ao selecionar a Suíça.

## Normalização taxonômica

Cada ocorrência preserva:

- nome original publicado;
- nome científico interpretado;
- nome científico aceito;
- nome canônico padronizado;
- chave da espécie aceita;
- status taxonômico e indicador de sinônimo.

Registros acima do nível de espécie ou sem espécie aceita são separados como
problemas taxonômicos. A tabela de espécies agrupa pela chave aceita e mantém
as listas de nomes originais, interpretados, status e sinônimos associados.

## Seleção no dashboard

O seletor usa a chave aceita como valor interno e mostra o nome canônico. Ele
aceita uma ou várias espécies; todos os indicadores, gráficos, mapa e tabela
recebem o mesmo conjunto de chaves selecionadas.

## Limites

A busca síncrona é uma amostra controlada quando a quantidade disponível
ultrapassa o teto configurado. Nesse caso, a lista observada não deve ser
apresentada como inventário completo do país. Para cobertura integral e
resultados citáveis, deve ser usado um GBIF Occurrence Download, preferencialmente
no formato `SPECIES_LIST`, com autenticação e DOI.

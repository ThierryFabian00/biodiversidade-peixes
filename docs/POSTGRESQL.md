# Integração PostgreSQL multípaís

## Visão geral

A Etapa 5 usa um modelo relacional normalizado para armazenar vários países e
táxons sem repetir a taxonomia em cada ocorrência. A implementação usa Psycopg
3, transações, chaves primárias e estrangeiras, índices, `UPSERT` e auditoria
de cada importação.

```mermaid
erDiagram
    COUNTRIES ||--o{ OCCURRENCES : possui
    TAXA ||--o{ OCCURRENCES : identifica
    COUNTRIES ||--o{ DATA_IMPORTS : registra
    TAXA o|--o{ DATA_IMPORTS : delimita

    COUNTRIES {
        bigint id PK
        char iso_code UK
        text name
    }
    TAXA {
        text taxon_key PK
        text scientific_name
        text accepted_scientific_name
        text taxonomic_status
        text class_name
        text order_name
        text family
        text genus
        text species
    }
    OCCURRENCES {
        bigint gbif_key PK
        text taxon_key FK
        char country_code FK
        float latitude
        float longitude
        timestamptz event_date
        text event_date_original
        text date_precision
        smallint year
        smallint month
        text dataset_key
    }
    DATA_IMPORTS {
        bigint id PK
        char country_code FK
        text taxon_key FK
        timestamptz started_at
        timestamptz finished_at
        int records_received
        int records_saved
        text status
    }
```

O catálogo `taxa` mantém também campos analíticos já usados pelo dashboard,
como nome canônico, origem e categoria IUCN. `data_imports.taxon_key` fica
nulo quando uma única execução contém várias espécies.

## Criação e migração

O arquivo
[`sql/postgresql_multicountry.sql`](../sql/postgresql_multicountry.sql) é a
fonte do schema. O carregador substitui o marcador `__SCHEMA__` somente depois
de validar o nome configurado.

O script é idempotente. Em um banco legado ele:

1. renomeia `species` para `taxa`;
2. renomeia chaves e campos de `occurrences`;
3. adiciona `country_code` e usa `BR` para registros históricos;
4. cria `countries` e `data_imports`;
5. recria índices e views.

Faça backup antes de aplicar qualquer migração em um banco compartilhado.

## Configuração

O projeto lê `DATABASE_URL` e `DB_SCHEMA` de `.env`. Para um PostgreSQL
local:

```powershell
Copy-Item .env.example .env
docker compose up -d db
docker compose ps
```

Ajuste a senha e a URL no arquivo local. O schema padrão é `biodiversity`.

## Validação e carga

O `dry-run` valida países, táxons, coordenadas, chaves GBIF duplicadas e
referências sem abrir conexão:

```powershell
python -m src.load --dry-run
```

A carga cria ou migra a estrutura e executa os upserts em lotes:

```powershell
python -m src.load
python -m src.load --tamanho-lote 1000

python -m src.load `
  --especies data/processed/especies_peixes_ch.csv `
  --ocorrencias data/processed/ocorrencias_peixes_ch.csv
```

`countries.iso_code`, `taxa.taxon_key` e `occurrences.gbif_key` impedem
duplicidades. Cada execução concluída acrescenta uma linha em `data_imports`
por país, com horário inicial/final, checksum, arquivos e contagens recebidas,
salvas, descartadas e rejeitadas por identificação taxonômica.
`quality_stats_complete` distingue cargas novas, com funil completo, de
importações legadas que não preservavam todas essas contagens.

## Consultas

```powershell
python -m src.query_db --consulta resumo
python -m src.query_db --consulta ranking --limite 20
python -m src.query_db --consulta anos
python -m src.query_db --consulta meses
python -m src.query_db --consulta origens
python -m src.query_db --consulta especie --termo "Astyanax lacustris" --limite 20
```

Consultas equivalentes estão em
[`sql/analysis_queries.sql`](../sql/analysis_queries.sql). As views mantidas
são `vw_species_ranking`, `vw_occurrences_by_year` e
`vw_occurrence_details`.

## Integridade e desempenho

- ocorrências só aceitam país e táxon existentes;
- `gbif_key` é único e duplicidades no mesmo arquivo também são rejeitadas;
- latitude, longitude, ano, mês, origem e contagens têm restrições;
- índices cobrem país, táxon, ano e a combinação dos três;
- inserções repetidas atualizam países, táxons e ocorrências;
- a carga roda dentro da transação administrada pelo Psycopg.

## Teste de integração

Os testes unitários não exigem banco. Para executar o teste reversível real:

```powershell
$env:TEST_DATABASE_URL="postgresql://usuario:senha@localhost:5432/biodiversidade_peixes_test"
python -m unittest tests.test_load -v
```

O teste usa o schema `biodiversity_test` e executa `rollback` ao final.

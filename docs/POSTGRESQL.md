# Integração PostgreSQL

## Visão geral

A Etapa 7 transforma as tabelas CSV processadas em um modelo relacional. A implementação usa Psycopg 3, transações, chaves primárias e estrangeiras, restrições de domínio, índices, `UPSERT`, auditoria de cargas e views analíticas.

```mermaid
erDiagram
    SPECIES ||--o{ OCCURRENCES : possui
    SPECIES {
        text species_key PK
        text canonical_name
        text family
        text origin_status
        int source_occurrence_count
    }
    OCCURRENCES {
        bigint gbif_id PK
        text species_key FK
        timestamptz event_date
        float decimal_latitude
        float decimal_longitude
        text basis_of_record
    }
    LOAD_RUNS {
        bigint load_id PK
        timestamptz loaded_at
        char source_checksum
        int species_rows
        int occurrence_rows
    }
```

## Configuração

O projeto lê `DATABASE_URL` e `DB_SCHEMA` do arquivo `.env`. Esse arquivo é ignorado pelo Git e não deve ser publicado.

```powershell
Copy-Item .env.example .env
```

Substitua `change-me` por uma senha local tanto em `POSTGRES_PASSWORD` quanto em `DATABASE_URL`.

Quando Docker estiver disponível, o serviço definido em `compose.yaml` pode iniciar o PostgreSQL:

```powershell
docker compose up -d db
docker compose ps
```

Também é possível usar uma instalação existente e ajustar apenas `DATABASE_URL`. O schema padrão é `biodiversity`.

## Validação e carga

O `dry-run` lê os CSVs, valida colunas obrigatórias, tipos, coordenadas e referências entre ocorrências e espécies sem abrir uma conexão:

```powershell
python -m src.load --dry-run
```

A carga real cria a estrutura e processa os dados em lotes de 500:

```powershell
python -m src.load
python -m src.load --tamanho-lote 1000
```

Espécies usam `species_key` como chave primária e ocorrências usam `gbif_id`. Em caso de conflito, os campos são atualizados. Cada execução concluída adiciona uma linha a `load_runs` com caminhos, checksum SHA-256 e quantidades processadas.

## Consultas

O módulo de consulta retorna JSON e nunca imprime a URL de conexão:

```powershell
python -m src.query_db --consulta resumo
python -m src.query_db --consulta ranking --limite 20
python -m src.query_db --consulta anos
python -m src.query_db --consulta meses
python -m src.query_db --consulta origens
python -m src.query_db --consulta especie --termo "Astyanax lacustris" --limite 20
```

Consultas SQL equivalentes estão em `sql/analysis_queries.sql`. As views disponíveis são:

- `biodiversity.vw_species_ranking`;
- `biodiversity.vw_occurrences_by_year`;
- `biodiversity.vw_occurrence_details`.

## Integridade e desempenho

- A chave estrangeira impede ocorrências sem espécie correspondente.
- Latitude, longitude, ano, mês, origem e contagens possuem restrições `CHECK`.
- Exclusão de espécie referenciada é bloqueada por `ON DELETE RESTRICT`.
- Índices atendem consultas por espécie, ano/mês, estado, tipo de registro e coordenadas.
- Datas são armazenadas como `TIMESTAMPTZ`; valores ausentes são convertidos para `NULL`.
- A carga inteira usa uma transação: uma falha não deixa apenas parte dos dados atualizada.

## Teste de integração

Os testes unitários não exigem banco. Para executar também o teste reversível contra um servidor real, defina uma URL separada:

```powershell
$env:TEST_DATABASE_URL="postgresql://usuario:senha@localhost:5432/biodiversity_test"
python -m unittest tests.test_load -v
```

O teste cria objetos no schema `biodiversity_test` dentro de uma transação e executa `rollback` ao final.

## Validação realizada

Em 15 de julho de 2026, a carga foi validada em PostgreSQL 18 no banco `biodiversidade_peixes`:

- 356 espécies carregadas;
- 3.792 ocorrências carregadas;
- três tabelas e três views criadas;
- zero IDs GBIF duplicados;
- zero referências órfãs;
- segunda execução concluída sem aumentar as contagens, confirmando a idempotência;
- teste de integração real aprovado com rollback.

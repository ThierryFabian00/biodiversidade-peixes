# Dashboard Streamlit

## Visão geral

A Etapa 8 disponibiliza uma interface interativa para explorar as ocorrências de peixes da porção brasileira da Região Hidrográfica do Paraná. O dashboard consulta o schema PostgreSQL `biodiversity` e usa os CSVs processados como fallback quando a conexão não está disponível.

## Execução

Instale as dependências e inicie o servidor:

```powershell
pip install -r requirements.txt
streamlit run app/app.py
```

Por padrão, a aplicação fica disponível em `http://localhost:8501`.

## Componentes

### Filtros

- espécie;
- classificação de origem;
- intervalo anual;
- tipo de registro;
- unidade administrativa informada.

Todos os indicadores e elementos visuais usam simultaneamente o mesmo recorte.

### Visão geral

- quantidade de ocorrências;
- espécies distintas;
- espécies introduzidas;
- unidades administrativas;
- período observado;
- ranking das espécies;
- distribuição das espécies por origem;
- série temporal mensal.

### Distribuição

O mapa usa PyDeck com o limite oficial simplificado apenas para renderização. Os pontos mantêm as coordenadas originais e são coloridos por origem. A aba também compara tipos de registro e unidades administrativas.

### Qualidade

A aba apresenta o funil da última carga, o percentual aproveitado, registros sem
identificação válida no nível de espécie, datas ausentes ou apenas mensais,
coordenadas ausentes ou inválidas, duplicidades potenciais, alertas do GBIF e
registros potencialmente fora do país. Também detalha a distribuição por tipo
de evidência e as frequências dos códigos de alerta.

### Dados

A tabela permite buscar por espécie, localidade ou unidade administrativa e exportar o recorte atual em CSV.

## Fonte de dados

A aplicação procura `DATABASE_URL` e `DB_SCHEMA` no ambiente ou no arquivo `.env`. Se o PostgreSQL falhar, tenta carregar:

- `data/processed/ocorrencias_peixes_bacia_parana.csv`;
- `data/processed/especies_bacia_parana.csv`.

A interface informa qual fonte está ativa e nunca exibe a URL de conexão.

## Publicação

Em uma hospedagem Streamlit, configure `DATABASE_URL` e `DB_SCHEMA` como secrets ou variáveis de ambiente. O banco precisa aceitar conexões da hospedagem. Os CSVs processados não são versionados e, portanto, não devem ser considerados fonte de produção sem uma etapa explícita de publicação dos dados.

## Validação

O dashboard foi validado com os 3.792 registros e 356 espécies do PostgreSQL:

- renderização sem exceções pelo framework de testes do Streamlit;
- filtros combinados testados com dados sintéticos;
- filtro de introduzidas validado com 131 ocorrências e 6 espécies;
- busca por *Oreochromis niloticus* validada com 58 ocorrências;
- mapa carregado com limite e pontos;
- layout desktop em 1440 px;
- layout mobile em 390 px, sem rolagem horizontal e com filtros inicialmente recolhidos.

As contagens representam ocorrências publicadas, não abundância biológica. A amostra atual também não substitui o download integral do GBIF com DOI.

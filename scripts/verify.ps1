$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Ambiente .venv não encontrado. Instale requirements-dev.txt."
}

& $python -m ruff check src app tests
& $python -m ruff format --check src app tests
& $python -m unittest discover -s tests -v
& $python -m pip check

if (Test-Path "data\processed\ocorrencias_peixes_bacia_parana.csv") {
    & $python -m src.load --dry-run
}

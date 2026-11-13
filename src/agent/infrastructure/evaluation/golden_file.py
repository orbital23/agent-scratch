from pathlib import Path

from pydantic import ValidationError

from agent.domain.evaluation import GoldenCase


def golden_files(directory: Path, domain: str) -> list[Path]:
    """El golden set del dominio: primero el base de evals.zip y después el caso de cada participante."""
    base = directory / f"{domain}.jsonl"
    if not base.exists():
        raise FileNotFoundError(f"falta {base}: descarga evals.zip de la plataforma (sesión 5, paso 1)")
    return [base, *sorted(directory.glob(f"{domain}.AIE_*.jsonl"))]


def read_golden(path: Path) -> list[GoldenCase]:
    """Lee el golden set: un caso por línea, en JSON. Un caso mal escrito dice en qué línea está."""
    cases = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(GoldenCase.model_validate_json(line))
        except ValidationError as error:
            raise ValueError(f"{path.name}, línea {number}: {error}") from error
    return cases
from collections import Counter

import pytest

from agent.infrastructure.config.settings import ROOT
from agent.infrastructure.evaluation.golden_file import golden_files, read_golden

GOLDEN = ROOT / "evals" / "golden"
DOMAINS = ["fraud", "fees", "cards", "loans", "support"]
CASES_BY_TYPE = {"answerable": 18, "follow_up": 3, "expired": 3, "noise": 2, "out_of_scope": 2, "personal_data": 2}


@pytest.mark.parametrize("domain", DOMAINS)
def test_every_domain_has_a_valid_golden_set(domain):
    base = GOLDEN / f"{domain}.jsonl"
    if not base.exists():
        pytest.skip("descarga evals.zip de la plataforma (sesión 5, paso 1)")
    cases = read_golden(base)

    assert Counter(case.type for case in cases) == CASES_BY_TYPE
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.id.startswith(f"{domain}-") for case in cases)


def test_each_participant_case_is_valid_and_has_its_own_id():
    for path in GOLDEN.glob("*.AIE_*.jsonl"):
        domain = path.name.split(".")[0]
        cases = read_golden(path)
        others = [other for other in [GOLDEN / f"{domain}.jsonl", *GOLDEN.glob(f"{domain}.AIE_*.jsonl")]
                  if other != path and other.exists()]
        taken = {case.id for other in others for case in read_golden(other)}

        assert cases, f"{path.name} está vacío"
        assert all(case.id.startswith(f"{domain}-") for case in cases), path.name
        assert not taken & {case.id for case in cases}, f"{path.name} repite un id"


def test_the_eval_reads_the_base_and_then_each_participant(tmp_path):
    for name in ["fraud.jsonl", "fraud.AIE_22CD.jsonl", "fraud.AIE_17AB.jsonl", "fees.AIE_17AB.jsonl"]:
        (tmp_path / name).write_text("", encoding="utf-8")

    assert [path.name for path in golden_files(tmp_path, "fraud")] == [
        "fraud.jsonl", "fraud.AIE_17AB.jsonl", "fraud.AIE_22CD.jsonl"]
    with pytest.raises(FileNotFoundError, match="evals.zip"):
        golden_files(tmp_path, "loans")
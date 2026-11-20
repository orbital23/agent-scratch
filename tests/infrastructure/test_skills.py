import json
from pathlib import Path

import pytest

from agent.infrastructure.skills.loader import SKILLS_DIR, load_skill

CONTRACT = json.loads((Path(__file__).parents[2] / "dev" / "mcp" / "contract.json").read_text(encoding="utf-8"))
DOMAINS = sorted(path.stem for path in SKILLS_DIR.glob("*.md"))


def test_there_is_one_skill_per_domain():
    assert DOMAINS == ["cards", "fees", "fraud", "loans", "support"]


@pytest.mark.parametrize("domain", DOMAINS)
def test_skill_only_lists_tools_its_domain_can_see(domain):
    skill = load_skill(domain)
    domain_tools = {tool["name"] for tool in CONTRACT if domain in tool["domains"]}
    assert skill.name == domain
    assert set(skill.tools) == domain_tools  # ni una tool de otro dominio, ni una del dominio olvidada
    assert 1 <= skill.max_tool_rounds <= 5
    assert "Terminas cuando" in skill.instructions  # criterio de terminación escrito, no solo el tope de vueltas


def test_unknown_domain_says_which_exist():
    with pytest.raises(ValueError, match="cards"):
        load_skill("mortgages")
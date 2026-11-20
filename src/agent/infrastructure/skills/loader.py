from pathlib import Path

from agent.domain.models import Skill

SKILLS_DIR = Path(__file__).parent


def load_skill(domain: str) -> Skill:
    """La skill del dominio: un .md con un encabezado (tools y max_tool_rounds) entre líneas --- y las instrucciones."""
    path = SKILLS_DIR / f"{domain}.md"
    if not path.is_file():
        available = sorted(skill.stem for skill in SKILLS_DIR.glob("*.md"))
        raise ValueError(f"No hay skill para DOMAIN '{domain}'. Disponibles: {available}")
    _, header, instructions = path.read_text(encoding="utf-8").split("---\n", 2)
    fields = dict(line.split(":", 1) for line in header.strip().splitlines())
    return Skill(
        name=domain,
        instructions=instructions.strip(),
        tools=[tool.strip() for tool in fields["tools"].split(",")],
        max_tool_rounds=int(fields["max_tool_rounds"]),
    )
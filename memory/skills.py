import json
from pathlib import Path

SKILLS_PATH = Path("skills.json")


def _load() -> dict:
    if SKILLS_PATH.exists():
        try:
            return json.loads(SKILLS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(skills: dict) -> None:
    SKILLS_PATH.write_text(json.dumps(skills, indent=2), encoding="utf-8")


def save_skill(name: str, steps: list[dict]) -> None:
    skills = _load()
    skills[name.strip().lower()] = steps
    _save(skills)


def get_skill(name: str) -> list[dict] | None:
    return _load().get(name.strip().lower())


def list_skills() -> list[str]:
    return list(_load().keys())
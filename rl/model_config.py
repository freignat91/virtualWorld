"""Selection publique des modeles RL, sans dependance ML."""

import re
from typing import Any, Dict, Tuple


def parse_model_spec(specification: str) -> Tuple[str, str]:
    """Accepte un run simple et un checkpoint optionnel, jamais un chemin."""
    if not isinstance(specification, str) or not re.fullmatch(
        r"[A-Za-z0-9_-][A-Za-z0-9_.-]*(?::[A-Za-z0-9_-][A-Za-z0-9_.-]*)?",
        specification,
    ):
        raise ValueError("identifiant de modele RL invalide")
    run_name, _, checkpoint = specification.partition(":")
    return run_name, checkpoint


def public_bot_models(config: Dict[str, Any]) -> Dict[str, str]:
    """Ne publie que les deux selections validees, sans autre configuration."""
    models = {}
    for key, default in (
        ("bot_rl_sub", "aisub_v15_scripted"),
        ("bot_rl_destroyer", "aidest_v3_scripted"),
    ):
        value = config.get(key, default)
        try:
            parse_model_spec(value)
        except ValueError as exc:
            raise ValueError(f"{key}: {exc}") from exc
        models[key] = value
    return models

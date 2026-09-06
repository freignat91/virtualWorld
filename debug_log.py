"""Logging par catégorie activable/désactivable à chaud.

Usage :
    from debug_log import dlog, enable_category, disable_category, toggle_category

    dlog("grenades", f"gid={gid} exploded at depth={d}m")

Catégories actives par défaut : aucune.
Activation à chaud via cheat client 'debug <cat>' (toggle).
"""

import logging

_logger = logging.getLogger("debug")

_enabled: set = set()
MAX_CATEGORIES = 64
MAX_CATEGORY_LENGTH = 64


def enable_category(cat: str) -> None:
    if not cat or len(cat) > MAX_CATEGORY_LENGTH:
        return
    if cat not in _enabled and len(_enabled) >= MAX_CATEGORIES:
        return
    _enabled.add(cat)


def disable_category(cat: str) -> None:
    _enabled.discard(cat)


def toggle_category(cat: str) -> bool:
    """Toggle une catégorie. Retourne True si activée après toggle."""
    if cat in _enabled:
        _enabled.discard(cat)
        return False
    if not cat or len(cat) > MAX_CATEGORY_LENGTH or len(_enabled) >= MAX_CATEGORIES:
        return False
    _enabled.add(cat)
    return True


def is_enabled(cat: str) -> bool:
    return cat in _enabled


def enabled_categories() -> list:
    return sorted(_enabled)


def dlog(cat: str, msg: str) -> None:
    """Log un message si la catégorie est active."""
    if cat in _enabled:
        _logger.info(f"[{cat}] {msg}")

# -*- coding: utf-8 -*-
"""Legacy bridge for the system.open_app adapter (Task 5).

The legacy skills module (`skills/system.py`) imports Windows-only
dependencies (psutil, pyautogui, winreg) at module import time. To keep
the core importable and testable on non-Windows machines WITHOUT copying
legacy code into core, we expose a lazy accessor that returns None when
the legacy stack is unavailable in the current environment.

This module owns NO app list and NO find logic — those live exclusively
in `config.APPS` and `SystemSkills.find_app` / `find_app_fuzzy`.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

_system_skills: Optional[Any] = None
_resolved = False


def get_system_skills() -> Optional[Any]:
    """Return a shared SystemSkills instance or None if unavailable here."""
    global _system_skills, _resolved
    if _resolved:
        return _system_skills
    _resolved = True
    try:
        from skills.system import SystemSkills  # noqa: WPS433 (lazy by design)

        class _SilentSpeech:
            def speak(self, text):  # legacy open_app calls speech.speak
                pass

        _system_skills = SystemSkills(speech=_SilentSpeech())
    except Exception:
        # psutil/pyautogui/winreg missing (non-Windows dev environment)
        _system_skills = None
    return _system_skills


def resolve_app(app_name: str) -> Tuple[Optional[str], bool]:
    """Resolve an app name through the LEGACY lookup chain.

    Returns (target, legacy_available):
      * (path_or_exe, True)  — found via config.APPS / find_app(_fuzzy);
      * (None, True)         — legacy stack works, app genuinely unknown;
      * (None, False)        — legacy stack unavailable in this OS env
                               (honest signal, never treated as success).
    """
    skills = get_system_skills()
    if skills is None:
        return None, False

    name = (app_name or "").strip().lower()
    if not name:
        return None, True

    # 1) canonical legacy mapping — config.APPS lives in legacy config,
    #    imported by skills.system; use it THROUGH the legacy module so
    #    there is exactly one source of the app dictionary.
    try:
        from skills.system import APPS as _LEGACY_APPS  # same dict object

        for key, exe in _LEGACY_APPS.items():
            if name == key or name in key or key in name:
                resolved = skills.find_app(exe) or exe
                return resolved, True
    except Exception:
        pass

    # 2) legacy fuzzy finder (Start menu / registry / common dirs)
    try:
        found = skills.find_app_fuzzy(name)
        if found:
            return found, True
    except Exception:
        pass

    # 3) plain executable lookup on PATH etc.
    try:
        found = skills.find_app(name if name.endswith(".exe") else f"{name}.exe")
        if found:
            return found, True
    except Exception:
        pass

    return None, True

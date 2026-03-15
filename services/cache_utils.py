"""
cache_utils.py - v1.0.0
Streamlit cache helpers with safe fallback for non-Streamlit environments.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

try:
    import streamlit as st  # type: ignore
    HAS_STREAMLIT = True
except ImportError:
    st = None  # type: ignore
    HAS_STREAMLIT = False


F = TypeVar("F", bound=Callable[..., Any])


def cache_data(ttl: int) -> Callable[[F], F]:
    """Wrap st.cache_data and fall back to a no-op decorator outside Streamlit."""
    if HAS_STREAMLIT and hasattr(st, "cache_data"):
        return st.cache_data(ttl=ttl)  # type: ignore[attr-defined]

    def decorator(func: F) -> F:
        setattr(func, "clear", lambda: None)
        return func

    return decorator


def clear_cached_functions(*functions: Callable[..., Any]) -> None:
    """Safely clear cached wrappers if the target exposes a .clear() method."""
    for function in functions:
        clear = getattr(function, "clear", None)
        if callable(clear):
            clear()


def get_cache_scope(service: Any) -> tuple[str, bool]:
    """Include user/session scope in cache keys to avoid cross-user leakage."""
    user_id_getter = getattr(service, "_get_current_user_id", None)
    dev_mode_getter = getattr(service, "is_dev_mode", None)

    user_id = user_id_getter() if callable(user_id_getter) else None
    dev_mode = dev_mode_getter() if callable(dev_mode_getter) else False

    return (user_id or "", bool(dev_mode))

"""
Cache helper tests - v1.0.0
Validate cache utility helpers without requiring a database.
"""

import importlib.util
from pathlib import Path
import unittest


_MODULE_PATH = Path(__file__).resolve().parents[1] / "services" / "cache_utils.py"
_SPEC = importlib.util.spec_from_file_location("cache_utils_under_test", _MODULE_PATH)
_CACHE_UTILS = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_CACHE_UTILS)

cache_data = _CACHE_UTILS.cache_data
clear_cached_functions = _CACHE_UTILS.clear_cached_functions
get_cache_scope = _CACHE_UTILS.get_cache_scope


class _FakeService:
    def __init__(self, user_id: str | None, dev_mode: bool):
        self._user_id = user_id
        self._dev_mode = dev_mode

    def _get_current_user_id(self):
        return self._user_id

    def is_dev_mode(self):
        return self._dev_mode


class TestCacheUtils(unittest.TestCase):
    def test_cache_decorator_exposes_clear(self):
        @cache_data(ttl=60)
        def sample(value: int) -> int:
            return value * 2

        self.assertEqual(sample(3), 6)
        self.assertTrue(callable(getattr(sample, "clear", None)))
        clear_cached_functions(sample)
        self.assertEqual(sample(4), 8)

    def test_get_cache_scope_includes_user_context(self):
        service = _FakeService(user_id="user-123", dev_mode=False)
        self.assertEqual(get_cache_scope(service), ("user-123", False))

    def test_get_cache_scope_defaults_empty_user(self):
        service = _FakeService(user_id=None, dev_mode=True)
        self.assertEqual(get_cache_scope(service), ("", True))


if __name__ == "__main__":
    unittest.main()

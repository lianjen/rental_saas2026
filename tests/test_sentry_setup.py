import logging
import unittest
from unittest.mock import Mock

from utils.sentry_setup import init_sentry


class FakeLoggingIntegration:
    def __init__(self, level, event_level):
        self.level = level
        self.event_level = event_level


class TestSentrySetup(unittest.TestCase):
    def test_skip_when_dsn_missing(self):
        logger = Mock()

        ok = init_sentry(
            {"environment": "test", "version": "v0"},
            lambda key, default=None: default,
            logger,
        )

        self.assertFalse(ok)
        logger.debug.assert_called_once()

    def test_initialize_sentry_when_dsn_exists(self):
        logger = Mock()
        captured = {}

        class FakeSentrySDK:
            @staticmethod
            def init(**kwargs):
                captured.update(kwargs)

        ok = init_sentry(
            {"environment": "production", "version": "v15.4"},
            lambda key, default=None: "https://example@sentry.invalid/1"
            if key == "SENTRY_DSN"
            else default,
            logger,
            sdk_loader=lambda: (FakeSentrySDK, FakeLoggingIntegration),
        )

        self.assertTrue(ok)
        self.assertEqual(captured["dsn"], "https://example@sentry.invalid/1")
        self.assertEqual(captured["environment"], "production")
        self.assertEqual(captured["release"], "v15.4")
        self.assertEqual(captured["traces_sample_rate"], 0.1)
        self.assertFalse(captured["send_default_pii"])
        integration = captured["integrations"][0]
        self.assertIsInstance(integration, FakeLoggingIntegration)
        self.assertEqual(integration.level, logging.WARNING)
        self.assertEqual(integration.event_level, logging.ERROR)
        logger.info.assert_called_once()

    def test_return_false_when_sdk_init_raises(self):
        logger = Mock()

        def failing_loader():
            raise RuntimeError("sdk import failed")

        ok = init_sentry(
            {"environment": "test", "version": "v0"},
            lambda key, default=None: "https://example@sentry.invalid/1",
            logger,
            sdk_loader=failing_loader,
        )

        self.assertFalse(ok)
        logger.error.assert_called_once()

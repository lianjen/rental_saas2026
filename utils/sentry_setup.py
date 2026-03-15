"""
Sentry setup helpers - v1.0.0
[NEW] Optional Sentry bootstrap for the Streamlit entrypoint.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional, Tuple


EnvGetter = Callable[[str, Optional[str]], Optional[str]]
SDKLoader = Callable[[], Tuple[Any, Any]]


def _load_sentry_sdk() -> Tuple[Any, Any]:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    return sentry_sdk, LoggingIntegration


def init_sentry(
    app_config: Mapping[str, Any],
    get_env: EnvGetter,
    logger: logging.Logger,
    sdk_loader: SDKLoader = _load_sentry_sdk,
) -> bool:
    """Initialize Sentry when a DSN is configured."""
    sentry_dsn = get_env("SENTRY_DSN", "")
    if not sentry_dsn:
        logger.debug("SENTRY_DSN 未設定，略過 Sentry 初始化")
        return False

    try:
        sentry_sdk, logging_integration_cls = sdk_loader()
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                logging_integration_cls(
                    level=logging.WARNING,
                    event_level=logging.ERROR,
                )
            ],
            traces_sample_rate=0.1,
            environment=str(app_config.get("environment", "production")),
            release=str(app_config.get("version", "unknown")),
            send_default_pii=False,
        )
        logger.info("✅ Sentry 初始化成功")
        return True
    except Exception as exc:
        logger.error(f"❌ Sentry 初始化失敗: {exc}")
        return False

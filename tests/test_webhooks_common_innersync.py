from unittest.mock import patch

import config

from webhooks.common import get_discord_link_webhook_secret


def test_get_discord_link_webhook_secret_prefers_dedicated():
    with patch.object(config, "DISCORD_LINK_WEBHOOK_SECRET", "dedicated", create=True):
        with patch.object(config, "APP_REFLECTIONS_WEBHOOK_SECRET", "other", create=True):
            assert get_discord_link_webhook_secret() == "dedicated"


def test_get_discord_link_webhook_secret_fallback_chain():
    with patch.object(config, "DISCORD_LINK_WEBHOOK_SECRET", None, create=True):
        with patch.object(config, "APP_REFLECTIONS_WEBHOOK_SECRET", "app", create=True):
            with patch.object(config, "WEBHOOK_SECRET", None, create=True):
                with patch.object(config, "SUPABASE_WEBHOOK_SECRET", None, create=True):
                    assert get_discord_link_webhook_secret() == "app"

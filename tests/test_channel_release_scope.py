from app.core.config import settings
from app.services.channel_attribution_service import ChannelAttributionService
from app.services.channel_import_service import ChannelImportService
from app.services.channel_post_button_service import ChannelPostButtonService
from app.services.channel_storefront_service import ChannelStorefrontService


def _assert_scope(shop_id: int, expected: bool) -> None:
    assert ChannelImportService.enabled_for_shop(shop_id) is expected
    assert ChannelPostButtonService.enabled_for_shop(shop_id) is expected
    assert ChannelStorefrontService.enabled_for_shop(shop_id) is expected
    assert ChannelAttributionService.enabled_for_shop(shop_id) is expected


def test_channel_release_scope_can_be_opened_for_all_shops(monkeypatch):
    monkeypatch.setattr(settings, "channel_import_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_attribution_enabled", True)
    monkeypatch.setattr(settings, "channel_import_pilot_shop_id", None)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", None)
    monkeypatch.setattr(settings, "channel_attribution_pilot_shop_id", None)

    _assert_scope(1, True)
    _assert_scope(999, True)


def test_channel_release_scope_can_be_rolled_back_to_one_shop(monkeypatch):
    monkeypatch.setattr(settings, "channel_import_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_attribution_enabled", True)
    monkeypatch.setattr(settings, "channel_import_pilot_shop_id", 17)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", 17)
    monkeypatch.setattr(settings, "channel_attribution_pilot_shop_id", 17)

    _assert_scope(17, True)
    _assert_scope(18, False)

from app.core.enums import OrderStatus
from app.utils.order_status import (
    STATUS_LABELS,
    STATUS_NOTIFICATIONS,
    STATUS_ORDER,
    NEXT_STATUS,
)


class TestOrderStatusEnum:

    def test_values_are_strings(self):
        assert OrderStatus.NEW == "new"
        assert OrderStatus.CONFIRMED == "confirmed"
        assert OrderStatus.PAID == "paid"
        assert OrderStatus.SHIPPED == "shipped"
        assert OrderStatus.DONE == "done"
        assert OrderStatus.CANCELLED == "cancelled"

    def test_str_returns_value(self):
        assert str(OrderStatus.NEW) == "new"
        assert str(OrderStatus.CANCELLED) == "cancelled"

    def test_from_string(self):
        assert OrderStatus("paid") is OrderStatus.PAID

    def test_hashable_as_string(self):
        d = {OrderStatus.NEW: "label"}
        assert d["new"] == "label"

    def test_in_tuple_comparison(self):
        assert "paid" in (OrderStatus.PAID, OrderStatus.DONE)
        assert "cancelled" not in (OrderStatus.PAID, OrderStatus.DONE)

    def test_all_statuses_in_labels(self):
        for status in OrderStatus:
            assert status in STATUS_LABELS

    def test_notifications_cover_active_statuses(self):
        notification_keys = set(STATUS_NOTIFICATIONS.keys())
        assert OrderStatus.NEW not in notification_keys
        assert OrderStatus.CANCELLED in notification_keys

    def test_status_order_starts_with_new_ends_with_done(self):
        assert STATUS_ORDER[0] == OrderStatus.NEW
        assert STATUS_ORDER[-1] == OrderStatus.DONE
        assert OrderStatus.CANCELLED not in STATUS_ORDER

    def test_next_status_mapping(self):
        assert NEXT_STATUS[OrderStatus.NEW] == OrderStatus.CONFIRMED
        assert NEXT_STATUS[OrderStatus.CONFIRMED] == OrderStatus.PAID
        assert NEXT_STATUS[OrderStatus.PAID] == OrderStatus.SHIPPED
        assert NEXT_STATUS[OrderStatus.SHIPPED] == OrderStatus.DONE
        assert OrderStatus.DONE not in NEXT_STATUS

    def test_next_status_values_are_strings(self):
        for key, val in NEXT_STATUS.items():
            assert isinstance(val, str)
            assert isinstance(key, str)

    def test_fstring_interpolation(self):
        assert f"{OrderStatus.PAID}" == "paid"
        assert f"status:{OrderStatus.NEW}" == "status:new"

    def test_count(self):
        assert len(list(OrderStatus)) == 6

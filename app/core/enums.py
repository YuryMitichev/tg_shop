from enum import StrEnum


class OrderStatus(StrEnum):
    NEW = "new"
    CONFIRMED = "confirmed"
    PAID = "paid"
    SHIPPED = "shipped"
    DONE = "done"
    CANCELLED = "cancelled"

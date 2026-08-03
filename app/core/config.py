from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Настройки приложения.

    Все значения автоматически читаются из файла .env
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # ==========================
    # Telegram
    # ==========================

    bot_token: str = Field(..., alias="BOT_TOKEN")

    # Токен платформенного бота (registrar) — для онбординга новых магазинов.
    platform_bot_token: str | None = Field(default=None, alias="PLATFORM_BOT_TOKEN")

    # ID чата/пользователя, куда бот присылает уведомления о новых
    # заказах. Необязателен — если не задан, уведомления просто не
    # отправляются. Узнать свой chat_id можно, например, у @userinfobot.
    manager_chat_id: int | None = Field(default=None, alias="MANAGER_CHAT_ID")

    # Telegram ID администраторов магазина (через запятую).
    # Только с этими ID доступна панель управления (/admin).
    # Узнать свой ID можно у @userinfobot.
    admin_ids: str = Field(default="", alias="ADMIN_IDS")

    # URL админ-панели (отдельный поддомен).
    admin_panel_url: str | None = Field(default=None, alias="ADMIN_PANEL_URL")

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    # ==========================
    # Database
    # ==========================

    database_url: str = Field(
        default="sqlite+aiosqlite:///./shop.db",
        alias="DATABASE_URL",
    )

    # ==========================
    # Application
    # ==========================

    debug: bool = Field(default=True, alias="DEBUG")

    # Прокси для доступа к Telegram API, если api.telegram.org
    # заблокирован. Форматы: http://host:port, socks5://host:port
    bot_proxy: str | None = Field(default=None, alias="BOT_PROXY")

    app_name: str = "TG Shop"

    shop_name: str = Field(default="Магазин по умолчанию", alias="SHOP_NAME")

    # Telegram ID супер-админов SaaS-платформы (через запятую).
    # Супер-админ может создавать/редактировать/удалять магазины.
    super_admin_ids: str = Field(default="", alias="SUPER_ADMIN_IDS")

    @property
    def super_admin_id_list(self) -> list[int]:
        return [int(x.strip()) for x in self.super_admin_ids.split(",") if x.strip()]

    app_version: str = "0.1.0"

    # ==========================
    # Tinkoff Acquiring (СБП QR)
    # ==========================

    tinkoff_terminal_key: str | None = Field(default=None, alias="TINKOFF_TERMINAL_KEY")
    tinkoff_password: str | None = Field(default=None, alias="TINKOFF_PASSWORD")

    # Базовый URL приложения для вебхуков Тинькофф,
    # например: https://shop.example.com
    app_base_url: str | None = Field(default=None, alias="APP_BASE_URL")

    @property
    def tinkoff_enabled(self) -> bool:
        return bool(self.tinkoff_terminal_key and self.tinkoff_password and self.app_base_url)

    # ==========================
    # Admin Panel (JWT)
    # ==========================

    jwt_secret: str = Field(default="", alias="JWT_SECRET")

    @property
    def resolved_jwt_secret(self) -> str:
        return self.jwt_secret or self.bot_token

    # ==========================
    # ЮKassa (оплата подписок)
    # ==========================

    yookassa_shop_id: str | None = Field(default=None, alias="YOOKASSA_SHOP_ID")
    yookassa_secret_key: str | None = Field(default=None, alias="YOOKASSA_SECRET_KEY")

    @property
    def yookassa_enabled(self) -> bool:
        return bool(self.yookassa_shop_id and self.yookassa_secret_key)

    # ==========================
    # Ручная оплата (без эквайринга)
    # ==========================

    payment_card_number: str | None = Field(default=None, alias="PAYMENT_CARD_NUMBER")
    payment_recipient_name: str | None = Field(default=None, alias="PAYMENT_RECIPIENT_NAME")

    @property
    def webapp_enabled(self) -> bool:
        return bool(self.app_base_url)

    @property
    def webapp_url(self) -> str | None:
        if self.app_base_url:
            return f"{self.app_base_url.rstrip('/')}/app/"
        return None


@lru_cache
def get_settings() -> Settings:
    """
    Создает объект настроек один раз.

    Благодаря lru_cache настройки не перечитываются
    при каждом импорте.
    """
    return Settings()


settings = get_settings()
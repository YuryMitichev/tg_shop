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

    # ID чата/пользователя, куда бот присылает уведомления о новых
    # заказах. Необязателен — если не задан, уведомления просто не
    # отправляются. Узнать свой chat_id можно, например, у @userinfobot.
    manager_chat_id: int | None = Field(default=None, alias="MANAGER_CHAT_ID")

    # Telegram ID администраторов магазина (через запятую).
    # Только с этими ID доступна панель управления (/admin).
    # Узнать свой ID можно у @userinfobot.
    admin_ids: str = Field(default="", alias="ADMIN_IDS")

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


@lru_cache
def get_settings() -> Settings:
    """
    Создает объект настроек один раз.

    Благодаря lru_cache настройки не перечитываются
    при каждом импорте.
    """
    return Settings()


settings = get_settings()
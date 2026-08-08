"""Сервис для работы с публичной офертой."""

from pathlib import Path

from sqlalchemy import select

from app.database.db import async_session
from app.models.offer_acceptance import OfferAcceptance

_OFFER_FILE = Path(__file__).resolve().parent.parent / "data" / "offer.txt"
_PRIVACY_FILE = Path(__file__).resolve().parent.parent / "data" / "privacy_policy.txt"

OFFER_VERSION = "2026-08-06"
PRIVACY_POLICY_VERSION = "2026-08-06"


def get_offer_text() -> str:
    """Возвращает текст оферты из файла."""
    if _OFFER_FILE.exists():
        return _OFFER_FILE.read_text(encoding="utf-8")
    return ""


def get_privacy_policy_text() -> str:
    """Возвращает текст политики конфиденциальности из файла."""
    if _PRIVACY_FILE.exists():
        return _PRIVACY_FILE.read_text(encoding="utf-8")
    return ""


class OfferAgreementService:
    """Управление принятием публичной оферты."""

    @staticmethod
    async def accept(
        telegram_user_id: int,
        full_name: str | None = None,
        username: str | None = None,
    ) -> OfferAcceptance:
        """Записывает факт принятия оферты. Если уже принято — возвращает существующую запись."""
        async with async_session() as session:
            existing = await session.execute(
                select(OfferAcceptance).where(
                    OfferAcceptance.telegram_user_id == telegram_user_id,
                    OfferAcceptance.offer_version == OFFER_VERSION,
                )
            )
            record = existing.scalar_one_or_none()
            if record:
                return record

            record = OfferAcceptance(
                telegram_user_id=telegram_user_id,
                full_name=full_name,
                username=username,
                offer_version=OFFER_VERSION,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    @staticmethod
    async def has_accepted(telegram_user_id: int) -> bool:
        """Проверяет, принял ли пользователь текущую версию оферты."""
        async with async_session() as session:
            result = await session.execute(
                select(OfferAcceptance).where(
                    OfferAcceptance.telegram_user_id == telegram_user_id,
                    OfferAcceptance.offer_version == OFFER_VERSION,
                )
            )
            return result.scalar_one_or_none() is not None

    @staticmethod
    async def list_acceptances() -> list[dict]:
        """Возвращает все записи о принятии оферты (для супер-админа)."""
        async with async_session() as session:
            result = await session.execute(
                select(OfferAcceptance).order_by(OfferAcceptance.accepted_at.desc())
            )
            return [
                {
                    "id": r.id,
                    "telegram_user_id": r.telegram_user_id,
                    "full_name": r.full_name,
                    "username": r.username,
                    "offer_version": r.offer_version,
                    "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
                }
                for r in result.scalars().all()
            ]

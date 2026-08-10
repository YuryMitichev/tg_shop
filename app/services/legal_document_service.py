from sqlalchemy import select

from app.database.db import async_session
from app.models.shop import Shop
from app.models.shop_legal_document import ShopLegalDocument


LEGAL_DOCUMENT_TITLES = {
    "privacy_policy": "Политика конфиденциальности",
    "customer_consent": "Согласие на обработку персональных данных",
    "order_terms": "Условия оформления заказа",
    "data_processing_mandate": "Поручение на обработку персональных данных",
}

_PLATFORM_NAME = "Telegram-магазин (Платформа SaaS)"
_PLATFORM_ADDRESS = "Адрес оператора Платформы: указывается в учредительных документах"

_LEGAL_TYPE_LABELS = {
    "individual": "Физическое лицо",
    "ip": "Индивидуальный предприниматель",
    "ooo": "Общество с ограниченной ответственностью",
}


def _operator_label(legal_type: str) -> str:
    return _LEGAL_TYPE_LABELS.get(legal_type, _LEGAL_TYPE_LABELS["individual"])


def _build_system_privacy_policy(shop: dict) -> str:
    name = shop.get("company_name") or shop.get("name") or "Продавец"
    inn = shop.get("company_inn") or "—"
    address = shop.get("company_address") or "—"

    return (
        "ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ\n\n"
        f"Оператор персональных данных: {name}\n"
        f"ИНН: {inn}\n"
        f"Адрес: {address}\n\n"
        "1. ОБЩИЕ ПОЛОЖЕНИЯ\n"
        "1.1. Настоящая Политика определяет порядок обработки персональных данных (ПДн)\n"
        "    пользователей интернет-магазина и меры по их защите в соответствии\n"
        "    с Федеральным законом № 152-ФЗ «О персональных данных».\n"
        "1.2. Использование сайта / бота означает согласие с настоящей Политикой.\n\n"
        "2. КАТЕГОРИИ ОБРАБАТЫВАЕМЫХ ДАННЫХ\n"
        "2.1. ФИО, номер телефона, имя пользователя в Telegram.\n"
        "2.2. Данные о заказах: состав, стоимость, адрес доставки.\n"
        "2.3. Технические данные: IP, cookie, данные браузера.\n\n"
        "3. ЦЕЛИ ОБРАБОТКИ\n"
        "3.1. Обработка и исполнение заказов.\n"
        "3.2. Информирование о статусе заказа и сервисных сообщениях.\n"
        "3.3. Улучшение качества сервиса.\n\n"
        "4. ПРАВОВЫЕ ОСНОВАНИЯ\n"
        "4.1. Обработка осуществляется на основании согласия субъекта ПДн (ст. 6 ФЗ-152)\n"
        "    и договора, заключаемого при оформлении заказа.\n\n"
        "5. ПЕРЕДАЧА ТРЕТЬИМ ЛИЦАМ\n"
        "5.1. ПДн могут передаваться курьерским службам для доставки заказа,\n"
        "    платёжным системам для проведения оплаты, а также Платформе,\n"
        "    обеспечивающей техническое функционирование магазина.\n\n"
        "6. ХРАНЕНИЕ И ЗАЩИТА\n"
        "6.1. Мы принимаем необходимые организационные и технические меры\n"
        "    для защиты ПДн от неправомерного доступа, изменения и раскрытия.\n"
        "6.2. ПДн хранятся не дольше, чем это необходимо для целей обработки.\n\n"
        "7. ПРАВА СУБЪЕКТА ПДн\n"
        "7.1. Право на доступ, исправление, удаление и ограничение обработки.\n\n"
        "8. КОНТАКТЫ\n"
        f"По вопросам обработки ПДн: {name}, ИНН {inn}, адрес: {address}\n"
    )


def _build_system_customer_consent(shop: dict) -> str:
    name = shop.get("company_name") or shop.get("name") or "Продавец"
    inn = shop.get("company_inn") or "—"
    address = shop.get("company_address") or "—"

    return (
        "СОГЛАСИЕ НА ОБРАБОТКУ ПЕРСОНАЛЬНЫХ ДАННЫХ\n\n"
        f"Настоящим, предоставляя свои персональные данные при оформлении заказа\n"
        f"в интернет-магазине, я даю согласие оператору:\n\n"
        f"Оператор: {name}\n"
        f"ИНН: {inn}\n"
        f"Адрес: {address}\n\n"
        "на обработку моих персональных данных, а именно:\n"
        "— фамилия, имя, отчество;\n"
        "— контактный номер телефона;\n"
        "— имя пользователя в Telegram;\n"
        "— адрес доставки.\n\n"
        "Цели обработки:\n"
        "— оформление, обработка и исполнение заказа;\n"
        "— информирование о статусе заказа;\n"
        "— организация доставки товара.\n\n"
        "Перечень действий с ПДн: сбор, запись, систематизация, накопление,\n"
        "хранение, уточнение, использование, передача (предоставление доступа)\n"
        "курьерским службам и платёжным системам, обезличивание, блокирование,\n"
        "удаление и уничтожение.\n\n"
        "Настоящее согласие действует со дня его предоставления и до дня отзыва.\n"
        "Согласие может быть отозвано путём направления оператору письменного заявления.\n\n"
        "Обработка ПДн также осуществляется Платформой, обеспечивающей\n"
        "техническое функционирование интернет-магазина, на основании отдельного\n"
        "поручения оператора.\n"
    )


def _build_system_order_terms(shop: dict) -> str:
    name = shop.get("company_name") or shop.get("name") or "Продавец"
    inn = shop.get("company_inn") or "—"
    address = shop.get("company_address") or "—"

    return (
        "УСЛОВИЯ ОФОРМЛЕНИЯ ЗАКАЗА\n\n"
        f"Продавец: {name}\n"
        f"ИНН: {inn}\n"
        f"Адрес: {address}\n\n"
        "1. ОФОРМЛЕНИЕ ЗАКАЗА\n"
        "1.1. Заказ оформляется через каталог магазина (бот / мини-приложение).\n"
        "1.2. Для завершения заказа необходимо указать ФИО, контактный телефон\n"
        "    и (при необходимости) адрес доставки.\n"
        "1.3. Оформляя заказ, покупатель заключает с продавцом договор купли-продажи.\n\n"
        "2. ПОДТВЕРЖДЕНИЕ ЗАКАЗА\n"
        "2.1. Заказ считается принятым после его подтверждения продавцом.\n"
        "2.2. Продавец вправе отказать в заказе при отсутствии товара на складе.\n\n"
        "3. ОПЛАТА\n"
        "3.1. Доступные способы оплаты указываются при оформлении заказа.\n"
        "3.2. Цены указываются в каталоге на момент оформления заказа.\n\n"
        "4. ДОСТАВКА\n"
        "4.1. Способы и стоимость доставки определяются при оформлении заказа.\n"
        "4.2. Сроки доставки зависят от выбранной курьерской службы.\n\n"
        "5. ВОЗВРАТ И ОБМЕН\n"
        "5.1. Возврат и обмен осуществляются в соответствии с Законом\n"
        "    «О защите прав потребителей».\n"
        "5.2. Для возврата свяжитесь с продавцом.\n\n"
        "6. КОНТАКТЫ\n"
        f"{name}, ИНН {inn}, адрес: {address}\n"
    )


def _build_data_processing_mandate(shop: dict) -> str:
    name = shop.get("company_name") or shop.get("name") or "Продавец"
    inn = shop.get("company_inn") or "—"
    address = shop.get("company_address") or "—"
    legal_type = shop.get("legal_type", "individual")
    operator = _operator_label(legal_type)

    return (
        "ПОРУЧЕНИЕ НА ОБРАБОТКУ ПЕРСОНАЛЬНЫХ ДАННЫХ\n\n"
        f"{operator} {name} (ИНН: {inn}, адрес: {address}),\n"
        "именуемый в дальнейшем «Оператор», с одной стороны, и\n"
        f"{_PLATFORM_NAME}, именуемая в дальнейшем «Обработчик», с другой стороны,\n"
        "заключили настоящее Поручение о следующем:\n\n"
        "1. ПРЕДМЕТ ПОРУЧЕНИЯ\n"
        "1.1. Оператор поручает, а Обработчик обязуется осуществлять обработку\n"
        "    персональных данных покупателей интернет-магазина Оператора\n"
        "    в целях обеспечения технического функционирования магазина,\n"
        "    обработки заказов и информационного обмена.\n\n"
        "2. КАТЕГОРИИ ПДн И ДЕЙСТВИЯ\n"
        "2.1. Обработке подлежат: ФИО, телефон, имя пользователя в Telegram,\n"
        "    адрес доставки, данные о заказах.\n"
        "2.2. Обработка включает: сбор, запись, систематизацию, накопление,\n"
        "    хранение, уточнение, извлечение, использование, передачу\n"
        "    (распространение, предоставление, доступ), обезличивание,\n"
        "    блокирование, удаление, уничтожение.\n\n"
        "3. ПРАВА И ОБЯЗАННОСТИ\n"
        "3.1. Обработчик обязуется обрабатывать ПДн только на основании\n"
        "    настоящего Поручения и в указанных целях.\n"
        "3.2. Обработчик обеспечивает конфиденциальность и безопасность ПДн.\n"
        "3.3. Обработчик не вправе использовать ПДн в собственных целях.\n"
        "3.4. По требованию Оператора Обработчик обязан незамедлительно\n"
        "    уничтожить или вернуть ПДн.\n\n"
        "4. СРОК\n"
        "4.1. Настоящее Поручение действует на срок существования договорных\n"
        "    отношений между Оператором и Платформой.\n\n"
        "5. РЕКВИЗИТЫ ОПЕРАТОРА\n"
        f"Правовая форма: {operator}\n"
        f"Наименование: {name}\n"
        f"ИНН: {inn}\n"
        f"Адрес: {address}\n\n"
        f"6. РЕКВИЗИТЫ ОБРАБОТЧИКА\n"
        f"{_PLATFORM_NAME}\n"
        f"{_PLATFORM_ADDRESS}\n\n"
        "Настоящий документ формируется автоматически на основании реквизитов\n"
        "магазина и не подлежит редактированию продавцом (ст. 6 ФЗ-152).\n"
    )


def _build_roskomnadzor_draft(shop: dict) -> str:
    name = shop.get("company_name") or shop.get("name") or "Продавец"
    inn = shop.get("company_inn") or "—"
    address = shop.get("company_address") or "—"
    legal_type = shop.get("legal_type", "individual")
    operator = _operator_label(legal_type)

    return (
        "УВЕДОМЛЕНИЕ О ОБРАБОТКЕ ПЕРСОНАЛЬНЫХ ДАННЫХ\n"
        "(проект для подачи в Роскомнадзор)\n\n"
        "В территориальный орган Роскомнадзора\n\n"
        f"От: {operator} {name}\n"
        f"ИНН: {inn}\n"
        f"Адрес: {address}\n\n"
        "УВЕДОМЛЕНИЕ\n"
        "о намерении осуществлять обработку персональных данных\n\n"
        "1. Наименование (ФИО), адрес оператора:\n"
        f"   {operator} {name}\n"
        f"   ИНН: {inn}\n"
        f"   Адрес: {address}\n\n"
        "2. Правовое основание обработки:\n"
        "   Федеральный закон от 27.07.2006 № 152-ФЗ\n"
        "   «О персональных данных», ст. 6 (согласие субъекта ПДн).\n\n"
        "3. Цели обработки:\n"
        "   — обработка и исполнение заказов покупателей;\n"
        "   — информирование о статусе заказа;\n"
        "   — организация доставки товара.\n\n"
        "4. Категории персональных данных:\n"
        "   ФИО, номер телефона, имя пользователя в Telegram, адрес доставки.\n\n"
        "5. Категории субъектов:\n"
        "   Покупатели интернет-магазина.\n\n"
        "6. Перечень действий с ПДн:\n"
        "   Сбор, запись, систематизация, накопление, хранение,\n"
        "   использование, передача (курьерским службам, платёжным системам),\n"
        "   обезличивание, блокирование, удаление, уничтожение.\n\n"
        "7. Описание способов обработки:\n"
        "   Автоматизированная обработка с использованием информационных систем.\n\n"
        "8. Срок или условие прекращения обработки:\n"
        "   До достижения целей обработки или отзыва согласия субъектом.\n\n"
        "9. Сведения о лице, ответственном за организацию обработки ПДн:\n"
        f"   {name}, ИНН {inn}\n\n"
        "Дата: _______________\n"
        "Подпись: _______________\n\n"
        "---\n"
        "Подача уведомления производится через портал Роскомнадзора:\n"
        "https://pd.rkn.gov.ru/owners/notification/\n"
        "Форма уведомления утверждена Приказом Роскомнадзора от 28.10.2022 № 180.\n"
    )


_SYSTEM_BUILDERS = {
    "privacy_policy": _build_system_privacy_policy,
    "customer_consent": _build_system_customer_consent,
    "order_terms": _build_system_order_terms,
}


class LegalDocumentService:
    """Сервис правовых документов магазина.

    Каждый документ = защищённый системный шаблон (генерируется кодом)
    + необязательное дополнение продавца (seller_addendum, хранится в БД).

    data_processing_mandate — полностью автогенерируемый, без дополнений.
    """

    @staticmethod
    def get_system_template(document_type: str, shop: dict) -> str:
        if document_type == "data_processing_mandate":
            return _build_data_processing_mandate(shop)
        builder = _SYSTEM_BUILDERS.get(document_type)
        if builder is None:
            return ""
        return builder(shop)

    @staticmethod
    def get_roskomnadzor_draft(shop: dict) -> str:
        return _build_roskomnadzor_draft(shop)

    @staticmethod
    async def get_seller_addendum(shop_id: int, document_type: str) -> str | None:
        async with async_session() as session:
            result = await session.execute(
                select(ShopLegalDocument).where(
                    ShopLegalDocument.shop_id == shop_id,
                    ShopLegalDocument.document_type == document_type,
                )
            )
            doc = result.scalar_one_or_none()
            return doc.seller_addendum if doc else None

    @staticmethod
    async def update_seller_addendum(
        shop_id: int, document_type: str, addendum: str | None
    ) -> str | None:
        async with async_session() as session:
            result = await session.execute(
                select(ShopLegalDocument).where(
                    ShopLegalDocument.shop_id == shop_id,
                    ShopLegalDocument.document_type == document_type,
                )
            )
            doc = result.scalar_one_or_none()

            if doc is None:
                doc = ShopLegalDocument(
                    shop_id=shop_id,
                    document_type=document_type,
                    seller_addendum=addendum or None,
                )
                session.add(doc)
            else:
                doc.seller_addendum = addendum or None

            await session.commit()
            return doc.seller_addendum

    @staticmethod
    async def render_document(shop_id: int, document_type: str) -> dict | None:
        """Возвращает полный текст документа: системный шаблон + дополнение продавца."""
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None
            shop_dict = {
                "name": shop.name,
                "company_name": shop.company_name,
                "company_inn": shop.company_inn,
                "company_address": shop.company_address,
                "legal_type": shop.legal_type,
            }

        system_text = LegalDocumentService.get_system_template(document_type, shop_dict)

        addendum = None
        if document_type != "data_processing_mandate":
            addendum = await LegalDocumentService.get_seller_addendum(shop_id, document_type)

        full_text = system_text
        if addendum:
            full_text += f"\n\n— ДОПОЛНИТЕЛЬНЫЕ УСЛОВИЯ ПРОДАВЦА —\n\n{addendum}"

        return {
            "document_type": document_type,
            "title": LEGAL_DOCUMENT_TITLES.get(document_type, document_type),
            "system_template": system_text,
            "seller_addendum": addendum,
            "text": full_text,
            "is_read_only": document_type == "data_processing_mandate",
        }

    @staticmethod
    async def get_all_documents(shop_id: int) -> list[dict] | None:
        """Возвращает все четыре документа магазина (для админки)."""
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None

        docs = []
        for doc_type in ["privacy_policy", "customer_consent", "order_terms", "data_processing_mandate"]:
            rendered = await LegalDocumentService.render_document(shop_id, doc_type)
            if rendered:
                docs.append(rendered)
        return docs

    @staticmethod
    async def get_customer_consent_text(shop_id: int) -> str | None:
        """Краткий текст согласия для отображения в боте при оформлении заказа."""
        rendered = await LegalDocumentService.render_document(shop_id, "customer_consent")
        if rendered is None:
            return None
        return rendered["text"]

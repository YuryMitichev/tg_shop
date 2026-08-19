import pytest

from app.services.channel_prefilter import classify_post


@pytest.mark.parametrize(
    "text",
    [
        "Свеча Кашемир 200 г. Цена 990 ₽. В наличии, доставка сегодня.",
        "Арт. AB-42, объём 100 мл — 1290 руб. Заказать в сообщениях.",
        "Новая модель, размер XL, материал хлопок, стоимость 2500 ₽",
    ],
)
def test_prefilter_keeps_product_posts(text):
    assert classify_post(text, has_photos=True).label == "product"


@pytest.mark.parametrize(
    "text",
    [
        "Поздравляем всех с праздником! Желаем радости и хорошего дня.",
        "Важная информация: завтра магазин закрыт, изменилось расписание работы.",
        "Опрос: в какое время вам удобнее читать наши новости?",
        "Открыта вакансия администратора. Ищем сотрудника в команду.",
    ],
)
def test_prefilter_skips_only_clear_non_products(text):
    decision = classify_post(text, has_photos=False)
    assert decision.label == "non_product"
    assert decision.confidence >= 0.95


def test_product_signal_wins_over_contest_word():
    decision = classify_post(
        "Конкурс завершён, но набор свечей всё ещё в наличии: цена 1500 ₽, заказать можно сегодня.",
        has_photos=True,
    )
    assert decision.label == "product"


def test_ambiguous_post_is_not_dropped():
    assert classify_post("Посмотрите, какая красота!", has_photos=True).label == "ambiguous"


def test_photo_only_requires_manual_review():
    assert classify_post(None, has_photos=True).label == "needs_manual"

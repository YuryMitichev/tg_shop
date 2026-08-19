import pytest

from app.services.channel_ai_service import (
    AIAttribute,
    AIFieldConfidence,
    AIProduct,
    AIVariant,
    ChannelAIService,
    PostAnalysis,
)


class _Usage:
    input_tokens = 100
    output_tokens = 20


class _Response:
    usage = _Usage()
    output_parsed = PostAnalysis(
        classification="product",
        confidence=0.98,
        reason="Есть цена и описание",
        products=[
            AIProduct(
                name="Свеча Кашемир",
                description="Ароматическая свеча",
                category_name="Свечи",
                variants=[AIVariant(title="200 г", price=990, stock=5)],
            )
        ],
    )


class _Responses:
    def __init__(self):
        self.kwargs = None

    async def parse(self, **kwargs):
        self.kwargs = kwargs
        return _Response()


class _Client:
    def __init__(self):
        self.responses = _Responses()


@pytest.mark.asyncio
async def test_ai_uses_structured_responses_and_text_only():
    client = _Client()
    result, usage = await ChannelAIService(client).analyze_post(
        "Свеча 990 ₽",
        categories=["Свечи"],
        attribute_definitions=["Аромат"],
    )

    assert result.products[0].name == "Свеча Кашемир"
    assert client.responses.kwargs["text_format"] is PostAnalysis
    assert "image" not in str(client.responses.kwargs).lower()
    assert usage == {"input_tokens": 100, "output_tokens": 20, "cost_microusd": 165}


def test_ai_product_converts_strict_lists_to_catalog_dicts():
    product = AIProduct(
        name="Свеча Лён",
        attributes=[AIAttribute(name="Аромат", value="Лён")],
        field_confidence=[AIFieldConfidence(field="name", confidence=0.96)],
        variants=[
            AIVariant(
                title="200 г",
                price=1200,
                stock=4,
                attributes=[AIAttribute(name="Вес", value="200 г")],
            )
        ],
    )

    data = product.to_catalog_dict()

    assert data["attributes"] == {"Аромат": "Лён"}
    assert data["field_confidence"] == {"name": 0.96}
    assert data["variants"][0]["attributes"] == {"Вес": "200 г"}


def test_post_analysis_schema_has_no_open_dictionary_fields():
    schema = PostAnalysis.model_json_schema()

    def assert_closed(value):
        if isinstance(value, dict):
            additional = value.get("additionalProperties")
            assert not isinstance(additional, dict)
            for child in value.values():
                assert_closed(child)
        elif isinstance(value, list):
            for child in value:
                assert_closed(child)

    assert_closed(schema)

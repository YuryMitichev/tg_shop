import html


def esc(text: str | None) -> str:
    """Экранирует пользовательский ввод для вставки в HTML-сообщение."""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)

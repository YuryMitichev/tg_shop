import html
from html.parser import HTMLParser


def esc(text: str | None) -> str:
    """Экранирует пользовательский ввод для вставки в HTML-сообщение."""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


class _TelegramHTMLSanitizer(HTMLParser):
    """Minimal allow-list sanitizer for owner-editable Telegram messages."""

    _ALLOWED_TAGS = {"b", "i", "code"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in self._ALLOWED_TAGS and not attrs:
            self.parts.append(f"<{normalized}>")
            self.open_tags.append(normalized)
        else:
            self.parts.append(esc(self.get_starttag_text()))

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in self._ALLOWED_TAGS and self.open_tags and self.open_tags[-1] == normalized:
            self.parts.append(f"</{normalized}>")
            self.open_tags.pop()
        else:
            self.parts.append(esc(f"</{tag}>"))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(esc(self.get_starttag_text()))

    def handle_data(self, data: str) -> None:
        self.parts.append(esc(data))

    def handle_entityref(self, name: str) -> None:
        if name in {"amp", "lt", "gt", "quot"}:
            self.parts.append(f"&{name};")
        else:
            self.parts.append(f"&amp;{esc(name)};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{esc(name)};")

    def close_open_tags(self) -> None:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")


def sanitize_telegram_html(text: str | None) -> str:
    """Allow only the formatting tags exposed by the admin UI."""
    sanitizer = _TelegramHTMLSanitizer()
    sanitizer.feed(str(text or ""))
    sanitizer.close()
    sanitizer.close_open_tags()
    return "".join(sanitizer.parts)

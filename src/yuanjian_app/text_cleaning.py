"""Turn untrusted feed markup into compact user-visible text."""

from html import unescape
from html.parser import HTMLParser


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(data)


def plain_text(value, max_length=None):
    """Return visible, whitespace-normalized text from possibly marked-up input."""
    parser = _VisibleTextParser()
    parser.feed(unescape(str(value or "")))
    parser.close()
    cleaned = " ".join("".join(parser.parts).split())
    if max_length is not None:
        limit = max(0, int(max_length))
        if len(cleaned) > limit:
            return cleaned[:limit].rstrip() + "…"
    return cleaned

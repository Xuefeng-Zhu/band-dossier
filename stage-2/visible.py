"""Project rendered provider Markdown to visible text without fetching assets."""

import re
from html.parser import HTMLParser

from markdown_it import MarkdownIt


MARKDOWN = MarkdownIt("commonmark", {"html": True})
BLOCKS = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
    "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
    "section", "summary", "table", "td", "th", "tr", "ul",
}
HIDDEN = {"head", "noscript", "script", "style", "template", "title"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}
HIDDEN_STYLE = re.compile(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\b", re.I)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.lines = []

    def allows(self, tag=None):
        if not self.stack:
            return True
        parent, hidden, closed = self.stack[-1]
        return not hidden and (not closed or parent == "details" and tag == "summary")

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        hidden = (not self.allows(tag) or tag in HIDDEN or "hidden" in attrs
                  or bool(HIDDEN_STYLE.search(attrs.get("style") or "")))
        if not hidden:
            if tag in BLOCKS:
                self.lines.append("\n")
            if tag == "img" and not (attrs.get("src") or attrs.get("srcset")):
                self.lines.append(attrs.get("alt") or "")
        if tag not in VOID:
            self.stack.append((tag, hidden, tag == "details" and "open" not in attrs))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            current, hidden, _closed = self.stack[index]
            if current == tag:
                del self.stack[index:]
                if not hidden and tag in BLOCKS:
                    self.lines.append("\n")
                return

    def handle_data(self, text):
        if self.allows():
            self.lines.append(text)


def visible_text(lines):
    """Keep source line breaks used by Appendix A, including Markdown soft breaks."""
    reader = VisibleText()
    reader.feed(MARKDOWN.render("\n".join(lines)))
    reader.close()
    return "".join(reader.lines)

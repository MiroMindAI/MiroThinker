import re
from urllib.parse import unquote

from markdown_it import MarkdownIt

# Reserved character encodings to be protected -> temporary placeholders
PROTECT = {
    "%2F": "__SLASH__",
    "%2f": "__SLASH__",
    "%3F": "__QMARK__",
    "%3f": "__QMARK__",
    "%23": "__HASH__",
    "%26": "__AMP__",
    "%3D": "__EQUAL__",
    "%20": "__SPACE__",
    "%2B": "__PLUS__",
    "%25": "__PERCENT__",
}

# Reverse mapping: placeholder -> original %xx (use uppercase for uniform output)
RESTORE = {v: k.upper() for k, v in PROTECT.items()}


def safe_unquote(s: str, encoding="utf-8", errors="ignore") -> str:
    # 1. Replace with placeholders
    for k, v in PROTECT.items():
        s = s.replace(k, v)
    # 2. Decode (only affects unprotected parts, e.g., Chinese characters)
    s = unquote(s, encoding=encoding, errors=errors)
    # 3. Replace placeholders back to original %xx
    for v, k in RESTORE.items():
        s = s.replace(v, k)
    return s


def decode_http_urls_in_dict(data):
    """
    Traverse all values in the data structure:
    - If it's a string starting with http, apply urllib.parse.unquote
    - If it's a list, recursively process each element
    - If it's a dict, recursively process each value
    - Other types remain unchanged
    """
    if isinstance(data, str):
        if "%" in data:
            return safe_unquote(data)
        else:
            return data
    elif isinstance(data, list):
        return [decode_http_urls_in_dict(item) for item in data]
    elif isinstance(data, dict):
        return {key: decode_http_urls_in_dict(value) for key, value in data.items()}
    else:
        return data


md = MarkdownIt("commonmark")


def strip_markdown_links(markdown: str) -> str:
    tokens = md.parse(markdown)

    def render(ts):
        out = []
        for tok in ts:
            t = tok.type

            # 1) Links: drop the wrapper, keep inner text (children will be rendered)
            if t == "link_open" or t == "link_close":
                continue

            # 2) Images: skip the entire image block
            if t == "image":
                continue

            # 3) Line breaks and block closings
            if t == "softbreak":  # inline single line break
                out.append("\n")
                continue
            if (
                t == "hardbreak"
            ):  # explicit line break (two spaces + newline in Markdown)
                out.append("\n")
                continue
            if t in ("paragraph_close", "heading_close", "blockquote_close"):
                out.append("\n\n")
                continue
            if t in ("list_item_close", "bullet_list_close", "ordered_list_close"):
                out.append("\n")
                continue
            if t == "hr":
                out.append("\n\n")
                continue

            # 4) Inline or nested tokens
            if tok.children:
                out.append(render(tok.children))
                continue

            # Preserve inline code style
            if t == "code_inline":
                out.append(f"`{tok.content}`")
            else:
                out.append(tok.content or "")

        return "".join(out)

    text = render(tokens)

    # normalize excessive blank lines (avoid more than 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"

    return text.strip()

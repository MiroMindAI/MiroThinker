from urllib.parse import unquote
from markdown_it import MarkdownIt
import re


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
url_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)|<([^>]+)>")


def extract_urls_from_markdown(text: str, encoding: str = "utf-8"):
    """
    Robust markdown URL extraction:
    - Use markdown-it syntax parsing
    - Preserve the original markdown URL expression
    - Handle exceptions and escaping
    """
    tokens = md.parse(text)
    results = []
    raw_matches = []

    for match in url_pattern.finditer(text):
        if match.group(2):  # [text](url)
            raw_matches.append(
                {
                    "text": match.group(1),
                    "url": match.group(2),
                    "original": match.group(0),
                }
            )

    def handle_tokens(token_list):
        stack = []
        for tok in token_list:
            if tok.type == "image":  # Skip images completely
                continue
            if tok.type == "link_open":
                attrs = dict(tok.attrs or [])
                href = attrs.get("href")
                stack.append({"href": href, "text": ""})
            elif tok.type == "text" and stack:
                stack[-1]["text"] += tok.content
            elif tok.type == "link_close" and stack:
                item = stack.pop()
                href = item["href"]
                link_text = item["text"]

                match = next(
                    (
                        m
                        for m in raw_matches
                        if m["url"] == href and m["text"] == link_text
                    ),
                    None,
                )
                if match:
                    original = match["original"]
                else:
                    original = f"[{link_text}]({href})" if link_text else f"<{href}>"

                results.append(
                    {
                        "original": original,
                        "url": href,
                        "text": link_text,
                    }
                )

            if tok.children:
                handle_tokens(tok.children)

    handle_tokens(tokens)

    return results


def strip_markdown_links(markdown: str):
    urls = extract_urls_from_markdown(markdown)
    for url_dict in urls:
        original = url_dict["original"]
        text = url_dict["text"]
        markdown = markdown.replace(original, text)
    return markdown

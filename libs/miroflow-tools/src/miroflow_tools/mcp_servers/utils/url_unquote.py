import re
from urllib.parse import unquote

from markdown_it import MarkdownIt

# RFC 3986 reserved characters percent-encoding (decoding these would alter URL semantics/structure)
# gen-delims: : / ? # [ ] @
# sub-delims: ! $ & ' ( ) * + , ; =
RESERVED_PERCENT_ENCODINGS = frozenset(
    {
        "%2f",
        "%2F",  # /  path separator
        "%3f",
        "%3F",  # ?  query string start
        "%23",  # #  fragment start
        "%26",  # &  query parameter separator
        "%3d",
        "%3D",  # =  key-value separator
        "%40",  # @
        "%3a",
        "%3A",  # :
        "%5b",
        "%5B",  # [
        "%5d",
        "%5D",  # ]
        "%21",  # !
        "%24",  # $
        "%27",  # '
        "%28",  # (
        "%29",  # )
        "%2a",
        "%2A",  # *
        "%2b",
        "%2B",  # +
        "%2c",
        "%2C",  # ,
        "%3b",
        "%3B",  # ;
        "%25",  # %  percent sign itself (prevents double-encoding issues)
        "%20",  # space (keep encoded to avoid URL semantic changes)
    }
)


def safe_unquote(url: str) -> str:
    """
    Safely decode URL-encoded strings, only decoding characters that won't alter URL semantics.

    Preserve the following encodings (because decoding would change URL structure/semantics):
    - %2F (/) - path separator, decoding would alter path hierarchy
    - %3F (?) - query string start marker
    - %23 (#) - fragment start marker (not sent to server)
    - %26 (&) - query parameter separator
    - %3D (=) - key-value separator
    - %25 (%) - percent sign itself (prevents double-encoding issues, e.g. %252F -> %2F -> /)
    - %20 ( ) - space (keep encoded to avoid URL semantic changes)
    - and other RFC 3986 reserved characters

    Only decode unreserved characters and UTF-8 encoded international characters (e.g. Chinese).
    """
    if not url:
        return url

    result = []
    i = 0
    n = len(url)

    while i < n:
        # Check if this is a percent-encoded sequence %XX
        if url[i] == "%" and i + 2 < n:
            hex_chars = url[i + 1 : i + 3]
            # Validate it's a valid hexadecimal
            if all(c in "0123456789ABCDEFabcdef" for c in hex_chars):
                percent_encoded = url[i : i + 3]

                # Check if this is a reserved character encoding that should be preserved
                if percent_encoded in RESERVED_PERCENT_ENCODINGS:
                    # Keep the encoding, don't decode
                    result.append(percent_encoded)
                    i += 3
                    continue

                # Try to decode (may be a UTF-8 multi-byte sequence)
                # Collect consecutive percent-encoded sequences
                encoded_sequence = percent_encoded
                j = i + 3
                while j + 2 < n and url[j] == "%":
                    next_hex = url[j + 1 : j + 3]
                    if all(c in "0123456789ABCDEFabcdef" for c in next_hex):
                        next_encoded = url[j : j + 3]
                        # Stop collecting if we encounter a reserved character
                        if next_encoded in RESERVED_PERCENT_ENCODINGS:
                            break
                        encoded_sequence += next_encoded
                        j += 3
                    else:
                        break

                # Decode the collected sequence
                try:
                    decoded = unquote(encoded_sequence)
                    result.append(decoded)
                    i = j
                    continue
                except Exception:
                    # Decoding failed, keep the original encoding
                    result.append(percent_encoded)
                    i += 3
                    continue

        result.append(url[i])
        i += 1

    return "".join(result)


def decode_http_urls_in_dict(data):
    """
    Traverse all values in the data structure:
    - If it's a string starting with http, apply urllib.parse.unquote
    - If it's a list, recursively process each element
    - If it's a dict, recursively process each value
    - Other types remain unchanged
    """
    if isinstance(data, str):
        if "%" in data and "http" in data:
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

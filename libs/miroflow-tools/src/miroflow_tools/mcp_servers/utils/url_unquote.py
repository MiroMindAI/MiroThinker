from urllib.parse import unquote

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

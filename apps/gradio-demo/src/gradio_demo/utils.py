import re


def contains_chinese(text):
    """
    Detect if a string contains Chinese characters or Chinese punctuation

    Args:
        text (str): The string to detect

    Returns:
        bool: True if contains Chinese characters or punctuation, False otherwise
    """
    # Chinese character Unicode ranges:
    # \u4e00-\u9fff: CJK Unified Ideographs
    # \u3400-\u4dbf: CJK Extension A
    # \uf900-\ufaff: CJK Compatibility Ideographs
    # \u3000-\u303f: CJK Symbols and Punctuation
    # \uff00-\uffef: Fullwidth ASCII, Fullwidth punctuation
    chinese_pattern = re.compile(
        r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffef]"
    )
    return bool(chinese_pattern.search(text))


def replace_chinese_punctuation(text):
    # Handle single-character replacements with translate
    punctuation_map = str.maketrans(
        {
            "，": ",",
            "。": ".",
            "！": "!",
            "？": "?",
            "；": ";",
            "：": ":",
            "“": '"',
            "”": '"',
            "‘": "'",
            "’": "'",
            "（": "(",
            "）": ")",
            "【": "[",
            "】": "]",
            "《": "<",
            "》": ">",
            "、": ",",
            "—": "-",
        }
    )
    # First, replace multi-character punctuation
    text = text.replace("……", "...")
    # Then apply single-character replacements
    return text.translate(punctuation_map)

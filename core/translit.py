"""Uzbek Latin -> Cyrillic transliteration for bot messages."""

import re

APOSTROPHES = "'ʻʼ‘’`"

_DIGRAPHS = {
    "sh": "ш",
    "ch": "ч",
    "yo": "ё",
    "yu": "ю",
    "ya": "я",
    "ye": "е",
}

_SINGLE = {
    "a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ", "i": "и",
    "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ",
    "r": "р", "s": "с", "t": "т", "u": "у", "v": "в", "x": "х", "y": "й", "z": "з",
}

_TAG = re.compile(r"(<[^>]+>|\{[^}]*\})")


def _case(src, out):
    if src[:1].isupper():
        if len(src) > 1 and src[1:2].isupper():
            return out.upper()
        return out[:1].upper() + out[1:]
    return out


def _word_start(text, i):
    return i == 0 or not text[i - 1].isalpha()


def _convert(text):
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        low = ch.lower()
        nxt = text[i + 1] if i + 1 < n else ""
        # o' and g'
        if low in "og" and nxt and nxt in APOSTROPHES:
            out.append(_case(ch, "ў" if low == "o" else "ғ"))
            i += 2
            continue
        pair = text[i : i + 2]
        after = text[i + 2] if i + 2 < n else ""
        # "yo'q" is й + ў, not ё
        if pair.lower() in _DIGRAPHS and not (pair[1:].lower() == "o" and after and after in APOSTROPHES):
            out.append(_case(pair, _DIGRAPHS[pair.lower()]))
            i += 2
            continue
        if low == "e" and _word_start(text, i):
            out.append(_case(ch, "э"))
        elif low in _SINGLE:
            out.append(_case(ch, _SINGLE[low]))
        elif ch in APOSTROPHES and i > 0 and text[i - 1].isalpha() and nxt.isalpha():
            out.append("ъ")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def to_cyrillic(text):
    """Transliterate, leaving HTML tags and {placeholders} untouched."""
    parts = _TAG.split(text)
    return "".join(p if _TAG.fullmatch(p) else _convert(p) for p in parts)

"""Parse common rental-catalog dimensions into normalized inches."""

from __future__ import annotations

import re

from shared.schema import Dimensions

_FRACTIONS = {
    "¼": 0.25,
    "½": 0.5,
    "¾": 0.75,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}
_LABELS = {
    "h": "height",
    "height": "height",
    "w": "width",
    "width": "width",
    "d": "depth",
    "depth": "depth",
    "l": "length",
    "length": "length",
    "diameter": "diameter",
    "dia": "diameter",
}
_NUMBER = r"\d+(?:\.\d+)?(?:\s*[¼½¾⅛⅜⅝⅞])?"


def parse_dimensions(value: str | None) -> Dimensions | None:
    if not value:
        return None
    text = (
        value.lower()
        .replace("″", '"')
        .replace("”", '"')
        .replace("“", '"')
        .replace("’", "'")
        .replace("′", "'")
        .replace("×", "x")
    )
    parsed: dict[str, float] = {}

    # Value-first forms: 37"H, 6' L, 30" diameter.
    value_first = re.compile(
        rf"(?P<value>{_NUMBER})\s*(?P<unit>[\"']?)\s*"
        rf"(?P<label>height|width|depth|length|diameter|dia|[hwdl])\b"
    )
    for match in value_first.finditer(text):
        parsed[_LABELS[match.group("label")]] = _to_inches(
            match.group("value"),
            match.group("unit"),
        )

    # Label-first forms: H: 5.625", W 35 1/2" (Unicode fractions supported).
    label_first = re.compile(
        rf"\b(?P<label>height|width|depth|length|diameter|dia|[hwdl])\s*:?\s*"
        rf"(?P<value>{_NUMBER})\s*(?P<unit>[\"']?)"
    )
    for match in label_first.finditer(text):
        field = _LABELS[match.group("label")]
        parsed.setdefault(
            field,
            _to_inches(match.group("value"), match.group("unit")),
        )

    # Common scraper forms omit W/D labels: 28" x 28" x 5" h.
    positional = re.search(
        rf"(?P<width>{_NUMBER})\s*\"\s*x\s*"
        rf"(?P<depth>{_NUMBER})\s*\"\s*x\s*"
        rf"(?P<height>{_NUMBER})\s*\"\s*h\b",
        text,
    )
    if positional:
        parsed.setdefault("width", _to_inches(positional.group("width"), '"'))
        parsed.setdefault("depth", _to_inches(positional.group("depth"), '"'))
        parsed.setdefault("height", _to_inches(positional.group("height"), '"'))

    square = re.search(
        rf"(?P<size>{_NUMBER})\s*\"\s*square\s*x\s*"
        rf"(?P<height>{_NUMBER})\s*\"\s*h\b",
        text,
    )
    if square:
        size = _to_inches(square.group("size"), '"')
        parsed.setdefault("width", size)
        parsed.setdefault("depth", size)
        parsed.setdefault("height", _to_inches(square.group("height"), '"'))

    if not parsed:
        return None
    return Dimensions(**parsed, unit="in")


def _to_inches(value: str, unit: str) -> float:
    fraction = next((amount for symbol, amount in _FRACTIONS.items() if symbol in value), 0)
    whole_text = re.sub(r"[¼½¾⅛⅜⅝⅞]", "", value).strip()
    amount = float(whole_text) if whole_text else 0.0
    amount += fraction
    return amount * 12 if unit == "'" else amount

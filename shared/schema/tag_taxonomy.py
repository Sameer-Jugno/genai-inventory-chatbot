"""Controlled inventory taxonomy and deterministic tag enrichment."""

from __future__ import annotations

import re
from collections.abc import Iterable

# The supplied catalogs contain seating, tabletop, bars, and service/event
# equipment. Keep tags controlled so OpenSearch keyword filters remain useful.
STARTER_TAGS: tuple[str, ...] = (
    # Top-level inventory concepts
    "furniture",
    "seating",
    "table",
    "bar",
    "glassware",
    "china",
    "flatware",
    "service-equipment",
    "event-equipment",
    "lighting",
    "linens",
    "decor",
    "tenting",
    "staging",
    "av",
    "signage",
    # Product forms / uses
    "chair",
    "armchair",
    "lounge",
    "sofa",
    "bench",
    "stool",
    "bistro",
    "folding",
    "stackable",
    "kids",
    "outdoor",
    "dining",
    "cocktail",
    "set",
    # Style
    "contemporary",
    "vintage",
    "mid-century",
    "modern",
    "industrial",
    "rustic",
    "boho",
    "glam",
    # Material / finish
    "wood",
    "metal",
    "steel",
    "leather",
    "velvet",
    "rattan",
    "wicker",
    "acrylic",
    "plastic",
    "glass",
    "fabric",
    "boucle",
    # Color facets observed in vendor catalogs
    "black",
    "white",
    "ivory",
    "cream",
    "beige",
    "brown",
    "tan",
    "red",
    "orange",
    "yellow",
    "gold",
    "green",
    "teal",
    "turquoise",
    "blue",
    "navy",
    "purple",
    "pink",
    "grey",
    "silver",
    "clear",
    "multicolor",
    # Functional attributes
    "adjustable",
    "swivel",
    "rolling",
    "customizable",
)

_CANONICAL_ALIASES: dict[str, str] = {
    "tables": "table",
    "wooden": "wood",
    "chairs": "chair",
    "childrens": "kids",
    "children's": "kids",
    "midcentury": "mid-century",
    "mid-century-modern": "mid-century",
}

_TAG_RULES: dict[str, tuple[str, ...]] = {
    "seating": (
        r"\bseating\b",
        r"\bchair\b",
        r"\barmchair\b",
        r"\bstool\b",
        r"\bbench\b",
        r"\bsofa\b",
        r"\btwo[- ]seater\b",
        r"\blounge\b",
    ),
    "furniture": (r"\bchair\b", r"\btable\b", r"\bbar\b", r"\bbench\b", r"\bsofa\b"),
    "chair": (r"\bchair\b", r"\barmchair\b"),
    "armchair": (r"\barmchair\b", r"\barm chair\b"),
    "lounge": (r"\blounge\b", r"\blow-slung\b"),
    "sofa": (r"\bsofa\b", r"\btwo[- ]seater\b"),
    "bench": (r"\bbench\b",),
    "stool": (r"\bstool\b",),
    "table": (r"\btable\b",),
    "bar": (r"\bbar\b",),
    "glassware": (r"\bglassware\b", r"\bwine glass\b", r"\bwater glass\b", r"\bcoupe\b", r"\bflute glass\b"),
    "china": (r"\bchina\b", r"\bplate\b", r"\bsaucer\b", r"\bporcelain\b"),
    "flatware": (r"\bflatware\b", r"\bfork\b", r"\bknife\b", r"\bspoon\b"),
    "service-equipment": (r"\bserving tray\b", r"\bcarafe\b", r"\bpitcher\b", r"\bcoffee urn\b", r"\bdispenser\b"),
    "event-equipment": (r"\bstanchion\b", r"\beasel\b", r"\bluggage cart\b", r"\bsteamer\b"),
    "bistro": (r"\bbistro\b", r"\bcafe chair\b"),
    "folding": (r"\bfold(?:ing|able)\b",),
    "stackable": (r"\bstackable\b", r"\bstacking\b"),
    "kids": (r"\bkids?\b", r"\bchildren(?:'s)?\b", r"\bbooster\b", r"\bhigh chair\b"),
    "outdoor": (
        r"\boutdoors?\b",
        r"\bpatios?\b",
        r"\blawn\b",
        r"\bpool(?:side)?\b",
        r"\bbeach\b",
    ),
    "dining": (r"\bdining\b", r"\bdinner\b"),
    "cocktail": (r"\bcocktail\b",),
    "set": (r"\bset\b", r"\bduo\b", r"\bwith ottoman\b"),
    "contemporary": (r"\bcontemporary\b",),
    "vintage": (r"\bvintage\b", r"\bantique\b"),
    "mid-century": (r"\bmid[- ]?century\b", r"\b1960s\b", r"\b1970s\b"),
    "modern": (r"\bmodern(?:ist)?\b", r"\bpostmodern\b"),
    "industrial": (r"\bindustrial\b", r"\butilitarian\b"),
    "rustic": (r"\brustic\b", r"\breclaimed\b"),
    "boho": (r"\bboho\b", r"\bbohemian\b"),
    "glam": (r"\bglam\b", r"\bluxe\b"),
    "wood": (r"\bwood(?:en)?\b", r"\bteak\b", r"\boak\b", r"\bwalnut\b", r"\bplywood\b", r"\bbentwood\b"),
    "metal": (r"\bmetal\b", r"\biron\b", r"\bchrome\b", r"\baluminum\b", r"\bbrass\b"),
    "steel": (r"\bsteel\b",),
    "leather": (r"\bleather(?:ette)?\b", r"\bvegan leather\b"),
    "velvet": (r"\bvelvet\b",),
    "rattan": (r"\brattan\b", r"\bcane\b"),
    "wicker": (r"\bwicker\b",),
    "acrylic": (r"\bacrylic\b", r"\blucite\b"),
    "plastic": (r"\bplastic\b", r"\bpolypropylene\b", r"\bfiberglass\b"),
    "glass": (r"\bglass\b",),
    "fabric": (r"\bfabric\b", r"\bupholster(?:ed|y)\b", r"\blinen\b", r"\bcotton\b"),
    "boucle": (r"\bboucl[eé]\b",),
    "black": (r"\bblack\b",),
    "white": (r"\bwhite\b",),
    "ivory": (r"\bivory\b",),
    "cream": (r"\bcream(?:y)?\b",),
    "beige": (r"\bbeige\b", r"\balmond\b"),
    "brown": (r"\bbrown\b", r"\bcognac\b", r"\btobacco\b", r"\bchestnut\b"),
    "tan": (r"\btan\b", r"\btaupe\b"),
    "red": (r"\bred\b", r"\bcranberry\b", r"\bburgundy\b", r"\bmaroon\b"),
    "orange": (r"\borange\b", r"\btangerine\b", r"\bterracotta\b"),
    "yellow": (r"\byellow\b", r"\bsaffron\b", r"\blemon\b", r"\bmaize\b"),
    "gold": (r"\bgold(?:en)?\b", r"\bbrass\b"),
    "green": (r"\bgreen\b", r"\bolive\b", r"\bsage\b", r"\bmint\b"),
    "teal": (r"\bteal\b", r"\bblue-green\b", r"\bsea glass\b"),
    "turquoise": (r"\bturquoise\b",),
    "blue": (r"\bblue\b", r"\bceladon\b", r"\bperiwinkle\b"),
    "navy": (r"\bnavy\b",),
    "purple": (r"\bpurple\b", r"\bviolet\b", r"\bplum\b", r"\beggplant\b"),
    "pink": (r"\bpink\b", r"\bblush\b", r"\brose\b", r"\braspberry\b"),
    "grey": (r"\bgr[ae]y\b", r"\bslate\b", r"\bcharcoal\b"),
    "silver": (r"\bsilver\b", r"\bchrome\b"),
    "clear": (r"\bclear\b", r"\btransparent\b"),
    "multicolor": (r"\bmulticolou?r\b", r"\bcolorful\b", r"\bprismatic\b"),
    "adjustable": (r"\badjustable\b", r"\badjusts?\b"),
    "swivel": (r"\bswivel\b",),
    "rolling": (r"\brolling\b", r"\bcasters?\b"),
    "customizable": (r"\bcustomizable\b", r"\bcustom branding\b", r"\bcustom lighting\b"),
    "lighting": (r"\blighting\b", r"\buplights?\b", r"\blamps?\b", r"\blanterns?\b"),
    "linens": (r"\blinens?\b", r"\btablecloth\b", r"\bnapkins?\b"),
    "decor": (r"\bdecor\b", r"\bcandelabra\b", r"\bcandles?\b"),
    "tenting": (r"\btents?\b", r"\bcanop(?:y|ies)\b"),
    "staging": (r"\bstag(?:e|ing)\b", r"\bplatform\b"),
    "av": (r"\baudio visual\b", r"\bprojector\b", r"\bspeakers?\b", r"\bmicrophones?\b"),
    "signage": (r"\bsignage\b", r"\bsigns?\b"),
}

COLOR_TAGS: frozenset[str] = frozenset(
    {
        "black",
        "white",
        "ivory",
        "cream",
        "beige",
        "brown",
        "tan",
        "red",
        "orange",
        "yellow",
        "gold",
        "green",
        "teal",
        "turquoise",
        "blue",
        "navy",
        "purple",
        "pink",
        "grey",
        "silver",
        "clear",
        "multicolor",
    }
)

# Priority when merging tags (ADR / Phase 2 plan): file > llm > defaults
TAG_PRIORITY = ("file", "llm", "default")


def normalize_tag(tag: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", tag.strip().lower()).strip("-")
    return _CANONICAL_ALIASES.get(normalized, normalized)


def derive_tags(*parts: str | None) -> list[str]:
    """Derive controlled tags from item text without an LLM call."""
    text = " ".join(part for part in parts if part).lower()
    return [
        tag
        for tag, patterns in _TAG_RULES.items()
        if any(re.search(pattern, text) for pattern in patterns)
    ]


def infer_category(*parts: str | None) -> str | None:
    """Infer one normalized top-level category from item text."""
    tags = set(derive_tags(*parts))
    for category in (
        "seating",
        "linens",
        "table",
        "bar",
        "glassware",
        "china",
        "flatware",
        "service-equipment",
        "event-equipment",
        "lighting",
        "decor",
        "tenting",
        "staging",
        "av",
        "signage",
    ):
        if category in tags:
            return category
    return None


def controlled_tags(tags: Iterable[str]) -> list[str]:
    """Normalize, de-duplicate, and discard tags outside the controlled set."""
    allowed = set(STARTER_TAGS)
    result: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = normalize_tag(raw)
        if tag in allowed and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def merge_tags(
    *,
    file_tags: list[str],
    llm_tags: list[str],
    derived_tags: list[str] | None = None,
) -> tuple[list[str], str]:
    """Return controlled tags and an accurate provenance label."""
    file_values = controlled_tags(file_tags)
    llm_values = controlled_tags(llm_tags)
    derived_values = controlled_tags(derived_tags or [])
    merged = controlled_tags(file_values + derived_values + llm_values)

    sources = sum(bool(values) for values in (file_values, derived_values, llm_values))
    if sources > 1:
        source = "mixed"
    elif file_values:
        source = "file"
    elif llm_values:
        source = "llm"
    elif derived_values:
        source = "derived"
    else:
        source = "derived"
    return merged, source

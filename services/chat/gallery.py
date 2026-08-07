"""Structured chat reply with optional catalog gallery (images + links)."""

from __future__ import annotations

from dataclasses import dataclass, field

_MAX_DESCRIPTION_CHARS = 160

# Stable marker so persisted display text can be split back apart: the cards
# carry short-lived presigned URLs that must never re-enter the model context.
GALLERY_MARKER = "<!-- catalog-cards -->"


@dataclass(frozen=True)
class GalleryItem:
    """One catalog card to render in the chat UI."""

    name: str
    vendor: str | None = None
    unit_price: float | None = None
    currency: str = "USD"
    quantity: float | None = None
    product_url: str | None = None
    image_url: str | None = None
    tags: tuple[str, ...] = ()
    description: str | None = None
    dimensions_text: str | None = None
    colors: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentReply:
    text: str
    gallery: tuple[GalleryItem, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return self.text


def cards_to_gallery(
    cards: list[dict],
    *,
    limit: int = 6,
) -> tuple[GalleryItem, ...]:
    """Build UI gallery cards from search_inventory tool hit cards."""
    items: list[GalleryItem] = []
    for card in cards:
        if len(items) >= limit:
            break
        name = str(card.get("name") or "").strip()
        if not name:
            continue
        image_urls = card.get("image_urls") or []
        image_url = image_urls[0] if image_urls else None
        product_url = card.get("product_url")
        if isinstance(product_url, str):
            product_url = product_url.strip() or None
        else:
            product_url = None
        tags = tuple(str(t) for t in (card.get("tags") or [])[:6])
        colors = tuple(str(c) for c in (card.get("colors") or [])[:4])
        price = card.get("unit_price")
        qty = card.get("quantity")
        items.append(
            GalleryItem(
                name=name,
                vendor=(str(card["vendor"]).strip() if card.get("vendor") else None),
                unit_price=float(price) if isinstance(price, (int, float)) else None,
                currency=str(card.get("currency") or "USD"),
                quantity=float(qty) if isinstance(qty, (int, float)) else None,
                product_url=product_url,
                image_url=image_url if isinstance(image_url, str) else None,
                tags=tags,
                description=_one_line(card.get("description")),
                dimensions_text=_one_line(card.get("dimensions_text"), limit=80),
                colors=colors,
            )
        )
    return tuple(items)


def gallery_markdown(items: list[GalleryItem] | tuple[GalleryItem, ...]) -> str:
    """Per-item cards: image, price/qty, key attributes, and new-tab links."""
    if not items:
        return ""

    lines = ["", GALLERY_MARKER, "", "---", "", "### Matching catalog items", ""]
    for position, item in enumerate(items, start=1):
        lines.append(f"**{position}. {item.name}** — {_price_qty(item)}")
        lines.append("")
        if item.image_url:
            lines.append(f"![{item.name}]({item.image_url})")
            lines.append("")
        for label, value in _attributes(item):
            lines.append(f"- **{label}:** {value}")
        links = _links(item)
        if links:
            lines.append(f"- {links}")
        lines.append("")
    return "\n".join(lines).rstrip()


def strip_gallery(content: str) -> str:
    """Drop rendered cards, keeping only the narrative the model should recall."""
    text = content or ""
    marker_at = text.find(GALLERY_MARKER)
    if marker_at != -1:
        return text[:marker_at].rstrip()
    # Messages persisted before the marker existed still end with a card block.
    legacy_at = text.find("### Matching catalog items")
    if legacy_at != -1:
        return text[:legacy_at].rstrip().removesuffix("---").rstrip()
    return text.strip()


def _price_qty(item: GalleryItem) -> str:
    if item.unit_price is None:
        price = "price not in catalog"
    elif item.currency and item.currency != "USD":
        price = f"{item.unit_price:g} {item.currency}"
    else:
        price = f"${item.unit_price:g}"
    qty = f"qty {item.quantity:g}" if item.quantity is not None else "qty unknown"
    return f"{price} · {qty}"


def _attributes(item: GalleryItem) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if item.vendor:
        rows.append(("Vendor", item.vendor))
    if item.dimensions_text:
        rows.append(("Dimensions", item.dimensions_text))
    if item.colors:
        rows.append(("Colors", ", ".join(item.colors)))
    if item.tags:
        rows.append(("Tags", ", ".join(item.tags)))
    if item.description:
        rows.append(("Details", item.description))
    return rows


def _links(item: GalleryItem) -> str:
    parts: list[str] = []
    if item.image_url:
        parts.append(f"[Open image]({item.image_url})")
    if item.product_url:
        parts.append(f"[Product page]({item.product_url})")
    return " · ".join(parts)


def _one_line(value: object, *, limit: int = _MAX_DESCRIPTION_CHARS) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"

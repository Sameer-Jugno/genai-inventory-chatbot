from __future__ import annotations

import base64
import io
import json
import unittest
from pathlib import Path

import openpyxl
from openpyxl.drawing.image import Image
from pypdf import PdfWriter

from services.ingestion.errors import InventoryFormatError
from services.ingestion.ids import stable_item_id
from services.ingestion.parsers.csv_parser import parse_csv
from services.ingestion.parsers.dimensions_parser import parse_dimensions
from services.ingestion.parsers.fixed_width_parser import parse_fixed_width_inventory
from services.ingestion.parsers.html_parser import chunk_text, html_to_text
from services.ingestion.parsers.pdf_parser import (
    chunk_pdf_pages,
    is_visual_catalog,
    split_pdf_pages,
)
from services.ingestion.parsers.pdf_catalog_parser import parse_product_page_pdf
from services.ingestion.parsers.xlsx_parser import parse_xlsx_inventory
from shared.schema import (
    EMBEDDING_DIMENSIONS,
    InventoryItem,
    SourceType,
    TagSource,
    derive_tags,
)


class CsvParserTests(unittest.TestCase):
    def test_parses_real_catalog_header_shape(self) -> None:
        content = (
            "product-link,product-link-href,product-description,"
            "product-quantity,product-price,product-dimensions,tags\n"
            'CH869 Demo Sling Chair,https://example.test/ch869,Teak outdoor chair,'
            '2,165,"37″H × 25″W × 44″D","chair, contemporary"\n'
        )

        [row] = parse_csv(
            content=content,
            vendor="sample-vendor",
            source_ref="s3://data/uploads/sample/catalog.csv",
        )

        self.assertEqual(row.item.source_item_id, "CH869")
        self.assertEqual(row.item.name, "Demo Sling Chair")
        self.assertEqual(row.item.category, "seating")
        self.assertEqual(row.item.unit_price, 165)
        self.assertEqual(row.item.currency, "USD")
        self.assertEqual(row.item.product_url, "https://example.test/ch869")
        self.assertIn("outdoor", row.item.tags)

    def test_rejects_non_inventory_csv(self) -> None:
        with self.assertRaises(InventoryFormatError):
            parse_csv(
                content="unrelated prose\nsome sentence\n",
                vendor="sample-vendor",
                source_ref="s3://data/uploads/sample/not-inventory.csv",
            )


class FixedWidthParserTests(unittest.TestCase):
    def test_parses_dataframe_style_export_without_pandas(self) -> None:
        widths = (30, 55, 70, 16, 13, 28, 24)
        headers = (
            "product-link",
            "product-link-href",
            "product-description",
            "product-quantity",
            "product-price",
            "product-dimensions",
            "tags",
        )
        values = (
            "CH100 Demo Rattan Lounge Chair",
            "https://example.test/ch100",
            "A vintage rattan chair for patios.",
            "4",
            "275",
            "30″H × 28″W × 31″D",
            "chair, vintage",
        )
        content = " ".join(
            value.rjust(width) for value, width in zip(headers, widths, strict=True)
        )
        content += "\n" + " ".join(
            value.rjust(width) for value, width in zip(values, widths, strict=True)
        )

        [row] = parse_fixed_width_inventory(
            content=content,
            vendor="sample-vendor",
            source_ref="s3://data/uploads/sample/catalog.txt",
        )

        self.assertEqual(row.item.source_item_id, "CH100")
        self.assertEqual(row.item.quantity, 4)
        self.assertEqual(row.item.unit_price, 275)
        self.assertIn("rattan", row.item.tags)
        self.assertIn("outdoor", row.item.tags)


class XlsxParserTests(unittest.TestCase):
    def test_parses_scraper_fields_quantity_prose_and_embedded_image(self) -> None:
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(
            [
                "product-title",
                "product-link-href",
                "product-description",
                "product-quantity",
                "product-dimensions",
                "web-scraper-start-url",
                "colors",
            ]
        )
        sheet.append(
            [
                "Test Blue Stool",
                "https://example.test/products/blue-stool",
                "Blue woven outdoor stool",
                "35 pieces available",
                '21" diameter x 18" h',
                "https://example.test/collection/seating",
                "Blue",
            ]
        )
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNg"
            "YAAAAAMAASsJTYQAAAAASUVORK5CYII="
        )
        image = Image(io.BytesIO(image_bytes))
        image.anchor = "H2"
        sheet.add_image(image)
        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()

        [row] = parse_xlsx_inventory(
            data=buffer.getvalue(),
            vendor="sample-vendor",
            source_ref="s3://data/uploads/sample/catalog.xlsx",
        )

        self.assertEqual(row.item.quantity, 35)
        self.assertEqual(row.item.category, "seating")
        self.assertEqual(row.item.colors, ["blue"])
        self.assertEqual(row.item.dimensions.diameter, 21)  # type: ignore[union-attr]
        self.assertEqual(len(row.embedded_images), 1)


class PdfChunkTests(unittest.TestCase):
    def test_chunks_on_page_boundaries_and_keeps_page_markers(self) -> None:
        pages = [(1, "a" * 600), (2, "b" * 600), (3, "c" * 100)]
        chunks = chunk_pdf_pages(pages, max_chars=1_000)

        self.assertEqual([(c.first_page, c.last_page) for c in chunks], [(1, 1), (2, 3)])
        self.assertTrue(chunks[0].text.startswith("[PAGE 1]"))
        self.assertIn("[PAGE 3]", chunks[1].text)

    def test_deterministic_product_page_catalog(self) -> None:
        pages = [
            (
                2,
                "Header\nCH100 Test Lounge Chair\n$300 each — 2 for rent\n"
                '32″H × 37″W × 32″D\nView more info',
            ),
            (
                3,
                "Header\nCH101 Test Side Chair\n$195 — 1 for rent\n"
                '30″H × 29″W × 24″D\nView more info',
            ),
        ]
        rows = parse_product_page_pdf(
            pages=pages,
            vendor="sample-vendor",
            source_ref="s3://data/uploads/sample/catalog.pdf",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].item.source_item_id, "CH100")
        self.assertEqual(rows[0].item.unit_price, 300)
        self.assertEqual(rows[0].item.source_page, 2)

    def test_visual_catalog_detection_and_page_split(self) -> None:
        pages = [
            (1, "specialty chairs\nChair One\nChair Two\nChair Three\nChair Four"),
            (2, "benches\nBench One\nBench Two\nBench Three\nBench Four"),
        ]
        self.assertTrue(is_visual_catalog(pages))

        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_blank_page(width=100, height=100)
        source = io.BytesIO()
        writer.write(source)
        split = split_pdf_pages(source.getvalue(), [1, 2])
        self.assertEqual([page for page, _ in split], [1, 2])
        self.assertTrue(all(data.startswith(b"%PDF") for _, data in split))


class HtmlParserTests(unittest.TestCase):
    def test_removes_non_visible_content_and_chunks_without_loss(self) -> None:
        text = html_to_text("<style>hidden</style><h1>Chair</h1><p>Visible details</p>")
        self.assertNotIn("hidden", text)
        self.assertIn("Visible details", text)

        source = ("a" * 700) + "\n\n" + ("b" * 700)
        chunks = chunk_text(source, max_chars=1_000)
        self.assertEqual(len(chunks), 2)
        self.assertEqual("".join(chunks).replace("\n\n", ""), source.replace("\n\n", ""))


class DimensionParserTests(unittest.TestCase):
    def test_parses_height_width_depth(self) -> None:
        parsed = parse_dimensions("37″H × 25″W × 44″D")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual((parsed.height, parsed.width, parsed.depth), (37, 25, 44))
        self.assertEqual(parsed.unit, "in")

    def test_converts_feet_to_inches(self) -> None:
        parsed = parse_dimensions("6' L x 30\" W x 30\" H")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.length, 72)
        self.assertEqual(parsed.width, 30)


class SchemaAndTagTests(unittest.TestCase):
    def test_sku_identity_survives_file_rename_and_row_reordering(self) -> None:
        first = stable_item_id(
            "sample-vendor",
            "s3://data/uploads/sample/old.csv",
            0,
            "Old title",
            source_item_id="CH100",
        )
        second = stable_item_id(
            "sample-vendor",
            "s3://data/uploads/sample/new.csv",
            99,
            "Edited title",
            source_item_id="CH100",
        )
        self.assertEqual(first, second)

    def test_embedding_text_and_opensearch_payload_include_retrieval_fields(self) -> None:
        item = InventoryItem(
            item_id="id-1",
            vendor="sample-vendor",
            source_type=SourceType.UPLOAD,
            source_ref="s3://data/uploads/sample/catalog.csv",
            source_item_id="CH100",
            name="Demo Lounge Chair",
            description="Blue velvet lounge chair",
            category="seating",
            quantity=2,
            unit_price=300,
            currency="USD",
            features=["swivels"],
            tags=["chair", "lounge", "velvet", "swivel"],
            tag_source=TagSource.DERIVED,
            ingested_at=1,
        )

        payload = item.to_opensearch_source([0.0] * EMBEDDING_DIMENSIONS)
        self.assertIn("Demo Lounge Chair", payload["search_text"])
        self.assertIn("category: seating", payload["search_text"])
        self.assertEqual(payload["source_item_id"], "CH100")
        self.assertGreater(payload["source_quality"], 0)

    def test_opensearch_mapping_covers_schema_and_computed_fields(self) -> None:
        root = Path(__file__).resolve().parents[1]
        mapping = json.loads(
            (root / "scripts" / "opensearch_index_mapping.json").read_text()
        )
        properties = set(mapping["mappings"]["properties"])
        expected = set(InventoryItem.model_fields) | {
            "search_text",
            "source_quality",
            "embedding",
        }
        self.assertEqual(expected - properties, set())

    def test_deterministic_tags_cover_supplied_catalog_language(self) -> None:
        tags = derive_tags(
            "Vintage Acrylic Folding Bistro Chair",
            "Stackable outdoor chair with a chrome frame and velvet cushion",
        )
        for expected in (
            "seating",
            "chair",
            "bistro",
            "folding",
            "stackable",
            "outdoor",
            "vintage",
            "metal",
            "acrylic",
            "velvet",
        ):
            self.assertIn(expected, tags)


if __name__ == "__main__":
    unittest.main()

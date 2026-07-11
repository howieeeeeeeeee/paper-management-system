from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperhub.link_context import (
    UnsafeUrlError,
    extract_urls,
    parse_landing_page,
    prepare_link_context,
    public_google_drive_download_url,
    validate_public_url,
)
from scripts.paper_fetcher import PaperMetadata


class LinkContextTests(unittest.TestCase):
    def test_extracts_unique_urls_from_named_heading(self) -> None:
        text = """# Backlog
- https://old.example/paper

## Paper Organizer Integration Tests
- https://example.com/one
- [Two](https://example.com/two)
- https://example.com/one

## Later
- https://example.com/three
"""
        self.assertEqual(
            extract_urls(text, "Paper Organizer Integration Tests"),
            ["https://example.com/one", "https://example.com/two"],
        )

    def test_rejects_local_network_urls(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            validate_public_url("http://127.0.0.1/paper")
        with self.assertRaises(UnsafeUrlError):
            validate_public_url("http://user:secret@example.com/paper")

    def test_builds_public_google_drive_download_url(self) -> None:
        self.assertEqual(
            public_google_drive_download_url(
                "https://drive.google.com/file/d/example-id/view"
            ),
            "https://drive.usercontent.google.com/download?"
            "id=example-id&export=download&confirm=t",
        )
        self.assertIsNone(
            public_google_drive_download_url("https://example.com/file/example-id")
        )

    def test_parses_citation_meta_and_json_ld(self) -> None:
        html = """
<html><head>
<meta name="citation_title" content="A Useful Paper">
<meta name="citation_author" content="Ada Example">
<meta name="citation_publication_date" content="2025-03-04">
<meta name="citation_journal_title" content="Journal of Tests">
<meta name="citation_doi" content="10.1234/test.1">
<meta name="citation_abstract" content="Exact public abstract.">
<meta name="citation_pdf_url" content="/paper.pdf">
<link rel="canonical" href="https://example.com/article">
</head></html>
"""
        parsed = parse_landing_page(html, "https://example.com/start")
        self.assertEqual(parsed["title"], "A Useful Paper")
        self.assertEqual(parsed["authors"], ["Ada Example"])
        self.assertEqual(parsed["year"], 2025)
        self.assertEqual(parsed["doi"], "10.1234/test.1")
        self.assertEqual(parsed["pdf_url"], "https://example.com/paper.pdf")

    @patch("paperhub.link_context.socket.getaddrinfo")
    @patch("paperhub.link_context.resolve_by_title")
    @patch("paperhub.link_context.resolve_by_url")
    @patch("paperhub.link_context.fetch_public_resource")
    def test_prepares_text_context_and_metadata_route(
        self,
        fetch_resource,
        resolve_url,
        resolve_title,
        getaddrinfo,
    ) -> None:
        getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        fetch_resource.return_value = (
            "https://example.com/article",
            "text/html",
            b"""
<meta name="citation_title" content="A Useful Paper">
<meta name="citation_author" content="Ada Example">
<meta name="citation_publication_date" content="2025">
<meta name="citation_journal_title" content="Journal of Tests">
<meta name="citation_abstract" content="Exact public abstract.">
""",
        )
        resolve_url.return_value = PaperMetadata(url="https://example.com/article")
        resolve_title.return_value = None
        with tempfile.TemporaryDirectory() as tmp:
            result = prepare_link_context(
                "https://example.com/article",
                "metadata-only",
                root=Path(tmp),
                session=object(),
            )
            text = Path(result["context_path"]).read_text(encoding="utf-8")
            machine = json.loads(
                text.split("```json\n", 1)[1].split("\n```", 1)[0]
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["route"], "link-metadata")
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(machine["metadata"]["abstract"], "Exact public abstract.")
        self.assertIn("## Coding-Agent Additions", text)
        self.assertNotIn("## Public PDF First Pages", text)

    @patch("paperhub.link_context.socket.getaddrinfo")
    @patch("paperhub.link_context.resolve_by_url")
    @patch("paperhub.link_context.fetch_public_resource")
    def test_public_pdf_routes_follow_requested_mode(
        self,
        fetch_resource,
        resolve_url,
        getaddrinfo,
    ) -> None:
        getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        fetch_resource.return_value = (
            "https://example.com/paper.pdf",
            "application/pdf",
            b"%PDF-1.4\npublic test fixture",
        )
        resolve_url.return_value = PaperMetadata(
            title="Fixture Paper",
            authors=["Ada Example"],
            year=2026,
            journal="Journal of Tests",
            abstract="Fixture abstract.",
            url="https://example.com/paper",
        )
        expected = {
            "auto": "pdf-pending-mode",
            "metadata-only": "pdf-metadata",
            "full": "pdf-full",
        }
        for requested_mode, route in expected.items():
            with self.subTest(requested_mode=requested_mode), tempfile.TemporaryDirectory() as tmp:
                result = prepare_link_context(
                    "https://example.com/paper.pdf",
                    requested_mode,
                    root=Path(tmp),
                    session=object(),
                )
                self.assertEqual(result["route"], route)
                self.assertTrue(Path(result["public_pdf_path"]).exists())


if __name__ == "__main__":
    unittest.main()

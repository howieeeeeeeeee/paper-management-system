from __future__ import annotations

import unittest

from paperhub import metadata_resolution
from paperhub.metadata_resolution import (
    VERSION_PUBLISHED,
    normalize_doi,
    reconstruct_abstract,
    resolve_by_url,
)


class MetadataResolutionTests(unittest.TestCase):
    def test_normalizes_doi_forms(self) -> None:
        self.assertEqual(
            normalize_doi("https://doi.org/10.1234/example.1"),
            "10.1234/example.1",
        )
        self.assertEqual(normalize_doi("doi:10.1234/example.1"), "10.1234/example.1")

    def test_reconstructs_openalex_abstract(self) -> None:
        self.assertEqual(
            reconstruct_abstract({"second": [1], "First": [0], "third": [2]}),
            "First second third",
        )

    def test_unknown_pdf_url_returns_minimal_metadata(self) -> None:
        meta = resolve_by_url(
            "https://example.com/paper.pdf?download=1",
            session=object(),
            email="reader@example.com",
        )

        self.assertIsNotNone(meta)
        assert meta is not None
        self.assertEqual(meta.oa_pdf_url, "https://example.com/paper.pdf?download=1")
        self.assertEqual(meta.source, "url")
        self.assertEqual(meta.version, VERSION_PUBLISHED)

    def test_module_exposes_no_downloader_cli_or_file_writers(self) -> None:
        for removed_name in (
            "build_arg_parser",
            "download_pdf",
            "resolve",
            "write_sidecar",
        ):
            with self.subTest(name=removed_name):
                self.assertFalse(hasattr(metadata_resolution, removed_name))


if __name__ == "__main__":
    unittest.main()

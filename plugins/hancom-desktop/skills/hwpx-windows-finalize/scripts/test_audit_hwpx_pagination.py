from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import fitz

from audit_hwpx_pagination import (
    audit_hwpx,
    audit_pdf,
    parse_expected_counts,
    result_exit_code,
    write_new,
)


def make_pdf(path: Path, page_texts: list[str]) -> None:
    document = fitz.open()
    for text in page_texts:
        page = document.new_page()
        page.insert_text((72, 72), text)
    document.save(path)
    document.close()


class PaginationAuditTests(unittest.TestCase):
    def make_hwpx(self, path: Path, sections: list[tuple[str, str]]) -> None:
        items = "".join(
            f'<item id="s{i}" href="{name}"/>' for i, (name, _) in enumerate(sections)
        )
        refs = "".join(f'<itemref idref="s{i}"/>' for i in range(len(sections)))
        with zipfile.ZipFile(path, "w") as package:
            package.writestr("Contents/content.hpf", f"<package><manifest>{items}</manifest><spine>{refs}</spine></package>")
            for name, content in sections:
                package.writestr(name, content)

    def test_trailing_blank_paragraph_is_only_a_signal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.hwpx"
            self.make_hwpx(source, [("Contents/section0.xml", "<sec><p><t>표식</t></p><p><t> </t></p></sec>")])
            result = audit_hwpx(source)
            self.assertTrue(result["trailingBlankParagraph"])
            self.assertEqual(result["layoutConclusion"], "NOT_RENDERED")
            self.assertEqual(result["status"], "PREFLIGHT_COMPLETE")

    def test_spine_order_and_own_paragraphs_exclude_nested_cells(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "spine.hwpx"
            self.make_hwpx(
                source,
                [
                    ("Contents/section1.xml", "<sec><p><t>first</t><tbl><p><t>cell</t></p></tbl></p></sec>"),
                    ("Contents/section0.xml", "<sec><p><t>last</t></p></sec>"),
                ],
            )
            result = audit_hwpx(source)
        self.assertEqual(result["sections"], ["Contents/section1.xml", "Contents/section0.xml"])
        self.assertEqual(result["counts"]["paragraphs"], 2)
        self.assertEqual(result["trailingParagraph"]["text"], "last")

    def test_missing_spine_is_unverified_and_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "unsupported.hwpx"
            with zipfile.ZipFile(source, "w") as package:
                package.writestr("Contents/section0.xml", "<s><p/></s>")
            result = audit_hwpx(source)
        self.assertEqual(result["status"], "UNVERIFIED_STRUCTURE")
        self.assertEqual(result_exit_code(result), 1)

    def test_unrecognized_root_and_no_paragraphs_are_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wrong_root = Path(directory) / "wrong-root.hwpx"
            no_paragraph = Path(directory) / "no-paragraph.hwpx"
            self.make_hwpx(wrong_root, [("Contents/section0.xml", "<unknown><p/></unknown>")])
            self.make_hwpx(no_paragraph, [("Contents/section0.xml", "<sec><tbl/></sec>")])
            wrong_result = audit_hwpx(wrong_root)
            empty_result = audit_hwpx(no_paragraph)
        self.assertEqual(wrong_result["status"], "UNVERIFIED_STRUCTURE")
        self.assertEqual(empty_result["status"], "UNVERIFIED_STRUCTURE")

    def test_existing_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            output.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_new(output, {"ok": True})

    def test_normal_labels_and_order_are_observed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "normal.pdf"
            make_pdf(source, ["FIRST_MARK", "LAST_MARK"])
            result = audit_pdf(
                source,
                ["FIRST_MARK", "LAST_MARK"],
                {"FIRST_MARK": 1, "LAST_MARK": 1},
                ["FIRST_MARK", "LAST_MARK"],
            )
        self.assertEqual(result["status"], "OBSERVED")
        self.assertTrue(result["orderMatched"])

    def test_same_page_duplicate_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "duplicate.pdf"
            make_pdf(source, ["FIRST_MARK FIRST_MARK LAST_MARK"])
            result = audit_pdf(
                source,
                ["FIRST_MARK", "LAST_MARK"],
                {"FIRST_MARK": 1, "LAST_MARK": 1},
                ["FIRST_MARK", "LAST_MARK"],
            )
        self.assertEqual(result["labelOccurrenceCounts"]["FIRST_MARK"], 2)
        self.assertIn("FIRST_MARK", result["labelCountMismatches"])
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_reverse_page_order_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "reverse.pdf"
            make_pdf(source, ["LAST_MARK", "FIRST_MARK"])
            result = audit_pdf(
                source,
                ["FIRST_MARK", "LAST_MARK"],
                {"FIRST_MARK": 1, "LAST_MARK": 1},
                ["FIRST_MARK", "LAST_MARK"],
            )
        self.assertFalse(result["orderMatched"])
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_count_parser_rejects_duplicate_contracts(self) -> None:
        with self.assertRaises(ValueError):
            parse_expected_counts(["MARK=1", "MARK=2"])

    def test_empty_label_and_order_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "normal.pdf"
            make_pdf(source, ["MARK"])
            with self.assertRaises(ValueError):
                audit_pdf(source, [""])
            with self.assertRaises(ValueError):
                audit_pdf(source, [], expected_order=[""])

    def test_zero_expected_count_accepts_absence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "absent.pdf"
            make_pdf(source, ["OTHER"])
            result = audit_pdf(source, [], {"FORBIDDEN": 0})
        self.assertEqual(result["missingLabels"], [])
        self.assertEqual(result["labelCountMismatches"], {})
        self.assertEqual(result["status"], "OBSERVED")

    def test_source_change_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "normal.pdf"
            make_pdf(source, ["MARK"])
            with mock.patch("audit_hwpx_pagination.sha256", side_effect=["before", "after"]):
                result = audit_pdf(source, ["MARK"])
        self.assertFalse(result["sourceUnchanged"])
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result_exit_code(result), 1)

    def test_hwpx_source_change_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "changed.hwpx"
            self.make_hwpx(source, [("Contents/section0.xml", "<sec><p><t>text</t></p></sec>")])
            with mock.patch("audit_hwpx_pagination.sha256", side_effect=["before", "after"]):
                result = audit_hwpx(source)
        self.assertFalse(result["sourceUnchanged"])
        self.assertEqual(result["status"], "UNVERIFIED_SOURCE_CHANGED")
        self.assertEqual(result_exit_code(result), 1)


if __name__ == "__main__":
    unittest.main()

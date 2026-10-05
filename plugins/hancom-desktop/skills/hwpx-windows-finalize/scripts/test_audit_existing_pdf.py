import tempfile
import unittest
import zipfile
from pathlib import Path

from audit_existing_pdf import audit_pdf, source_labels, unsafe_output_reason


class ExistingPdfAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.temp.name) / "existing.pdf"
        self.pdf.write_bytes(b"not parsed because tests inject extraction")

    def tearDown(self):
        self.temp.cleanup()

    def test_normal_labels_pass_and_sparse_only_warns(self):
        result = audit_pdf(self.pdf, ["R01"], lambda _: ["R01"])
        self.assertEqual(result["outcome"], "checked_no_source_label_mismatch")
        self.assertEqual(result["findings"][0]["kind"], "sparse_page")

    def test_missing_and_duplicate_labels_fail(self):
        result = audit_pdf(self.pdf, ["R01", "R02"], lambda _: ["R01 R01"])
        self.assertEqual(result["outcome"], "content_mismatch")
        self.assertEqual(result["missing_label_counts"], {"R02": 1})
        self.assertEqual(result["duplicate_label_counts"], {"R01": 1})

    def test_missing_pdf_is_not_checked(self):
        result = audit_pdf(Path(self.temp.name) / "absent.pdf", ["R01"])
        self.assertEqual(result["inspection_state"], "not_checked")
        self.assertEqual(result["reason"], "missing_pdf")

    def test_missing_dependency_is_not_checked(self):
        def no_dependency(_: Path):
            raise ModuleNotFoundError("No module named 'pypdf'", name="pypdf")
        result = audit_pdf(self.pdf, ["R01"], no_dependency)
        self.assertEqual(result["inspection_state"], "not_checked")
        self.assertEqual(result["reason"], "missing_dependency")
        self.assertEqual(result["render_status"], "render_not_performed")

    def test_source_inventory_reads_text_not_attribute_values(self):
        source = Path(self.temp.name) / "source.hwpx"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("Contents/section0.xml", '<root marker="R99"><t>R01</t><p style="R98"><t>keep</t></p></root>')
        self.assertEqual(source_labels(source, r"R\d{2}"), ["R01"])

    def test_empty_or_overlapping_expected_labels_are_not_checked(self):
        empty = audit_pdf(self.pdf, [], lambda _: ["R01"])
        overlap = audit_pdf(self.pdf, ["R1", "R10"], lambda _: ["R10"])
        self.assertEqual(empty["reason"], "empty_expected_labels")
        self.assertEqual(overlap["reason"], "ambiguous_expected_labels")

    def test_existing_or_input_output_paths_are_rejected(self):
        existing = Path(self.temp.name) / "already.json"
        existing.write_text("old", encoding="utf-8")
        self.assertEqual(unsafe_output_reason(existing, [self.pdf]), "unsafe_output_already_exists")
        self.assertEqual(unsafe_output_reason(self.pdf, [self.pdf]), "unsafe_output_matches_input")


if __name__ == "__main__":
    unittest.main()

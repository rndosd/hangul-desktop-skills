from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import pymupdf
import hancom_completion_gate as gate

class PreviewEntry(unittest.TestCase):
    def test_same_pdf_reuses_images_and_detects_changed_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pdf=root/'한글 경로.pdf'
            with pymupdf.open() as doc:
                doc.new_page().insert_text((30,30),'Preview');doc.save(pdf)
            result=gate.preview_pdf(pdf,root/'pages')
            self.assertEqual(result['visual'],'NOT_CHECKED')
            with patch.object(gate,'_render_proofs',side_effect=AssertionError('unnecessary rerender')):
                reused=gate.preview_pdf(pdf,root/'pages');self.assertTrue(reused['reused'])
            Path(result['pages'][0]['image']['path']).write_bytes(b'changed')
            with self.assertRaises(gate.GateError):gate.preview_pdf(pdf,root/'pages')

    def test_changed_pdf_does_not_reuse_old_images(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pdf=root/'document.pdf'
            with pymupdf.open() as doc:doc.new_page();doc.save(pdf)
            gate.preview_pdf(pdf,root/'pages')
            pdf.write_bytes(pdf.read_bytes()+b'\n% changed')
            with self.assertRaises(gate.GateError):gate.preview_pdf(pdf,root/'pages')

if __name__=='__main__':unittest.main()

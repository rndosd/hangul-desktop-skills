"""Validate SFNT metadata portability and rejection, without installing fonts."""
from pathlib import Path
import os, sys, struct, unittest, uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'plugins/hancom-desktop/skills/hwpx/scripts'))
import fresh_header_serialization as header
import font_space_indent as indent

def sfnt(family='Malgun Gothic',panose=None):
    panose=panose or [2,11,5,3,2,0,0,2,0,4]
    os2=bytes(32)+bytes(panose)
    name=family.encode('utf-16-be')
    names=struct.pack('>HHH',0,1,18)+struct.pack('>HHHHHH',3,1,0x409,1,len(name),0)+name
    start=44
    return struct.pack('>IHHHH',0x10000,2,0,0,0)+struct.pack('>4sIII',b'OS/2',0,start,len(os2))+struct.pack('>4sIII',b'name',0,start+len(os2),len(names))+os2+names

class PortableFont(unittest.TestCase):
    def setUp(self):self.path=ROOT/('.test-font-'+uuid.uuid4().hex+'.ttf')
    def tearDown(self):self.path.unlink(missing_ok=True)
    def read(self,data):self.path.write_bytes(data);return header.font_metadata(self.path)
    def test_new_hash_same_family_keeps_native_unverified(self):
        r=self.read(sfnt());self.assertEqual(r['nativeFontQualification'],'UNVERIFIED_LOCAL_FONT_VERSION');self.assertEqual(r['typeInfo']['weight'],'5');self.assertNotEqual(r['sha256'],header.QUALIFIED_FONT_SHA)
    def test_korean_family_accepted(self):self.assertEqual(self.read(sfnt('맑은 고딕'))['panose'],[2,11,5,3,2,0,0,2,0,4])
    def test_other_family_rejected_even_with_matching_panose(self):
        with self.assertRaisesRegex(ValueError,'not Malgun'):self.read(sfnt('Other Font'))
    def test_other_panose_rejected(self):
        with self.assertRaisesRegex(ValueError,'PANOSE'):self.read(sfnt(panose=[2,11,9,3,2,0,0,2,0,4]))
    def test_truncated_directory_rejected(self):
        with self.assertRaises(ValueError):self.read(sfnt()[:20])
    def test_table_outside_file_rejected(self):
        data=bytearray(sfnt());struct.pack_into('>I',data,20,99999)
        with self.assertRaisesRegex(ValueError,'bounds'):self.read(data)
    def test_name_string_outside_table_rejected(self):
        data=bytearray(sfnt());struct.pack_into('>H',data,44+42+16,9999)
        with self.assertRaisesRegex(ValueError,'bounds'):self.read(data)
    def test_real_installed_font_metadata(self):
        font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/malgun.ttf'
        self.assertTrue(font.is_file(),'Windows Malgun Gothic prerequisite missing')
        actual=header.font_metadata(font);self.assertEqual(actual['typeInfo']['familyType'],'FCAT_GOTHIC')
    def test_space_metric_uses_current_windows_root(self):
        indent.space_metric.cache_clear()
        with patch.dict(os.environ,{'WINDIR':str(ROOT/'.test-missing-windows')}),patch.object(Path,'read_bytes',side_effect=FileNotFoundError) as read:
            with self.assertRaises(FileNotFoundError):indent.space_metric('맑은 고딕')
            self.assertEqual(read.call_count,1)

if __name__=='__main__':unittest.main()

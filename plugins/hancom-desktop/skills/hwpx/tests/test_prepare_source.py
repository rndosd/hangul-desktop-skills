from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_source as source_tool


class PrepareSourceTests(unittest.TestCase):
    def setUp(self):
        parent = Path.cwd() / "work" / "hwpx-upgrade"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="source-test-", dir=parent)
        self.folder = Path(self.temporary.name).resolve()
        self.assertTrue(self.folder.is_relative_to(parent.resolve()))
        self.addCleanup(self.temporary.cleanup)
        self.cache = self.folder / "analysis-cache"
        self.first = ROOT / "assets/document-templates/source-library/extra-04.hwpx"
        self.second = ROOT / "assets/document-templates/source-library/extra-02.hwpx"

    def prepare(self, source=None):
        return source_tool.prepare_source(source or self.first, self.cache)

    def test_two_real_sources_reuse_without_reanalysis_or_source_writes(self):
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.first, self.second)}
        for path, expected_tables in ((self.first, 8), (self.second, 4)):
            with self.subTest(source=path.name):
                initial = self.prepare(path)
                self.assertEqual(initial["status"], "ANALYZED")
                self.assertFalse(initial["cacheHit"])
                self.assertEqual(initial["summary"]["tableCount"], expected_tables)
                with patch.object(source_tool, "_analyze", side_effect=AssertionError("cache hit must not analyze")):
                    repeated = self.prepare(path)
                self.assertEqual(repeated["status"], "REUSED")
                self.assertEqual(repeated["analysisPath"], initial["analysisPath"])
                self.assertEqual(repeated["native"], "NOT_CHECKED")
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before[path])
                self.assertEqual(source_tool.check_source(path, initial["analysisPath"])["status"], "CURRENT")

    def test_renamed_identical_source_reuses_analysis_and_returns_current_path(self):
        initial = self.prepare()
        renamed = self.folder / "사용자가 고른 양식.hwpx"
        shutil.copyfile(self.first, renamed)
        result = self.prepare(renamed)
        self.assertTrue(result["cacheHit"])
        self.assertEqual(result["source"], str(renamed))
        self.assertEqual(result["analysisPath"], initial["analysisPath"])
        record = json.loads(Path(result["analysisPath"]).read_text(encoding="utf-8"))
        self.assertEqual(record["payload"]["templateAnalysis"]["source_name"], f"sha256:{result['sourceSha256']}.hwpx")
        self.assertNotIn(str(self.first), Path(result["analysisPath"]).read_text(encoding="utf-8"))

    def test_source_replacement_invalidates_old_analysis_and_produces_new_key(self):
        selected = self.folder / "my-form.hwpx"
        shutil.copyfile(self.first, selected)
        initial = self.prepare(selected)
        shutil.copyfile(self.second, selected)
        check = source_tool.check_source(selected, initial["analysisPath"])
        self.assertEqual(check["status"], "STALE")
        result = self.prepare(selected)
        self.assertFalse(result["cacheHit"])
        self.assertNotEqual(initial["analysisPath"], result["analysisPath"])
        self.assertTrue(Path(initial["analysisPath"]).is_file())

    def test_analysis_contract_change_invalidates_cache(self):
        initial = self.prepare()
        with patch.object(source_tool, "ANALYSIS_CONTRACT", "changed-contract"):
            self.assertEqual(source_tool.check_source(self.first, initial["analysisPath"])["status"], "STALE")
            changed = self.prepare()
        self.assertNotEqual(initial["analysisPath"], changed["analysisPath"])
        self.assertFalse(changed["cacheHit"])

    def test_corrupted_cache_is_rejected_and_preserved(self):
        initial = self.prepare()
        path = Path(initial["analysisPath"])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["payload"]["summary"]["tableCount"] = 9000
        path.write_text(json.dumps(data), encoding="utf-8")
        corrupt = path.read_bytes()
        with self.assertRaises(ValueError):
            self.prepare()
        with self.assertRaises(ValueError):
            source_tool.check_source(self.first, path)
        self.assertEqual(path.read_bytes(), corrupt)

    def test_engine_version_change_invalidates_cache(self):
        initial = self.prepare()
        version = source_tool.version
        with patch.object(source_tool, "version", side_effect=lambda package: "changed-engine" if package == "python-hwpx-automation" else version(package)):
            self.assertEqual(source_tool.check_source(self.first, initial["analysisPath"])["status"], "STALE")
            changed = self.prepare()
        self.assertNotEqual(initial["analysisPath"], changed["analysisPath"])
        self.assertFalse(changed["cacheHit"])

    def test_rejects_legacy_hwp_and_source_as_cache_without_writing(self):
        legacy = self.folder / "old.hwp"
        legacy.write_bytes(b"legacy-test")
        with self.assertRaises(ValueError):
            self.prepare(legacy)
        with self.assertRaises(ValueError):
            source_tool.prepare_source(self.first, self.first)
        self.assertEqual(legacy.read_bytes(), b"legacy-test")
        self.assertFalse(self.cache.exists())

    def test_rejects_cache_inside_skill(self):
        with self.assertRaises(ValueError):
            source_tool.prepare_source(self.first, ROOT / "test-analysis-cache")
        self.assertFalse((ROOT / "test-analysis-cache").exists())

    def test_source_change_during_analysis_publishes_nothing(self):
        selected = self.folder / "changing.hwpx"
        shutil.copyfile(self.first, selected)
        analyze = source_tool._analyze

        def change_during_analysis(path, sha):
            result = analyze(path, sha)
            shutil.copyfile(self.second, selected)
            return result

        with patch.object(source_tool, "_analyze", side_effect=change_during_analysis):
            with self.assertRaises(ValueError):
                self.prepare(selected)
        self.assertFalse(self.cache.exists())

    def test_common_cli_reports_reuse_and_stale_exit(self):
        entry = ROOT / "scripts/hangul_task.py"

        def run(*args):
            process = subprocess.run([sys.executable, "-X", "utf8", "-B", str(entry), *map(str, args)],
                                     capture_output=True, text=True, encoding="utf-8", timeout=60)
            return process.returncode, json.loads(process.stdout)

        code, initial = run("source", self.first, "--cache", self.cache)
        self.assertEqual(code, 0)
        self.assertEqual(initial["status"], "ANALYZED")
        code, repeated = run("source", self.first, "--cache", self.cache)
        self.assertEqual(code, 0)
        self.assertTrue(repeated["cacheHit"])
        code, current = run("source-check", self.first, "--analysis", initial["analysisPath"])
        self.assertEqual(code, 0)
        self.assertEqual(current["status"], "CURRENT")
        code, stale = run("source-check", self.second, "--analysis", initial["analysisPath"])
        self.assertEqual(code, 2)
        self.assertEqual(stale["status"], "STALE")


if __name__ == "__main__":
    unittest.main()

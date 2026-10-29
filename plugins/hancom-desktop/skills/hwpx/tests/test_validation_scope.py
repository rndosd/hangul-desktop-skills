from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from candidate_runtime import activate
activate()
from hwpx.tools import package_validator as validator


class ValidationScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (Path(__file__).resolve().parents[1] / 'vendor/hwpx/data/Skeleton.hwpx').read_bytes()

    def test_exact_bytes_and_failure_results_are_reused_only_inside_scope(self):
        original = validator._validate_editor_open_safety_uncached
        with patch.object(validator, '_validate_editor_open_safety_uncached', wraps=original) as work:
            with validator.editor_open_safety_scope():
                first = validator.validate_editor_open_safety(self.data)
                second = validator.validate_editor_open_safety(bytes(bytearray(self.data)))
                damaged = validator.validate_editor_open_safety(b'not a ZIP archive')
                repeated = validator.validate_editor_open_safety(b'not a ZIP archive')
                self.assertEqual(first.to_dict(), second.to_dict())
                self.assertIsNot(first, second)
                self.assertTrue(first.ok)
                self.assertFalse(damaged.ok)
                self.assertEqual(damaged.to_dict(), repeated.to_dict())
                self.assertEqual(work.call_count, 2)
            validator.validate_editor_open_safety(self.data)
            validator.validate_editor_open_safety(self.data)
            self.assertEqual(work.call_count, 4)

    def test_changed_payload_and_nested_operation_have_own_evidence(self):
        original = validator._validate_editor_open_safety_uncached
        with patch.object(validator, '_validate_editor_open_safety_uncached', wraps=original) as work:
            with validator.editor_open_safety_scope():
                validator.validate_editor_open_safety(self.data)
                validator.validate_editor_open_safety(self.data + b'changed trailer')
                with validator.editor_open_safety_scope():
                    validator.validate_editor_open_safety(self.data)
                    validator.validate_editor_open_safety(self.data)
                validator.validate_editor_open_safety(self.data)
                self.assertEqual(work.call_count, 3)

    def test_exception_restores_context_and_does_not_store_a_result(self):
        with patch.object(validator, '_validate_editor_open_safety_uncached', side_effect=RuntimeError('injected')) as work:
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                with validator.editor_open_safety_scope():
                    validator.validate_editor_open_safety(self.data)
            self.assertIsNone(validator._OPEN_SAFETY_SCOPE.get())
            self.assertEqual(work.call_count, 1)

    def test_memory_limit_keeps_validation_active(self):
        original = validator._validate_editor_open_safety_uncached
        with patch.object(validator, '_OPEN_SAFETY_SCOPE_MAX_BYTES', 1), patch.object(validator, '_validate_editor_open_safety_uncached', wraps=original) as work:
            with validator.editor_open_safety_scope():
                self.assertTrue(validator.validate_editor_open_safety(self.data).ok)
                self.assertTrue(validator.validate_editor_open_safety(self.data).ok)
                self.assertFalse(validator._OPEN_SAFETY_SCOPE.get())
                self.assertEqual(work.call_count, 2)

    def test_other_thread_does_not_inherit_operation_evidence(self):
        original = validator._validate_editor_open_safety_uncached
        with patch.object(validator, '_validate_editor_open_safety_uncached', wraps=original) as work:
            with validator.editor_open_safety_scope():
                validator.validate_editor_open_safety(self.data)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    self.assertTrue(pool.submit(validator.validate_editor_open_safety, self.data).result().ok)
                validator.validate_editor_open_safety(self.data)
                self.assertEqual(work.call_count, 2)


if __name__ == '__main__':
    unittest.main()

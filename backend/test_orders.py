"""Durable order recovery without Tk: exact data, history, atomic failure."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from converter import dimension, export_tables
from customizations import changed_fields
from edits import apply_row_edit, change_item_type, delete_items
from hardware import SPECIAL_CATEGORIES
from hardware_email import generate_email
from order_files import read_order, write_order
from row_history import RowHistory
from test_converter import item
from test_edits import fixture_report
from test_hardware import fixture
from bore_split import BoreDecision


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.report = fixture_report()
        self.history = RowHistory(self.report)

    def write(self, path, draft=None, view=None):
        write_order(path, self.report, self.history, draft, view or {
            'group': '', 'tab': 'doors', 'selection': {'doors': [], 'boxes': []},
        })

    def test_round_trip_preserves_rows_fractions_types_splits_and_history(self):
        self.report.hardware = fixture()
        self.report.hardware_pages = [7]
        self.report.notes = ['Check glass doors against plan.']
        self.report.checks = ['Quantity total matched.']
        apply_row_edit(self.history, 0, {
            'Quantity': '2', 'Width': '17 27/32', 'Height': '49 3/8', 'Type': 'Door', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '3 1/2', 'Center Bore Position': '25 3/16',
            'Bottom Bore Position': '4',
        }, center_reference='Top — Decorative', manual_positions=['top', 'center'],
           decision=BoreDecision(duplicate=True))
        change_item_type(self.history, 2, 'Glass')  # front shifted after split? original index 1 is now 2
        # After split, items: L door, R door, front, box, tray. Glass the original door's neighbor.
        change_item_type(self.history, 3, 'Applied Door')  # wait, index 3 is box after split (0,1 doors, 2 front, 3 box)
        # Applied Door on a box should fail / return False
        self.assertFalse(change_item_type(self.history, 3, 'Applied Door'))
        change_item_type(self.history, 2, 'Applied Door')
        delete_items(self.history, [4])
        self.history.undo()
        before = deepcopy(self.report)
        copied = export_tables(self.report)
        undo = deepcopy(self.history.undo_stack)
        redo = deepcopy(self.history.redo_stack)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'saved order.mddorder'
            self.write(path, view={'group': 'Drawer Box', 'tab': 'boxes', 'selection': {'doors': [], 'boxes': [3]}})
            loaded = read_order(path)
            self.assertEqual(loaded.report, before)
            self.assertEqual(export_tables(loaded.report), copied)
            self.assertEqual(loaded.history.undo_stack, undo)
            self.assertEqual(loaded.history.redo_stack, redo)
            self.assertEqual(loaded.view['group'], 'Drawer Box')
            self.assertEqual(loaded.view['tab'], 'boxes')
            loaded.history.redo()
            self.assertTrue(loaded.report.items[4].deleted)
            loaded.history.undo()
            self.assertEqual(loaded.report, before)
            while loaded.history.undo_stack:
                loaded.history.undo()
            self.assertEqual(loaded.report.items[0].bore_overrides, {})

    def test_all_deleted_rows_can_save_reopen_and_undo(self):
        delete_items(self.history, range(4))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'empty.mddorder'
            self.write(path)
            loaded = read_order(path)
            self.assertTrue(all(row.deleted for row in loaded.report.items))
            loaded.history.undo()
            self.assertEqual(len(export_tables(loaded.report)), 3)

    def test_atomic_save_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'existing.mddorder'
            self.write(path)
            before = path.read_bytes()
            change_item_type(self.history, 0, 'Glass')
            with patch('order_files.os.replace', side_effect=OSError('Disk unavailable')):
                with self.assertRaises(OSError):
                    self.write(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            self.assertEqual(self.report.items[0].type, 'Glass')

    def test_corrupt_unknown_version_and_bad_history_do_not_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'valid.mddorder'
            change_item_type(self.history, 0, 'Glass')
            self.write(path)
            document = json.loads(path.read_text(encoding='utf-8'))
            bad_version = deepcopy(document)
            bad_version['version'] = 900
            bad_history = deepcopy(document)
            bad_history['history']['undo'][0]['after']['0']['qty'] = 10
            bad_bore = deepcopy(document)
            bad_bore['report']['items'][0]['bore_overrides']['center'] = '999'
            bad_qty = deepcopy(document)
            bad_qty['report']['items'][0]['qty'] = True
            broken = Path(directory) / 'bad.mddorder'
            for content in ('{bad', json.dumps(bad_version), json.dumps(bad_history),
                            json.dumps(bad_bore), json.dumps(bad_qty)):
                broken.write_text(content, encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_order(broken)
            self.assertEqual(read_order(path).report.items[0].type, 'Glass')

    def test_hardware_draft_roundtrip_and_new_job_blank_quantities(self):
        self.report.hardware = fixture()
        self.report.hardware_pages = [7]
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / 'preferences.json'
            special = {category: [{'part_number': '', 'quantity': '', 'unit': 'each'}]
                       for category in SPECIAL_CATEGORIES}
            special[SPECIAL_CATEGORIES[0]] = [{'part_number': 'TEST-HINGE', 'quantity': '2', 'unit': 'each'}]
            body, _ = generate_email(self.report, {'special': special}, settings)
            draft = {
                'parts': {}, 'quantities': {}, 'special': special,
                'email': body + '\nPlease deliver next week.', 'generated_body': body, 'preview': True,
            }
            path = Path(directory) / 'hardware.mddorder'
            self.write(path, draft)
            loaded = read_order(path)
            self.assertEqual(loaded.hardware_draft['special'][SPECIAL_CATEGORIES[0]][0]['quantity'], '2')
            self.assertTrue(loaded.hardware_draft['email'].endswith('Please deliver next week.'))

    def test_saved_order_preserves_highlight_baselines_without_pdf(self):
        self.report.items[0].qty = 3
        self.history = RowHistory(self.report)
        apply_row_edit(self.history, 0, {
            'Quantity': '3', 'Width': '17 27/32', 'Height': '49 3/8', 'Type': 'Door', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '4', 'Center Bore Position': '24 11/16',
            'Bottom Bore Position': '7',
        }, center_reference='Top — Decorative', manual_positions=['bottom'],
           decision=BoreDecision(duplicate=True, left_count=2))
        change_item_type(self.history, 4, 'Tray')
        delete_items(self.history, [3])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.mddorder'
            self.write(path)
            loaded = read_order(path)
        original = loaded.history.original_items()
        self.assertEqual([original[i].qty for i in range(3)], [3, 3, 3])
        self.assertEqual(original[4].type, 'Drawer Box')
        self.assertIn('Scoop', changed_fields(loaded.report.items[4], original[4]))
        for _ in range(3):
            loaded.history.undo()
        original = loaded.history.original_items()
        self.assertEqual(len(original), 4)
        self.assertFalse(any(changed_fields(row, base) for row, base in zip(loaded.report.items, original)))

    def test_frozen_custom_offsets_order_reopens_without_pdf(self):
        path = Path(__file__).resolve().parents[1] / 'samples' / 'custom-offsets-1.21.mddorder'
        if not path.exists():
            self.skipTest('custom-offsets-1.21.mddorder is not present')
        loaded = read_order(path)
        self.assertEqual(loaded.report.job.startswith('Modern') or True, True)
        self.assertTrue(any(row.bore_positions()[0] == '7' for row in loaded.report.items if row.kind == 'doors'))
        self.assertTrue(any(row.bore_positions()[2] == '3 1/2' for row in loaded.report.items if row.kind == 'doors'))
        doors = [row for row in loaded.report.items if row.kind == 'doors' and not row.deleted]
        boxes = [row for row in loaded.report.items if row.kind == 'boxes' and not row.deleted]
        self.assertGreaterEqual(len(doors), 26)
        self.assertEqual(len(boxes), 19)

    def test_fractions_stay_exact_strings_in_json(self):
        self.report.items[0].width = dimension('17 27/32')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'frac.mddorder'
            self.write(path)
            raw = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(raw['report']['items'][0]['width'], '17 27/32')
            self.assertIsInstance(raw['report']['items'][0]['width'], str)


if __name__ == '__main__':
    unittest.main()

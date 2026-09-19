import copy
import csv
import io
import tempfile
import unittest

from bore_split import BoreDecision, PendingBoreDecision, confirm_custom_bores, custom_bores_changed
from clipboard import clipboard_for_kind
from converter import Report, dimension, export_items, export_report, export_tables
from customizations import changed_fields
from edits import apply_row_edit, change_item_type, delete_items
from row_history import RowHistory
from test_converter import item


def fixture_report():
    door = item('49 3/8')
    front = item('6', '5-Piece Drawer Front')
    box = item('4', 'Drawer Box', 'boxes')
    tray = item('4', 'Tray', 'boxes')
    box.group = tray.group = 'Drawer Box'
    tray.scoop = 'A'
    return Report('example.pdf', 'Row changes', [door, front, box, tray])


class EditTests(unittest.TestCase):
    def setUp(self):
        self.report = fixture_report()
        self.history = RowHistory(self.report)

    def test_delete_hides_row_from_review_and_every_export_then_undo_restores(self):
        self.assertEqual(delete_items(self.history, [1]), 1)
        self.assertTrue(self.report.items[1].deleted)
        self.assertNotIn('short_fronts', export_tables(self.report))
        self.assertTrue(self.history.dirty)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(len(export_report(self.report, directory)), 2)
        self.history.undo()
        self.assertFalse(self.report.items[1].deleted)
        self.assertEqual(len(export_tables(self.report)['short_fronts'][1]), 1)

    def test_delete_all_blocks_export_and_reimport_resets_history(self):
        delete_items(self.history, range(4))
        with self.assertRaisesRegex(ValueError, 'no included rows'):
            export_tables(self.report)
        self.history.undo()
        self.assertEqual(sum(len(batch) for batch in export_items(self.report).values()), 4)

    def test_type_change_resets_bores_and_syncs_scoop(self):
        change_item_type(self.history, 0, 'Applied Door')
        self.assertEqual(self.report.items[0].type, 'Applied Door')
        self.assertEqual(self.report.items[0].values()[5:], ['None', 'none', 'no', '', '', ''])
        self.assertEqual(self.report.items[0].supplier_values()[0], 'Door')
        change_item_type(self.history, 2, 'Tray')
        self.assertEqual(self.report.items[2].scoop, 'A')
        change_item_type(self.history, 3, 'Drawer Box')
        self.assertEqual(self.report.items[3].scoop, '')

    def test_glass_front_door_label_stores_glass(self):
        change_item_type(self.history, 0, 'Glass Front Door')
        self.assertEqual(self.report.items[0].type, 'Glass')
        self.assertEqual(self.report.items[0].values()[0], 'Glass')

    def test_bore_overrides_keep_fractions_and_midpoint_until_edited(self):
        apply_row_edit(self.history, 0, {
            'Quantity': '1', 'Width': '17 27/32', 'Height': '52', 'Type': 'Door', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '3 1/2', 'Center Bore Position': '29 3/4',
            'Bottom Bore Position': '5 1/4',
        }, center_reference='Top — Decorative', manual_positions=['top', 'center', 'bottom'],
           decision=BoreDecision(side='L'))
        self.assertEqual(self.report.items[0].values()[8:], ['3 1/2', '29 3/4', '5 1/4'])
        apply_row_edit(self.history, 0, {
            'Quantity': '1', 'Width': '17 27/32', 'Height': '52', 'Type': 'Door', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '4', 'Center Bore Position': '26',
            'Bottom Bore Position': '4',
        }, center_reference='Top — Decorative', manual_positions=[])
        self.assertEqual(self.report.items[0].bore_overrides, {})

    def test_front_positions_editable_without_enabling_boring(self):
        apply_row_edit(self.history, 1, {
            'Quantity': '1', 'Width': '17 27/32', 'Height': '6', 'Type': '5-Piece Drawer Front',
            'Location': 'none', 'French Lite': '', 'Top Bore Position': '1 1/2',
            'Center Bore Position': '3', 'Bottom Bore Position': '1 3/4',
        }, center_reference='Top — Decorative', manual_positions=['top', 'center', 'bottom'])
        self.assertEqual(self.report.items[1].values()[5:], ['None', 'none', 'no', '1 1/2', '3', '1 3/4'])

    def test_center_from_mozaik_bottom_stores_decorative_top(self):
        apply_row_edit(self.history, 0, {
            'Quantity': '1', 'Width': '17 27/32', 'Height': '48', 'Type': 'Door', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '4', 'Center Bore Position': '24 1/2',
            'Bottom Bore Position': '4',
        }, center_reference='Bottom — Mozaik', manual_positions=['center'],
           decision=BoreDecision(side='L'))
        self.assertEqual(self.report.items[0].bore_overrides['center'], dimension('23 1/2'))
        self.assertEqual(self.report.items[0].bore_positions()[1], '23 1/2')

    def test_invalid_offset_blocks_apply(self):
        before = copy.deepcopy(self.report.items)
        for offset in ('oops', '=3+4', '1/0', '-4', '-5', '50'):
            with self.assertRaises(ValueError):
                apply_row_edit(self.history, 0, {
                    'Quantity': '1', 'Width': '17 27/32', 'Height': '49 3/8', 'Type': 'Door',
                    'Location': 'L', 'French Lite': '', 'Top Bore Position': '7',
                    'Center Bore Position': '', 'Bottom Bore Position': '4',
                }, manual_positions=['top'], edge_offsets={'top': offset})
            self.assertEqual(self.report.items, before)

    def test_yes_splits_pair_with_identical_positions(self):
        self.report.items[0].qty = 2
        self.history = RowHistory(self.report)
        before = copy.deepcopy(self.report.items)
        apply_row_edit(self.history, 0, {
            'Quantity': '2', 'Width': '17 27/32', 'Height': '49 3/8', 'Type': 'Door', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '3.5', 'Center Bore Position': '23 3/16',
            'Bottom Bore Position': '5 1/4',
        }, center_reference='Top — Decorative', manual_positions=['top', 'center', 'bottom'],
           decision=BoreDecision(duplicate=True))
        rows = self.report.items[:2]
        self.assertEqual([(row.qty, row.location) for row in rows], [(1, 'L'), (1, 'R')])
        for row in rows:
            self.assertEqual(row.bore_positions(), ['3 1/2', '23 3/16', '5 1/4'])
            self.assertEqual(row.original, before[0].original)
        copied = list(csv.reader(io.StringIO(clipboard_for_kind(self.report, 'doors')), delimiter='\t'))
        self.assertEqual([row[6] for row in copied[1:3]], ['L', 'R'])
        self.assertEqual(copied[1][8:], copied[2][8:])
        self.history.undo()
        self.assertEqual(self.report.items, before)
        self.history.redo()
        self.assertEqual([row.location for row in self.report.items[:2]], ['L', 'R'])

    def test_no_changes_one_door_and_preserves_remainder(self):
        self.report.items[0].qty = 3
        self.history = RowHistory(self.report)
        original = copy.deepcopy(self.report.items[0])
        apply_row_edit(self.history, 0, {
            'Quantity': '3', 'Width': '17 27/32', 'Height': '49 3/8', 'Type': 'Door', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '3.5', 'Center Bore Position': '23 3/16',
            'Bottom Bore Position': '5 1/4',
        }, center_reference='Top — Decorative', manual_positions=['top', 'center', 'bottom'],
           decision=BoreDecision(duplicate=False, side='R'))
        self.assertEqual([(row.qty, row.location) for row in self.report.items[:2]], [(1, 'R'), (2, 'L')])
        self.assertEqual(self.report.items[1].bore_overrides, original.bore_overrides)
        self.assertEqual(self.report.items[0].bore_positions(), ['3 1/2', '23 3/16', '5 1/4'])

    def test_quantity_five_uses_left_count(self):
        self.report.items[0].qty = 5
        self.history = RowHistory(self.report)
        apply_row_edit(self.history, 0, {
            'Quantity': '5', 'Width': '17 27/32', 'Height': '49 3/8', 'Type': 'Door', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '3', 'Center Bore Position': '24',
            'Bottom Bore Position': '5',
        }, center_reference='Top — Decorative', manual_positions=['top', 'center', 'bottom'],
           decision=BoreDecision(duplicate=True, left_count=2))
        sides = [row.location for row in self.report.items[:5]]
        self.assertEqual(sides, ['L', 'L', 'R', 'R', 'R'])
        self.assertTrue(all(row.qty == 1 for row in self.report.items[:5]))
        self.assertEqual(sum(row.qty for row in self.report.items[:5]), 5)

    def test_pending_decision_does_not_mutate(self):
        self.report.items[0].qty = 2
        self.history = RowHistory(self.report)
        before = copy.deepcopy(self.report.items)
        with self.assertRaises(PendingBoreDecision) as caught:
            apply_row_edit(self.history, 0, {
                'Quantity': '2', 'Width': '17 27/32', 'Height': '49 3/8', 'Type': 'Door', 'Location': 'L',
                'French Lite': '', 'Top Bore Position': '3', 'Center Bore Position': '24',
                'Bottom Bore Position': '5',
            }, center_reference='Top — Decorative', manual_positions=['top', 'center', 'bottom'])
        self.assertIn('other door', caught.exception.question)
        self.assertEqual(self.report.items, before)

    def test_reference_toggle_without_manual_change_is_not_custom(self):
        original = copy.deepcopy(self.report.items[0])
        edited = copy.deepcopy(original)
        self.assertFalse(custom_bores_changed(original, edited))
        self.assertEqual(confirm_custom_bores(original, edited), [edited])

    def test_undo_redo_restores_full_rows(self):
        original = copy.deepcopy(self.report.items)
        apply_row_edit(self.history, 0, {
            'Quantity': '3', 'Width': '19 1/2', 'Height': '51', 'Type': 'Door', 'Location': 'R',
            'French Lite': '', 'Top Bore Position': '3 1/2', 'Center Bore Position': '24 1/4',
            'Bottom Bore Position': '5',
        }, center_reference='Top — Decorative', manual_positions=['top', 'center', 'bottom'],
           decision=BoreDecision(duplicate=False, side='R'))
        edited = copy.deepcopy(self.report.items)
        box_index = next(i for i, row in enumerate(self.report.items) if row.kind == 'boxes')
        change_item_type(self.history, box_index, 'Tray')
        typed = copy.deepcopy(self.report.items)
        delete_items(self.history, [i for i, row in enumerate(self.report.items) if row.kind == 'doors'])
        for expected in (typed, edited, original):
            self.history.undo()
            self.assertEqual(self.report.items, expected)
        for expected in (edited, typed):
            self.history.redo()
            self.assertEqual(self.report.items, expected)

    def test_new_change_after_undo_clears_redo(self):
        change_item_type(self.history, 0, 'Glass')
        change_item_type(self.history, 0, 'Applied Door')
        self.history.undo()
        change_item_type(self.history, 0, 'Glass')
        self.assertEqual(len(self.history.redo_stack), 1)
        apply_row_edit(self.history, 0, {
            'Quantity': '1', 'Width': '20', 'Height': '49 3/8', 'Type': 'Glass', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '4', 'Center Bore Position': '24 11/16',
            'Bottom Bore Position': '4',
        }, center_reference='Top — Decorative', manual_positions=[])
        self.assertEqual(self.history.redo_stack, [])
        self.assertEqual(self.report.items[0].type, 'Glass')

    def test_short_front_moves_groups_after_type_change(self):
        change_item_type(self.history, 1, 'Applied Door')
        self.assertNotIn('short_fronts', export_tables(self.report))
        self.history.undo()
        self.assertEqual(list(export_items(self.report)['short_fronts']), [self.report.items[1]])

    def test_split_children_keep_original_quantity_baseline(self):
        self.report.items[0].qty = 2
        self.history = RowHistory(self.report)
        apply_row_edit(self.history, 0, {
            'Quantity': '2', 'Width': '17 27/32', 'Height': '49 3/8', 'Type': 'Door', 'Location': 'L',
            'French Lite': '', 'Top Bore Position': '7', 'Center Bore Position': '24 11/16',
            'Bottom Bore Position': '4 1/2',
        }, center_reference='Top — Decorative', manual_positions=['top', 'bottom'],
           decision=BoreDecision(duplicate=True))
        originals = self.history.original_items()
        for index in (0, 1):
            self.assertEqual(originals[index].qty, 2)
            self.assertIn('Quantity', changed_fields(self.report.items[index], originals[index]))
            self.assertIn('Top Bore Position', changed_fields(self.report.items[index], originals[index]))


if __name__ == '__main__':
    unittest.main()

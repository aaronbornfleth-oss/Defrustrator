import csv
import io
import unittest

from clipboard import CLIPBOARD_BOX_HEADERS, CLIPBOARD_DOOR_HEADERS, clipboard_for_kind, clipboard_text
from converter import BOX_HEADERS, DOOR_HEADERS, Report, csv_text, export_tables
from test_converter import item


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        door = item('49 3/8')
        door.qty = 2
        front = item('7', type='5-Piece Drawer Front')
        excluded = item('40')
        excluded.included = False
        box = item('4', kind='boxes', type='Drawer Box')
        box.group = 'Drawer Box'
        tray = item('4', kind='boxes', type='Tray')
        tray.group = 'Trays'
        tray.scoop = 'A'
        self.report = Report('example.pdf', 'Example job', [door, front, excluded, box, tray])

    def parse(self, text):
        self.assertFalse(text.endswith(('\r', '\n')))
        self.assertTrue(all(line for line in text.split('\r\n')))
        return list(csv.reader(io.StringIO(text), delimiter='\t'))

    def test_copy_all_preserves_supplier_columns_fractions_and_blank_cells(self):
        text = clipboard_for_kind(self.report, 'doors')
        rows = self.parse(text)
        self.assertEqual(rows, [CLIPBOARD_DOOR_HEADERS, self.report.items[0].values(), self.report.items[1].values()])
        self.assertEqual(rows[1][2:4], ['17 27/32', '49 3/8'])
        self.assertEqual(rows[1][9], '24 11/16')
        self.assertEqual(rows[2][5:], ['None', 'none', 'no', '', '', ''])
        self.assertTrue(all(len(row) == 11 for row in rows))
        self.assertEqual(rows.count(CLIPBOARD_DOOR_HEADERS), 1)

    def test_headings_always_included_and_bore_space_only_in_csv(self):
        self.assertEqual(self.parse(clipboard_for_kind(self.report, 'doors'))[0], CLIPBOARD_DOOR_HEADERS)
        self.assertEqual(CLIPBOARD_DOOR_HEADERS[5], 'Bore')
        self.assertEqual(DOOR_HEADERS[5], 'Bore ')
        box_rows = self.parse(clipboard_for_kind(self.report, 'boxes'))
        self.assertEqual(box_rows[0], CLIPBOARD_BOX_HEADERS)
        self.assertEqual(box_rows[1:], [self.report.items[3].values(), self.report.items[4].values()])
        self.assertEqual([row[-1] for row in box_rows[1:]], ['', 'A'])

    def test_final_blank_cells_remain_without_an_extra_row(self):
        for kind, index, trailing_tabs in [('doors', 1, 3), ('boxes', 0, 1)]:
            with self.subTest(kind=kind):
                text = clipboard_for_kind(self.report, kind, selected_indices=[index])
                lines = text.split('\r\n')
                self.assertEqual(len(lines), 2)
                source = 1 if kind == 'doors' else 3
                self.assertEqual(lines[-1].split('\t'), self.report.items[source].values())
                self.assertTrue(text.endswith('\t' * trailing_tabs))

    def test_selected_rows_keep_document_order(self):
        text = clipboard_for_kind(self.report, 'doors', selected_indices=[1, 0])
        rows = self.parse(text)
        self.assertEqual(rows, [CLIPBOARD_DOOR_HEADERS, self.report.items[0].values(), self.report.items[1].values()])

    def test_copy_selected_with_no_matching_rows_raises(self):
        with self.assertRaisesRegex(ValueError, 'Select one or more'):
            clipboard_for_kind(self.report, 'doors', selected_indices=[99])

    def test_csv_keeps_template_bore_space_clipboard_does_not(self):
        csv_header = list(csv.reader(io.StringIO(csv_text(self.report.items, 'doors'))))[0]
        self.assertEqual(csv_header, DOOR_HEADERS)
        self.assertEqual(csv_header[5], 'Bore ')
        self.assertEqual(self.parse(clipboard_for_kind(self.report, 'doors'))[0][5], 'Bore')

    def test_section_filter_and_trailing_tab_for_blank_scoop(self):
        text = clipboard_for_kind(self.report, 'boxes', group='Drawer Box')
        self.assertTrue(text.endswith('\t'))
        self.assertEqual(self.parse(text)[1][0], '1')
        tables = export_tables(self.report, 'Example Door')
        self.assertIn('doors', tables)
        self.assertNotIn('boxes', tables)

    def test_clipboard_text_does_not_rstrip_required_tabs(self):
        text = clipboard_text(['Qty', 'Scoop'], [['1', '']])
        self.assertEqual(text, 'Qty\tScoop\r\n1\t')


if __name__ == '__main__':
    unittest.main()

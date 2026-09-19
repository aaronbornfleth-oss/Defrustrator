import copy
import csv
import io
import os
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from converter import *


def item(height='36', type='Door', kind='doors'):
    return Item(kind, 1, dimension('17 27/32'), dimension(height), dimension('21') if kind == 'boxes' else None,
                type, 'L', '', '', 1, 'Example Door', '{Door Size}', 'R1:1', '(1) 17 27/32 36 {Door Size} R1:1')


class RulesTests(unittest.TestCase):
    def test_fraction_precision(self):
        for raw, result in [('17 27/32', '17 27/32'), ('34.34375', '34 11/32'),
                            ('0.0625','1/16'), ('17-27/32','17 27/32'), ('30.0','30'),
                            ('17 2/4','17 1/2'), ('1/3','1/3')]:
            self.assertEqual(fractional(dimension(raw)), result)
            self.assertEqual(dimension(result),dimension(raw))
        for raw in ('0', '-1', '17 3', '1/0', '=1+1', 'nan'):
            with self.assertRaises(ValueError): dimension(raw)

    def test_center_bore_boundary(self):
        self.assertEqual(item('36').values()[7:], ['No','4','','4'])
        self.assertEqual(item('36 1/32').values()[7:], ['Yes','4','18 1/64','4'])
        self.assertEqual(item('49 3/8').values()[5:], ['A','L','Yes','4','24 11/16','4'])

    def test_fronts_never_bored_even_when_tall(self):
        for type in ['5-Piece Drawer Front','Solid Drawer Front','Routed Drawer Front']:
            location = 'none' if type == '5-Piece Drawer Front' else ''
            center_bore = 'no' if type == '5-Piece Drawer Front' else ''
            for height in ['6', '36', '49 3/8']:
                self.assertEqual(item(height, type).values()[5:], ['None',location,center_bore,'','',''])

    def test_five_piece_location_overrides_any_previous_door_location(self):
        row = item('49 3/8', '5-Piece Drawer Front')
        for location in ['', 'L', 'R', 'Susan', 'none']:
            row.location = location
            self.assertEqual(row.values()[6], 'none')

    def test_classification(self):
        self.assertEqual(classify('doors', '{Drawer Front Size}', 'Shaker 90'), ('5-Piece Drawer Front','',''))
        self.assertEqual(classify('doors', '{Glass Door Size}', 'Shaker'), ('Glass','L',''))
        self.assertEqual(classify('doors', '{Applied Door Size}', 'Shaker'), ('Applied Door','',''))
        self.assertEqual(classify('doors', '{Door Size}', 'Lazy Susan Door'), ('Door','Susan',''))
        self.assertEqual(classify('boxes', 'Tray', 'Tray-Blind Dado 6 Piece'), ('Tray','','A'))
        self.assertEqual(classify('boxes', 'Drawer Box', 'Drawer-Blind Dado Box'), ('Drawer Box','',''))
        with self.assertRaises(ValueError): classify('doors','Panel','Unknown')

    def test_french_lite_validation(self):
        row = item(type='French Lite')
        with self.assertRaises(ValueError): row.values()
        row.french_lite='6 Equal Lts'
        self.assertEqual(row.values()[4], '6 Equal Lts')
        row.french_lite='=BAD()'
        with self.assertRaises(ValueError): row.values()

    def test_csv_schema_and_empty_cells(self):
        rows = list(csv.reader(io.StringIO(csv_text([item(), item(type='5-Piece Drawer Front')], 'doors'))))
        self.assertEqual(rows[0], DOOR_HEADERS)
        self.assertTrue(all(len(row) == 11 for row in rows))
        self.assertEqual(rows[2][5:], ['None','none','no','','',''])
        self.assertEqual(rows[1][2:4],['17 27/32','36'])
        self.assertEqual(list(csv.reader(io.StringIO(csv_text([item(kind='boxes')], 'boxes'))))[0], BOX_HEADERS)

    def test_export_scope_exclusion_and_no_overwrite(self):
        first, second, third = item(), item(), item(kind='boxes')
        second.included = False
        third.group = 'Drawer Box'
        report = Report('example.pdf', 'Test', [first,second,third])
        with tempfile.TemporaryDirectory() as directory:
            paths = export_report(report, directory, 'Example Door')
            self.assertEqual(len(paths),1)
            with paths[0].open(newline='') as exported:
                self.assertEqual(len(list(csv.reader(exported))),2)
            paths2 = export_report(report, directory, 'Example Door')
            self.assertNotEqual(paths, paths2)
            self.assertEqual(len(export_report(report, directory)),2)
            report.errors.append('Missing page')
            with self.assertRaises(ValueError): export_report(report, directory)

    def test_applied_doors_have_no_boring_and_export_as_door(self):
        for height in ['6', '36', '49 3/8']:
            row = item(height, 'Applied Door')
            self.assertEqual(row.values()[0], 'Applied Door')
            self.assertEqual(row.values()[5:], ['None', 'none', 'no', '', '', ''])
            self.assertEqual(row.supplier_values()[0], 'Door')
            self.assertEqual(row.export_kind, 'doors')
            row.location = ''
            self.assertEqual(row.supplier_values()[5:], ['None', 'none', 'no', '', '', ''])

    def test_short_fronts_partition_exact_boundary_scope_and_latest_edits(self):
        regular = item('7', '5-Piece Drawer Front')
        short = item('6 31/32', '5-Piece Drawer Front')
        solid = item('6', 'Solid Drawer Front')
        routed = item('6 1/2', 'Routed Drawer Front')
        small_door = item('6', 'Applied Door')
        excluded = item('4', '5-Piece Drawer Front')
        excluded.included = False
        other = item('5', '5-Piece Drawer Front')
        other.group = 'Another style'
        box = item(kind='boxes', type='Drawer Box')
        box.group = 'Drawer Box'
        report = Report('example.pdf', 'Partition', [regular, short, solid, routed, small_door, excluded, other, box])
        batches = export_items(report, 'Example Door')
        self.assertEqual(batches['doors'], [regular, small_door])
        self.assertEqual(batches['short_fronts'], [short, solid, routed])
        self.assertNotIn('boxes', batches)
        with tempfile.TemporaryDirectory() as directory:
            paths = export_report(report, directory)
            self.assertEqual(len(paths), 3)
            self.assertIn('drawer-fronts-under-7-inches', paths[1].name)
            matrices = [list(csv.reader(io.StringIO(path.read_text(encoding='utf-8')))) for path in paths]
            self.assertEqual([len(matrix)-1 for matrix in matrices], [2, 4, 1])
            self.assertEqual(matrices[1][0], DOOR_HEADERS)
            self.assertEqual(matrices[1][1][3], '6 31/32')
            self.assertEqual(matrices[0][2][0], 'Door')
            self.assertEqual(sum(int(row[1]) for matrix in matrices[:2] for row in matrix[1:]), 6)
        short.height = dimension('7')
        solid.type = 'Glass'
        batches = export_items(report, 'Example Door')
        self.assertEqual(batches['doors'], [regular, short, solid, small_door])
        self.assertEqual(batches['short_fronts'], [routed])
        for row in report.items:
            row.included = row is routed
        self.assertEqual(list(export_tables(report)), ['short_fronts'])

    def test_missing_and_mismatched_totals_block(self):
        class Page:
            def extract_text(self): return 'Job: Example\nCutlist for Door Sizes (Door)'
            def extract_tables(self): return [[['Quan','Width','Height','Part','Room# Cab# (Quan)'], ['(1)','18','36','{Door Size}','R1:1'], ['(2)','Doors','(Total)','','']]]
        class PDF:
            pages = [Page()]
            def __enter__(self): return self
            def __exit__(self,*args): pass
        with patch('converter.pdfplumber.open', return_value=PDF()):
            report=read_report('test.pdf')
            self.assertTrue(any('PDF total 2' in error for error in report.errors))

    def test_unrecognized_and_scanned_pages_block(self):
        class Page:
            def __init__(self, text): self.text=text
            def extract_text(self): return self.text
        class PDF:
            pages = [Page(''),Page('Unknown size report')]
            def __enter__(self): return self
            def __exit__(self,*args): pass
        with patch('converter.pdfplumber.open', return_value=PDF()):
            report=read_report('test.pdf')
            self.assertTrue(any('no readable text' in error for error in report.errors))
            self.assertTrue(any('not recognized' in error for error in report.errors))


@unittest.skipUnless(os.environ.get('MOZAIK_SAMPLE_PDF'), 'Set MOZAIK_SAMPLE_PDF to test the supplied sample.')
class SampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.report = read_report(os.environ['MOZAIK_SAMPLE_PDF'])

    def test_complete_sample(self):
        r=self.report
        self.assertEqual(r.errors, [])
        self.assertEqual(len(r.items),45)
        self.assertEqual(r.hardware_pages,[7])
        self.assertEqual(len(r.checks),6)
        # Current sample revision, regenerated in Mozaik on 2026-09-15 at 10:00.
        self.assertEqual(sum(i.qty for i in r.items if i.kind=='doors' and not i.is_front),31)
        self.assertEqual(sum(i.qty for i in r.items if i.is_front),20)
        self.assertEqual(sum(i.qty for i in r.items if i.type=='Tray'),6)
        self.assertEqual(sum(i.qty for i in r.items if i.type=='Drawer Box'),19)
        self.assertEqual(sum(i.qty for i in r.items if i.kind=='doors' and i.values()[7]=='Yes'),4)

    def test_every_sample_dimension_against_independent_text_read(self):
        # Independent row extraction uses page text, not table cells.
        import re
        expected=[]
        number=r'(\d+(?:\s+\d+/\d+)?|\d+/\d+)'
        with pdfplumber.open(os.environ['MOZAIK_SAMPLE_PDF']) as pdf:
            for pageno,page in enumerate(pdf.pages[:6],1):
                pattern=r'^\((\d+)\)\s+' + number + r'\s+' + number
                if pageno in (5,6): pattern+=r'\s+'+number
                pattern+=r'\s+(?:\{|Tray|Drawer Box)'
                for line in page.extract_text().splitlines():
                    match=re.match(pattern,line)
                    if match: expected.append((pageno,int(match[1]),*[dimension(x) for x in match.groups()[1:]]))
        actual=[(i.page,i.qty,i.width,i.height,*([i.depth] if i.kind=='boxes' else [])) for i in self.report.items]
        self.assertEqual(len(expected),45)
        self.assertEqual(actual,expected)

    def test_fractional_csvs_preserve_every_exact_sample_measurement(self):
        for kind in EXPORT_KINDS:
            exported=list(csv.reader(io.StringIO(csv_text(self.report.items,kind))))
            source=[row for row in self.report.items if row.export_kind==kind]
            self.assertEqual(len(exported)-1,len(source))
            for cells,row in zip(exported[1:],source):
                if kind!='boxes':
                    self.assertEqual([dimension(value) for value in cells[2:4]],[row.width,row.height])
                    sizes=cells[2:4]+[value for value in cells[8:11] if value]
                    if cells[9]: self.assertEqual(dimension(cells[9]),row.height/2)
                else:
                    self.assertEqual([dimension(value) for value in cells[1:4]],[row.width,row.height,row.depth])
                    sizes=cells[1:4]
                self.assertTrue(all('.' not in value for value in sizes))


if __name__ == '__main__': unittest.main()

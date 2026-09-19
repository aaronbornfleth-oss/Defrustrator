import json
import os
import tempfile
import unittest
from pathlib import Path

from converter import Report, read_report
from hardware import (CLIP_PART, DEFAULT_SPACER_PART, HINGE_PART, LEG_LEVELER_PART, SPECIAL_CATEGORIES,
                      HardwareItem, OrderLine, classify_hardware, email_body, order_lines,
                      parse_hardware_tables)
from hardware_email import collect_extras, generate_email
from hardware_settings import load_parts, save_parts


def fixture():
    return [HardwareItem('hinges', 54, HINGE_PART, 'Euro Frameless', 7),
            HardwareItem('glides', 6, '563.3050B', 'Blum TANDEM 563H3050B', 7),
            HardwareItem('glides', 18, '563.4570B', 'Blum TANDEM 563H4570B', 7),
            HardwareItem('glides', 26, '563.5330B', 'Blum TANDEM 563H5330B', 7),
            HardwareItem('spacers', 24, DEFAULT_SPACER_PART, 'Blum TANDEM 563H (USA) Spacers', 7)]


class HardwareTests(unittest.TestCase):
    def test_sample_rules_and_length_separation(self):
        rows = order_lines(fixture())
        self.assertEqual([(r.part_number, r.quantity, r.unit) for r in rows],
                         [(HINGE_PART, 54, 'each'), (CLIP_PART, 54, 'each'), ('563.3050B', 3, 'sets'),
                          ('563.4570B', 9, 'sets'), ('563.5330B', 13, 'sets'), ('T593570', 24, 'each')])
        self.assertIn('12 inches', rows[2].description)
        self.assertIn('18 inches', rows[3].description)
        self.assertIn('21 inches', rows[4].description)
        self.assertEqual(CLIP_PART[-1], 'I')

    def test_spacers_not_treated_as_glides_and_rest_ignored(self):
        self.assertEqual(classify_hardware('Blum TANDEM 563H (USA) Spacers'), ('spacers', 'T593570'))
        self.assertEqual(classify_hardware('Blum Spacers Part no: TEST.123'), ('spacers', 'T593570'))
        for label in ('Wire Pull', 'Flat Metal Pin 5mm', 'Confirmat', 'Drawer Front Adjuster',
                      'Blum TANDEM locking device', 'Euro Frameless hinge clips', 'TANDEM rear bracket'):
            self.assertIsNone(classify_hardware(label)[0])
        self.assertEqual(classify_hardware('Blum TANDEM 563H (USA) - TANDEM 563H5330B'), ('glides', '563.5330B'))
        self.assertEqual(classify_hardware('Blum TANDEM - 563.4570B'), ('glides', '563.4570B'))

    def test_aggregate_before_pair_conversion_and_do_not_round_odd(self):
        first = HardwareItem('glides', 3, '563.3050B', 'TANDEM', 7)
        second = HardwareItem('glides', 3, '563.3050B', 'TANDEM', 8)
        combined = order_lines([first, second])[0]
        self.assertEqual(combined.quantity, 3)
        self.assertEqual(combined.pages, [7, 8])
        odd = order_lines([first])[0]
        self.assertIsNone(odd.quantity)
        with self.assertRaises(ValueError):
            email_body('Job', [odd])

    def test_standard_hardware_needs_no_special_hinge_decisions(self):
        text = email_body('Job', order_lines(fixture()))
        self.assertIn('54 each - 71B3590', text)
        for category in SPECIAL_CATEGORIES:
            self.assertNotIn(category, text)

    def test_email_lists_hinges_clips_separate_glides_spacers_and_extras(self):
        rows = order_lines(fixture())
        extras = [OrderLine(SPECIAL_CATEGORIES[2], 'AVENTOS-TEST', 'Lift mechanism', 2, 'sets'),
                  OrderLine(SPECIAL_CATEGORIES[2], 'COVER-TEST', 'Cover caps', 4, 'each')]
        text = email_body('Example job', rows, extras)
        for expected in ['54 each - 71B3590', '54 each - 174H7100I', '3 sets - 563.3050B',
                         '9 sets - 563.4570B', '13 sets - 563.5330B', '24 each - T593570',
                         '2 sets - AVENTOS-TEST', '4 each - COVER-TEST']:
            self.assertIn(expected, text)
        self.assertNotIn('Wire Pull', text)
        self.assertNotIn(SPECIAL_CATEGORIES[0], text)

    def test_missing_part_or_mismatched_hinge_clips_blocks_draft(self):
        rows = order_lines(fixture())
        rows[-1].part_number = ''
        with self.assertRaisesRegex(ValueError, 'part number'):
            email_body('Job', rows)
        rows = rows[:-1]
        rows[1].quantity -= 1
        with self.assertRaisesRegex(ValueError, 'must match'):
            email_body('Job', rows)

    def test_hardware_extraction_flags_bad_selected_quantities_only(self):
        table = [['Quan', 'Part', 'Room# Cab# (Quan)', 'Other'], ['bad', 'Euro Frameless', '', ''],
                 ['2', 'Wire Pull', '', ''],
                 ['6', 'Blum TANDEM 563H (USA)\n- TANDEM 563H3050B', 'R1C1(6)', '']]
        items, errors = parse_hardware_tables([table], 7)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].qty, 6)
        self.assertEqual(items[0].part_number, '563.3050B')
        self.assertTrue(parse_hardware_tables([], 7)[1])

    def test_leg_levelers_keep_individual_counts_and_aggregate_across_pages(self):
        items = []
        for page, qty, label in [(7, 7, 'Adjustable Leg Levelers'), (8, 5, 'Adjustable Leg Leveller')]:
            parsed, errors = parse_hardware_tables([[['Quan', 'Part'], [str(qty), label]]], page)
            self.assertEqual(errors, [])
            items.extend(parsed)
        self.assertEqual([(x.category, x.part_number) for x in items], [('levelers', '40027290')] * 2)
        rows = order_lines(items)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].quantity, rows[0].unit, rows[0].pages), (12, 'each', [7, 8]))
        self.assertIn('12 each - 40027290 - Adjustable leg levelers', email_body('Job', rows))
        self.assertIsNone(classify_hardware('Leg leveler clips')[0])
        self.assertEqual(LEG_LEVELER_PART, '40027290')

    def test_thirty_six_individuals_become_eighteen_sets(self):
        rows = order_lines([HardwareItem('glides', 36, '563.4570B', 'TANDEM', 7)])
        self.assertEqual(rows[0].quantity, 18)
        self.assertEqual(rows[0].unit, 'sets')

    @unittest.skipUnless(os.environ.get('MOZAIK_SAMPLE_PDF'), 'Set MOZAIK_SAMPLE_PDF for PDF integration.')
    def test_actual_pdf_hardware(self):
        report = read_report(os.environ['MOZAIK_SAMPLE_PDF'])
        self.assertEqual(report.errors, [])
        self.assertEqual(report.hardware_errors, [])
        self.assertEqual(len(report.hardware), 5)
        self.assertEqual([(x.category, x.qty) for x in report.hardware],
                         [('spacers', 30), ('hinges', 56), ('glides', 6), ('glides', 18), ('glides', 26)])
        rows = order_lines(report.hardware)
        self.assertEqual([x.quantity for x in rows], [56, 56, 3, 9, 13, 30])
        self.assertEqual(rows[-1].part_number, 'T593570')
        self.assertFalse(any(x.category == 'levelers' for x in rows))


class HardwareDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Path(self.temp.name) / 'hardware-parts.json'
        self.report = Report('example.pdf', 'Example job', hardware_pages=[7], hardware=fixture())

    def special(self, category, part, qty, unit='each'):
        rows = {cat: [{'part_number': '', 'quantity': '', 'unit': 'each'}] for cat in SPECIAL_CATEGORIES}
        rows[category] = [{'part_number': part, 'quantity': qty, 'unit': unit}]
        return rows

    def test_blank_and_zero_quantities_skip_but_remember_parts(self):
        special = {}
        for category, qty in zip(SPECIAL_CATEGORIES, ('', '0', '00')):
            special[category] = [{'part_number': 'TEST-SKIP', 'quantity': qty, 'unit': 'each'}]
        extras, remembered = collect_extras(special)
        self.assertEqual(extras, [])
        self.assertTrue(all(rows[0]['part_number'] == 'TEST-SKIP' for rows in remembered.values()))
        body, _ = generate_email(self.report, {'special': special}, self.settings)
        self.assertNotIn('TEST-SKIP', body)
        self.assertNotIn('quantity', self.settings.read_text())

    def test_quantity_requires_part(self):
        special = self.special(SPECIAL_CATEGORIES[0], '', '2')
        with self.assertRaisesRegex(ValueError, 'part number'):
            generate_email(self.report, {'special': special}, self.settings)
        self.assertFalse(self.settings.exists())

    def test_remember_parts_without_job_quantities(self):
        special = {SPECIAL_CATEGORIES[0]: [{'part_number': 'TEST-HINGE', 'quantity': '2', 'unit': 'each'}],
                   SPECIAL_CATEGORIES[1]: [{'part_number': '', 'quantity': '', 'unit': 'each'}],
                   SPECIAL_CATEGORIES[2]: [{'part_number': 'TEST-COMPONENT', 'quantity': '1', 'unit': 'sets'}]}
        body, _ = generate_email(self.report, {'special': special}, self.settings)
        self.assertIn('2 each - TEST-HINGE', body)
        self.assertIn('1 set - TEST-COMPONENT', body)
        saved = json.loads(self.settings.read_text())
        self.assertNotIn('quantity', json.dumps(saved['parts']))
        self.assertNotIn('Example job', self.settings.read_text())

    def test_bad_quantities_block_email(self):
        for qty in ('-1', '1.5', 'two', '²'):
            special = self.special(SPECIAL_CATEGORIES[0], 'TEST-PART', qty)
            with self.assertRaisesRegex(ValueError, 'whole quantity'):
                generate_email(self.report, {'special': special}, self.settings)

    def test_hardware_error_blocks_email_but_not_size_export(self):
        self.report.hardware_errors.append('Unreadable hardware row')
        with self.assertRaisesRegex(ValueError, 'extraction'):
            generate_email(self.report, {'special': {}}, self.settings)
        self.assertEqual(self.report.errors, [])


class HardwareSettingsTests(unittest.TestCase):
    def test_saved_preferences_exclude_quantities_and_unrelated_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hardware.json'
            save_parts({SPECIAL_CATEGORIES[0]: [{'part_number': 'TEST-HINGE', 'unit': 'each', 'quantity': 99}],
                        'job': 'Example job'}, path)
            data = json.loads(path.read_text())
            self.assertEqual(data['parts'][SPECIAL_CATEGORIES[0]], [{'part_number': 'TEST-HINGE', 'unit': 'each'}])
            self.assertNotIn('job', data['parts'])
            self.assertEqual(load_parts(path), data['parts'])

    def test_invalid_settings_do_not_replace_previously_saved_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hardware.json'
            save_parts({SPECIAL_CATEGORIES[0]: [{'part_number': 'TEST-HINGE', 'unit': 'each'}]}, path)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                save_parts({SPECIAL_CATEGORIES[0]: [{'part_number': '', 'unit': 'each'}]}, path)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

import unittest
from fractions import Fraction

from bore_math import (BOTTOM, STANDARD, TOP, center_preview, display_from_top, edge_equation,
                       from_top, move_center, offset_from_position, position_from_offset,
                       signed_inches)
from converter import dimension, fractional


class BoreMathTests(unittest.TestCase):
    def test_bottom_input_converts_once_to_top(self):
        height = dimension('48')
        top = from_top(height, dimension('24 1/2'), BOTTOM)
        self.assertEqual(top, dimension('23 1/2'))
        self.assertEqual(display_from_top(height, top, BOTTOM), dimension('24 1/2'))
        preview = center_preview(height, top, True)
        self.assertIn('23 1/2″ from the top', preview['export'])
        self.assertEqual(preview['offset'], '1/2″ above center')

    def test_up_and_down_move_physical_direction(self):
        height = dimension('48')
        top = from_top(height, dimension('24'), TOP)
        up = move_center(height, top, dimension('1/2'), 'up')
        self.assertEqual(up, dimension('23 1/2'))
        down = move_center(height, up, dimension('1'), 'down')
        self.assertEqual(down, dimension('24 1/2'))

    def test_reference_toggle_preserves_physical_position(self):
        height = dimension('48')
        stored = dimension('23 1/2')
        for _ in range(5):
            bottom = display_from_top(height, stored, BOTTOM)
            top = display_from_top(height, stored, TOP)
            self.assertEqual(from_top(height, bottom, BOTTOM), stored)
            self.assertEqual(from_top(height, top, TOP), stored)
            self.assertEqual(bottom, dimension('24 1/2'))
            self.assertEqual(top, dimension('23 1/2'))

    def test_signed_offsets_accept_zero_and_fractions_exactly(self):
        for text, value in [('0', 0), ('0.0', 0), ('0/2', 0), ('+3', 3),
                            ('-1/2', Fraction(-1, 2)), ('−1 1/2', Fraction(-3, 2))]:
            self.assertEqual(signed_inches(text), value)
        for text in ('', '+', '--1', '-1+2', '1/0'):
            with self.assertRaises(ValueError):
                signed_inches(text)

    def test_offset_three_and_negative_half(self):
        self.assertEqual(position_from_offset('0'), STANDARD)
        self.assertEqual(fractional(position_from_offset('3')), '7')
        self.assertEqual(fractional(position_from_offset('-1/2')), '3 1/2')
        self.assertEqual(fractional(position_from_offset('-1 1/2')), '2 1/2')
        self.assertEqual(fractional(offset_from_position(dimension('7'))), '3')
        self.assertIn('4″ + 3″ = 7″ from top', edge_equation('top', dimension('7')))
        self.assertIn('4″ − 1 1/2″ = 2 1/2″ from bottom', edge_equation('bottom', dimension('2 1/2')))

    def test_zero_and_outside_positions_rejected(self):
        with self.assertRaises(ValueError):
            from_top(dimension('36'), Fraction(0), TOP)
        with self.assertRaises(ValueError):
            from_top(dimension('36'), dimension('36'), TOP)
        with self.assertRaises(ValueError):
            position_from_offset('oops')

    def test_blank_center_and_disabled_setting(self):
        preview = center_preview(dimension('48'), None, False)
        self.assertEqual(preview['mozaik'], 'Mozaik: blank')
        self.assertIn('Blank center bore', preview['export'])
        self.assertIn('Center Bore setting: No', preview['offset'])


if __name__ == '__main__':
    unittest.main()

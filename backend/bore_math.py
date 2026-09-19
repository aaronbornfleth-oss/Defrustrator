"""UI-independent center and edge bore math. Stored/exported center is from the top."""
from __future__ import annotations

from fractions import Fraction

from converter import dimension, fractional

BOTTOM = 'Bottom — Mozaik'
TOP = 'Top — Decorative'
STANDARD = Fraction(4)


def from_top(height, position, reference):
    if reference not in (BOTTOM, TOP):
        raise ValueError('Choose Bottom — Mozaik or Top — Decorative.')
    if position is None:
        return None
    if not 0 < position < height:
        raise ValueError('Center bore must be inside the door: greater than zero and less than its height.')
    return height - position if reference == BOTTOM else position


def display_from_top(height, top_position, reference):
    """Convert a stored Decorative-from-top value into the editor's selected reference."""
    if top_position is None:
        return None
    if reference not in (BOTTOM, TOP):
        raise ValueError('Choose Bottom — Mozaik or Top — Decorative.')
    return height - top_position if reference == BOTTOM else top_position


def move_center(height, top_position, amount, direction):
    if direction not in ('up', 'down'):
        raise ValueError('Choose Move up or Move down.')
    if top_position is None:
        raise ValueError('Enter a center bore position before moving it.')
    moved = top_position - amount if direction == 'up' else top_position + amount
    return from_top(height, moved, TOP)


def signed_inches(text):
    text = text.strip().replace('−', '-')
    sign = -1 if text.startswith('-') else 1
    if text.startswith(('-', '+')):
        text = text[1:].strip()
    if not text:
        raise ValueError('Enter a Mozaik offset, such as 0, 3, or -1/2.')
    try:
        return sign * dimension(text)
    except ValueError:
        # The dimension parser deliberately rejects zero sizes; zero offsets
        # are valid, including decimal and fractional representations.
        try:
            if Fraction(text) == 0:
                return Fraction(0)
        except (ValueError, ZeroDivisionError):
            pass
        raise ValueError('Enter a Mozaik offset, such as 0, 3, or -1/2.') from None


def position_from_offset(offset_text):
    text = offset_text.strip()
    if not text:
        return None
    return STANDARD + signed_inches(text)


def offset_from_position(position):
    if position is None:
        return None
    return position - STANDARD


def validate_edge_position(edge, height, position):
    if position is not None and (position <= 0 or position >= height):
        raise ValueError(f'{edge.title()} bore must be inside the door.')
    return position


def edge_equation(edge, position):
    if position is None:
        return f'{edge.title()}: blank'
    offset = position - STANDARD
    operator = '+' if offset >= 0 else '−'
    return f'{edge.title()}: 4″ {operator} {fractional(abs(offset))}″ = {fractional(position)}″ from {edge}'


def center_preview(height, top, enabled):
    if top is None:
        return {
            'mozaik': 'Mozaik: blank',
            'export': 'Decorative will receive:\nBlank center bore position',
            'offset': 'Center Bore setting: Yes' if enabled else 'Center Bore setting: No',
            'valid': True,
        }
    bottom = height - top
    offset = height / 2 - top
    offset_text = ('Exactly centered' if not offset else
                   f'{fractional(abs(offset))}″ {"above" if offset > 0 else "below"} center')
    if not enabled:
        offset_text += ' · Center Bore setting: No'
    return {
        'mozaik': f'Mozaik: {fractional(bottom)}″ from bottom',
        'export': f'Decorative will receive:\n{fractional(top)}″ from the top',
        'offset': offset_text,
        'valid': True,
        'from_top': fractional(top),
        'from_bottom': fractional(bottom),
    }

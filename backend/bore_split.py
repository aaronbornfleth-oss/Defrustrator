"""Confirm custom boring and split quantity rows without UI widgets."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from converter import BORE_FIELDS


def custom_bores_changed(original, edited):
    if not edited.has_hinge_boring:
        return False
    before, after = original.bore_positions(), edited.bore_positions()
    return any(key in edited.bore_overrides
               and (key not in original.bore_overrides or edited.bore_overrides[key] != original.bore_overrides[key])
               and before[position] != after[position]
               for position, key in enumerate(BORE_FIELDS))


@dataclass
class BoreDecision:
    """User answers for custom-bore confirmation prompts."""
    duplicate: bool | None = None
    side: str | None = None
    left_count: int | None = None


class PendingBoreDecision(Exception):
    def __init__(self, quantity, location):
        self.quantity = quantity
        self.location = location
        if quantity == 1:
            question = 'Is this door left- or right-hinging?'
            details = 'Confirm Left (L) or Right (R). The confirmed location will be saved on this line item.'
        elif quantity == 2:
            question = 'Do you want to duplicate this custom bore position for the other door?'
            details = 'Yes creates two quantity-1 rows: one L and one R.'
        else:
            question = 'Do you want to duplicate this custom bore position for the other doors?'
            details = f'Yes creates {quantity} quantity-1 rows; you will confirm the L/R counts.'
        self.question = question
        self.details = details
        super().__init__(question)

    def payload(self):
        return {
            'pending': 'custom_bores',
            'quantity': self.quantity,
            'location': self.location,
            'question': self.question,
            'details': self.details,
            'suggested_left': (self.quantity + 1) // 2 if self.quantity > 2 else None,
        }


def hinge_sides(quantity, location=None, side=None, left_count=None):
    if quantity == 1:
        chosen = side if side in ('L', 'R') else (location if location in ('L', 'R') else None)
        if chosen not in ('L', 'R'):
            raise ValueError('Choose Left (L) or Right (R).')
        return [chosen]
    if left_count is None:
        raise ValueError(f'Enter a whole number from 0 to {quantity} for left-hinging doors.')
    if type(left_count) is not int or not 0 <= left_count <= quantity:
        raise ValueError(f'Enter a whole number from 0 to {quantity} for left-hinging doors.')
    return ['L'] * left_count + ['R'] * (quantity - left_count)


def confirm_custom_bores(original, edited, decision=None):
    """Return replacement rows. Raise PendingBoreDecision when a prompt is required."""
    if not custom_bores_changed(original, edited):
        return [edited]
    quantity = edited.qty
    if decision is None:
        raise PendingBoreDecision(quantity, edited.location)
    if quantity > 1:
        if decision.duplicate is None:
            raise PendingBoreDecision(quantity, edited.location)
        duplicate = decision.duplicate
    else:
        duplicate = False
    if duplicate:
        sides = ['L', 'R'] if quantity == 2 else hinge_sides(quantity, edited.location, left_count=decision.left_count)
    else:
        sides = hinge_sides(1, edited.location, side=decision.side)
    # Freeze all three effective positions, including blanks, for matching rows.
    positions = edited.default_bore_positions()
    positions.update(edited.bore_overrides)
    rows = []
    for side in sides:
        row = deepcopy(edited)
        row.qty = 1
        row.location = side
        if duplicate:
            row.bore_overrides = deepcopy(positions)
        rows.append(row)
    if not duplicate and quantity > 1:
        remainder = deepcopy(original)
        remainder.qty = quantity - 1
        rows.append(remainder)
    if sum(row.qty for row in rows) != quantity:
        raise ValueError('The split must preserve the total number of doors.')
    for row in rows:
        row.values()
    return rows

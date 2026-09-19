"""Build a hardware email draft from JSON-serializable form data. Never sends mail."""
from __future__ import annotations

from copy import deepcopy

from hardware import SPECIAL_CATEGORIES, OrderLine, email_body, order_lines
from hardware_settings import load_parts, save_parts


def empty_special():
    return {category: [{'part_number': '', 'quantity': '', 'unit': 'each'}] for category in SPECIAL_CATEGORIES}


def remembered_special(path=None):
    try:
        saved = load_parts(path)
    except (OSError, ValueError) as exc:
        return empty_special(), f'Saved part numbers could not be loaded. Re-enter them below. {exc}'
    special = empty_special()
    for category in SPECIAL_CATEGORIES:
        entries = saved.get(category) or []
        if entries:
            special[category] = [{'part_number': entry['part_number'], 'quantity': '', 'unit': entry['unit']}
                                 for entry in entries]
    return special, ''


def serialize_order_line(line, index):
    return {
        'index': index,
        'category': line.category,
        'part_number': line.part_number,
        'description': line.description,
        'quantity': line.quantity,
        'unit': line.unit,
        'source_quantity': line.source_quantity,
        'pages': list(line.pages),
        'needs_part': not bool(line.part_number),
        'needs_quantity': line.quantity is None,
    }


def collect_extras(special):
    extras = []
    remembered = {category: [] for category in SPECIAL_CATEGORIES}
    for category in SPECIAL_CATEGORIES:
        rows = special.get(category) or []
        for row in rows:
            part = str(row.get('part_number', '')).strip()
            raw_qty = str(row.get('quantity', '')).strip()
            unit = row.get('unit', 'each')
            if raw_qty and (not raw_qty.isascii() or not raw_qty.isdigit()):
                raise ValueError(f'{category}: enter a whole quantity, or leave it blank to skip.')
            quantity = int(raw_qty) if raw_qty else 0
            if part or quantity:
                line = OrderLine(category, part, category, quantity or 1, unit)
                line.validate()
                remembered[category].append({'part_number': part, 'unit': unit})
                if quantity:
                    extras.append(line)
    return extras, remembered


def generate_email(report, draft, settings_path=None):
    """Return (body, remembered_notice). Raises ValueError on invalid draft fields."""
    if report.hardware_errors:
        raise ValueError('Fix the hardware extraction issues and reopen the PDF.')
    lines = deepcopy(order_lines(report.hardware))
    parts = draft.get('parts') or {}
    quantities = draft.get('quantities') or {}
    for index, value in parts.items():
        lines[int(index)].part_number = str(value).strip()
    for index, value in quantities.items():
        qty = str(value).strip()
        if not qty.isdigit():
            raise ValueError(f'{lines[int(index)].description}: enter a whole number of sets.')
        lines[int(index)].quantity = int(qty)
    extras, remembered = collect_extras(draft.get('special') or {})
    body = email_body(report.job, lines, extras)
    notice = 'Part numbers remembered. Save order to keep this job’s draft.'
    try:
        save_parts(remembered, settings_path)
    except (OSError, ValueError) as exc:
        notice = f'Email ready, but part numbers could not be remembered: {exc}'
    return body, notice


def default_draft(report, settings_path=None, existing=None):
    special, load_notice = remembered_special(settings_path)
    draft = {
        'parts': {},
        'quantities': {},
        'special': special,
        'email': '',
        'generated_body': '',
        'preview': False,
    }
    if existing:
        draft = deepcopy(existing)
        if not draft.get('special'):
            draft['special'] = special
    return draft, load_notice

"""Hardware extraction and plain-text order drafts. Does not send email."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HINGE_PART = '71B3590'
CLIP_PART = '174H7100I'
DEFAULT_SPACER_PART = 'T593570'
LEG_LEVELER_PART = '40027290'
SPECIAL_CATEGORIES = ('Lazy Susan / bi-fold hinges', 'Blind-corner hinges', 'Blum AVENTOS hardware')
# Nominal drawer lengths from Blum's 563H component table:
# https://d2.blum.com/services/BEC003/tdmbmn_ep_dok_bus_%24sen-us_%24aof_%24v14.pdf
GLIDE_LENGTHS = {'229': '9 inches', '305': '12 inches', '381': '15 inches',
                 '457': '18 inches', '533': '21 inches'}


def clean(value):
    return ' '.join(str(value or '').split())


@dataclass
class HardwareItem:
    category: str
    qty: int
    part_number: str
    description: str
    page: int
    cabinets: str = ''
    original: str = ''


@dataclass
class OrderLine:
    category: str
    part_number: str
    description: str
    quantity: int | None
    unit: str = 'each'
    source_quantity: int | None = None
    pages: list[int] = field(default_factory=list)

    def validate(self):
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ValueError(f'{self.description}: enter a positive whole order quantity.')
        if not self.part_number.strip() or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._/-]*', self.part_number):
            raise ValueError(f'{self.description}: enter the part number.')
        if self.unit not in ('each', 'sets'):
            raise ValueError(f'{self.description}: choose each or sets.')
        if not self.description.strip() or '\n' in self.description or '\r' in self.description:
            raise ValueError('Enter a one-line hardware description.')


def classify_hardware(label):
    if re.search(r'\bspacers?\b', label, re.I):
        return 'spacers', DEFAULT_SPACER_PART
    if re.search(r'\b(?:clips?|plates?|brackets?|screws?|pins?|locking\s+devices?)\b', label, re.I):
        return None, ''
    if re.search(r'\bleg[\s-]+levell?ers?\b|\blevell?ing[\s-]+legs?\b', label, re.I):
        return 'levelers', LEG_LEVELER_PART
    if re.search(r'\beuro\s+frameless\b', label, re.I):
        return 'hinges', HINGE_PART
    match = re.search(r'\b563(?:H|\.)([0-9][A-Z0-9.-]*)\b', label, re.I)
    if match:
        return 'glides', '563.' + match[1].upper()
    if re.search(r'\b(?:glides?|slides?|runners?|TANDEM|MOVENTO)\b', label, re.I):
        # A glide without a specific SKU stays visible for user completion.
        return 'glides', ''
    return None, ''


def parse_hardware_tables(tables, page_number):
    items, errors = [], []
    found_header = False
    for table in tables:
        columns = None
        for cells in table:
            row = [clean(cell) for cell in cells]
            if 'Quan' in row and 'Part' in row:
                columns = {'qty': row.index('Quan'), 'part': row.index('Part'),
                           'cab': next((i for i, text in enumerate(row) if 'Room' in text), None)}
                found_header = True
                continue
            if columns is None or not any(row):
                continue
            if len(row) <= max(columns['qty'], columns['part']):
                errors.append(f'Hardware page {page_number}: a table row is incomplete.')
                continue
            label = row[columns['part']]
            category, part_number = classify_hardware(label)
            if category is None:
                continue
            raw_qty = row[columns['qty']]
            match = re.fullmatch(r'\(?([0-9]+)\)?', raw_qty)
            if not match or int(match[1]) <= 0:
                errors.append(f'Hardware page {page_number}: invalid quantity {raw_qty!r} for {label}.')
                continue
            cabinet = row[columns['cab']] if columns['cab'] is not None and columns['cab'] < len(row) else ''
            items.append(HardwareItem(category, int(match[1]), part_number, label,
                                      page_number, cabinet, ' | '.join(row)))
    if not found_header:
        errors.append(f'Hardware page {page_number}: no readable hardware table was found.')
    return items, errors


def order_lines(items):
    """Aggregate identical SKUs before converting individual glides into sets."""
    grouped = {}
    for item in items:
        key = (item.category, item.part_number, item.description if not item.part_number else '')
        if key not in grouped:
            grouped[key] = [0, set(), item.description]
        grouped[key][0] += item.qty
        grouped[key][1].add(item.page)
    result = []
    for (category, part_number, _), (qty, pages, label) in grouped.items():
        if category == 'hinges':
            result.append(OrderLine('hinges', HINGE_PART, 'Euro frameless hinges', qty, 'each', qty, sorted(pages)))
            result.append(OrderLine('clips', CLIP_PART, 'Hinge clips', qty, 'each', qty, sorted(pages)))
        elif category == 'glides':
            match = re.match(r'563\.(\d{3})', part_number)
            length = GLIDE_LENGTHS.get(match[1]) if match else None
            description = f'Blum TANDEM drawer glides, {length}' if length else label
            result.append(OrderLine('glides', part_number, description, qty // 2 if qty % 2 == 0 else None,
                                    'sets', qty, sorted(pages)))
        elif category == 'levelers':
            result.append(OrderLine('levelers', LEG_LEVELER_PART, 'Adjustable leg levelers', qty, 'each', qty, sorted(pages)))
        else:
            result.append(OrderLine('spacers', part_number, label, qty, 'each', qty, sorted(pages)))
    rank = {'hinges': 0, 'clips': 1, 'glides': 2, 'spacers': 3, 'levelers': 4}
    return sorted(result, key=lambda line: (rank[line.category], line.part_number, line.description))


def email_body(job, base_lines, extras=()):
    """Draft standard hardware and any optional parts with reviewed quantities."""
    if any(line.category not in SPECIAL_CATEGORIES for line in extras):
        raise ValueError('Choose a supported special-hardware category.')
    lines = list(base_lines) + list(extras)
    if not lines:
        raise ValueError('No hardware is selected for this email.')
    for line in lines:
        line.validate()
    hinge_qty = sum(line.quantity for line in base_lines if line.category == 'hinges')
    clip_qty = sum(line.quantity for line in base_lines if line.category == 'clips')
    if hinge_qty != clip_qty:
        raise ValueError('The standard hinge and hinge-clip quantities must match.')
    if any(line.part_number != HINGE_PART for line in base_lines if line.category == 'hinges'):
        raise ValueError(f'Standard hinges must use {HINGE_PART}.')
    if any(line.part_number != CLIP_PART for line in base_lines if line.category == 'clips'):
        raise ValueError(f'Standard hinge clips must use {CLIP_PART}.')
    headings = [('Hinges and hinge clips', ('hinges', 'clips')),
                ('Drawer glide sets', ('glides',)), ('Spacers', ('spacers',)),
                ('Adjustable leg levelers', ('levelers',))]
    headings.extend((category, (category,)) for category in SPECIAL_CATEGORIES)
    output = [f'Please order the following hardware for {clean(job)}:', '']
    for heading, categories in headings:
        members = [line for line in lines if line.category in categories]
        if not members:
            continue
        output.append(heading)
        for line in members:
            unit = 'set' if line.unit == 'sets' and line.quantity == 1 else line.unit
            output.append(f'- {line.quantity} {unit} - {line.part_number} - {line.description}')
        output.append('')
    output.extend(['Please confirm availability and delivery timing.', '', 'Thank you.'])
    return '\n'.join(output)

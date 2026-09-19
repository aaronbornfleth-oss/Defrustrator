"""Mozaik report extraction and supplier CSV rules. All processing is local."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import pdfplumber
from hardware import HardwareItem, parse_hardware_tables

DOOR_HEADERS = ['Type', 'Qty', 'Width', 'Height', 'French Lite', 'Bore ', 'Location',
                'Center Bore', 'Top Bore Position', 'Center Bore Position', 'Bottom Bore Position']
BOX_HEADERS = ['Qty', 'Drawer Width', 'Drawer Height', 'Drawer Depth', 'Scoop']
DOOR_TYPES = ['Door', 'Applied Door', '5-Piece Drawer Front', 'Solid Drawer Front', 'Routed Drawer Front', 'Glass', 'French Lite']
TYPE_LABELS = {value: 'Glass Front Door' if value == 'Glass' else value for value in DOOR_TYPES}
TYPE_CHOICES = list(TYPE_LABELS.values())
QUICK_TYPES = ['Door', 'Applied Door', 'Glass Front Door', '5-Piece Drawer Front']
BOX_TYPES = ['Drawer Box', 'Tray']
BORE_FIELDS = {'top': 'Top Bore Position', 'center': 'Center Bore Position', 'bottom': 'Bottom Bore Position'}
EXPORT_KINDS = ('doors', 'short_fronts', 'boxes')
EXPORT_SUFFIXES = {'doors': 'doors-and-fronts', 'short_fronts': 'drawer-fronts-under-7-inches', 'boxes': 'drawer-boxes-and-trays'}
LOCATIONS = ['L', 'R', 'Susan']


def canonical_type(label):
    return 'Glass' if label == 'Glass Front Door' else label


def clean(value):
    return ' '.join(str(value or '').split())


def dimension(text: str) -> Fraction:
    """Parse inches without rounding; reject malformed or non-positive sizes."""
    text = clean(text).replace('⁄', '/').rstrip('"').strip()
    text = re.sub(r'(?<=\d)-(?=\d+\s*/)', ' ', text)
    if not re.fullmatch(r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)', text):
        raise ValueError(f'Invalid size: {text!r}. Use inches, such as 17 27/32 or 17.84375.')
    try:
        value = sum((Fraction(x) for x in text.split()), Fraction())
    except (ValueError, ZeroDivisionError):
        raise ValueError(f'Invalid fraction: {text!r}.') from None
    if value <= 0:
        raise ValueError('Sizes must be greater than zero.')
    return value


def fractional(value: Fraction) -> str:
    """Format exact inches as reduced mixed fractions, using plain CSV text."""
    sign = '-' if value < 0 else ''
    whole, numerator = divmod(abs(value.numerator), value.denominator)
    if not numerator:
        return f'{sign}{whole}'
    prefix = f'{whole} ' if whole else ''
    return f'{sign}{prefix}{numerator}/{value.denominator}'


@dataclass
class Item:
    kind: str
    qty: int
    width: Fraction
    height: Fraction
    depth: Fraction | None
    type: str
    location: str
    scoop: str
    french_lite: str
    page: int
    group: str
    part: str
    cabinets: str
    original: str
    included: bool = True
    deleted: bool = False
    # Missing keys follow the type/height defaults. None explicitly clears a cell.
    # Center positions are always measured from the top for Decorative.
    bore_overrides: dict[str, Fraction | None] = field(default_factory=dict)

    @property
    def is_front(self):
        return 'Drawer Front' in self.type

    @property
    def has_hinge_boring(self):
        return self.kind == 'doors' and not self.is_front and self.type != 'Applied Door'

    @property
    def export_kind(self):
        return 'short_fronts' if self.kind == 'doors' and self.is_front and self.height < 7 else self.kind

    @property
    def bore_location(self):
        if self.type in ('5-Piece Drawer Front', 'Applied Door'):
            return 'none'
        return '' if self.is_front else self.location

    def default_bore_positions(self):
        return {'top': Fraction(4) if self.has_hinge_boring else None,
                'center': self.height / 2 if self.has_hinge_boring and self.height > 36 else None,
                'bottom': Fraction(4) if self.has_hinge_boring else None}

    def bore_positions(self):
        positions = self.default_bore_positions()
        for key, value in self.bore_overrides.items():
            if key not in BORE_FIELDS:
                raise ValueError('Unknown bore position.')
            if value is not None and (value <= 0 or value >= self.height):
                raise ValueError(f'{BORE_FIELDS[key]} must be greater than zero and less than the height, or blank.')
            positions[key] = value
        return [fractional(positions[key]) if positions[key] is not None else '' for key in BORE_FIELDS]

    def values(self):
        if self.qty <= 0 or not isinstance(self.qty, int):
            raise ValueError('Quantity must be a positive whole number.')
        for value in (self.width, self.height, *([self.depth] if self.kind == 'boxes' else [])):
            if value is None or value <= 0:
                raise ValueError('Every size must be greater than zero.')
        if self.kind == 'boxes':
            if self.scoop not in ('', 'A'):
                raise ValueError('Scoop must be blank or A.')
            return [str(self.qty), fractional(self.width), fractional(self.height), fractional(self.depth), self.scoop]
        if self.type not in DOOR_TYPES:
            raise ValueError('Choose a supported door or drawer-front type.')
        if self.has_hinge_boring and self.location not in LOCATIONS:
            raise ValueError('Choose L, R, or Susan for the hinge location.')
        if self.type == 'French Lite' and not self.french_lite.strip():
            raise ValueError('Enter the French Lite configuration before export.')
        # Variable supplier text is never interpreted as a spreadsheet formula.
        if self.french_lite.lstrip().startswith(('=', '+', '-', '@')):
            raise ValueError('French Lite must be a configuration label, not a formula.')
        center = self.has_hinge_boring and self.height > 36
        if not self.has_hinge_boring:
            center_bore = 'no' if self.type in ('5-Piece Drawer Front', 'Applied Door') else ''
        else:
            center_bore = 'Yes' if center else 'No'
        return [self.type, str(self.qty), fractional(self.width), fractional(self.height),
                self.french_lite if self.type == 'French Lite' else '',
                'A' if self.has_hinge_boring else 'None', self.bore_location,
                center_bore, *self.bore_positions()]

    def supplier_values(self):
        values = self.values()
        if self.type == 'Applied Door':
            values[0] = 'Door'
        return values


@dataclass
class Report:
    source: str
    job: str = ''
    items: list[Item] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    hardware_pages: list[int] = field(default_factory=list)
    hardware: list[HardwareItem] = field(default_factory=list)
    hardware_errors: list[str] = field(default_factory=list)


def classify(kind, part, group):
    label = f'{part} {group}'.lower()
    if kind == 'boxes':
        # The section distinguishes trays from drawer boxes, including the
        # generic report heading "Dwr Box/Tray Sizes" that contains both words.
        if re.search(r'\btray\b', part.lower()) or re.search(r'\btray\b', group.lower()):
            return 'Tray', '', 'A'
        if re.search(r'\b(drawer|dwr)\b', label):
            return 'Drawer Box', '', ''
        raise ValueError(f'Cannot identify drawer box or tray: {part!r}.')
    if re.search(r'drawer\s*front|\bdrawer\b', label):
        return '5-Piece Drawer Front', '', ''
    location = 'Susan' if re.search(r'\bsusan\b', label) else 'L'
    if re.search(r'\bglass\b', label):
        return 'Glass', location, ''
    if re.search(r'french\s*lite', label):
        return 'French Lite', location, ''
    if re.search(r'\bapplied\s+door\b', label):
        return 'Applied Door', '', ''
    if re.search(r'\bdoor\b', label):
        return 'Door', location, ''
    raise ValueError(f'Cannot identify door type: {part!r}.')


def read_report(path: str | Path) -> Report:
    path = Path(path)
    report = Report(str(path))
    # Totals may appear only on the final page of a multi-page section.
    pending: dict[tuple[str, str], int] = {}
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ''
            job = re.search(r'^Job:\s*(.+)', text, re.M)
            if job and not report.job:
                report.job = clean(job[1])
            if not text.strip():
                report.errors.append(f'Page {page_no}: no readable text. Export a text PDF from Mozaik; scanned pages are not supported.')
                continue
            if re.search(r'^Hardware(?: List)?\s*$', text, re.M | re.I):
                report.hardware_pages.append(page_no)
                hardware, errors = parse_hardware_tables(page.extract_tables(), page_no)
                report.hardware.extend(hardware)
                report.hardware_errors.extend(errors)
                continue
            title = re.search(r'Cutlist for (Door Sizes|Dwr Box/Tray Sizes)\s*\((.+)\)', text, re.I)
            if not title:
                report.errors.append(f'Page {page_no}: report section is not recognized. No rows from this page were exported.')
                continue
            kind = 'doors' if title[1].lower() == 'door sizes' else 'boxes'
            group = clean(title[2])
            key = (kind, group)
            pending.setdefault(key, 0)
            page_rows = 0
            found_header = False
            total_seen = False
            for table in page.extract_tables():
                columns = None
                for cells in table:
                    row = [clean(c) for c in cells]
                    if 'Quan' in row and 'Width' in row and 'Height' in row and 'Part' in row:
                        columns = {name: row.index(name) for name in ('Quan', 'Width', 'Height', 'Part')}
                        if kind == 'boxes' and 'Depth' not in row:
                            report.errors.append(f'Page {page_no}: drawer depth column is missing.')
                            columns = None
                            continue
                        if kind == 'boxes':
                            columns['Depth'] = row.index('Depth')
                        columns['Cab'] = next((i for i, x in enumerate(row) if 'Room' in x), len(row) - 1)
                        found_header = True
                        continue
                    if columns is None:
                        continue
                    joined = ' '.join(row)
                    if '(Total)' in joined:
                        if re.search(r'\b(Doors|Boxes)\b', joined):
                            match = re.fullmatch(r'\(?([0-9]+)\)?', row[columns['Quan']])
                            if not match:
                                report.errors.append(f'Page {page_no}: unreadable section quantity total.')
                            else:
                                expected = int(match[1])
                                actual = pending[key]
                                report.checks.append(f'{group}: {actual} extracted / {expected} reported (page {page_no})')
                                if actual != expected:
                                    report.errors.append(f'Page {page_no}, {group}: extracted quantity {actual}, PDF total {expected}.')
                                pending[key] = 0
                                total_seen = True
                        continue
                    if not any(row):
                        continue
                    qty_text = row[columns['Quan']]
                    # Catch rows with dimensions but no readable quantity.
                    if not qty_text and not row[columns['Width']] and not row[columns['Height']]:
                        continue
                    try:
                        match = re.fullmatch(r'\(?([0-9]+)\)?', qty_text)
                        if not match or int(match[1]) <= 0:
                            raise ValueError(f'Invalid quantity: {qty_text!r}.')
                        qty = int(match[1])
                        width, height = dimension(row[columns['Width']]), dimension(row[columns['Height']])
                        depth = dimension(row[columns['Depth']]) if kind == 'boxes' else None
                        part = row[columns['Part']]
                        item_type, location, scoop = classify(kind, part, group)
                        item = Item(kind, qty, width, height, depth, item_type, location, scoop, '',
                                    page_no, group, part, row[columns['Cab']], joined)
                        report.items.append(item)
                        pending[key] += qty
                        page_rows += 1
                        if item_type == 'French Lite':
                            report.notes.append(f'Page {page_no}: enter the French Lite configuration for {item.cabinets}.')
                    except (ValueError, IndexError) as error:
                        report.errors.append(f'Page {page_no}: {error} Source row: {joined}')
            if not found_header or page_rows == 0:
                report.errors.append(f'Page {page_no}: no readable size rows found in the expected table.')
            if total_seen and pending[key]:
                report.errors.append(f'Page {page_no}: rows appear after the section total.')
        for (_, group), qty in pending.items():
            if qty:
                report.errors.append(f'{group}: extracted quantity {qty} has no matching PDF section total.')
    if not report.items:
        report.errors.append('No door, drawer-front, drawer-box, or tray sizes were found.')
    if not report.job:
        report.job = path.stem
    return report


def delimited_text(headers, rows, delimiter=',', include_headers=True):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator='\r\n')
    if include_headers:
        writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue()


def csv_text(items: list[Item], kind: str) -> str:
    return delimited_text(BOX_HEADERS if kind == 'boxes' else DOOR_HEADERS,
                          [item.supplier_values() for item in items if item.export_kind == kind and item.included and not item.deleted])


def safe_name(text):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', text).strip(' .')[:140] or 'Mozaik'


def export_items(report: Report, group: str | None = None):
    """Partition included rows once; small fronts never occur in the standard batch."""
    if report.errors:
        raise ValueError('Fix the source PDF and import it again. Extraction errors block export:\n' + '\n'.join(report.errors))
    items = [item for item in report.items if item.included and not item.deleted and (group is None or item.group == group)]
    if not items:
        raise ValueError('There are no included rows to export.')
    return {kind: batch for kind in EXPORT_KINDS if (batch := [item for item in items if item.export_kind == kind])}


def export_tables(report: Report, group: str | None = None):
    """One validated snapshot for both saved CSVs and clipboard previews."""
    return {kind: (list(BOX_HEADERS if kind == 'boxes' else DOOR_HEADERS),
                   [item.supplier_values() for item in items])
            for kind, items in export_items(report, group).items()}


def export_report(report: Report, directory: str | Path, group: str | None = None):
    # Validate every included row before any file is written.
    tables = export_tables(report, group)
    payloads = {kind: delimited_text(headers, rows) for kind, (headers, rows) in tables.items()}
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = safe_name(report.job + (f' - {group}' if group else ''))
    paths = []
    for kind, text in payloads.items():
        suffix = EXPORT_SUFFIXES[kind]
        target = directory / f'{stem} - {suffix}.csv'
        number = 2
        while target.exists():
            target = directory / f'{stem} - {suffix} ({number}).csv'
            number += 1
        with target.open('x', encoding='utf-8', newline='') as output:
            output.write(text)
        paths.append(target)
    return paths

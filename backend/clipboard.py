"""Supplier clipboard TSV: headers always, CRLF rows, no trailing blank row."""
from converter import BOX_HEADERS, DOOR_HEADERS, delimited_text, export_tables

CLIPBOARD_DOOR_HEADERS = [header.strip() for header in DOOR_HEADERS]
CLIPBOARD_BOX_HEADERS = [header.strip() for header in BOX_HEADERS]
LABELS = {
    'doors': 'Doors & standard fronts',
    'short_fronts': 'Fronts under 7 inches',
    'boxes': 'Drawer boxes & trays',
}
BATCH_NOTES = {
    'doors': 'Doors of any height and drawer fronts 7 inches or taller. Applied doors copy as Door with no hinge boring.',
    'short_fronts': 'Copy these drawer fronts separately. Configure narrower top and bottom rails in Decorative for this group.',
    'boxes': 'Change type switches Drawer Box / Tray and updates Scoop. The five supplier columns are copied; row labels are for review.',
}


def clipboard_text(headers, rows):
    # Decorative consumes the first line as headers. Use the original supplier
    # names, without preview letters or incidental template spaces.
    # A final row separator becomes an empty row in Decorative's paste box.
    # Remove only that separator; trailing tabs are required blank cells.
    return delimited_text([header.strip() for header in headers], rows,
                          delimiter='\t', include_headers=True).removesuffix('\r\n')


def item_total(kind, rows):
    quantity_column = 0 if kind == 'boxes' else 1
    return sum(int(row[quantity_column]) for row in rows)


def clipboard_for_kind(report, kind, group=None, selected_indices=None):
    tables = export_tables(report, group)
    if kind not in tables:
        raise ValueError('There are no included rows in that Decorative copy group.')
    headers, rows = tables[kind]
    if selected_indices is not None:
        chosen = set(selected_indices)
        rows = [row for index, row in enumerate(rows) if index in chosen]
        if not rows:
            raise ValueError('Select one or more rows to copy.')
    return clipboard_text(headers, rows)

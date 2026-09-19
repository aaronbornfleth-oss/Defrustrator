"""Versioned, self-contained order documents. JSON only; writes are atomic."""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
from fractions import Fraction
import json
import os
from pathlib import Path
import tempfile

import branding as brand
from converter import Item, Report, BORE_FIELDS, DOOR_TYPES, BOX_TYPES, dimension, fractional
from hardware import HardwareItem, SPECIAL_CATEGORIES, order_lines
from row_history import Change, RowHistory

FORMAT = 'mozaik-decorative-order'
VERSION = 1
EXTENSION = '.mddorder'
MAX_BYTES = 128 * 1024 * 1024


def require(condition, message='The order file contains invalid data.'):
    if not condition:
        raise ValueError(message)


def mapping(value, keys):
    require(type(value) is dict and set(value) == set(keys))
    return value


def text(value):
    require(type(value) is str)
    return value


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum)
    return value


def sequence(value, decode):
    require(type(value) is list)
    return [decode(entry) for entry in value]


def measure(value):
    return dimension(text(value))


def decode_item(raw):
    data = dict(mapping(raw, [f.name for f in fields(Item)]))
    for key in ('kind', 'type', 'location', 'scoop', 'french_lite', 'group', 'part', 'cabinets', 'original'):
        text(data[key])
    require(data['kind'] in ('doors', 'boxes'))
    require(data['type'] in (DOOR_TYPES if data['kind'] == 'doors' else BOX_TYPES))
    integer(data['qty'], 1)
    integer(data['page'], 1)
    for key in ('included', 'deleted'):
        require(type(data[key]) is bool)
    for key in ('width', 'height'):
        data[key] = measure(data[key])
    data['depth'] = None if data['depth'] is None else measure(data['depth'])
    overrides = data['bore_overrides']
    require(type(overrides) is dict and set(overrides) <= set(BORE_FIELDS))
    data['bore_overrides'] = {key: None if value is None else measure(value) for key, value in overrides.items()}
    item = Item(**data)
    # An unfinished French Lite configuration may be saved for later review.
    checked = deepcopy(item)
    if checked.type == 'French Lite' and not checked.french_lite.strip():
        checked.french_lite = 'Configuration required'
    checked.values()
    return item


def decode_hardware(raw):
    data = dict(mapping(raw, [f.name for f in fields(HardwareItem)]))
    for key in ('category', 'part_number', 'description', 'cabinets', 'original'):
        text(data[key])
    require(data['category'] in ('hinges', 'glides', 'spacers', 'levelers'))
    integer(data['qty'], 1)
    integer(data['page'], 1)
    return HardwareItem(**data)


def decode_report(raw):
    data = dict(mapping(raw, [f.name for f in fields(Report)]))
    text(data['source'])
    text(data['job'])
    data['items'] = sequence(data['items'], decode_item)
    data['hardware'] = sequence(data['hardware'], decode_hardware)
    for key in ('errors', 'notes', 'checks', 'hardware_errors'):
        sequence(data[key], text)
    sequence(data['hardware_pages'], lambda value: integer(value, 1))
    return Report(**data)


def decode_changes(raw):
    def index_map(data):
        require(type(data) is dict and all(type(key) is str and key.isascii() and key.isdigit() for key in data))
        result = {int(key): decode_item(value) for key, value in data.items()}
        require(len(result) == len(data))
        return result
    def change(data):
        mapping(data, [f.name for f in fields(Change)])
        result = Change(text(data['label']), index_map(data['before']), index_map(data['after']),
                        None if data['before_rows'] is None else sequence(data['before_rows'], decode_item),
                        None if data['after_rows'] is None else sequence(data['after_rows'], decode_item))
        require(result.before and result.before.keys() == result.after.keys())
        require((result.before_rows is None) == (result.after_rows is None))
        return result
    return sequence(raw, change)


def check_history(items, changes, undo):
    state = deepcopy(items)
    for change in reversed(changes):
        expected = change.after if undo else change.before
        target = change.before if undo else change.after
        expected_rows = change.after_rows if undo else change.before_rows
        target_rows = change.before_rows if undo else change.after_rows
        require(all(index < len(state) and state[index] == item for index, item in expected.items()),
                'The saved undo history does not match the order rows.')
        if expected_rows is not None:
            require(state == expected_rows)
            require(all(index < len(target_rows) and target_rows[index] == item for index, item in target.items()))
            state = deepcopy(target_rows)
        else:
            for index, item in target.items():
                state[index] = deepcopy(item)


def decode_draft(raw, report):
    if raw is None:
        return None
    mapping(raw, ('parts', 'quantities', 'special', 'email', 'generated_body', 'preview'))
    count = len(order_lines(report.hardware))
    for key in ('parts', 'quantities'):
        require(type(raw[key]) is dict)
        for index, value in raw[key].items():
            require(type(index) is str and index.isascii() and index.isdigit() and int(index) < count)
            text(value)
    mapping(raw['special'], SPECIAL_CATEGORIES)
    for rows in raw['special'].values():
        require(type(rows) is list and len(rows) > 0)
        for row in rows:
            mapping(row, ('part_number', 'quantity', 'unit'))
            for value in row.values(): text(value)
            require(row['unit'] in ('each', 'sets'))
    text(raw['email'])
    text(raw['generated_body'])
    require(type(raw['preview']) is bool)
    return deepcopy(raw)


@dataclass
class SavedOrder:
    report: Report
    history: RowHistory
    hardware_draft: dict | None
    view: dict


def decode_document(raw):
    mapping(raw, ('format', 'version', 'app_version', 'report', 'history', 'hardware_draft', 'view'))
    require(raw['format'] == FORMAT, 'This is not a Defrustrator order file.')
    require(type(raw['version']) is int and raw['version'] == VERSION,
            'This order format is not supported by this app version.')
    text(raw['app_version'])
    report = decode_report(raw['report'])
    mapping(raw['history'], ('undo', 'redo'))
    history = RowHistory(report)
    history.undo_stack = decode_changes(raw['history']['undo'])
    history.redo_stack = decode_changes(raw['history']['redo'])
    check_history(report.items, history.undo_stack, undo=True)
    check_history(report.items, history.redo_stack, undo=False)
    draft = decode_draft(raw['hardware_draft'], report)
    view = mapping(raw['view'], ('group', 'tab', 'selection'))
    text(view['group'])
    require(view['tab'] in ('doors', 'boxes'))
    mapping(view['selection'], ('doors', 'boxes'))
    for indices in view['selection'].values():
        sequence(indices, integer)
        require(all(index < len(report.items) for index in indices))
    return SavedOrder(report, history, draft, deepcopy(view))


def read_order(path):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, 'This order file is too large to open.')
        return decode_document(json.loads(raw.decode('utf-8-sig')))
    except (UnicodeError, RecursionError, TypeError, KeyError) as exc:
        raise ValueError('The order file is damaged or has an invalid format.') from exc


def write_order(path, report, history, hardware_draft, view):
    def encode(value):
        if isinstance(value, Fraction): return fractional(value)
        raise TypeError(f'Unsupported order value: {type(value).__name__}')
    payload = {'format': FORMAT, 'version': VERSION, 'app_version': brand.APP_VERSION,
               'report': asdict(report),
               'history': {'undo': [asdict(change) for change in history.undo_stack],
                           'redo': [asdict(change) for change in history.redo_stack]},
               'hardware_draft': hardware_draft, 'view': view}
    data = json.dumps(payload, default=encode, ensure_ascii=False, indent=2).encode('utf-8')
    require(len(data) <= MAX_BYTES, 'This order is too large to save.')
    decode_document(json.loads(data))  # Ensure the document can reopen before replacing a saved file.
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix='.defrustrator-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

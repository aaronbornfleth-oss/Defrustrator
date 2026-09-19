"""In-memory staff session: one active report, history, and hardware draft."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from clipboard import BATCH_NOTES, LABELS, clipboard_text, item_total
from converter import (BOX_HEADERS, BOX_TYPES, DOOR_HEADERS, EXPORT_KINDS, QUICK_TYPES,
                       TYPE_CHOICES, delimited_text, export_items, export_tables, read_report,
                       safe_name)
from customizations import field_values
from edits import (apply_row_edit, change_item_type, default_editor_fields, delete_items,
                   item_counts, serialize_item)
from hardware import SPECIAL_CATEGORIES, order_lines
from hardware_email import default_draft, generate_email, serialize_order_line
from order_files import EXTENSION, SavedOrder, decode_document, read_order, write_order
from row_history import RowHistory

MAX_PDF_BYTES = 32 * 1024 * 1024


@dataclass
class Workspace:
    report: object | None = None
    history: RowHistory | None = None
    hardware_draft: dict | None = None
    saved_hardware_draft: dict | None = None
    order_filename: str | None = None
    view: dict = field(default_factory=lambda: {
        'group': '',
        'tab': 'doors',
        'selection': {'doors': [], 'boxes': []},
    })
    generation: int = 0
    lock: Lock = field(default_factory=Lock)

    @property
    def dirty(self):
        if not self.history:
            return False
        return self.history.dirty or self.hardware_draft != self.saved_hardware_draft

    def require_report(self):
        if not self.report or not self.history:
            raise ValueError('Open a Mozaik PDF or a saved .mddorder file first.')
        return self.report, self.history

    def clear(self):
        self.report = None
        self.history = None
        self.hardware_draft = None
        self.saved_hardware_draft = None
        self.order_filename = None
        self.view = {'group': '', 'tab': 'doors', 'selection': {'doors': [], 'boxes': []}}
        self.generation += 1

    def accept_report(self, report, history=None, hardware_draft=None, view=None, filename=None, mark_saved=False):
        self.generation += 1
        self.report = report
        self.history = history or RowHistory(report)
        self.hardware_draft = deepcopy(hardware_draft)
        self.saved_hardware_draft = deepcopy(hardware_draft) if mark_saved else None
        self.order_filename = filename
        if view:
            self.view = deepcopy(view)
        else:
            self.view = {'group': '', 'tab': 'doors', 'selection': {'doors': [], 'boxes': []}}
        if mark_saved:
            self.history.mark_saved()

    def load_pdf(self, path, original_name=None):
        report = read_report(path)
        if original_name:
            report.source = original_name
        self.accept_report(report)
        return report

    def load_order_bytes(self, raw, filename):
        import json
        from order_files import MAX_BYTES, require
        require(len(raw) <= MAX_BYTES, 'This order file is too large to open.')
        saved = decode_document(json.loads(raw.decode('utf-8-sig')))
        name = filename if filename.endswith(EXTENSION) else Path(filename).stem + EXTENSION
        self.accept_report(saved.report, saved.history, saved.hardware_draft, saved.view,
                           filename=name, mark_saved=True)
        return saved

    def load_order_path(self, path):
        saved = read_order(path)
        self.accept_report(saved.report, saved.history, saved.hardware_draft, saved.view,
                           filename=Path(path).name, mark_saved=True)
        return saved

    def apply_type(self, index, label):
        _, history = self.require_report()
        return change_item_type(history, index, label)

    def apply_delete(self, indices):
        _, history = self.require_report()
        return delete_items(history, indices)

    def apply_edit(self, index, payload):
        _, history = self.require_report()
        return apply_row_edit(
            history, index, payload.get('fields') or {},
            included=payload.get('included'),
            center_reference=payload.get('center_reference', 'Bottom — Mozaik'),
            manual_positions=payload.get('manual_positions'),
            edge_offsets=payload.get('edge_offsets'),
            decision=payload.get('decision'),
        )

    def undo(self):
        _, history = self.require_report()
        return history.undo()

    def redo(self):
        _, history = self.require_report()
        return history.redo()

    def set_view(self, **updates):
        self.view.update({key: value for key, value in updates.items() if value is not None})

    def set_hardware_draft(self, draft):
        self.require_report()
        self.hardware_draft = deepcopy(draft)

    def order_payload_path(self, directory, filename=None):
        report, history = self.require_report()
        name = filename or self.order_filename or f'{safe_name(report.job)}{EXTENSION}'
        if not name.endswith(EXTENSION):
            raise ValueError('Save the editable order as a .mddorder file.')
        path = Path(directory) / name
        write_order(path, report, history, self.hardware_draft, self.view)
        self.history.mark_saved()
        self.saved_hardware_draft = deepcopy(self.hardware_draft)
        self.order_filename = name
        return path

    def encode_order(self):
        report, history = self.require_report()
        from dataclasses import asdict
        from fractions import Fraction
        import json
        import branding as brand
        from converter import fractional
        from order_files import FORMAT, VERSION, decode_document

        def encode(value):
            if isinstance(value, Fraction):
                return fractional(value)
            raise TypeError(f'Unsupported order value: {type(value).__name__}')

        payload = {
            'format': FORMAT, 'version': VERSION, 'app_version': brand.APP_VERSION,
            'report': asdict(report),
            'history': {'undo': [asdict(change) for change in history.undo_stack],
                        'redo': [asdict(change) for change in history.redo_stack]},
            'hardware_draft': self.hardware_draft, 'view': self.view,
        }
        data = json.dumps(payload, default=encode, ensure_ascii=False, indent=2).encode('utf-8')
        decode_document(json.loads(data))
        name = self.order_filename or f'{safe_name(report.job)}{EXTENSION}'
        if not name.endswith(EXTENSION):
            name = Path(name).stem + EXTENSION
        self.history.mark_saved()
        self.saved_hardware_draft = deepcopy(self.hardware_draft)
        self.order_filename = name
        return name, data

    def snapshot(self):
        if not self.report:
            return empty_snapshot()
        report, history = self.report, self.history
        originals = history.original_items()
        group = self.view.get('group') or ''
        items = [serialize_item(item, originals[index], index)
                 for index, item in enumerate(report.items)]
        visible_group = group or None
        counts = item_counts(report.items, visible_group)
        invalid = [row['issue'] for row in items if row['issue'] and not row['deleted']]
        export_blocked = bool(report.errors or invalid or not any(
            item.included and not item.deleted and (not group or item.group == group)
            for item in report.items
        ))
        groups = list(dict.fromkeys(item.group for item in report.items))
        hardware_lines = [serialize_order_line(line, index)
                          for index, line in enumerate(order_lines(report.hardware))]
        tables = {}
        if not report.errors and not invalid:
            try:
                exported = export_tables(report, group or None)
                source = export_items(report, group or None)
                id_map = {id(item): index for index, item in enumerate(report.items)}
                for kind in EXPORT_KINDS:
                    headers, rows = exported.get(kind, (BOX_HEADERS if kind == 'boxes' else DOOR_HEADERS, []))
                    indices = [id_map[id(item)] for item in source.get(kind, [])]
                    tables[kind] = {
                        'label': LABELS[kind],
                        'note': BATCH_NOTES[kind],
                        'headers': [header.strip() for header in headers],
                        'csv_headers': list(headers),
                        'rows': rows,
                        'source_indices': indices,
                        'item_total': item_total(kind, rows),
                    }
            except ValueError:
                tables = {}
                export_blocked = True
        return {
            'app_name': 'Mozaik to Decorative Defrustrator',
            'app_version': '1.21',
            'has_report': True,
            'job': report.job,
            'source': report.source,
            'dirty': self.dirty,
            'can_undo': bool(history.undo_stack),
            'can_redo': bool(history.redo_stack),
            'undo_label': history.undo_stack[-1].label if history.undo_stack else '',
            'redo_label': history.redo_stack[-1].label if history.redo_stack else '',
            'errors': list(report.errors),
            'notes': list(report.notes),
            'checks': list(report.checks),
            'hardware_errors': list(report.hardware_errors),
            'hardware_pages': list(report.hardware_pages),
            'groups': groups,
            'view': deepcopy(self.view),
            'counts': counts,
            'items': items,
            'hardware': [
                {
                    'category': item.category,
                    'qty': item.qty,
                    'part_number': item.part_number,
                    'description': item.description,
                    'page': item.page,
                    'cabinets': item.cabinets,
                    'original': item.original,
                }
                for item in report.hardware
            ],
            'hardware_lines': hardware_lines,
            'hardware_draft': deepcopy(self.hardware_draft),
            'export_blocked': export_blocked,
            'order_filename': self.order_filename,
            'quick_types': QUICK_TYPES,
            'type_choices': TYPE_CHOICES,
            'box_types': BOX_TYPES,
            'special_categories': list(SPECIAL_CATEGORIES),
            'tables': tables,
        }


def empty_snapshot():
    return {
        'app_name': 'Mozaik to Decorative Defrustrator',
        'app_version': '1.21',
        'has_report': False,
        'job': 'Open a Mozaik report to begin',
        'source': '',
        'dirty': False,
        'can_undo': False,
        'can_redo': False,
        'undo_label': '',
        'redo_label': '',
        'errors': [],
        'notes': [],
        'checks': [],
        'hardware_errors': [],
        'hardware_pages': [],
        'groups': [],
        'view': {'group': '', 'tab': 'doors', 'selection': {'doors': [], 'boxes': []}},
        'counts': {'doors': 0, 'fronts': 0, 'boxes': 0, 'trays': 0, 'short_fronts': 0},
        'items': [],
        'hardware': [],
        'hardware_lines': [],
        'hardware_draft': None,
        'export_blocked': True,
        'order_filename': None,
        'quick_types': QUICK_TYPES,
        'type_choices': TYPE_CHOICES,
        'box_types': BOX_TYPES,
        'special_categories': list(SPECIAL_CATEGORIES),
        'tables': {},
    }


workspace = Workspace()

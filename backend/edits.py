"""Report mutations shared by the web API and domain tests."""
from __future__ import annotations

from copy import copy, deepcopy

from bore_math import BOTTOM, STANDARD, from_top, signed_inches
from bore_split import BoreDecision, confirm_custom_bores
from converter import (BORE_FIELDS, BOX_TYPES, DOOR_TYPES, LOCATIONS, canonical_type,
                       dimension, fractional)
from customizations import changed_fields, field_values


def change_item_type(history, index, label):
    item = history.report.items[index]
    if item.deleted:
        return False
    updated = copy(item)
    updated.type = canonical_type(label)
    if item.kind == 'boxes':
        if updated.type not in BOX_TYPES:
            return False
        updated.scoop = 'A' if updated.type == 'Tray' else ''
    else:
        updated.location = (item.location if item.location in LOCATIONS else 'L') if updated.has_hinge_boring else ''
        updated.french_lite = item.french_lite if updated.type == 'French Lite' else ''
        if updated.type != item.type:
            updated.bore_overrides = {}
    updated.values()
    return history.apply({index: updated}, 'change row type')


def delete_items(history, indices):
    batch = [index for index in sorted(set(indices))
             if 0 <= index < len(history.report.items) and not history.report.items[index].deleted]
    if not batch:
        return 0
    updates = {index: deepcopy(history.report.items[index]) for index in batch}
    for item in updates.values():
        item.deleted = True
    history.apply(updates, f'delete {len(batch)} row(s)')
    return len(batch)


def _parse_quantity(text):
    qty = str(text).strip()
    if not qty.isdigit() or int(qty) <= 0:
        raise ValueError('Quantity must be a positive whole number.')
    return int(qty)


def _optional_measure(text):
    value = str(text).strip() if text is not None else ''
    return dimension(value) if value else None


def build_updated_item(item, fields, *, included=None, center_reference=BOTTOM, manual_positions=None,
                       edge_offsets=None):
    """Build an edited Item from editor field strings. Center input uses center_reference."""
    updated = copy(item)
    updated.qty = _parse_quantity(fields.get('Quantity', item.qty))
    updated.width = dimension(str(fields.get('Width', fractional(item.width))))
    updated.height = dimension(str(fields.get('Height', fractional(item.height))))
    updated.included = item.included if included is None else bool(included)
    manual = set(manual_positions or ())
    if item.kind == 'doors':
        if edge_offsets:
            for edge, raw in edge_offsets.items():
                text = str(raw).strip()
                if text:
                    computed = STANDARD + signed_inches(text)
                    if computed <= 0 or computed >= updated.height:
                        raise ValueError(f'{edge.title()} bore must be inside the door.')
                    result = _optional_measure(fields.get(BORE_FIELDS[edge], ''))
                    if result is not None and result >= updated.height:
                        raise ValueError(f'{edge.title()} bore must be inside the door.')
        updated.type = canonical_type(fields.get('Type', item.type))
        if updated.type not in DOOR_TYPES:
            raise ValueError('Choose a supported door or drawer-front type.')
        updated.location = fields.get('Location', item.location) if updated.has_hinge_boring else ''
        if updated.has_hinge_boring and updated.location not in LOCATIONS:
            raise ValueError('Choose L, R, or Susan for the hinge location.')
        updated.french_lite = str(fields.get('French Lite', '')).strip() if updated.type == 'French Lite' else ''
        overrides = {}
        for key in manual:
            if key not in BORE_FIELDS:
                raise ValueError('Unknown bore position.')
            raw = fields.get(BORE_FIELDS[key], '')
            if key == 'center':
                text = str(raw).strip()
                overrides[key] = from_top(updated.height, dimension(text) if text else None, center_reference)
            else:
                overrides[key] = _optional_measure(raw)
        updated.bore_overrides = overrides
    else:
        updated.depth = dimension(str(fields.get('Depth', fractional(item.depth))))
        updated.type = fields.get('Type', item.type)
        if updated.type not in BOX_TYPES:
            raise ValueError('Choose Drawer Box or Tray.')
        updated.scoop = fields.get('Scoop', item.scoop)
    updated.values()
    return updated


def apply_row_edit(history, index, fields, *, included=None, center_reference=BOTTOM,
                   manual_positions=None, edge_offsets=None, decision=None):
    item = history.report.items[index]
    if item.deleted:
        raise ValueError('This row has been deleted.')
    updated = build_updated_item(
        item, fields, included=included, center_reference=center_reference,
        manual_positions=manual_positions, edge_offsets=edge_offsets,
    )
    if isinstance(decision, dict):
        decision = BoreDecision(**{key: decision.get(key) for key in ('duplicate', 'side', 'left_count')})
    replacements = confirm_custom_bores(item, updated, decision)
    history.replace_row(index, replacements, 'split doors for custom bores' if len(replacements) > 1 else 'edit row')
    return replacements


def item_counts(items, group=None, visible_only=True):
    counts = {'doors': 0, 'fronts': 0, 'boxes': 0, 'trays': 0, 'short_fronts': 0}
    for item in items:
        if visible_only and (item.deleted or (group and item.group != group)):
            continue
        if not item.included:
            continue
        if item.kind == 'doors' and item.is_front:
            counts['fronts'] += item.qty
            if item.export_kind == 'short_fronts':
                counts['short_fronts'] += item.qty
        elif item.kind == 'doors':
            counts['doors'] += item.qty
        elif item.type == 'Tray':
            counts['trays'] += item.qty
        else:
            counts['boxes'] += item.qty
    return counts


def serialize_item(item, original=None, index=0):
    values = None
    supplier = None
    issue = None
    try:
        values = item.values()
        supplier = item.supplier_values()
    except ValueError as exc:
        issue = str(exc)
        saved = item.french_lite
        item.french_lite = 'Configuration required'
        try:
            values = item.values()
            supplier = item.supplier_values()
        finally:
            item.french_lite = saved
    changed = sorted(changed_fields(item, original)) if original is not None else []
    baseline = None
    if original is not None:
        baseline = {}
        for key, value in field_values(original, defaults=True).items():
            if hasattr(value, 'numerator'):
                baseline[key] = None if value is None else fractional(value)
            else:
                baseline[key] = value
    return {
        'index': index,
        'kind': item.kind,
        'qty': item.qty,
        'width': fractional(item.width),
        'height': fractional(item.height),
        'depth': None if item.depth is None else fractional(item.depth),
        'type': item.type,
        'type_label': 'Glass Front Door' if item.type == 'Glass' else item.type,
        'location': item.location,
        'bore_location': item.bore_location,
        'scoop': item.scoop,
        'french_lite': item.french_lite,
        'page': item.page,
        'group': item.group,
        'part': item.part,
        'cabinets': item.cabinets,
        'original': item.original,
        'included': item.included,
        'deleted': item.deleted,
        'values': values,
        'supplier_values': supplier,
        'export_kind': item.export_kind,
        'has_hinge_boring': item.has_hinge_boring,
        'is_front': item.is_front,
        'bore_overrides': {key: None if value is None else fractional(value) for key, value in item.bore_overrides.items()},
        'bore_positions': item.bore_positions(),
        'changed_fields': changed,
        'customized': bool(changed),
        'issue': issue,
        'baseline': baseline,
    }


def default_editor_fields(item, center_reference=BOTTOM):
    fields = {
        'Quantity': str(item.qty),
        'Width': fractional(item.width),
        'Height': fractional(item.height),
    }
    if item.kind == 'doors':
        top, center, bottom = item.bore_positions()
        if center:
            stored = dimension(center)
            displayed = item.height - stored if center_reference == BOTTOM else stored
            center = fractional(displayed)
        fields.update({
            'Type': 'Glass Front Door' if item.type == 'Glass' else item.type,
            'Location': item.bore_location,
            'French Lite': item.french_lite,
            'Top Bore Position': top,
            'Center Bore Position': center,
            'Bottom Bore Position': bottom,
        })
    else:
        fields.update({
            'Depth': fractional(item.depth),
            'Type': item.type,
            'Scoop': item.scoop,
        })
    return fields

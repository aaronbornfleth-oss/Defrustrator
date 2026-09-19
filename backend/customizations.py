"""Compare current values with the imported row, independently of saving."""
from converter import BORE_FIELDS


def field_values(item, defaults=False):
    values = {'Quantity': item.qty, 'Width': item.width, 'Height': item.height,
              'Type': item.type, 'Included': item.included, 'Deleted': item.deleted}
    if item.kind == 'boxes':
        values.update(Depth=item.depth, Scoop=item.scoop)
    else:
        positions = item.default_bore_positions()
        if not defaults:
            positions.update(item.bore_overrides)
        values.update(Location=item.bore_location, **{'French Lite': item.french_lite})
        values.update({BORE_FIELDS[key]: value for key, value in positions.items()})
    return values


def changed_fields(item, original):
    current, baseline = field_values(item), field_values(original, defaults=True)
    return {key for key in current if current[key] != baseline[key]}


def row_tags(item, original, index):
    tags = ['custom'] if changed_fields(item, original) else ['odd'] if index % 2 else []
    if not item.included:
        tags.append('excluded')
    return tuple(tags)

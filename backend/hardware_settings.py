"""Remember optional hardware parts on this computer, never job quantities."""
import json
import os
import tempfile
from pathlib import Path

from hardware import SPECIAL_CATEGORIES, OrderLine


def settings_path():
    override = os.environ.get('DEFRUSTRATOR_HARDWARE_PARTS')
    if override:
        return Path(override)
    local = os.environ.get('LOCALAPPDATA')
    if local:
        return Path(local) / 'Mozaik Converter' / 'hardware-parts.json'
    xdg = os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))
    return Path(xdg) / 'mozaik-converter' / 'hardware-parts.json'


def checked_parts(parts):
    if not isinstance(parts, dict):
        raise ValueError('Saved hardware parts must contain a list for each hinge type.')
    result = {}
    for category in SPECIAL_CATEGORIES:
        entries = parts.get(category, [])
        if not isinstance(entries, list):
            raise ValueError(f'{category}: saved parts are unreadable.')
        result[category] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('part_number'), str):
                raise ValueError(f'{category}: a saved part number is unreadable.')
            line = OrderLine(category, entry['part_number'].strip(), category, 1, entry.get('unit', 'each'))
            line.validate()
            # Deliberately omit quantities and all PDF/job information.
            result[category].append({'part_number': line.part_number, 'unit': line.unit})
    return result


def load_parts(path=None):
    path = Path(path) if path is not None else settings_path()
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {category: [] for category in SPECIAL_CATEGORIES}
    if not isinstance(saved, dict) or saved.get('version') != 1:
        raise ValueError('Saved hardware parts have an unsupported format.')
    return checked_parts(saved.get('parts'))


def save_parts(parts, path=None):
    path = Path(path) if path is not None else settings_path()
    text = json.dumps({'version': 1, 'parts': checked_parts(parts)}, indent=2) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='hardware-parts-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

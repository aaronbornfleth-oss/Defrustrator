"""FastAPI service for Mozaik to Decorative Defrustrator. Does not send email or place orders."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import branding as brand
from bore_math import BOTTOM, STANDARD, TOP, center_preview, display_from_top, edge_equation
from bore_math import from_top, move_center, offset_from_position, position_from_offset, signed_inches
from bore_split import PendingBoreDecision
from clipboard import clipboard_for_kind
from converter import EXPORT_KINDS, EXPORT_SUFFIXES, dimension, fractional, safe_name
from edits import default_editor_fields
from hardware_email import default_draft, generate_email
from order_files import EXTENSION
from session import MAX_PDF_BYTES, workspace

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT.parent / 'frontend' / 'dist'
SAMPLES = ROOT.parent / 'samples'


class EditPayload(BaseModel):
    fields: dict[str, str] = Field(default_factory=dict)
    included: bool | None = None
    center_reference: str = BOTTOM
    manual_positions: list[str] = Field(default_factory=list)
    edge_offsets: dict[str, str] | None = None
    decision: dict | None = None


class TypePayload(BaseModel):
    label: str


class DeletePayload(BaseModel):
    indices: list[int]


class ViewPayload(BaseModel):
    group: str | None = None
    tab: str | None = None
    selection: dict | None = None


class ClipboardPayload(BaseModel):
    kind: str
    selected: list[int] | None = None


class HardwareDraftPayload(BaseModel):
    parts: dict[str, str] = Field(default_factory=dict)
    quantities: dict[str, str] = Field(default_factory=dict)
    special: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    email: str = ''
    generated_body: str = ''
    preview: bool = False


class CenterPayload(BaseModel):
    height: str
    position: str = ''
    reference: str = BOTTOM
    amount: str = '1/2'
    direction: str | None = None
    door_type: str = 'Door'


class OffsetPayload(BaseModel):
    edge: str
    height: str
    offset: str = ''
    position: str = ''
    source: str = 'offset'


app = FastAPI(title=brand.APP_NAME, version=brand.APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


def snapshot_response():
    return workspace.snapshot()


def fail(exc: Exception, status=400):
    raise HTTPException(status_code=status, detail=str(exc)) from exc


@app.get('/api/health')
def health():
    return {'ok': True, 'app': brand.APP_NAME, 'version': brand.APP_VERSION}


@app.get('/api/session')
def get_session():
    with workspace.lock:
        return snapshot_response()


@app.post('/api/session/clear')
def clear_session():
    with workspace.lock:
        workspace.clear()
        return snapshot_response()


@app.post('/api/session/view')
def set_view(payload: ViewPayload):
    with workspace.lock:
        workspace.set_view(group=payload.group, tab=payload.tab, selection=payload.selection)
        return snapshot_response()


@app.post('/api/import/pdf')
async def import_pdf(file: UploadFile = File(...)):
    name = file.filename or 'report.pdf'
    if not name.lower().endswith('.pdf'):
        fail(ValueError('Choose a Mozaik PDF report.'))
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        fail(ValueError('This PDF is too large to import.'))
    if not data:
        fail(ValueError('The uploaded PDF is empty.'))
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        with workspace.lock:
            workspace.load_pdf(path, original_name=name)
            return snapshot_response()
    except Exception as exc:
        fail(exc)
    finally:
        Path(path).unlink(missing_ok=True)


@app.post('/api/import/order')
async def import_order(file: UploadFile = File(...)):
    name = file.filename or f'order{EXTENSION}'
    data = await file.read()
    try:
        with workspace.lock:
            workspace.load_order_bytes(data, name)
            return snapshot_response()
    except ValueError as exc:
        fail(exc)
    except Exception as exc:
        fail(ValueError('The order file is damaged or has an invalid format.'))


@app.post('/api/demo/spigener')
def load_demo():
    path = SAMPLES / 'Spigener-report-2026-09-15-1000.pdf'
    if not path.exists():
        fail(ValueError('The frozen Spigener sample PDF is not in samples/.'))
    with workspace.lock:
        workspace.load_pdf(path, original_name=path.name)
        return snapshot_response()


@app.post('/api/items/type')
def change_type(payload: TypePayload, index: int):
    try:
        with workspace.lock:
            workspace.apply_type(index, payload.label)
            return snapshot_response()
    except ValueError as exc:
        fail(exc)


@app.post('/api/items/delete')
def delete_rows(payload: DeletePayload):
    try:
        with workspace.lock:
            workspace.apply_delete(payload.indices)
            return snapshot_response()
    except ValueError as exc:
        fail(exc)


@app.post('/api/items/{index}/edit')
def edit_row(index: int, payload: EditPayload):
    try:
        with workspace.lock:
            workspace.apply_edit(index, payload.model_dump())
            return snapshot_response()
    except PendingBoreDecision as pending:
        return JSONResponse(status_code=409, content=pending.payload())
    except ValueError as exc:
        fail(exc)


@app.get('/api/items/{index}/editor')
def editor_state(index: int, reference: str = BOTTOM):
    with workspace.lock:
        report, history = workspace.require_report()
        if index < 0 or index >= len(report.items):
            fail(ValueError('That row is not in the current order.'))
        item = report.items[index]
        original = history.original_items()[index]
        return {
            'fields': default_editor_fields(item, reference),
            'included': item.included,
            'center_reference': reference,
            'manual_positions': list(item.bore_overrides),
            'original': {key: (fractional(value) if hasattr(value, 'numerator') else value)
                         for key, value in field_values_safe(original).items()},
            'item': workspace.snapshot()['items'][index],
        }


def field_values_safe(item):
    from customizations import field_values
    values = field_values(item, defaults=True)
    encoded = {}
    for key, value in values.items():
        if hasattr(value, 'numerator'):
            encoded[key] = fractional(value)
        else:
            encoded[key] = value
    return encoded


@app.post('/api/undo')
def undo():
    with workspace.lock:
        workspace.undo()
        return snapshot_response()


@app.post('/api/redo')
def redo():
    with workspace.lock:
        workspace.redo()
        return snapshot_response()


@app.post('/api/export/clipboard')
def export_clipboard(payload: ClipboardPayload):
    try:
        with workspace.lock:
            report, _ = workspace.require_report()
            group = workspace.view.get('group') or None
            text = clipboard_for_kind(report, payload.kind, group, payload.selected)
            return {'text': text, 'kind': payload.kind}
    except ValueError as exc:
        fail(exc)


@app.get('/api/export/csv/{kind}')
def export_csv(kind: str):
    if kind not in EXPORT_KINDS:
        fail(ValueError('Unknown export group.'))
    try:
        with workspace.lock:
            report, _ = workspace.require_report()
            group = workspace.view.get('group') or None
            from converter import export_tables, delimited_text
            tables = export_tables(report, group)
            if kind not in tables:
                fail(ValueError('There are no included rows in that Decorative copy group.'))
            headers, rows = tables[kind]
            text = delimited_text(headers, rows)
            stem = safe_name(report.job + (f' - {group}' if group else ''))
            filename = f'{stem} - {EXPORT_SUFFIXES[kind]}.csv'
            return Response(
                content=text.encode('utf-8'),
                media_type='text/csv; charset=utf-8',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'},
            )
    except ValueError as exc:
        fail(exc)


@app.get('/api/export/order')
def export_order():
    try:
        with workspace.lock:
            name, data = workspace.encode_order()
            return Response(
                content=data,
                media_type='application/json; charset=utf-8',
                headers={'Content-Disposition': f'attachment; filename="{name}"'},
            )
    except ValueError as exc:
        fail(exc)


@app.get('/api/hardware')
def hardware_state():
    with workspace.lock:
        report, _ = workspace.require_report()
        draft, notice = default_draft(report, existing=workspace.hardware_draft)
        return {
            'draft': draft,
            'notice': notice,
            'lines': workspace.snapshot()['hardware_lines'],
            'errors': list(report.hardware_errors),
            'job': report.job,
        }


@app.post('/api/hardware/draft')
def save_hardware_draft(payload: HardwareDraftPayload):
    with workspace.lock:
        workspace.set_hardware_draft(payload.model_dump())
        return snapshot_response()


@app.post('/api/hardware/generate')
def generate_hardware(payload: HardwareDraftPayload):
    try:
        with workspace.lock:
            report, _ = workspace.require_report()
            body, notice = generate_email(report, payload.model_dump())
            draft = payload.model_dump()
            draft['email'] = body
            draft['generated_body'] = body
            draft['preview'] = True
            workspace.set_hardware_draft(draft)
            return {'body': body, 'notice': notice, 'draft': draft, 'session': snapshot_response()}
    except ValueError as exc:
        fail(exc)


@app.post('/api/helpers/center')
def helper_center(payload: CenterPayload):
    try:
        height = dimension(payload.height)
        text = payload.position.strip()
        position = dimension(text) if text else None
        top = from_top(height, position, payload.reference)
        if payload.direction:
            amount = dimension(payload.amount)
            top = move_center(height, top, amount, payload.direction)
        enabled = 'Drawer Front' not in payload.door_type and payload.door_type != 'Applied Door' and height > 36
        preview = center_preview(height, top, enabled)
        displayed = display_from_top(height, top, payload.reference)
        return {
            'top': None if top is None else fractional(top),
            'displayed': '' if displayed is None else fractional(displayed),
            'preview': preview,
            'reference': payload.reference,
        }
    except ValueError as exc:
        fail(exc)


@app.post('/api/helpers/edge')
def helper_edge(payload: OffsetPayload):
    try:
        height = dimension(payload.height)
        if payload.source == 'offset':
            position = position_from_offset(payload.offset)
        else:
            position = dimension(payload.position) if payload.position.strip() else None
            if payload.offset.strip():
                signed_inches(payload.offset)
        if position is not None and (position <= 0 or position >= height):
            raise ValueError(f'{payload.edge.title()} bore must be inside the door.')
        offset = offset_from_position(position)
        return {
            'position': '' if position is None else fractional(position),
            'offset': '' if offset is None else fractional(offset),
            'equation': edge_equation(payload.edge, position),
            'standard': fractional(STANDARD),
        }
    except ValueError as exc:
        fail(exc)


@app.get('/api/branding')
def branding():
    return {
        'name': brand.APP_NAME,
        'version': brand.APP_VERSION,
        'colors': {
            'primary': brand.PRIMARY,
            'teal': brand.TEAL,
            'blue': brand.BLUE,
            'sage': brand.SAGE,
            'background': brand.BACKGROUND,
            'surface': brand.SURFACE,
            'text': brand.TEXT,
            'muted': brand.MUTED,
            'border': brand.BORDER,
            'paleGreen': brand.PALE_GREEN,
            'paleBlue': brand.PALE_BLUE,
            'custom': brand.CUSTOM,
            'selected': brand.SELECTED,
            'stripe': brand.STRIPE,
            'disabled': brand.DISABLED,
            'error': brand.ERROR,
        },
        'references': {
            'BOTTOM': BOTTOM,
            'TOP': TOP,
        },
    }


if FRONTEND_DIST.exists():
    app.mount('/', StaticFiles(directory=FRONTEND_DIST, html=True), name='ui')
else:
    @app.get('/')
    def root():
        return {
            'app': brand.APP_NAME,
            'version': brand.APP_VERSION,
            'ui': 'Frontend is not built yet. Run npm run build in frontend/, or use the Vite dev server.',
            'health': '/api/health',
        }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), reload=True)

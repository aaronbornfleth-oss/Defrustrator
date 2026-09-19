# Mozaik to Decorative Defrustrator

Web port of the Windows **v1.21** staff tool for Left Coast Cabinets. It converts Mozaik PDF size/hardware reports into Decorative Specialties paste tables, review/edit UI, hardware **email drafts**, and `.mddorder` save/load.

Spell **Defrustrator** exactly. This app does **not** send email, place Decorative orders, or publish a Shopify storefront page.

## What is included

- FastAPI backend that reuses the v1.21 domain core: `converter.py`, `hardware.py`, `order_files.py`, Fraction math, grouping, clipboard TSV, custom bores, undo/redo history.
- React + TypeScript UI for browser review, bore editors, Copy for Decorative, hardware draft, and file download.
- Branding colors from the Windows app and logos from `source/assets` (wordmark, heron favicon, Left Coast Cabinets footer mark).
- Frozen Spigener PDF and `.mddorder` fixtures under `samples/`.
- Domain and API tests, including frozen-fixture expectations when the sample PDF is present.

## Requirements

- Python 3.12+
- Node.js 20+ (for the UI)
- A text-based Mozaik Door Sizes / Dwr Box/Tray Sizes PDF (scanned pages are not supported)

## Run locally (two processes)

```bash
# API — from the repo root
cd backend
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# UI — second terminal
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 (Vite proxies `/api` to port 8000).

## Run locally (single process, production-style)

```bash
cd frontend && npm install && npm run build
cd ../backend
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000. FastAPI serves the built UI and the API.

## Docker

```bash
docker compose up --build
```

Then open http://127.0.0.1:8000.

## Tests

```bash
cd backend
python3 -m pip install -r requirements.txt
export MOZAIK_SAMPLE_PDF="$(pwd)/../samples/Spigener-report-2026-09-15-1000.pdf"
python3 -m unittest discover -p 'test_*.py'
```

The suite covers fractions, grouping, clipboard TSV (headers, no trailing blank row, `Bore` vs CSV `Bore `), hardware SKUs, bore math/splits, `.mddorder` schema, and the frozen Spigener PDF when that file is present.

Expected frozen fixture (SHA-256 `BC5E5A6E0CE5D750F9A0A99CB02EF5798E7E96A02A30122A60F30729C9EAE413`):

- 7 pages; 45 size rows
- 31 doors + 20 fronts; 19 boxes + 6 trays
- 56 hinges/clips; 30 spacers
- Glide sets: 3×563.3050B, 9×563.4570B, 13×563.5330B

## Workflow

1. Open PDF (or **Load sample PDF**) or Open order (`.mddorder`).
2. Review **Doors & drawer fronts** and **Drawer boxes & trays**. Edit types, sizes, and bores. Fronts under 7 inches are a separate Decorative group; exactly 7" stays with standard fronts.
3. **Copy for Decorative** — three tabs. Copy always includes headers, uses tab + CRLF, and does **not** add a blank last row. CSV download keeps the workbook’s `Bore ` trailing space; clipboard uses `Bore`.
4. **Hardware email** — review standard hinges `71B3590`, clips `174H7100I` (capital I), glide sets, spacers `T593570`, optional extras. Create and copy a draft. Nothing is sent.
5. **Save order** downloads a UTF-8 `.mddorder` (format `mozaik-decorative-order`, version 1, app_version `1.21`). Reopen it without the original PDF.

Undo/Redo: Ctrl+Z / Ctrl+Y (or Ctrl+Shift+Z). Delete removes selected table rows; in a text field it still edits text.

## Branding

| Token | Hex |
|---|---|
| Primary | `#2a664c` |
| Teal | `#2f7867` |
| Sea | `#88b6c5` |
| Sage | `#bcd8a8` |
| Background | `#f1f6f2` |
| Text | `#193c2e` |
| Custom highlight | `#e6f2fb` |
| Selected | `#cfe4eb` |
| Error | `#9b341f` |

Logos used: `frontend/public/defrustrator-wordmark-byline.png` (header), `heron.png` / `heron.ico` (favicon), `lcc-logo.png` (Powered by footer). The same files live in `backend/assets/`.

## Shopify / hosting (not done in this repo)

This is a staff tool first. A later Shopify page can iframe the hosted UI, for example `/pages/defrustrator` with `?embed=1`, **without** adding a public nav menu until you ask for that. Still needed before any storefront publish:

- Staff-only vs customer-facing access
- Hosting URL, HTTPS, and iframe/clipboard permissions
- Whether orders stay as downloaded `.mddorder` files or move to cloud history
- Theme width and “open full screen” fallback

Do not treat conversion drafts as Shopify commerce orders or Decorative submissions.

## Desktop source

The Windows v1.21 Tk app is not required to run the web port. Domain modules were copied from that release; Tk dialogs were replaced by the browser UI and FastAPI session. Optional remembered hardware parts are stored under `$XDG_DATA_HOME/mozaik-converter/hardware-parts.json` (or `%LOCALAPPDATA%\Mozaik Converter\hardware-parts.json` on Windows). Quantities are never stored in that file.

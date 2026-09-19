import { useState } from 'react'
import { clipboardText, copyText, downloadCsv } from './api'
import type { ExportKind, ItemRow, Session } from './types'

const KINDS: ExportKind[] = ['doors', 'short_fronts', 'boxes']

type Props = {
  session: Session
  items: ItemRow[]
  onClose: () => void
  onEdit: (index: number) => void
  onDelete: (indices: number[]) => void
  onType: (index: number, label: string) => void
  onSaveOrder: () => void
}

export default function CopyDialog({ session, items, onClose, onEdit, onDelete, onType, onSaveOrder }: Props) {
  const available = KINDS.filter((kind) => session.tables[kind]?.rows.length)
  const [kind, setKind] = useState<ExportKind>(available[0] || 'doors')
  const [selected, setSelected] = useState<number[]>([])
  const [status, setStatus] = useState('')
  const [fallback, setFallback] = useState('')
  const table = session.tables[kind]

  async function copy(selectedOnly: boolean) {
    if (!table) return
    try {
      const text = await clipboardText(kind, selectedOnly ? selected : undefined)
      const ok = await copyText(text)
      setFallback(text)
      setStatus(ok
        ? `Copied column headings and ${selectedOnly ? selected.length : table.rows.length} data rows. Paste into Decorative’s ${kind === 'boxes' ? 'drawer-box' : 'door / drawer-front'} input.${kind === 'short_fronts' ? ' Configure the narrower rails for this group.' : ''}`
        : 'Clipboard is blocked. The table is selected below — press Ctrl+C to copy it.')
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : 'Copy failed.')
    }
  }

  if (!table) {
    return (
      <div className="overlay">
        <div className="modal">
          <h2>Copy for Decorative Specialties</h2>
          <p>There are no included rows to copy.</p>
          <div className="actions"><button className="btn" onClick={onClose}>Close</button></div>
        </div>
      </div>
    )
  }

  return (
    <div className="overlay" role="dialog" aria-labelledby="copy-title">
      <div className="modal">
        <h2 id="copy-title">Copy for Decorative Specialties</h2>
        <p className="sub">Choose a table, copy the rows, and paste into Decorative’s matching Excel-data box. {session.job} · Section: {session.view.group || 'All sections'}</p>
        <div className="toolbar" style={{ padding: 0 }}>
          <button className="btn" onClick={onSaveOrder}>Save order</button>
          <button className="btn" disabled={selected.length !== 1} onClick={() => onEdit(table.source_indices[selected[0]])}>Edit selected row</button>
          <select disabled={selected.length !== 1} onChange={(event) => { if (event.target.value) onType(table.source_indices[selected[0]], event.target.value); event.target.selectedIndex = 0 }}>
            <option value="">Change type</option>
            {(kind === 'boxes' ? session.box_types : session.quick_types).map((label) => <option key={label}>{label}</option>)}
          </select>
          <button className="btn" disabled={!selected.length} onClick={() => onDelete(selected.map((row) => table.source_indices[row]))}>
            {selected.length > 1 ? 'Delete rows' : 'Delete row'}
          </button>
        </div>
        <div className="tab-bar" style={{ marginTop: 12 }}>
          {KINDS.map((key) => {
            const batch = session.tables[key]
            return (
              <button key={key} className={`btn-tab${kind === key ? ' active' : ''}`} disabled={!batch?.rows.length}
                onClick={() => { setKind(key); setSelected([]); setStatus(''); setFallback('') }}>
                {batch?.label || key} ({batch?.item_total || 0} items)
              </button>
            )
          })}
        </div>
        <p className="sub">{table.note}</p>
        <div className="table-wrap" style={{ maxHeight: 360 }}>
          <table>
            <thead>
              <tr>
                <th>#</th>
                {table.headers.map((header, index) => (
                  <th key={header}>{String.fromCharCode(65 + index)} · {header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, index) => {
                const source = items[table.source_indices[index]]
                return (
                  <tr key={index}
                    className={`${source?.customized ? 'custom' : index % 2 ? 'stripe' : ''} ${selected.includes(index) ? 'selected' : ''}`}
                    onClick={(event) => {
                      if (event.shiftKey && selected.length) {
                        const start = Math.min(selected[0], index)
                        const end = Math.max(selected[0], index)
                        setSelected(Array.from({ length: end - start + 1 }, (_, offset) => start + offset))
                      } else if (event.metaKey || event.ctrlKey) {
                        setSelected((current) => current.includes(index) ? current.filter((value) => value !== index) : [...current, index])
                      } else {
                        setSelected([index])
                      }
                    }}
                    onDoubleClick={() => onEdit(table.source_indices[index])}>
                    <td>{kind === 'boxes' ? `${index + 1} · ${source?.type || ''}` : index + 1}</td>
                    {(source?.values || row).map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="legend">
          {table.item_total} items · {table.rows.length} rows · {table.headers.length} columns · {selected.length} rows selected · Exact fractional inches
          {kind !== 'boxes' ? ' · Center bore measured from top (Decorative)' : ''}
        </p>
        <p className="sub">Column headings are always included. Light blue = customized. Copying does not mark the order saved.</p>
        {status && <p className="status">{status}</p>}
        {fallback && <textarea className="tsv-fallback" readOnly value={fallback} onFocus={(event) => event.currentTarget.select()} />}
        <div className="actions">
          <button className="btn" onClick={() => downloadCsv(kind).catch((exc) => setStatus(exc.message))}>Download CSV</button>
          <button className="btn" disabled={!selected.length} onClick={() => copy(true)}>Copy selected rows</button>
          <button className="btn btn-accent" onClick={() => copy(false)}>Copy all rows</button>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  changeType, clearSession, deleteRows, downloadOrder, editRow, getSession,
  importOrder, importPdf, loadDemo, redo, setView, undo,
} from './api'
import CopyDialog from './CopyDialog'
import HardwareDialog from './HardwareDialog'
import RowEditor from './RowEditor'
import type { BorePending, ItemRow, Kind, Session } from './types'

const emptyJob = 'Open a Mozaik report to begin'

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [status, setStatus] = useState('PDFs are processed by this app. Sizes stay exact fractional inches. Hardware email is a draft only.')
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Kind>('doors')
  const [group, setGroup] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const [editor, setEditor] = useState<ItemRow | null>(null)
  const [copyOpen, setCopyOpen] = useState(false)
  const [hardwareOpen, setHardwareOpen] = useState(false)
  const [checksOpen, setChecksOpen] = useState(false)
  const [confirm, setConfirm] = useState<{ message: string; proceed: () => void } | null>(null)
  const pdfInput = useRef<HTMLInputElement>(null)
  const orderInput = useRef<HTMLInputElement>(null)
  const embed = new URLSearchParams(window.location.search).get('embed') === '1'

  useEffect(() => {
    getSession().then(applySession).catch((exc) => setError(exc.message))
  }, [])

  useEffect(() => {
    document.body.classList.toggle('embed', embed)
  }, [embed])

  function applySession(next: Session) {
    setSession(next)
    setTab(next.view.tab || 'doors')
    setGroup(next.view.group || '')
    setError(next.errors.length ? `${next.errors.length} extraction issue(s). Export blocked. Open Rules & checks.` : '')
    if (next.has_report && !next.errors.length) {
      setStatus(`${next.items.filter((row) => !row.deleted).length} rows shown. PDF totals checked. Hardware pages: ${next.hardware_pages.join(', ') || 'none'}.${next.dirty ? ' Unsaved order changes.' : ''}`)
    }
  }

  const visible = useMemo(() => {
    if (!session) return []
    return session.items.filter((item) => !item.deleted && item.kind === tab && (!group || item.group === group))
  }, [session, tab, group])

  const selectedItem = visible.find((item) => selected.includes(item.index)) || null

  function guard(action: () => void) {
    if (session?.dirty) {
      setConfirm({
        message: 'This order has unsaved changes. Save the .mddorder file before continuing?',
        proceed: action,
      })
      return
    }
    action()
  }

  async function saveOrder() {
    try {
      await downloadOrder()
      applySession(await getSession())
      setStatus('Downloaded .mddorder. Copying or saving CSVs does not mark the editable order saved.')
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Save failed.')
    }
  }

  async function onPdf(file: File | undefined) {
    if (!file) return
    try {
      applySession(await importPdf(file))
      setSelected([])
      setStatus(`Imported ${file.name}. Review sizes, then copy for Decorative or save the order.`)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Import failed.')
    }
  }

  async function onOrder(file: File | undefined) {
    if (!file) return
    try {
      applySession(await importOrder(file))
      setSelected([])
      setStatus(`Opened ${file.name}. The original PDF is not required.`)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'The order file is damaged or has an invalid format.')
    }
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement
      const typing = target.matches('input, textarea, select')
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        if (session?.has_report) void saveOrder()
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'o' && !event.shiftKey) {
        event.preventDefault()
        pdfInput.current?.click()
      }
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'o') {
        event.preventDefault()
        orderInput.current?.click()
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && !event.shiftKey && !typing) {
        event.preventDefault()
        if (session?.can_undo) void undo().then(applySession)
      }
      if ((event.ctrlKey || event.metaKey) && (event.key.toLowerCase() === 'y' || (event.shiftKey && event.key.toLowerCase() === 'z')) && !typing) {
        event.preventDefault()
        if (session?.can_redo) void redo().then(applySession)
      }
      if ((event.key === 'Delete' || event.key === 'Del') && !typing && selected.length && !editor) {
        event.preventDefault()
        void deleteRows(selected).then(applySession)
        setSelected([])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [session, selected, editor])

  const counts = session?.counts
  const detail = selectedItem
    ? detailText(selectedItem)
    : 'Select a row to see its original PDF entry and calculated boring positions.\nGlass and lazy Susan doors require an explicit PDF label or a manual selection here.'

  return (
    <div className="app">
      <header className="brand-bar">
        <img className="wordmark" src="/defrustrator-wordmark-byline.png" alt="Mozaik to Decorative Defrustrator by Left Coast Cabinets" />
        <div className="version">v{session?.app_version || '1.21'} · staff tool · never sends email</div>
      </header>
      <div className="toolbar">
        <button className="btn btn-accent" onClick={() => guard(() => pdfInput.current?.click())}>Open PDF</button>
        <button className="btn" onClick={() => guard(() => orderInput.current?.click())}>Open order</button>
        <button className="btn" disabled={!session?.has_report} onClick={() => void saveOrder()}>Save order</button>
        <button className="btn" disabled={!session?.has_report || session.export_blocked} onClick={() => setCopyOpen(true)}>Copy for Decorative</button>
        <button className="btn" disabled={!session?.has_report} onClick={() => setHardwareOpen(true)}>Hardware email</button>
        <button className="btn" disabled={!session?.can_undo} onClick={() => undo().then(applySession)}>Undo{session?.undo_label ? ` · ${session.undo_label}` : ''}</button>
        <button className="btn" disabled={!session?.can_redo} onClick={() => redo().then(applySession)}>Redo</button>
        <button className="btn" disabled={!selectedItem} onClick={() => selectedItem && setEditor(selectedItem)}>Edit selected row</button>
        <select disabled={!selectedItem} value="" onChange={(event) => {
          if (selectedItem && event.target.value) changeType(selectedItem.index, event.target.value).then(applySession)
        }}>
          <option value="">Change type</option>
          {((tab === 'boxes' ? session?.box_types : session?.quick_types) ?? []).map((label) => <option key={label}>{label}</option>)}
        </select>
        <button className="btn" disabled={!selected.length} onClick={() => { deleteRows(selected).then(applySession); setSelected([]) }}>Delete row</button>
        <button className="btn" disabled={!session?.has_report} onClick={() => setChecksOpen(true)}>Rules & checks</button>
        <button className="btn" disabled={!session?.has_report} onClick={() => guard(() => { clearSession().then(applySession); setSelected([]); setStatus('Data cleared. Open a PDF to start a new conversion.') })}>Clear data</button>
        <button className="btn" onClick={() => guard(() => loadDemo().then(applySession).then(() => setStatus('Loaded the frozen Spigener sample. This is a fixture, not a live order.')))}>Load sample PDF</button>
        <input ref={pdfInput} type="file" accept=".pdf,application/pdf" hidden onChange={(event) => { void onPdf(event.target.files?.[0]); event.target.value = '' }} />
        <input ref={orderInput} type="file" accept=".mddorder,application/json" hidden onChange={(event) => { void onOrder(event.target.files?.[0]); event.target.value = '' }} />
      </div>
      <div className="job-line">
        {session?.job || emptyJob}
        {session?.order_filename ? ` · ${session.order_filename}` : ''}
        {session?.dirty ? ' · Unsaved changes' : session?.has_report ? ' · Saved / no unsaved edits' : ''}
        {group ? ` · Section: ${group}` : session?.has_report ? ' · All sections' : ''}
      </div>
      {session?.has_report && (
        <div className="toolbar" style={{ paddingTop: 0 }}>
          <label>Export section{' '}
            <select value={group} onChange={(event) => {
              const value = event.target.value
              setGroup(value)
              void setView({ group: value, tab })
            }}>
              <option value="">All sections</option>
              {session.groups.map((name) => <option key={name}>{name}</option>)}
            </select>
          </label>
        </div>
      )}
      <div className="stats">
        Doors {counts?.doors ?? '—'} &nbsp;&nbsp; Drawer fronts {counts?.fronts ?? '—'} &nbsp;&nbsp; Drawer boxes {counts?.boxes ?? '—'} &nbsp;&nbsp; Trays {counts?.trays ?? '—'}
      </div>
      <div className="scope">
        {session?.has_report
          ? `Copy for Decorative and CSV downloads use the included rows in the selected section.${counts?.short_fronts ? ` ${counts.short_fronts} drawer fronts under 7 inches will copy and save separately for narrower rails.` : ''}`
          : 'Choose a PDF, review its sizes, then copy for Decorative or save a .mddorder file. In Shopify, load this app with ?embed=1. This app does not place supplier orders.'}
      </div>
      <div className={`status${error ? ' error' : ''}`}>{error || status}</div>
      <main className="main">
        {!session?.has_report && (
          <div className="empty">
            <h2>Mozaik to Decorative Defrustrator</h2>
            <p>Open a text-based Mozaik Door Sizes / Dwr Box/Tray Sizes PDF, or resume a saved .mddorder. All fractions stay exact. Hardware email is generated as copyable draft text only.</p>
          </div>
        )}
        {session?.has_report && (
          <>
            <div className="tab-bar">
              <button className={`btn-tab${tab === 'doors' ? ' active' : ''}`} onClick={() => switchTab('doors')}>Doors & drawer fronts</button>
              <button className={`btn-tab${tab === 'boxes' ? ' active' : ''}`} onClick={() => switchTab('boxes')}>Drawer boxes & trays</button>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {tab === 'doors'
                      ? ['Inc', 'Page', 'Section', 'Type', 'Qty', 'Width', 'Height', 'French Lite', 'Bore', 'Location', 'Center Bore', 'Top', 'Center', 'Bottom', 'Cabinets'].map((label) => <th key={label}>{label}</th>)
                      : ['Inc', 'Page', 'Section', 'Type', 'Qty', 'Width', 'Height', 'Depth', 'Scoop', 'Cabinets'].map((label) => <th key={label}>{label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {visible.map((item, displayIndex) => (
                    <tr key={item.index}
                      className={`${item.customized ? 'custom' : displayIndex % 2 ? 'stripe' : ''} ${selected.includes(item.index) ? 'selected' : ''} ${item.included ? '' : 'excluded'}`}
                      onClick={(event) => {
                        if (event.shiftKey && selected.length) {
                          const indices = visible.map((row) => row.index)
                          const start = indices.indexOf(selected[0])
                          const end = indices.indexOf(item.index)
                          const [from, to] = start < end ? [start, end] : [end, start]
                          setSelected(indices.slice(from, to + 1))
                        } else {
                          setSelected([item.index])
                        }
                      }}
                      onDoubleClick={() => setEditor(item)}>
                      {tab === 'doors' ? (
                        <>
                          <td>{item.included ? 'Yes' : 'No'}</td>
                          <td>{item.page}</td>
                          <td>{item.group}</td>
                          {item.values.map((cell, index) => <td key={index}>{cell}</td>)}
                          <td>{item.cabinets}</td>
                        </>
                      ) : (
                        <>
                          <td>{item.included ? 'Yes' : 'No'}</td>
                          <td>{item.page}</td>
                          <td>{item.group}</td>
                          <td>{item.type}</td>
                          {item.values.map((cell, index) => <td key={index}>{cell}</td>)}
                          <td>{item.cabinets}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="detail">{detail}</div>
            <p className="legend"><span className="swatch" /> Light blue marks customized rows compared with the imported values or standard bore defaults. Selection uses a stronger blue. The Delete key removes a selected table row; in a text field it still edits text.</p>
          </>
        )}
      </main>
      <footer className="footer">
        <span>Powered by</span>
        <img src="/lcc-logo.png" alt="Left Coast Cabinets" />
        <span className="footer-shopify">Private staff tool. Do not add a public Shopify menu until hosting and access are decided. Embed with <code>?embed=1</code>.</span>
      </footer>
      {editor && session && (
        <RowEditor
          item={editor}
          typeChoices={session.type_choices}
          boxTypes={session.box_types}
          onClose={() => setEditor(null)}
          onApply={async (payload) => {
            const result = await editRow(editor.index, payload)
            if ('pending' in result) return result as BorePending
            applySession(result)
            setEditor(null)
            return null
          }}
        />
      )}
      {copyOpen && session && (
        <CopyDialog
          session={session}
          items={session.items}
          onClose={() => setCopyOpen(false)}
          onEdit={(index) => { setCopyOpen(false); setEditor(session.items[index]) }}
          onDelete={(indices) => { deleteRows(indices).then(applySession) }}
          onType={(index, label) => { changeType(index, label).then(applySession) }}
          onSaveOrder={() => void saveOrder()}
        />
      )}
      {hardwareOpen && session && (
        <HardwareDialog
          session={session}
          onClose={(next) => { if (next) applySession(next); setHardwareOpen(false) }}
          onSaveOrder={() => void saveOrder()}
        />
      )}
      {checksOpen && session && (
        <div className="overlay" role="dialog">
          <div className="modal">
            <h2>Conversion rules and PDF checks</h2>
            <pre className="help">{rulesText(session)}</pre>
            <div className="actions"><button className="btn" onClick={() => setChecksOpen(false)}>Close</button></div>
          </div>
        </div>
      )}
      {confirm && (
        <div className="overlay" role="dialog">
          <div className="modal narrow">
            <h2>Unsaved changes</h2>
            <p>{confirm.message}</p>
            <div className="actions">
              <button className="btn" onClick={() => setConfirm(null)}>Cancel</button>
              <button className="btn" onClick={() => { setConfirm(null); confirm.proceed() }}>Don’t save</button>
              <button className="btn btn-accent" onClick={async () => { await saveOrder(); setConfirm(null); confirm.proceed() }}>Save order</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )

  function switchTab(next: Kind) {
    setTab(next)
    setSelected([])
    if (group && session && !session.items.some((item) => item.kind === next && item.group === group)) {
      setGroup('')
      void setView({ group: '', tab: next })
    } else {
      void setView({ tab: next, group })
    }
  }
}

function detailText(item: ItemRow): string {
  let bore = item.kind === 'boxes'
    ? (item.scoop ? 'Scoop A.' : 'No scoop.')
    : item.type === 'Applied Door'
      ? 'Applied door: no hinge boring; exports as Door.'
      : item.is_front
        ? 'No hinge boring on drawer fronts.'
        : `Bore A, location ${item.location}; top 4, bottom 4; ${Number(item.height) > 36 || item.height.includes(' ') ? `center ${item.bore_positions[1] || 'default'}.` : 'no center bore (height is 36 inches or less).'}`
  if (item.export_kind === 'short_fronts') bore += ' Copy separately from Fronts under 7 inches; configure narrower rails in Decorative.'
  if (Object.keys(item.bore_overrides).length) {
    bore = 'Bore positions: ' + ['top', 'center', 'bottom'].map((key, index) => `${key} ${item.bore_positions[index] || 'blank'}`).join(', ') + '.'
  }
  if (item.bore_positions[1]) bore += ' Center position is from top (Decorative).'
  return `PDF page ${item.page} · ${item.group}\nOriginal: ${item.original}\n${bore}`
}

function rulesText(session: Session): string {
  let text = `YOUR CONVERSION RULES

• Save order keeps an editable .mddorder file. Open order resumes it without the source PDF.
• Copy for Decorative and CSV downloads create supplier data; they do not save the editable order.
• Drawer fronts default to 5-Piece Drawer Front with Bore None, Location none, and Center Bore no.
• Applied Door exports as Door with boring disabled. Glass Front Door stores and exports as Glass.
• Fronts under 7 inches are a separate copy tab. Exactly 7 inches stays with standard fronts.
• Center bore Yes only when height > 36. Stored/exported center is from the top (Decorative).
• Top/bottom final = 4 + signed Mozaik offset. Light blue marks customized rows and fields.
• Hardware email is a DRAFT. This app never sends email or places a Decorative order.
• Clip SKU ends with capital I: 174H7100I.

REPORT SUPPORT

Reads text-based Mozaik Door Sizes and Dwr Box/Tray Sizes cutlists. Scanned PDFs are not supported.

`
  if (session.checks.length) text += 'PDF TOTALS (BEFORE ROW EDITS)\n\n' + session.checks.join('\n')
  if (session.errors.length) text += '\n\nEXTRACTION ISSUES — EXPORT BLOCKED\n\n' + session.errors.join('\n\n')
  if (session.notes.length) text += '\n\nREVIEW\n\n' + session.notes.join('\n')
  if (session.hardware_errors.length) text += '\n\nHARDWARE ISSUES\n\n' + session.hardware_errors.join('\n')
  return text
}

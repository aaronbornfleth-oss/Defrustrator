import { useEffect, useMemo, useState } from 'react'
import { helperCenter, helperEdge } from './api'
import { CenterDiagram, EdgeGuide } from './BoreHelpers'
import type { BorePending, ItemRow } from './types'
import { BOTTOM, TOP } from './types'

const DOOR_FIELDS = ['Quantity', 'Width', 'Height', 'Type', 'Location', 'French Lite',
  'Top Bore Position', 'Center Bore Position', 'Bottom Bore Position'] as const
const BOX_FIELDS = ['Quantity', 'Width', 'Height', 'Depth', 'Type', 'Scoop'] as const

type Props = {
  item: ItemRow
  typeChoices: string[]
  boxTypes: string[]
  onClose: () => void
  onApply: (payload: {
    fields: Record<string, string>
    included: boolean
    center_reference: string
    manual_positions: string[]
    edge_offsets: Record<string, string>
    decision?: { duplicate?: boolean | null; side?: string | null; left_count?: number | null }
  }) => Promise<BorePending | null>
}

function initialFields(item: ItemRow): Record<string, string> {
  if (item.kind === 'boxes') {
    return {
      Quantity: String(item.qty),
      Width: item.width,
      Height: item.height,
      Depth: item.depth || '',
      Type: item.type,
      Scoop: item.scoop,
    }
  }
  const [top, centerTop, bottom] = item.bore_positions
  return {
    Quantity: String(item.qty),
    Width: item.width,
    Height: item.height,
    Type: item.type_label,
    Location: item.bore_location,
    'French Lite': item.french_lite,
    'Top Bore Position': top,
    'Center Bore Position': '',
    'Bottom Bore Position': bottom,
    _centerTop: centerTop,
  }
}

export default function RowEditor({ item, typeChoices, boxTypes, onClose, onApply }: Props) {
  const [fields, setFields] = useState<Record<string, string>>(() => initialFields(item))
  const [included, setIncluded] = useState(item.included)
  const [reference, setReference] = useState(BOTTOM)
  const [amount, setAmount] = useState('1/2')
  const [manual, setManual] = useState<Set<string>>(() => new Set(Object.keys(item.bore_overrides)))
  const [offsets, setOffsets] = useState({ top: '', bottom: '' })
  const [equations, setEquations] = useState({ top: 'Top: blank', bottom: 'Bottom: blank' })
  const [centerInfo, setCenterInfo] = useState<{ mozaik: string; export: string; offset: string; from_top?: string; from_bottom?: string } | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState<BorePending | null>(null)
  const [side, setSide] = useState(item.location === 'R' ? 'R' : 'L')
  const [leftCount, setLeftCount] = useState('')
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<Array<Record<string, string>>>([])
  const [draftRedo, setDraftRedo] = useState<Array<Record<string, string>>>([])

  useEffect(() => {
    const centerTop = item.bore_positions[1]
    if (!centerTop) return
    helperCenter({ height: item.height, position: centerTop, reference: TOP, door_type: item.type })
      .then((result) => {
        setFields((current) => ({ ...current, 'Center Bore Position': result.displayed }))
        setCenterInfo(result.preview)
      })
      .catch(() => undefined)
    helperEdge({ edge: 'top', height: item.height, position: item.bore_positions[0], source: 'position' })
      .then((result) => {
        setOffsets((current) => ({ ...current, top: result.offset }))
        setEquations((current) => ({ ...current, top: result.equation }))
      })
      .catch(() => undefined)
    helperEdge({ edge: 'bottom', height: item.height, position: item.bore_positions[2], source: 'position' })
      .then((result) => {
        setOffsets((current) => ({ ...current, bottom: result.offset }))
        setEquations((current) => ({ ...current, bottom: result.equation }))
      })
      .catch(() => undefined)
  }, [item])

  function pushDraft(next: Record<string, string>) {
    setDraft((stack) => [...stack, fields])
    setDraftRedo([])
    setFields(next)
  }

  function setField(name: string, value: string, mark?: string) {
    const next = { ...fields, [name]: value }
    if (mark) setManual((current) => new Set(current).add(mark))
    pushDraft(next)
    if (item.kind === 'doors' && (name === 'Type' || name === 'Height') && !mark) {
      // Type/height defaults are applied on the server when manual positions are empty.
    }
  }

  async function changeReference(next: string) {
    try {
      const converted = await helperCenter({
        height: fields.Height,
        position: fields['Center Bore Position'],
        reference,
        door_type: fields.Type,
      })
      const flipped = await helperCenter({
        height: fields.Height,
        position: converted.top || '',
        reference: TOP,
        door_type: fields.Type,
      })
      const displayed = next === BOTTOM ? flipped.preview.from_bottom || '' : flipped.preview.from_top || ''
      setReference(next)
      setFields((current) => ({ ...current, 'Center Bore Position': displayed }))
      setCenterInfo(flipped.preview)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Check the center bore before switching reference.')
    }
  }

  async function move(direction: 'up' | 'down') {
    try {
      const result = await helperCenter({
        height: fields.Height,
        position: fields['Center Bore Position'],
        reference,
        amount,
        direction,
        door_type: fields.Type,
      })
      setManual((current) => new Set(current).add('center'))
      pushDraft({ ...fields, 'Center Bore Position': result.displayed })
      setCenterInfo(result.preview)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Could not move the center bore.')
    }
  }

  async function changeOffset(edge: 'top' | 'bottom', value: string) {
    setOffsets((current) => ({ ...current, [edge]: value }))
    setManual((current) => new Set(current).add(edge))
    try {
      const result = await helperEdge({ edge, height: fields.Height, offset: value, source: 'offset' })
      const key = edge === 'top' ? 'Top Bore Position' : 'Bottom Bore Position'
      pushDraft({ ...fields, [key]: result.position })
      setEquations((current) => ({ ...current, [edge]: result.equation }))
      setError('')
    } catch (exc) {
      setEquations((current) => ({ ...current, [edge]: `${edge[0].toUpperCase()}${edge.slice(1)}: check offset / position` }))
      if (!value.trim()) {
        const key = edge === 'top' ? 'Top Bore Position' : 'Bottom Bore Position'
        pushDraft({ ...fields, [key]: '' })
      }
      if (value.trim()) setError(exc instanceof Error ? exc.message : 'Check offset')
    }
  }

  async function changePosition(edge: 'top' | 'bottom', value: string) {
    const key = edge === 'top' ? 'Top Bore Position' : 'Bottom Bore Position'
    setManual((current) => new Set(current).add(edge))
    pushDraft({ ...fields, [key]: value })
    try {
      const result = await helperEdge({ edge, height: fields.Height, position: value, source: 'position' })
      setOffsets((current) => ({ ...current, [edge]: result.offset }))
      setEquations((current) => ({ ...current, [edge]: result.equation }))
    } catch {
      setEquations((current) => ({ ...current, [edge]: `${edge}: check offset / position` }))
    }
  }

  function resetBores() {
    setManual(new Set())
    const height = fields.Height
    const hinged = !fields.Type.includes('Drawer Front') && fields.Type !== 'Applied Door'
    const next = {
      ...fields,
      'Top Bore Position': hinged ? '4' : '',
      'Bottom Bore Position': hinged ? '4' : '',
      'Center Bore Position': '',
    }
    pushDraft(next)
    setOffsets({ top: hinged ? '0' : '', bottom: hinged ? '0' : '' })
    helperCenter({ height, position: '', reference, door_type: fields.Type })
      .then((result) => setCenterInfo(result.preview))
      .catch(() => undefined)
  }

  function custom(name: string) {
    const baseline = item.baseline || {}
    const current = name === 'Type' ? (fields.Type === 'Glass Front Door' ? 'Glass' : fields.Type) : fields[name]
    const original = baseline[name]
    if (name === 'Quantity') return String(current) !== String(original)
    if (original == null && !String(current || '').trim()) return false
    return String(current ?? '') !== String(original ?? '')
  }

  const names = item.kind === 'doors' ? DOOR_FIELDS : BOX_FIELDS

  const diagramTop = useMemo(() => {
    if (!centerInfo?.from_top) return null
    return parseLoose(centerInfo.from_top)
  }, [centerInfo])
  const diagramBottom = useMemo(() => {
    if (!centerInfo?.from_bottom) return null
    return parseLoose(centerInfo.from_bottom)
  }, [centerInfo])

  async function apply(decision?: Props['onApply'] extends (p: infer P) => unknown ? P extends { decision?: infer D } ? D : never : never) {
    setBusy(true)
    setError('')
    try {
      const payload = {
        fields: Object.fromEntries(Object.entries(fields).filter(([key]) => !key.startsWith('_'))),
        included,
        center_reference: item.kind === 'doors' ? reference : BOTTOM,
        manual_positions: [...manual],
        edge_offsets: offsets,
        decision,
      }
      const result = await onApply(payload)
      if (result) {
        setPending(result)
        setLeftCount(String(result.suggested_left ?? Math.ceil(result.quantity / 2)))
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Check this row.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" role="dialog" aria-labelledby="editor-title">
      <div className="modal editor">
        <h2 id="editor-title">Edit row · PDF page {item.page}</h2>
        <p className="sub">{item.group} · Cabinets: {item.cabinets}</p>
        <div className="editor-layout">
          <div>
            <div className="form-grid">
              {names.map((name) => {
                if (item.kind === 'doors' && (name === 'Top Bore Position' || name === 'Bottom Bore Position')) {
                  const edge = name.startsWith('Top') ? 'top' : 'bottom'
                  return (
                    <div key={name} style={{ display: 'contents' }}>
                      <label>{name}</label>
                      <div className="linked">
                        <input className={`field${custom(name) ? ' custom' : ''}`} value={offsets[edge]}
                          onChange={(event) => changeOffset(edge, event.target.value)} aria-label={`${edge} Mozaik offset`} />
                        <span> + 4″ → </span>
                        <input className={`field${custom(name) ? ' custom' : ''}`} value={fields[name] || ''}
                          onChange={(event) => changePosition(edge, event.target.value)} />
                      </div>
                    </div>
                  )
                }
                if (name === 'Type') {
                  const choices = item.kind === 'doors' ? typeChoices : boxTypes
                  return (
                    <div key={name} style={{ display: 'contents' }}>
                      <label>{name}</label>
                      <select className={custom(name) ? 'custom' : ''} value={fields.Type}
                        onChange={(event) => {
                          const value = event.target.value
                          const next: Record<string, string> = { ...fields, Type: value }
                          if (item.kind === 'boxes') next.Scoop = value === 'Tray' ? 'A' : ''
                          if (item.kind === 'doors') {
                            const hinged = !value.includes('Drawer Front') && value !== 'Applied Door'
                            next.Location = hinged ? (fields.Location === 'R' || fields.Location === 'Susan' ? fields.Location : 'L') : (value === '5-Piece Drawer Front' || value === 'Applied Door' ? 'none' : '')
                          }
                          setManual(new Set())
                          pushDraft(next)
                        }}>
                        {choices.map((choice) => <option key={choice}>{choice}</option>)}
                      </select>
                    </div>
                  )
                }
                if (name === 'Location' || name === 'Scoop') {
                  const choices = name === 'Location' ? ['L', 'R', 'Susan', 'none', ''] : ['', 'A']
                  return (
                    <div key={name} style={{ display: 'contents' }}>
                      <label>{name}</label>
                      <select className={custom(name) ? 'custom' : ''} value={fields[name] || ''}
                        onChange={(event) => setField(name, event.target.value)}>
                        {choices.map((choice) => <option key={choice} value={choice}>{choice || '(blank)'}</option>)}
                      </select>
                    </div>
                  )
                }
                return (
                  <div key={name} style={{ display: 'contents' }}>
                    <label>
                      {name === 'Center Bore Position'
                        ? `Center Bore Position · ${reference === BOTTOM ? 'from bottom · Mozaik' : 'from top · Decorative'}`
                        : name}
                    </label>
                    <input className={`field${custom(name) ? ' custom' : ''}`} value={fields[name] || ''}
                      onChange={(event) => setField(name, event.target.value, name === 'Center Bore Position' ? 'center' : undefined)} />
                  </div>
                )
              })}
            </div>
            <label className={`check${included !== item.baseline?.Included ? ' custom' : ''}`} style={{ display: 'block', marginTop: 12 }}>
              <input type="checkbox" checked={included} onChange={(event) => setIncluded(event.target.checked)} />
              {' '}Include this row in copies and CSVs
            </label>
            {item.kind === 'doors' && (
              <button className="btn" style={{ marginTop: 10 }} onClick={resetBores}>Reset bore positions</button>
            )}
            <p className="help">
              {item.kind === 'doors'
                ? 'Light blue = changed from the imported row / defaults.\nEnter the Mozaik offset for top / bottom; 4″ is added.\nOr edit the final From top / From bottom position.\nBlank clears a position. Reset restores type/height defaults.\nCenter bore: choose the reference edge at right.\nPosition edits do not change Bore or Center Bore settings.\nDrawer fronts under 7 inches copy and save separately.'
                : 'Light blue = changed from the imported row / defaults.\nSizes accept fractions such as 17 27/32.\nChanging to Tray sets Scoop A. Drawer Box clears Scoop.'}
            </p>
          </div>
          {item.kind === 'doors' && (
            <div>
              <div className="diagram">
                <h3>Center bore placement</h3>
                <label>Input measured from</label>
                <select value={reference} onChange={(event) => changeReference(event.target.value)}>
                  <option>{BOTTOM}</option>
                  <option>{TOP}</option>
                </select>
                <div className="linked" style={{ margin: '8px 0' }}>
                  <span>Move by</span>
                  <input className="field" value={amount} onChange={(event) => setAmount(event.target.value)} />
                  <span>inches</span>
                </div>
                <div className="actions" style={{ marginTop: 0 }}>
                  <button className="btn" onClick={() => move('up')}>↑ Move up</button>
                  <button className="btn" onClick={() => move('down')}>↓ Move down</button>
                </div>
                <CenterDiagram
                  height={parseLoose(fields.Height) || 1}
                  fromTop={diagramTop}
                  fromBottom={diagramBottom}
                  location={fields.Location}
                />
                <p>{centerInfo?.offset || 'Preview unavailable'}</p>
                <p>{centerInfo?.mozaik || 'Mozaik: —'}</p>
                <p className="preview-ok">{centerInfo?.export || 'Enter a valid height and center bore.'}</p>
              </div>
              <div style={{ height: 8 }} />
              <EdgeGuide />
              <p>{equations.top}</p>
              <p>{equations.bottom}</p>
            </div>
          )}
        </div>
        {error && <p className="status error">{error}</p>}
        <div className="actions">
          <button className="btn" onClick={() => {
            const previous = draft[draft.length - 1]
            if (!previous) return
            setDraftRedo((stack) => [...stack, fields])
            setDraft((stack) => stack.slice(0, -1))
            setFields(previous)
          }} disabled={!draft.length}>Undo form</button>
          <button className="btn" onClick={() => {
            const next = draftRedo[draftRedo.length - 1]
            if (!next) return
            setDraft((stack) => [...stack, fields])
            setDraftRedo((stack) => stack.slice(0, -1))
            setFields(next)
          }} disabled={!draftRedo.length}>Redo form</button>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-accent" disabled={busy} onClick={() => apply()}>Apply changes</button>
        </div>
        {pending && (
          <div className="diagram" style={{ marginTop: 16 }}>
            <h3>{pending.question}</h3>
            <p>{pending.details}</p>
            {pending.quantity === 1 && (
              <div>
                <label><input type="radio" checked={side === 'L'} onChange={() => setSide('L')} /> Left (L)</label>
                <label style={{ marginLeft: 16 }}><input type="radio" checked={side === 'R'} onChange={() => setSide('R')} /> Right (R)</label>
                <div className="actions">
                  <button className="btn" onClick={() => setPending(null)}>Cancel</button>
                  <button className="btn btn-accent" onClick={() => apply({ side })}>Confirm hinge side</button>
                </div>
              </div>
            )}
            {pending.quantity === 2 && (
              <div>
                <p>If you choose No, confirm the hinge side for the one custom door:</p>
                <label><input type="radio" checked={side === 'L'} onChange={() => setSide('L')} /> Left (L)</label>
                <label style={{ marginLeft: 16 }}><input type="radio" checked={side === 'R'} onChange={() => setSide('R')} /> Right (R)</label>
                <div className="actions">
                  <button className="btn" onClick={() => setPending(null)}>Cancel</button>
                  <button className="btn" onClick={() => apply({ duplicate: false, side })}>No — one door</button>
                  <button className="btn btn-accent" onClick={() => apply({ duplicate: true })}>Yes — L and R</button>
                </div>
              </div>
            )}
            {pending.quantity > 2 && (
              <div>
                <p>Apply custom bores to every door, or only one?</p>
                <label>Left-hinging (L)
                  <input className="field" value={leftCount} onChange={(event) => setLeftCount(event.target.value)} />
                </label>
                <p>Right-hinging (R): {Number.isFinite(Number(leftCount)) ? pending.quantity - Number(leftCount) : '—'}</p>
                <p>If you choose No, confirm the hinge side for the one custom door:</p>
                <label><input type="radio" checked={side === 'L'} onChange={() => setSide('L')} /> Left (L)</label>
                <label style={{ marginLeft: 16 }}><input type="radio" checked={side === 'R'} onChange={() => setSide('R')} /> Right (R)</label>
                <div className="actions">
                  <button className="btn" onClick={() => setPending(null)}>Cancel</button>
                  <button className="btn" onClick={() => apply({ duplicate: false, side })}>No — one door</button>
                  <button className="btn btn-accent" onClick={() => apply({ duplicate: true, left_count: Number(leftCount) })}>Yes — all doors</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function parseLoose(text: string): number | null {
  const value = text.trim()
  if (!value) return null
  const mixed = /^(-?)(\d+)\s+(\d+)\/(\d+)$/.exec(value)
  if (mixed) {
    const sign = mixed[1] ? -1 : 1
    return sign * (Number(mixed[2]) + Number(mixed[3]) / Number(mixed[4]))
  }
  const frac = /^(-?)(\d+)\/(\d+)$/.exec(value)
  if (frac) return (frac[1] ? -1 : 1) * Number(frac[2]) / Number(frac[3])
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

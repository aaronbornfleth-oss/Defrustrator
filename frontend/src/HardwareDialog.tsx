import { useEffect, useState } from 'react'
import { copyText, generateHardware, hardwareState, saveHardwareDraft } from './api'
import type { HardwareDraft, HardwareLine, Session } from './types'

type Props = {
  session: Session
  onClose: (session?: Session) => void
  onSaveOrder: () => void
}

export default function HardwareDialog({ session, onClose, onSaveOrder }: Props) {
  const [draft, setDraft] = useState<HardwareDraft>(session.hardware_draft || emptyDraft(session))
  const [lines, setLines] = useState<HardwareLine[]>(session.hardware_lines)
  const [notice, setNotice] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const [preview, setPreview] = useState(Boolean(session.hardware_draft?.preview))

  useEffect(() => {
    hardwareState().then((state) => {
      setDraft(state.draft)
      setLines(state.lines)
      setNotice(state.notice)
      setPreview(state.draft.preview)
    }).catch((exc) => setNotice(exc.message))
  }, [])

  function updateSpecial(category: string, index: number, key: 'part_number' | 'quantity' | 'unit', value: string) {
    setDraft((current) => ({
      ...current,
      special: {
        ...current.special,
        [category]: current.special[category].map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row),
      },
    }))
  }

  async function createBody() {
    try {
      const result = await generateHardware(draft)
      setDraft(result.draft)
      setNotice(result.notice)
      setPreview(true)
      setCopyStatus('')
    } catch (exc) {
      setNotice(exc instanceof Error ? exc.message : 'Could not create the email body.')
    }
  }

  async function close() {
    const saved = await saveHardwareDraft({ ...draft, preview })
    onClose(saved)
  }

  return (
    <div className="overlay" role="dialog" aria-labelledby="hw-title">
      <div className="modal">
        <h2 id="hw-title">{preview ? 'Email body' : 'Review hardware for this job'}</h2>
        <p className="sub">{session.job}. Hardware covers the whole PDF. This window never sends email.</p>
        {!preview && (
          <>
            {session.hardware_errors.length > 0 && (
              <p className="status error">Hardware extraction needs attention:<br />{session.hardware_errors.join('\n')}</p>
            )}
            <div className="table-wrap" style={{ maxHeight: 220, minHeight: 140 }}>
              <table>
                <thead>
                  <tr><th>Part number</th><th>Hardware</th><th>PDF qty</th><th>Order qty</th><th>Unit</th></tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <tr key={line.index}>
                      <td>
                        {line.needs_part
                          ? <input className="field" value={draft.parts[String(line.index)] || ''}
                              onChange={(event) => setDraft({ ...draft, parts: { ...draft.parts, [line.index]: event.target.value } })} />
                          : line.part_number}
                      </td>
                      <td>{line.description}</td>
                      <td>{line.category === 'clips' ? '—' : line.source_quantity}</td>
                      <td>
                        {line.needs_quantity
                          ? <input className="field" value={draft.quantities[String(line.index)] || ''}
                              onChange={(event) => setDraft({ ...draft, quantities: { ...draft.quantities, [line.index]: event.target.value } })} />
                          : line.quantity ?? 'Review'}
                      </td>
                      <td>{line.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="sub">Glides: 2 individuals = 1 set. Hinges, spacers, and leg levelers keep the PDF quantity; clips match standard hinges.</p>
            <h3>Additional hinges (optional)</h3>
            <p className="sub">Enter a quantity to include a part; leave blank or 0 to skip. Parts are added to the standard hardware. New PDF jobs start with blank additional quantities.</p>
            {session.special_categories.map((category) => (
              <div key={category}>
                {(draft.special[category] || []).map((row, index) => (
                  <div className="special-row" key={`${category}-${index}`}>
                    <span>{index === 0 ? category : ''}</span>
                    <input className="field" placeholder="Part number" value={row.part_number}
                      onChange={(event) => updateSpecial(category, index, 'part_number', event.target.value)} />
                    <input className="field" placeholder="Qty" value={row.quantity}
                      onChange={(event) => updateSpecial(category, index, 'quantity', event.target.value)} />
                    <select value={row.unit} onChange={(event) => updateSpecial(category, index, 'unit', event.target.value)}>
                      <option>each</option>
                      <option>sets</option>
                    </select>
                    {index === 0
                      ? <button className="btn" onClick={() => setDraft({
                          ...draft,
                          special: { ...draft.special, [category]: [...draft.special[category], { part_number: '', quantity: '', unit: 'each' }] },
                        })}>+ Part</button>
                      : <button className="btn" onClick={() => setDraft({
                          ...draft,
                          special: { ...draft.special, [category]: draft.special[category].filter((_, rowIndex) => rowIndex !== index) },
                        })}>Remove</button>}
                  </div>
                ))}
              </div>
            ))}
          </>
        )}
        {preview && (
          <>
            <p className="sub">Review or edit the text, then copy it into your email.</p>
            <textarea className="tsv-fallback" style={{ minHeight: 320 }} value={draft.email}
              onChange={(event) => setDraft({ ...draft, email: event.target.value })} />
          </>
        )}
        {notice && <p className="status error">{notice}</p>}
        {copyStatus && <p className="status">{copyStatus}</p>}
        <div className="actions">
          {preview && <button className="btn" onClick={() => setPreview(false)}>Back to hardware</button>}
          <button className="btn" onClick={onSaveOrder}>Save order</button>
          {!preview && <button className="btn btn-accent" disabled={session.hardware_errors.length > 0} onClick={createBody}>Create email body</button>}
          {preview && <button className="btn btn-accent" onClick={async () => {
            const ok = await copyText(draft.email)
            setCopyStatus(ok ? 'Copied. Paste this into your email.' : 'Clipboard is blocked. Select the text and copy it.')
          }}>Copy email body</button>}
          <button className="btn" onClick={close}>Close</button>
        </div>
      </div>
    </div>
  )
}

function emptyDraft(session: Session): HardwareDraft {
  return {
    parts: {},
    quantities: {},
    special: Object.fromEntries(session.special_categories.map((category) => [category, [{ part_number: '', quantity: '', unit: 'each' }]])),
    email: '',
    generated_body: '',
    preview: false,
  }
}

import type { BorePending, ExportKind, HardwareDraft, Kind, Session } from './types'

async function readError(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map((part: { msg?: string }) => part.msg || JSON.stringify(part)).join(' ')
    return JSON.stringify(data)
  } catch {
    return response.statusText
  }
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<T>
}

export async function getSession(): Promise<Session> {
  return json(await fetch('/api/session'))
}

export async function clearSession(): Promise<Session> {
  return json(await fetch('/api/session/clear', { method: 'POST' }))
}

export async function setView(view: { group?: string; tab?: Kind; selection?: Session['view']['selection'] }): Promise<Session> {
  return json(await fetch('/api/session/view', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(view),
  }))
}

export async function importPdf(file: File): Promise<Session> {
  const body = new FormData()
  body.append('file', file)
  return json(await fetch('/api/import/pdf', { method: 'POST', body }))
}

export async function importOrder(file: File): Promise<Session> {
  const body = new FormData()
  body.append('file', file)
  return json(await fetch('/api/import/order', { method: 'POST', body }))
}

export async function loadDemo(): Promise<Session> {
  return json(await fetch('/api/demo/spigener', { method: 'POST' }))
}

export async function changeType(index: number, label: string): Promise<Session> {
  return json(await fetch(`/api/items/type?index=${index}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label }),
  }))
}

export async function deleteRows(indices: number[]): Promise<Session> {
  return json(await fetch('/api/items/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ indices }),
  }))
}

export async function editRow(index: number, payload: {
  fields: Record<string, string>
  included?: boolean
  center_reference?: string
  manual_positions?: string[]
  edge_offsets?: Record<string, string>
  decision?: { duplicate?: boolean | null; side?: string | null; left_count?: number | null }
}): Promise<Session | BorePending> {
  const response = await fetch(`/api/items/${index}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await response.json()
  if (response.status === 409 && data.pending === 'custom_bores') return data as BorePending
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Edit failed.')
  return data as Session
}

export async function undo(): Promise<Session> {
  return json(await fetch('/api/undo', { method: 'POST' }))
}

export async function redo(): Promise<Session> {
  return json(await fetch('/api/redo', { method: 'POST' }))
}

export async function clipboardText(kind: ExportKind, selected?: number[]): Promise<string> {
  const data = await json<{ text: string }>(await fetch('/api/export/clipboard', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind, selected: selected ?? null }),
  }))
  return data.text
}

export async function downloadCsv(kind: ExportKind): Promise<void> {
  const response = await fetch(`/api/export/csv/${kind}`)
  if (!response.ok) throw new Error(await readError(response))
  await saveBlob(response)
}

export async function downloadOrder(): Promise<void> {
  const response = await fetch('/api/export/order')
  if (!response.ok) throw new Error(await readError(response))
  await saveBlob(response)
}

export async function hardwareState(): Promise<{ draft: HardwareDraft; notice: string; lines: Session['hardware_lines']; errors: string[]; job: string }> {
  return json(await fetch('/api/hardware'))
}

export async function saveHardwareDraft(draft: HardwareDraft): Promise<Session> {
  return json(await fetch('/api/hardware/draft', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draft),
  }))
}

export async function generateHardware(draft: HardwareDraft): Promise<{ body: string; notice: string; draft: HardwareDraft; session: Session }> {
  return json(await fetch('/api/hardware/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draft),
  }))
}

export async function helperCenter(payload: {
  height: string
  position: string
  reference: string
  amount?: string
  direction?: string | null
  door_type?: string
}): Promise<{ top: string | null; displayed: string; preview: { mozaik: string; export: string; offset: string; valid: boolean; from_top?: string; from_bottom?: string }; reference: string }> {
  return json(await fetch('/api/helpers/center', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function helperEdge(payload: {
  edge: string
  height: string
  offset?: string
  position?: string
  source?: 'offset' | 'position'
}): Promise<{ position: string; offset: string; equation: string; standard: string }> {
  return json(await fetch('/api/helpers/edge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

async function saveBlob(response: Response): Promise<void> {
  const blob = await response.blob()
  const match = /filename="([^"]+)"/.exec(response.headers.get('content-disposition') || '')
  const name = match?.[1] || 'download'
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.left = '-9999px'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    area.remove()
    return ok
  }
}

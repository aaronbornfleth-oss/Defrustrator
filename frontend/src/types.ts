export type Kind = 'doors' | 'boxes'
export type ExportKind = 'doors' | 'short_fronts' | 'boxes'

export interface ItemRow {
  index: number
  kind: Kind
  qty: number
  width: string
  height: string
  depth: string | null
  type: string
  type_label: string
  location: string
  bore_location: string
  scoop: string
  french_lite: string
  page: number
  group: string
  part: string
  cabinets: string
  original: string
  included: boolean
  deleted: boolean
  values: string[]
  supplier_values: string[]
  export_kind: ExportKind
  has_hinge_boring: boolean
  is_front: boolean
  bore_overrides: Record<string, string | null>
  bore_positions: string[]
  changed_fields: string[]
  customized: boolean
  issue: string | null
  baseline: Record<string, string | number | boolean | null> | null
}

export interface ExportTable {
  label: string
  note: string
  headers: string[]
  csv_headers: string[]
  rows: string[][]
  source_indices: number[]
  item_total: number
}

export interface HardwareLine {
  index: number
  category: string
  part_number: string
  description: string
  quantity: number | null
  unit: string
  source_quantity: number | null
  pages: number[]
  needs_part: boolean
  needs_quantity: boolean
}

export interface HardwareDraft {
  parts: Record<string, string>
  quantities: Record<string, string>
  special: Record<string, Array<{ part_number: string; quantity: string; unit: string }>>
  email: string
  generated_body: string
  preview: boolean
}

export interface Session {
  app_name: string
  app_version: string
  has_report: boolean
  job: string
  source: string
  dirty: boolean
  can_undo: boolean
  can_redo: boolean
  undo_label: string
  redo_label: string
  errors: string[]
  notes: string[]
  checks: string[]
  hardware_errors: string[]
  hardware_pages: number[]
  groups: string[]
  view: { group: string; tab: Kind; selection: { doors: number[]; boxes: number[] } }
  counts: { doors: number; fronts: number; boxes: number; trays: number; short_fronts: number }
  items: ItemRow[]
  hardware: Array<{
    category: string
    qty: number
    part_number: string
    description: string
    page: number
    cabinets: string
    original: string
  }>
  hardware_lines: HardwareLine[]
  hardware_draft: HardwareDraft | null
  export_blocked: boolean
  order_filename: string | null
  quick_types: string[]
  type_choices: string[]
  box_types: string[]
  special_categories: string[]
  tables: Partial<Record<ExportKind, ExportTable>>
}

export interface BorePending {
  pending: 'custom_bores'
  quantity: number
  location: string
  question: string
  details: string
  suggested_left: number | null
}

export const BOTTOM = 'Bottom — Mozaik'
export const TOP = 'Top — Decorative'

export const DOOR_COLUMNS = [
  'Type', 'Qty', 'Width', 'Height', 'French Lite', 'Bore', 'Location',
  'Center Bore', 'Top Bore Position', 'Center Bore Position', 'Bottom Bore Position',
]
export const BOX_COLUMNS = ['Qty', 'Drawer Width', 'Drawer Height', 'Drawer Depth', 'Scoop']

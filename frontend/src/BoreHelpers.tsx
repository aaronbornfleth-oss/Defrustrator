import { BOTTOM, TOP } from './types'

export function CenterDiagram({
  height,
  fromTop,
  fromBottom,
  location,
}: {
  height: number
  fromTop: number | null
  fromBottom: number | null
  location: string
}) {
  const y = fromTop != null && height > 0 ? 24 + 106 * (fromTop / height) : null
  const x = location === 'R' ? 176 : 124
  return (
    <svg viewBox="0 0 300 155" width="300" height="155" role="img" aria-label="Center bore placement">
      <rect x="105" y="24" width="90" height="106" fill="#ffffff" stroke="#2a664c" strokeWidth="2" />
      <text x="150" y="14" textAnchor="middle" fill="#526c60" fontSize="11">TOP</text>
      <text x="150" y="148" textAnchor="middle" fill="#526c60" fontSize="11">BOTTOM</text>
      <line x1="105" y1="77" x2="195" y2="77" stroke="#c5d7cc" strokeDasharray="3 3" />
      {y != null && fromTop != null && fromBottom != null && (
        <>
          <line x1="105" y1={y} x2="195" y2={y} stroke="#2f7867" />
          <circle cx={x} cy={y} r="5" fill="#88b6c5" stroke="#2a664c" strokeWidth="2" />
          <line x1="87" y1="24" x2="87" y2={y} stroke="#2f7867" markerEnd="url(#arrow)" />
          <line x1="213" y1={y} x2="213" y2="130" stroke="#2f7867" />
          <text x="42" y={Math.max(49, (24 + y) / 2)} fill="#193c2e" fontSize="10" textAnchor="middle">
            {fromTop}″ from top
          </text>
          <text x="256" y={Math.min(111, (130 + y) / 2)} fill="#193c2e" fontSize="10" textAnchor="middle">
            {fromBottom}″ from bottom
          </text>
        </>
      )}
    </svg>
  )
}

export function EdgeGuide() {
  return (
    <div className="diagram">
      <h3>Top & bottom: enter the Mozaik offset</h3>
      <svg viewBox="0 0 310 80" width="310" height="80" role="img" aria-label="Top and bottom offset example">
        {[8, 166].map((x, i) => {
          const edge = i === 0 ? 'top' : 'bottom'
          const standard = edge === 'top' ? 28 : 49
          const custom = edge === 'top' ? 43 : 34
          return (
            <g key={edge}>
              <rect x={x} y="14" width="54" height="49" fill="#ffffff" stroke="#2a664c" strokeWidth="2" />
              <line x1={x} y1={standard} x2={x + 54} y2={standard} stroke="#88b6c5" strokeDasharray="3 2" />
              <circle cx={x + 14} cy={custom} r="4" fill="#88b6c5" stroke="#2a664c" />
              <line x1={x + 38} y1={standard} x2={x + 38} y2={custom} stroke="#2f7867" strokeWidth="2" />
              <text x={x + 27} y={edge === 'top' ? 10 : 74} textAnchor="middle" fill="#526c60" fontSize="10">
                {edge.toUpperCase()}
              </text>
              <text x={x + 98} y="39" fill="#2a664c" fontSize="13" fontWeight="650">4″ + 3″ = 7″</text>
            </g>
          )
        })}
      </svg>
      <p className="sub">0 = standard 4″. Positive moves inward; negative moves toward the edge.</p>
    </div>
  )
}

export { BOTTOM, TOP }

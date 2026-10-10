/** An admin page whose editor has not been built yet: says so, and lists what it will hold. */
export default function ComingSoon({ title, summary, items }: { title: string; summary: string; items: string[] }) {
  return (
    <div className="stack">
      <h1>{title}</h1>
      <div className="card stack">
        <p>{summary}</p>
        <div className="notice notice-warn">These values cannot be edited here yet. For now they are set in <code>backend/app/game/config.py</code>.</div>
        <div>
          <p className="muted small">This page will cover:</p>
          <ul className="admin-planned">
            {items.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      </div>
    </div>
  )
}

import { Link, useParams } from 'react-router-dom'
import SeriesResultView from './game/SeriesResultView'

export default function SeriesPage() {
  const seriesId = Number(useParams().seriesId)
  return (
    <div className="stack">
      <SeriesResultView seriesId={seriesId} />
      <Link to="/">← Back home</Link>
    </div>
  )
}

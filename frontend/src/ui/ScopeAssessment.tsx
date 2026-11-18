import { useEffect, useState } from 'react'
import { getScope } from '../api/client'
import type { ScopeReport } from '../api/types'
import Button from './Button'
import Notice from './Notice'

export default function ScopeAssessment({ path }: { path: string }) {
  const [report, setReport] = useState<ScopeReport | null>(null)
  const [error, setError] = useState('')
  const [requested, setRequested] = useState(0)
  const [busy, setBusy] = useState(false)
  useEffect(() => { setReport(null); setError(''); setRequested(0) }, [path])
  useEffect(() => {
    if (!requested) { setBusy(false); return }
    let active = true
    setBusy(true); setError('')
    getScope(path).then(value => { if (active) setReport(value) })
      .catch(() => { if (active) setError('지원 범위 진단을 불러오지 못했습니다.') })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [path, requested])
  return <div className="extension-card">
    <h2>구현 지원 범위 진단</h2>
    <p>분석된 요구에서 추가 구현이 예상되는 항목을 확인합니다. 업무 완료 판정과 별도입니다.</p>
    <Button disabled={busy} onClick={() => setRequested(v => v + 1)}>{busy ? '진단 중' : '요구별 지원 범위 확인'}</Button>
    {error && <Notice kind="error" title={error} />}
    {report && <>
      <p>기준 버전 {report.revision} · 검토 필요 {report.needs_review}건 · 확장 검토 후보 {report.extension_candidates}건</p>
      <p>{report.notice}</p>
      {!report.items.length && <p>아직 분석된 요구사항이 없습니다.</p>}
      {report.items.map(item => <details key={item.requirement_id}>
        <summary>{item.requirement_id} · {item.disposition === 'extension_candidate' ? '추가 구현 검토' : '실행 계약 확인'}</summary>
        <p>{item.text}</p>
        <ul>{item.hints.map(h => <li key={h.capability_id}>{h.capability_name}: {h.message}<br />확인한 표현: {h.evidence.join(', ')}</li>)}</ul>
        <p>{item.next_action}</p>
      </details>)}
    </>}
  </div>
}

import { useState } from 'react'
import type { Bundle, Specification } from '../api/specifications'
import Button from './Button'
import Notice from './Notice'
import { readPreparation, preparationDraft, type TestPreparation } from './testPreparation'

export default function TestPreparationImport({ spec, disabled, onApply }: {
  spec: Specification; disabled: boolean; onApply: (bundle: Bundle) => void
}) {
  const [packet, setPacket] = useState<TestPreparation | null>(null)
  const [accepted, setAccepted] = useState(false)
  const [error, setError] = useState('')
  return <section className="panel extension-card">
    <h2>E2E 준비 파일 검토</h2>
    <p>현재 명세에 맞춰 준비한 범위·계약·독립 기대값을 불러옵니다. 편집기에 반영한 뒤 새 버전 저장과 승인을 직접 진행하세요.</p>
    <label>준비 파일 선택<input type="file" accept=".json,application/json" disabled={disabled} onChange={async e => {
      setPacket(null); setAccepted(false); setError('')
      const file = e.target.files?.[0]
      if (!file) return
      try {
        if (file.size > 2_000_000) throw new Error('준비 파일은 2MB 이하만 불러올 수 있습니다.')
        setPacket(readPreparation(await file.text(), spec))
      } catch (reason) { setError(reason instanceof Error ? reason.message : '준비 파일을 확인하세요.') }
    }} /></label>
    {error && <Notice kind="error" title={error} />}
    {packet && <>
      <p>포함 {packet.scope.filter(s => s.disposition === 'included').length}개 · 후속 검증 {packet.scope.filter(s => s.disposition === 'deferred').length}개 · 실행 사례 {packet.bundle.acceptance_cases.filter(c => c.execution).length}개</p>
      <details><summary>요구별 포함·제외 근거</summary><ul>{packet.scope.map(s => <li key={s.requirement_id}>
        <strong>{packet.bundle.requirements.find(r => r.id === s.requirement_id)?.legacy_id ?? s.requirement_id} · {s.disposition === 'included' ? '포함' : '후속 검증'}</strong><p>{s.rationale}</p>
      </li>)}</ul></details>
      <details><summary>실행 전 작성한 인수 기대값</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(packet.bundle.acceptance_cases.filter(c => c.execution), null, 2)}</pre></details>
      <details><summary>미확정 질문의 테스트 가정 {packet.answer_proposals.length}개</summary><ul>{packet.answer_proposals.map(a => <li key={a.question_id}>
        <p>{packet.bundle.questions.find(q => q.id === a.question_id)?.question}</p><p>{a.answer}</p>
      </li>)}</ul></details>
      <p><label><input type="checkbox" checked={accepted} disabled={disabled} onChange={e => setAccepted(e.target.checked)} />포함·제외 범위와 테스트 가정을 검토했으며, 제안된 답변을 편집기에 함께 반영합니다.</label></p>
      <Button variant="primary" type="button" disabled={disabled} onClick={() => {
        try {
          const checked = readPreparation(JSON.stringify(packet), spec)
          onApply(preparationDraft(checked, accepted))
        } catch (reason) { setError(reason instanceof Error ? reason.message : '기준 명세를 다시 확인하세요.') }
      }}>준비안을 편집기에 반영</Button>
      {!accepted && <p>가정을 확인하지 않으면 기존 미답변 상태를 유지합니다.</p>}
    </>}
  </section>
}

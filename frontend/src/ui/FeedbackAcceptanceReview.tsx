import type { Bundle } from '../api/specifications'

import type { AcceptanceDraft } from './feedbackAcceptance'

export default function FeedbackAcceptanceReview({ bundle, draft, onChange, disabled }: {
  bundle: Bundle | null; draft: AcceptanceDraft[]; onChange: (value: AcceptanceDraft[]) => void; disabled: boolean
}) {
  if (!draft.length) return null
  function update(id: string, value: Partial<AcceptanceDraft>) {
    onChange(draft.map(r => r.case_id === id ? { ...r, ...value } : r))
  }
  return <article className="panel extension-card">
    <h2>명령·계산 변경 인수 검토</h2>
    <p>모든 실행 사례를 검토해야 승인할 수 있습니다. AI는 기대값을 수정하지 않습니다. 결과를 실행하기 전에 계산 근거와 기대값을 확인하세요. 입력·단계·실패 검사는 보존됩니다.</p>
    {draft.map(r => {
      const test = bundle?.acceptance_cases.find(c => c.id === r.case_id)
      return <fieldset key={r.case_id} aria-label={r.case_id} disabled={disabled}>
        <legend>{r.case_id} · {test?.execution?.category}</legend>
        <details><summary>기존 입력·기대값 확인</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(test?.execution, null, 2)}</pre></details>
        <label>검토 근거 (10자 이상)<textarea aria-label="검토 근거 (10자 이상)" value={r.reason} onChange={e => update(r.case_id, { reason: e.target.value, confirmed: false })} /></label>
        <details><summary>기대값 변경 입력</summary>
          <p>유지하면 []입니다. 수정 시 0부터 시작하는 step_index와 전체 expect를 입력하세요. 예: {`[{"step_index":4,"expect":{"kind":"exact","status":200,"body":{"total":"3.03"}}}]`}. 기존 응답의 모든 필드를 유지해야 합니다.</p>
          <textarea aria-label={r.case_id + ' 기대값 변경'} rows={6} value={r.replacements} onChange={e => update(r.case_id, { replacements: e.target.value, confirmed: false })} />
        </details>
        <label><input type="checkbox" checked={r.confirmed} disabled={disabled || r.reason.trim().length < 10} onChange={e => update(r.case_id, { confirmed: e.target.checked })} />이 사례의 입력·기대값과 변경 영향을 검토했습니다.</label>
      </fieldset>
    })}
  </article>
}

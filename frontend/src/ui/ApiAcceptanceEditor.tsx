import { useState } from 'react'
import type { Bundle } from '../api/specifications'
import Button from './Button'
import Notice from './Notice'

export default function ApiAcceptanceEditor({ bundle, disabled, onChange }: {
  bundle: Bundle; disabled: boolean; onChange: (bundle: Bundle) => void
}) {
  const [text, setText] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [error, setError] = useState('')
  if (!bundle.domain) return null
  const cases = bundle.acceptance_cases.filter(c => c.execution)
  function create() {
    const api = bundle.apis[0]
    if (!api) return
    const use = bundle.use_cases.find(u => u.id === api.use_case_id)!
    const sample = (fields: typeof api.request_fields) => Object.fromEntries(fields.map(f => [f.name,
      f.data_type === 'integer' ? 0 : f.data_type === 'boolean' ? false : f.data_type === 'decimal' ? '0.00'
        : f.data_type === 'date' ? '2030-01-01' : f.data_type === 'datetime' ? '2030-01-01T00:00:00'
          : f.data_type === 'uuid' ? '00000000-0000-0000-0000-000000000001' : '예시값']))
    setEditing(null); setError('')
    setText(JSON.stringify({ id: 'TC-api-' + crypto.randomUUID().slice(0, 8), req_ids: use.req_ids,
      use_case_ids: [use.id], tier: 'api', given: ['빈 격리 DB에서 필요한 데이터를 API로 등록'],
      when: '검토한 입력으로 API 호출', then: ['명시한 응답 및 후속 조회 결과와 일치'], fixture_ids: ['explicit-api-values'],
      execution: { version: 'api-scenario-v1', category: 'normal', initial_state: 'empty_database', steps: [{
        api_id: api.id, actor: 'allowed', body: api.method === 'GET' ? null : sample(api.request_fields),
        request_key: use.transaction === 'read_only' ? null : 'command-1',
        expect: { kind: 'exact', status: 200, body: api.method === 'GET' ? [] : sample(api.response_fields) },
      }] } }, null, 2))
  }
  function apply() {
    try {
      const value = JSON.parse(text) as Bundle['acceptance_cases'][number]
      if (!value || typeof value.id !== 'string' || !value.id || value.tier !== 'api'
        || !Array.isArray(value.execution?.steps) || !value.execution.steps.length
        || !['normal', 'boundary', 'failure'].includes(value.execution.category)
        || !Array.isArray(value.req_ids) || !value.req_ids.length || value.req_ids.some(r => typeof r !== 'string')) throw Error('API 사례 ID·분류·요구 연결·실행 단계를 확인하세요.')
      if (editing && value.id !== editing) throw Error('기존 사례의 ID는 유지하세요.')
      if (!editing && bundle.acceptance_cases.some(c => c.id === value.id)) throw Error('이미 사용 중인 사례 ID입니다.')
      const apis = value.execution.steps.map(s => bundle.apis.find(a => a.id === s.api_id))
      if (apis.some(a => !a)) throw Error('명세에 없는 API가 포함되어 있습니다.')
      value.use_case_ids = [...new Set(apis.map(a => a!.use_case_id))]
      onChange({ ...bundle, schema_version: ['spec-v0.8','spec-v0.9'].includes(bundle.schema_version) ? bundle.schema_version : 'spec-v0.7', acceptance_cases: editing
        ? bundle.acceptance_cases.map(c => c.id === editing ? value : c) : [...bundle.acceptance_cases, value] })
      setText(''); setEditing(null); setError('')
    } catch (e) { setError(e instanceof Error ? e.message : '실행 인수 JSON을 확인하세요.') }
  }
  return <section className="extension-card">
    <h2>실행 인수 테스트</h2>
    <p>요구별 API 입력·기대 응답·후속 조회를 작성합니다. 사례마다 빈 격리 DB에서 시작하므로 준비 데이터 등록도 단계에 포함하세요. 정상·경계·실패 사례를 각각 작성할 수 있습니다.</p>
    <p>예시값을 업무 조건에 맞게 수정한 뒤 명세에 적용하고 새 버전을 저장·승인하세요. 기대값은 API 실행 결과에서 자동 복사하지 않습니다. 소스 생성 후 격리 검증에서 실행됩니다.</p>
    <Button disabled={disabled || !bundle.apis.length} onClick={create}>API 인수 사례 초안 작성</Button>
    <ul>{cases.map(c => <li key={c.id}>{c.id} · {c.execution?.category} · {c.execution?.steps.length}단계{' '}
      <Button variant="secondary" disabled={disabled} onClick={() => { setEditing(c.id); setText(JSON.stringify(c, null, 2)); setError('') }}>사례 편집</Button>
    </li>)}</ul>
    {text && <>
      <details><summary>API 식별자와 입력 항목</summary><ul>{bundle.apis.map(a => <li key={a.id}>{a.id} · {a.method} {a.path} · 입력: {a.request_fields.map(f => f.name).join(', ') || '없음'}</li>)}</ul></details>
      <p>실패 응답 예: <code>{'{"kind":"error","status":409,"code":"RULE_VIOLATION"}'}</code>. category는 normal/boundary/failure, actor는 allowed/unauthenticated/denied입니다. 금액은 문자열로 작성하세요.</p>
      <p>계산·집계 POST에는 입력 본문과 <code>request_key: null</code>을 작성합니다. 0분모·숫자 범위 오류는 CALCULATION_ERROR, 최대 행 수 초과는 RESULT_LIMIT_EXCEEDED입니다.</p>
      <label>실행 인수 사례 JSON<textarea aria-label="실행 인수 사례 JSON" rows={20} disabled={disabled} value={text} onChange={e => setText(e.target.value)} style={{ width: '100%', fontFamily: 'monospace' }} /></label>
      <Button disabled={disabled} onClick={apply}>인수 사례를 명세 편집기에 적용</Button>
      <Button variant="secondary" disabled={disabled} onClick={() => { setText(''); setError('') }}>작성 취소</Button>
      <p>적용은 편집기에만 반영합니다. 최종 계약 검사는 새 버전을 저장할 때 수행합니다.</p>
    </>}
    {error && <Notice kind="error" title={error} />}
  </section>
}

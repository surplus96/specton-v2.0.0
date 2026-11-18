export type RequirementEvidence = {
  version: string
  notice: string
  items: {
    requirement_id: string
    text: string
    api_check_status: 'checks_passed' | 'partial' | 'failed' | 'not_run'
    api_ids: string[]
    passed_api_ids: string[]
    failed_api_ids: string[]
    missing_api_ids: string[]
    acceptance_cases: { id: string; tier: string; status: string; execution_kind?: string; category?: string; reason?: string; steps?: {index: number; status: string; reason?: string}[] }[]
  }[]
}

const STATUS = {
  checks_passed: '연결 API 검사 통과',
  partial: '일부 API만 검증',
  failed: 'API 검사 실패',
  not_run: 'API 검사 근거 없음',
}

export default function RequirementResults({ evidence }: { evidence?: RequirementEvidence }) {
  if (!evidence) return null
  return <details>
    <summary>요구사항별 검증 근거 ({evidence.items.length}건)</summary>
    <p>{evidence.notice}</p>
    {evidence.items.map(item => <details key={item.requirement_id}>
      <summary>{item.requirement_id} · {STATUS[item.api_check_status]}</summary>
      <p>{item.text}</p>
      <p>연결 API {item.api_ids.length}개 · 검사 통과 {item.passed_api_ids.length}개</p>
      {item.failed_api_ids.length > 0 && <p>실패: {item.failed_api_ids.join(', ')}</p>}
      {item.missing_api_ids.length > 0 && <p>검사 근거 없음: {item.missing_api_ids.join(', ')}</p>}
      <p>업무 전체 인수는 별도 검토가 필요합니다. 실행 계약 없는 사례 {item.acceptance_cases.filter(c => c.execution_kind !== 'api').length}건은 미실행입니다.</p>
      <ul>{item.acceptance_cases.map(c => <li key={c.id}>{c.id} · {c.execution_kind === 'api' ? '실행 인수' : '자연어 인수'} · {c.status === 'passed' ? '통과' : c.status === 'failed' ? '실패' : '미실행'}{c.category && ` · ${c.category}`}
        {c.steps?.filter(s => s.status !== 'passed').map(s => <p key={s.index}>{s.index}단계: {s.reason ?? s.status}</p>)}
        {c.reason && <p>{c.reason}</p>}
      </li>)}</ul>
    </details>)}
  </details>
}

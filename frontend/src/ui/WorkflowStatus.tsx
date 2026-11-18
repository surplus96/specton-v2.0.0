import StatusTag from '../layout/StatusTag'
import type { Tone } from '../theme'

const states: Record<string, [string, Tone]> = {
  active: ['연결됨', 'success'], disconnected: ['연결 해제됨', 'neutral'],
  received: ['접수됨', 'neutral'], analysing: ['분석 중', 'info'],
  needs_input: ['보완 필요', 'warning'], awaiting_decision: ['승인 대기', 'warning'],
  approved: ['승인됨', 'success'], rejected: ['반려됨', 'danger'],
  validating: ['검증 중', 'info'], applied: ['반영 완료', 'success'],
  queued: ['대기 중', 'neutral'], running: ['진행 중', 'info'],
  cancelling: ['취소 중', 'warning'], cancelled: ['취소됨', 'neutral'],
  recovering: ['복구 중', 'warning'], failed: ['실패', 'danger'],
  smoke_passed: ['기본 검증 통과', 'success'], passed: ['통과', 'success'],
  ready: ['준비 완료', 'success'], closed: ['종료됨', 'neutral'],
  starting: ['준비 중', 'info'], pending: ['대기 중', 'neutral'],
  succeeded: ['완료', 'success'], completed: ['완료', 'success'],
  draft: ['초안', 'neutral'], ready_for_review: ['승인 검토 가능', 'warning'],
  not_run: ['미실행', 'neutral'],
}

export default function WorkflowStatus({ state }: { state: string | null | undefined }) {
  const [label, tone] = states[state ?? 'not_run'] ?? [state ?? '미실행', 'neutral']
  return <StatusTag tone={tone}>{label}</StatusTag>
}

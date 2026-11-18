export type AcceptanceDraft = { case_id: string; reason: string; replacements: string; confirmed: boolean }
export type AcceptanceReview = { case_id: string; reason: string; replacements: unknown[] }
export function acceptancePayload(draft: AcceptanceDraft[]): AcceptanceReview[] {
  return draft.filter(r => r.confirmed).map(r => {
    const replacements: unknown = JSON.parse(r.replacements)
    if (!Array.isArray(replacements)) throw new Error('기대값 변경은 JSON 배열로 입력하세요.')
    return { case_id: r.case_id, reason: r.reason, replacements }
  })
}

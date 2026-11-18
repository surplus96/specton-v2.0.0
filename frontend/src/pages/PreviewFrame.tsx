import Notice from '../ui/Notice'
import { useEffect, useRef, useState } from 'react'
import { specificationRequest } from '../api/specifications'

export default function PreviewFrame({ id }: { id: string }) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [document, setDocument] = useState<{ id: string; html: string } | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    let inflight = 0
    specificationRequest<{ html: string }>(`/previews/${id}/document`)
      .then(value => { if (active) { setDocument({ id, html: value.html }); setError('') } })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : '미리보기 조회 실패') })
    async function message(event: MessageEvent) {
      if (!active || event.source !== frame.current?.contentWindow || event.origin !== 'null') return
      const data = event.data as Record<string, unknown> | null
      if (!data || data.type !== 'specton-preview-request' || !Number.isSafeInteger(data.id) || typeof data.path !== 'string' || data.path.length > 1024 || !['GET', 'POST', 'PATCH'].includes(String(data.method)) || (data.body !== null && (typeof data.body !== 'string' || data.body.length > 16384)) || inflight >= 4) return
      inflight++
      let result: { status: number; body: string }
      try {
        result = await specificationRequest(`/previews/${id}/rpc`, 'POST', {
          method: data.method, path: data.path, body: data.body, command_key: data.command_key ?? null,
        })
      } catch (e) {
        const reason = e instanceof Error ? e.message : '미리보기 요청 실패'
        if (active) setError(reason)
        result = { status: 503, body: JSON.stringify({ detail: reason }) }
      } finally { inflight-- }
      if (active) frame.current?.contentWindow?.postMessage({ type: 'specton-preview-response', id: data.id, ...result }, '*')
    }
    window.addEventListener('message', message)
    return () => { active = false; window.removeEventListener('message', message) }
  }, [id])
  return <div>
    <p>15분 동안 사용할 수 있는 합성 검증 데이터 기반 미리보기입니다. 모든 데모 역할을 사용하며 변경 내용은 폐기됩니다.</p>
    {error && <Notice kind="error" title={error} />}
    {document?.id === id && <iframe ref={frame} title="격리된 생성 앱 미리보기" sandbox="allow-scripts allow-forms" referrerPolicy="no-referrer" srcDoc={document.html} className="extension-preview" />}
  </div>
}

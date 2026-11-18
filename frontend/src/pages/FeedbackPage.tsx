import WorkflowStatus from '../ui/WorkflowStatus'
import Button from '../ui/Button'
import Notice from '../ui/Notice'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { specificationRequest as api } from '../api/specifications'

type Connection = { id: string; email: string; state: string; query: string; automatic: boolean; last_sync_at: string | null; error_code: string | null }
type Message = { id: string; subject: string; sender: string; received_at: string; body?: string; attachments?: { name: string; size: number }[] }
type Job = { id: string; kind: string; state: string; error_code: string | null }
type Status = { connection: Connection | null; configured: boolean; analysis_enabled: boolean }
type Listing = { items: Message[]; next: string | null }

export default function FeedbackPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [status, setStatus] = useState<Status | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [next, setNext] = useState<string | null>(null)
  const [selected, setSelected] = useState<Message | null>(null)
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([])
  const [project, setProject] = useState('')
  const [changes, setChanges] = useState<{ id: string; title: string; state: string }[]>([])
  const [query, setQuery] = useState('newer_than:30d -in:drafts')
  const [automatic, setAutomatic] = useState(false)
  const [jobs, setJobs] = useState<Job[]>([])
  const [title, setTitle] = useState('')
  const [quote, setQuote] = useState('')
  const [instruction, setInstruction] = useState('')
  const [eraseConfirmed, setEraseConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID())
  const callback = params.get('gmail')
  useEffect(() => {
    let active = true
    async function load(first: boolean) {
      try {
        const [state, inbox, work] = await Promise.all([api<Status>('/integrations/gmail'), api<Listing>('/feedback'), api<Job[]>('/feedback-jobs')])
        if (!active) return
        setStatus(state); setJobs(work)
        if (first) {
          setMessages(inbox.items); setNext(inbox.next)
          if (state.connection) { setQuery(state.connection.query); setAutomatic(state.connection.automatic) }
          const list = await api<{ id: string; name: string }[]>('/projects')
          if (active) { setProjects(list); setProject(list[0]?.id ?? '') }
        }
      } catch (e) { if (active) setError(e instanceof Error ? e.message : '조회 실패') }
    }
    void load(true)
    const timer = setInterval(() => void load(false), 5000)
    return () => { active = false; clearInterval(timer) }
  }, [])
  useEffect(() => {
    if (!project) return
    let active = true
    api<{ id: string; title: string; state: string }[]>('/projects/' + project + '/changes')
      .then(rows => { if (active) setChanges(rows) })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : '변경 요청 조회 실패') })
    return () => { active = false }
  }, [project])
  async function refreshInbox() {
    const inbox = await api<Listing>('/feedback')
    setMessages(inbox.items); setNext(inbox.next)
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : '처리 실패') }
    finally { setBusy(false) }
  }
  const connection = status?.connection
  return <section className="screen extension-page">
    <Link to="/projects">내 프로젝트</Link>
    <header className="screen-head"><h1 className="hero">고객 메일·변경 요청</h1></header>
    <div className="panel extension-content">
    <p>Gmail 읽기 권한으로 지정한 메일을 수집합니다. 메일 전송·삭제·읽음 처리는 하지 않습니다.</p>
    {callback && <Notice kind={callback === 'connected' ? 'success' : 'warning'} title={callback === 'connected' ? 'Gmail 연결을 완료했습니다. 수집 범위를 저장하고 동기화하세요.' : 'Gmail 연결을 완료하지 못했습니다. 로그인한 계정으로 다시 연결하세요.'} />}
    {error && <Notice kind="error" title={error} />}
    {!status?.configured && <p>Google OAuth 설정과 서버의 Gmail 토큰 암호화 키가 필요합니다.</p>}
    <p>연결: {connection ? <>{connection.email} <WorkflowStatus state={connection.state} /></> : '없음'}</p>
    <Button variant="secondary" type="button" disabled={busy || !status?.configured} onClick={() => void perform(async () => {
      const result = await api<{ url: string }>('/integrations/gmail/connect', 'POST')
      window.location.assign(result.url)
    })}>{connection?.state === 'active' ? 'Gmail 다시 연결' : 'Gmail 연결'}</Button>
    {connection && connection.state !== 'disconnected' && <Button variant="danger" type="button" disabled={busy} onClick={() => void perform(async () => {
      const result = await api<{ google_revoked: boolean }>('/integrations/gmail/' + connection.id, 'DELETE')
      setStatus(await api<Status>('/integrations/gmail'))
      if (!result.google_revoked) setError('수집은 중지했습니다. Google 계정의 연결된 앱에서도 권한을 해제하세요.')
    })}>Gmail 연결 해제</Button>}
    {connection?.state === 'active' && <>
      <form onSubmit={e => { e.preventDefault(); void perform(async () => {
        await api('/integrations/gmail/' + connection.id, 'PATCH', { query, automatic })
        setStatus(await api<Status>('/integrations/gmail'))
      }) }}>
        <p><label>수집할 메일 검색 조건 <input  maxLength={500} required value={query} onChange={e => setQuery(e.target.value)} /></label></p>
        <p>예: from:client@example.com newer_than:30d -in:drafts · 범위당 최대 500건. 검색 조건은 앱 수집 필터이며 Google 권한을 특정 메일로 제한하지 않습니다.</p>
        <label><input type="checkbox" checked={automatic} onChange={e => setAutomatic(e.target.checked)} />주기적으로 동기화</label>{' '}
        <Button variant="primary" type="submit" disabled={busy}>수집 범위 저장</Button>
      </form>
      <Button variant="secondary" type="button" disabled={busy} onClick={() => void perform(async () => {
        await api('/integrations/gmail/' + connection.id + '/sync', 'POST')
        setJobs(await api<Job[]>('/feedback-jobs'))
      })}>지금 동기화</Button>
      <p>최근 수집: {connection.last_sync_at ? new Date(connection.last_sync_at).toLocaleString() : '아직 없음'} {connection.error_code && '· ' + connection.error_code}</p>
    </>}
    <details><summary>동기화·분석 작업 상태</summary><ul>{jobs.map(j => <li key={j.id}>{j.kind} · <WorkflowStatus state={j.state} /> {j.error_code && '· ' + j.error_code}</li>)}</ul><p>대기 상태가 계속되면 피드백 작업자의 실행 상태를 확인하세요.</p></details>
    <h2>프로젝트 변경 요청</h2>
    <label>조회 프로젝트 <select value={project} onChange={e => setProject(e.target.value)}>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
    <Button variant="secondary" type="button" disabled={busy || !project} onClick={() => void perform(async () => setChanges(await api('/projects/' + project + '/changes')))}>요청 목록 새로고침</Button>
    {status && !changes.length && <p className="extension-empty">등록된 변경 요청이 없습니다. 수집한 메일에서 요청을 등록하세요.</p>}
    <ul>{changes.map(c => <li key={c.id}><Link to={'/changes/' + c.id}>{c.title}</Link> · <WorkflowStatus state={c.state} /></li>)}</ul>
    <h2>수집한 메일</h2>
    <Button variant="secondary" type="button" disabled={busy} onClick={() => void perform(refreshInbox)}>수신함 새로고침</Button>
    {status && !messages.length && <p className="extension-empty">수집한 메일이 없습니다. Gmail 연결과 검색 조건을 확인하고 동기화하세요.</p>}
    <ul>{messages.map(m => <li key={m.id}><Button variant="secondary" type="button" disabled={busy} onClick={() => void perform(async () => {
      const mail = await api<Message>('/feedback/' + m.id)
      setSelected(mail); setTitle(mail.subject.slice(0, 200)); setQuote(''); setInstruction(''); setEraseConfirmed(false); setRequestKey(crypto.randomUUID())
    })}>{m.subject || '(제목 없음)'}</Button> · {m.sender} · {new Date(m.received_at).toLocaleString()}</li>)}</ul>
    {next && <Button variant="secondary" type="button" disabled={busy} onClick={() => void perform(async () => {
      const more = await api<Listing>('/feedback?before=' + next)
      setMessages([...messages, ...more.items]); setNext(more.next)
    })}>이전 메일 더 보기</Button>}
    {selected && <article className="panel extension-card">
      <h2>{selected.subject}</h2>
      <p>{selected.sender}</p>
      <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto' }}>{selected.body}</pre>
      <p>첨부 파일은 자동으로 열거나 분석하지 않습니다.</p>
      <ul>{selected.attachments?.map((a, i) => <li key={i}>{a.name} · {a.size} bytes</li>)}</ul>
      <h3>변경 요청 등록</h3>
      <p>구현 기준이 채택된 프로젝트를 선택하세요. 한 메일의 여러 요청을 나누어 등록할 수 있습니다.</p>
      <form onSubmit={e => { e.preventDefault(); void perform(async () => {
        const result = await api<{ id: string }>('/feedback/' + selected.id + '/changes', 'POST',
          { project_id: project, request_key: requestKey, title, quote, instruction })
        navigate('/changes/' + result.id)
      }) }}>
        <p><label>프로젝트 <select required value={project} onChange={e => { setProject(e.target.value); setRequestKey(crypto.randomUUID()) }}>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label></p>
        <p><label>요청 제목 <input required maxLength={200} value={title} onChange={e => { setTitle(e.target.value); setRequestKey(crypto.randomUUID()) }} /></label></p>
        <p><label>요청 원문 인용 (본문에서 그대로 복사)<br /><textarea required maxLength={8000} rows={5} style={{ width: '100%' }} value={quote} onChange={e => { setQuote(e.target.value); setRequestKey(crypto.randomUUID()) }} /></label></p>
        <p><label>검토자가 추가할 설명<br /><textarea maxLength={4000} rows={3} style={{ width: '100%' }} value={instruction} onChange={e => { setInstruction(e.target.value); setRequestKey(crypto.randomUUID()) }} /></label></p>
        <Button variant="primary" type="submit" disabled={busy || !project || !quote.trim()}>변경 요청 등록</Button>
      </form>
      <details><summary>수집한 원문 삭제</summary>
        <p>메일 원문과 요청의 분석 내용을 지웁니다. 이미 생성·승인한 명세와 소스는 별도 이력으로 남습니다. Gmail 원본은 삭제하지 않습니다.</p>
        <label><input type="checkbox" checked={eraseConfirmed} onChange={e => setEraseConfirmed(e.target.checked)} />삭제 범위를 확인했습니다.</label>{' '}
        <Button variant="danger" type="button" disabled={busy || !eraseConfirmed} onClick={() => void perform(async () => {
          await api('/feedback/' + selected.id, 'DELETE'); setSelected(null); await refreshInbox()
        })}>수집 원문 삭제</Button>
      </details>
    </article>}
    {busy && <Notice title="처리 중입니다." />}
    </div>
  </section>
}

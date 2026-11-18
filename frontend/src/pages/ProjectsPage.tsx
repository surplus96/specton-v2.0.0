import Button from '../ui/Button'
import Notice from '../ui/Notice'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { specificationRequest, type Specification } from '../api/specifications'

type Project = { id: string; name: string }
type Baseline = { id: string; run_id: string; revision: number }
type Detail = Project & { baselines: Baseline[] }

async function api<T>(path: string, body?: unknown): Promise<T> {
  const csrf = document.cookie.split('; ').find(v => v.startsWith('specton_csrf='))?.split('=')[1] ?? ''
  const response = await fetch('/api/v1' + path, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) throw new Error(response.status === 401 ? 'Google 계정으로 로그인해 주세요.' : '요청을 처리하지 못했습니다. 소유권과 승인 상태를 확인해 주세요.')
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export default function ProjectsPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [projects, setProjects] = useState<Project[]>([])
  const [selected, setSelected] = useState<Detail | null>(null)
  const [name, setName] = useState('')
  const [run, setRun] = useState(() => params.get('run') ?? sessionStorage.getItem('specton-project-run') ?? '')
  const [revision, setRevision] = useState(() => Math.max(0, Number(params.get('revision') ?? sessionStorage.getItem('specton-project-revision')) || 0))
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    Promise.all([api<{ email: string }>('/auth/me'), api<Project[]>('/projects')])
      .then(([user, list]) => { if (active) { setEmail(user.email); setProjects(list) } })
      .catch(e => { if (active) setError(String(e.message)) })
    return () => { active = false }
  }, [])
  useEffect(() => {
    sessionStorage.setItem('specton-project-run', run)
    sessionStorage.setItem('specton-project-revision', String(revision))
  }, [run, revision])
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : '처리 실패') }
    finally { setBusy(false) }
  }
  return <section className="screen extension-page">
    <header className="screen-head"><h1 className="hero">내 프로젝트</h1></header>
    <div className="panel extension-content">
    <p><Link to="/feedback">Gmail 연결·고객 변경 요청</Link></p>
    <p>Google 계정으로 프로젝트와 승인한 설계를 이어서 관리합니다.</p>
    {error && <Notice kind="error" title={error} />}
    {notice && <Notice kind="success" title={notice} />}
    {!email ? <a className="btn" href="/api/v1/auth/google">Google 계정으로 로그인</a> : <>
      <p>{email} <Button variant="secondary" type="button" disabled={busy} onClick={() => void perform(async () => {
        await api('/auth/logout', {}); setEmail(''); setProjects([]); setSelected(null)
      })}>로그아웃</Button></p>
      <form onSubmit={e => { e.preventDefault(); void perform(async () => {
        await api('/projects', { name }); setName(''); setProjects(await api<Project[]>('/projects'))
      }) }}>
        <label>프로젝트 이름 <input value={name} maxLength={120} required onChange={e => setName(e.target.value)} /></label>
        <Button variant="primary" type="submit" disabled={busy || !name.trim()}>프로젝트 만들기</Button>
      </form>
      {projects.length === 0 && <p className="extension-empty">아직 프로젝트가 없습니다. 이름을 입력해 첫 프로젝트를 만드세요.</p>}
      <ul>{projects.map(p => <li key={p.id}><Button variant="secondary" type="button" disabled={busy} onClick={() => void perform(async () => {
        setSelected(await api<Detail>(`/projects/${p.id}`))
      })}>{p.name}</Button></li>)}</ul>
      {selected && <article className="panel extension-card">
        <h2>{selected.name}</h2>
        <p><Link to={`/projects/${selected.id}/candidates`}>검증 후보 비교·채택</Link></p>
        <p>현재 계정 또는 이 브라우저가 소유한 실행만 연결할 수 있습니다.</p>
        <label>실행 ID <input value={run} onChange={e => setRun(e.target.value)} /></label>
        <Button variant="secondary" type="button" disabled={busy || !run.trim()} onClick={() => void perform(async () => {
          await api(`/projects/${selected.id}/runs/${encodeURIComponent(run)}/claim`, {})
          setNotice('실행을 프로젝트에 연결했습니다.')
        })}>실행 소유권 확인 후 연결</Button>
        <p>완료된 실행의 승인 파일과 검증 근거를 확인해 SDD 기준 버전으로 고정합니다.</p>
        <label>설계 버전 <input type="number" min={0} value={revision} onChange={e => setRevision(Number(e.target.value))} /></label>
        <Button variant="primary" type="button" disabled={busy || !run.trim()} onClick={() => void perform(async () => {
          await api(`/projects/${selected.id}/baselines`, { run_id: run, revision })
          setSelected(await api<Detail>(`/projects/${selected.id}`))
        })}>승인 설계를 기준 버전으로 연결</Button>
        <ul>{selected.baselines.map(b => <li key={b.id}>실행 {b.run_id} · revision {b.revision} · 기준 {b.id} <Button variant="secondary" type="button" disabled={busy} onClick={() => void perform(async () => {
          const result = await specificationRequest<Specification>(`/baselines/${b.id}/specs`, 'POST')
          navigate(`/specifications/${result.bundle.spec_id}`)
        })}>실행 명세 작성·조회</Button></li>)}</ul>
        {!selected.baselines.length && <p>연결된 승인 기준 버전이 없습니다.</p>}
      </article>}
    </>}
    {busy && <Notice title="처리 중입니다." />}
    </div>
  </section>
}

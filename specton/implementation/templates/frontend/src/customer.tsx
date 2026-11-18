import React, { createContext, useContext, useEffect, useState } from 'react'

type User = { username:string; roles:string[]; csrf:string }
type Access = { mode:string; user:User|null; enabled:boolean; headers:()=>Record<string,string>; can:(roles:string[])=>boolean; expired:()=>void }
const Context = createContext<Access>(null!)
export const useAccess = () => useContext(Context)
const preview = !!(window as unknown as {spectonPreview?:boolean}).spectonPreview
export function CustomerAccess({children}:{children:React.ReactNode}) {
  const [mode,setMode]=useState(preview?'token':'loading')
  const [user,setUser]=useState<User|null>(null)
  const [token,setToken]=useState(preview?'preview':'')
  const [username,setUsername]=useState(''),[password,setPassword]=useState('')
  const [error,setError]=useState(''),[busy,setBusy]=useState(false)
  const [retry,setRetry]=useState(0)
  useEffect(()=>{if(preview)return;let active=true
    void fetch('/api/auth/session').then(async response=>{
      if(!response.ok)throw Error();const value=await response.json()
      if(active){setMode(value.mode);setUser(value.user);setError('')}
    }).catch(()=>{if(active){setMode('failed');setError('로그인 상태를 확인하지 못했습니다.')}})
    return()=>{active=false}
  },[retry])
  const headers=():Record<string,string>=>mode==='token'?{Authorization:`Bearer ${token}`}:{'X-CSRF-Token':user?.csrf??''}
  async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('')
    try{const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})})
      if(!response.ok)throw Error(response.status===429?'잠시 후 다시 로그인해 주세요.':'아이디 또는 비밀번호를 확인해 주세요.')
      const value=await response.json();setUser(value.user);setPassword('')
    }catch(e){setError(e instanceof Error?e.message:'로그인하지 못했습니다.')}finally{setBusy(false)}
  }
  async function logout(){setBusy(true);setError('')
    try{const r=await fetch('/api/auth/logout',{method:'POST',headers:headers()});if(!r.ok&&r.status!==401)throw Error();setUser(null)}
    catch{setError('로그아웃하지 못했습니다. 다시 시도해 주세요.')}finally{setBusy(false)}
  }
  if(mode==='loading')return <main><p role="status">로그인 상태 확인 중…</p></main>
  if(mode==='failed')return <main><p role="alert">{error}</p><button onClick={()=>{setMode('loading');setRetry(v=>v+1)}}>다시 연결</button></main>
  if(mode==='session'&&!user)return <main className="login"><h1>업무 시스템 로그인</h1><form onSubmit={login}>
    <label>아이디<input autoComplete="username" required maxLength={64} value={username} onChange={e=>setUsername(e.target.value)}/></label>
    <label>비밀번호<input type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label>
    <button disabled={busy}>로그인</button></form>{error&&<p role="alert">{error}</p>}</main>
  return <Context.Provider value={{mode,user,enabled:mode==='session'?!!user:!!token,headers,can:roles=>mode!=='session'||!!user?.roles.some(r=>roles.includes(r)),expired:()=>{if(mode==='session'){setUser(null);setPassword('');setError('로그인이 만료되었습니다. 다시 로그인해 주세요.')}}}}>
    <header className="account">{mode==='session'?<><span>{user?.username}</span><button disabled={busy} onClick={()=>void logout()}>로그아웃</button></>:!preview&&<label>데모 접근 토큰<input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)}/></label>}{error&&<p role="alert">{error}</p>}</header>
    {children}
  </Context.Provider>
}

export function message(data:unknown):string {
  const detail=(data as {detail?:unknown})?.detail
  const messages:Record<string,string>={AUTH_REQUIRED:'다시 로그인해 주세요.',FORBIDDEN:'이 작업을 수행할 권한이 없습니다.',CSRF_REJECTED:'로그인 상태를 새로고침해 주세요.',DUPLICATE_KEY:'이미 등록된 식별자입니다.',NOT_FOUND:'대상을 찾을 수 없습니다.',REFERENCE_NOT_FOUND:'연결할 데이터를 먼저 등록하거나 다시 선택해 주세요.',FOREIGN_KEY_VIOLATION:'연결할 데이터를 확인해 주세요.',RULE_VIOLATION:'입력값이 승인된 업무 조건에 맞지 않습니다.',INVALID_STATE:'현재 상태에서는 변경할 수 없습니다.',IDEMPOTENCY_CONFLICT:'요청 정보가 달라 다시 시도해야 합니다.'}
  return typeof detail==='string'?(messages[detail]??'요청을 처리하지 못했습니다. 입력값을 확인해 주세요.'):'입력 형식과 필수값을 확인해 주세요.'
}

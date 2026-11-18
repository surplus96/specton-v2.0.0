import { useRef, useState } from 'react'
import { message, useAccess } from './customer'
import type { Operation } from './records'

export function CommandForms({operations,busy,onBusy,onResult,onError}:{operations:Operation[];busy:boolean;onBusy:(value:boolean)=>void;onResult:(value:unknown)=>void;onError:(value:string)=>void}) {
  const access=useAccess()
  const [values,setValues]=useState<Record<string,string>>({})
  const attempts=useRef<Record<string,{body:string;key:string}>>({})
  const submitting=useRef(false)
  async function submit(op:Operation) {
    if(submitting.current)return
    submitting.current=true;onBusy(true);onError('');onResult(null)
    try {
      const data:Record<string,unknown>={}
      for(const f of op.fields){const v=values[op.id+':'+f.name]??'';data[f.name]=!v&&!f.required?null:f.data_type==='boolean'?v==='true':f.data_type==='integer'?Number(v):v}
      const body=JSON.stringify(data)
      if(attempts.current[op.id]?.body!==body)attempts.current[op.id]={body,key:crypto.randomUUID()}
      const response=await fetch('/api'+op.path,{method:'POST',headers:{...access.headers(),'Content-Type':'application/json','Idempotency-Key':attempts.current[op.id].key},body})
      const result=await response.json()
      if(response.status===401)access.expired()
      if(!response.ok)throw Error(message(result))
      onResult(result)
    } catch(error){onError(error instanceof Error?error.message:'명령 실행 실패')}
    finally{submitting.current=false;onBusy(false)}
  }
  return <>{operations.filter(o=>o.action==='command'&&access.can(o.actor_roles)).map(op=><form data-api={op.id} key={op.id} onSubmit={e=>{e.preventDefault();void submit(op)}}>
    <h3>{op.label}</h3><p>연결된 변경을 함께 처리합니다. 하나라도 실패하면 모두 취소됩니다.</p>
    {op.fields.map(f=><label key={f.name} style={{display:'block',marginBlock:8}}>{f.label}{f.data_type==='boolean'?<select data-field={f.name} required={f.required} value={values[op.id+':'+f.name]??''} disabled={busy} onChange={e=>setValues(v=>({...v,[op.id+':'+f.name]:e.target.value}))}><option value="">선택</option><option value="true">예</option><option value="false">아니오</option></select>:<input data-field={f.name} required={f.required} maxLength={f.length??undefined} disabled={busy} type={f.data_type==='date'?'date':f.data_type==='datetime'?'datetime-local':'text'} value={values[op.id+':'+f.name]??''} onChange={e=>setValues(v=>({...v,[op.id+':'+f.name]:e.target.value}))}/>}</label>)}
    <button type="submit" disabled={busy||!access.enabled}>함께 실행·결과 확인</button>
    <button type="button" disabled={busy} onClick={()=>{delete attempts.current[op.id];setValues(v=>Object.fromEntries(Object.entries(v).filter(([key])=>!key.startsWith(op.id+':'))));onResult(null);onError('')}}>새 요청 작성</button>
    <p>동일 입력의 재시도는 처리 결과를 다시 확인합니다. 별도 업무를 처리하려면 새 요청을 작성하세요.</p>
  </form>)}</>
}

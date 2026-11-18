import { useRef, useState } from 'react'
import { message, useAccess } from './customer'
import type { Operation } from './records'
type ComputationOperation=Operation&{response_metadata?:{name:string;unit?:Record<string,number>}[]}

export function CommandForms({operations,busy,onBusy,onResult,onError}:{operations:ComputationOperation[];busy:boolean;onBusy:(value:boolean)=>void;onResult:(value:unknown)=>void;onError:(value:string)=>void}) {
  const access=useAccess()
  const [values,setValues]=useState<Record<string,string>>({})
  const [outputs,setOutputs]=useState<Record<string,Record<string,unknown>|null>>({})
  const attempts=useRef<Record<string,{body:string;key:string}>>({})
  const submitting=useRef(false)
  async function submit(op:Operation) {
    if(submitting.current)return
    submitting.current=true;onBusy(true);onError('');onResult(null)
    setOutputs(v=>({...v,[op.id]:null}))
    try {
      const data:Record<string,unknown>={}
      for(const f of op.fields){const v=values[op.id+':'+f.name]??'';data[f.name]=!v&&!f.required?null:f.data_type==='boolean'?v==='true':f.data_type==='integer'?Number(v):v}
      const body=JSON.stringify(data)
      if(op.action==='command'&&attempts.current[op.id]?.body!==body)attempts.current[op.id]={body,key:crypto.randomUUID()}
      const response=await fetch('/api'+op.path,{method:'POST',headers:{...access.headers(),'Content-Type':'application/json',...(op.action==='command'?{'Idempotency-Key':attempts.current[op.id].key}:{})},body})
      const result=await response.json()
      if(response.status===401)access.expired()
      if(!response.ok){const explanation:Record<string,string>={CALCULATION_ERROR:'계산 값·기간·0분모와 숫자 범위를 확인해 주세요.',RESULT_LIMIT_EXCEEDED:'집계할 데이터가 승인한 최대 건수를 넘었습니다. 조회 범위를 좁혀 주세요.',COMMAND_TIMEOUT:'처리 시간이 초과되었습니다. 조회 범위나 잠금 상태를 확인하고 다시 시도해 주세요.'};throw Error(explanation[result.detail]??message(result))}
      onResult(result)
      if(op.action==='calculation')setOutputs(v=>({...v,[op.id]:result}))
    } catch(error){onError(error instanceof Error?error.message:'명령 실행 실패')}
    finally{submitting.current=false;onBusy(false)}
  }
  return <>{operations.filter(o=>['command','calculation'].includes(o.action)&&access.can(o.actor_roles)).map(op=><form data-api={op.id} key={op.id} onSubmit={e=>{e.preventDefault();void submit(op)}}>
    <h3>{op.label}</h3><p>{op.action==='calculation'?'승인한 범위의 데이터를 읽어 계산합니다. 저장 데이터는 변경하지 않습니다.':'연결된 변경을 함께 처리합니다. 하나라도 실패하면 모두 취소됩니다.'}</p>
    {op.fields.map(f=><label key={f.name} style={{display:'block',marginBlock:8}}>{f.label}{f.data_type==='boolean'?<select data-field={f.name} required={f.required} value={values[op.id+':'+f.name]??''} disabled={busy} onChange={e=>setValues(v=>({...v,[op.id+':'+f.name]:e.target.value}))}><option value="">선택</option><option value="true">예</option><option value="false">아니오</option></select>:<input data-field={f.name} required={f.required} maxLength={f.length??undefined} disabled={busy} type={f.data_type==='date'?'date':f.data_type==='datetime'?'datetime-local':'text'} value={values[op.id+':'+f.name]??''} onChange={e=>setValues(v=>({...v,[op.id+':'+f.name]:e.target.value}))}/>}</label>)}
    <button type="submit" disabled={busy||!access.enabled}>{op.action==='calculation'?'계산·집계 결과 확인':'함께 실행·결과 확인'}</button>
    <button type="button" disabled={busy} onClick={()=>{delete attempts.current[op.id];setValues(v=>Object.fromEntries(Object.entries(v).filter(([key])=>!key.startsWith(op.id+':'))));setOutputs(v=>({...v,[op.id]:null}));onResult(null);onError('')}}>새 요청 작성</button>
    <p>{op.action==='calculation'?'다시 실행하면 현재 저장된 데이터로 집계합니다.':'동일 입력의 재시도는 처리 결과를 다시 확인합니다. 별도 업무를 처리하려면 새 요청을 작성하세요.'}</p>
    {outputs[op.id]&&<div className="table-wrap"><table aria-label="계산·집계 결과"><thead><tr><th>항목</th><th>결과</th><th>단위</th></tr></thead><tbody>{op.response_metadata?.map(field=><tr key={field.name} data-result={field.name}><th>{field.name}</th><td>{outputs[op.id]![field.name]===null?'값 없음':String(outputs[op.id]![field.name])}</td><td>{Object.entries(field.unit??{}).map(([name,power])=>power===1?name:`${name}^${power}`).join(' · ')||'—'}</td></tr>)}</tbody></table></div>}
  </form>)}</>
}

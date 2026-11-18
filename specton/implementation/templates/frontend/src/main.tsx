import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import rawContract from './contract.json'
import { CustomerAccess, useAccess, message } from './customer'
import { RelationPicker, Records, type Domain, type Operation as DomainOperation } from './records'
import './style.css'
import { CommandForms } from './commands'
type MasterField = {id:string;name:string;data_type:string;required:boolean;length:number|null}
type MasterOperation = {api_id:string;actor_roles:string[];action:string;path:string;method:string;fields:MasterField[];key:{name:string;data_type:string}}
const contract=rawContract as unknown as {operations:MasterOperation[];screens:{id:string;name:string;route:string;actor_roles:string[];api_ids:string[];empty_state:string;loading_state:string;error_state:string}[]}


type InventoryOperation = { id: string; actor_roles:string[]; action: string; path: string; method: string; request_fields: { name: string; data_type: string }[] }
const stock = (contract as unknown as { inventory: { operations: InventoryOperation[] } | null }).inventory
const actionNames: Record<string, string> = { insert: '등록', get: '단건 조회', list: '목록 조회', update: '수정', draft: '입출고 초안 작성', edit: '초안 수량 수정', confirm: '확정', cancel: '확정 취소', movement: '입출고 조회', balance: '재고 조회' }

type CommerceOperation = { id:string; actor_roles:string[]; action:string; title:string; path:string; method:string; request_fields:{name:string;data_type:string}[] }
const commerce = (contract as unknown as {commerce?:{operations:CommerceOperation[];cutoff_hour:number;return_warning_percent:number;expiry_days:number}}).commerce

const labels:Record<string,string>={id:'번호',name:'이름',specification:'규격',barcode:'바코드',tax:'과세 구분',safety_stock:'안전재고 수량',product_id:'상품 코드',factor:'낱개 환산 수량',is_default:'기본 거래 단위',representative:'대표자명',business_number:'사업자등록번호',grade:'거래 등급',expires:'유통기한',quantity:'수량',member_id:'회원점 번호',amount:'반품 금액',note:'비고',unit:'거래 단위',price:'판매 단가'}
type OrderLine={product_id:string;unit:string;quantity:string;price:string}
const emptyLine=():OrderLine=>({product_id:'',unit:'',quantity:'',price:''})
const domain=(rawContract as unknown as {domain?:Domain}).domain
function App() {
  const access=useAccess();const token=access.enabled
  const [queries,setQueries]=useState<Record<string,string>>({})
  const [page,setPage]=useState(0),[lastDomain,setLastDomain]=useState<DomainOperation|null>(null)
  const [locked,setLocked]=useState<Record<string,boolean>>({})
  const [screen, setScreen] = useState(contract.screens.find(s => s.route === window.location.pathname)?.id ?? contract.screens[0]?.id ?? '')
  const [values, setValues] = useState<Record<string, string>>({})
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState('')
  const [orderLines,setOrderLines]=useState<Record<string,OrderLine[]>>({})
  const [busy, setBusy] = useState(false)
  const selected = contract.screens.find(s => s.id === screen && access.can(s.actor_roles)) ?? contract.screens.find(s=>access.can(s.actor_roles))
  const operations = contract.operations.filter(o => selected?.api_ids.includes(o.api_id)&&access.can(o.actor_roles))
  async function invoke(op: typeof contract.operations[number]) {
    setBusy(true); setError(''); setResult(null)
    try {
      let path = op.path
      const headers: Record<string, string> = access.headers()
      let body: string | undefined
      if (op.action === 'get') path = path.replace('{key}', encodeURIComponent(values[op.api_id + ':key'] ?? ''))
      else if (op.action !== 'list') {
        const data: Record<string, unknown> = {}
        for (const f of op.fields) {
          const value = values[op.api_id + ':' + f.name] ?? ''
          data[f.name] = !value && !f.required ? null : f.data_type === 'integer' ? Number(value) : f.data_type === 'boolean' ? value === 'true' : value
        }
        headers['Content-Type'] = 'application/json'
        headers['Idempotency-Key'] = crypto.randomUUID()
        if (op.action === 'update') path = path.replace('{key}', encodeURIComponent(String(data[op.key.name])))
        body = JSON.stringify(data)
      }
      const response = await fetch('/api' + path, { method: op.method, headers, body })
      const data: unknown = await response.json()
      if(response.status===401)access.expired();if (!response.ok) throw new Error(message(data))
      setResult(data)
    } catch (e) { setError(e instanceof Error ? e.message : '요청 실패') }
    finally { setBusy(false) }
  }
  async function invokeStock(op: InventoryOperation) {
    setBusy(true); setError(''); setResult(null)
    try {
      let path = op.path.replace('{key}', encodeURIComponent(values[op.id + ':key'] ?? ''))
      const input: Record<string, string> = {}
      for (const f of op.request_fields) if (f.name !== 'key') input[f.name] = values[op.id + ':' + f.name] ?? ''
      if (op.method === 'GET' && Object.keys(input).length) path += '?' + new URLSearchParams(input)
      const headers: Record<string,string> = { ...access.headers(), 'Content-Type': 'application/json' }
      if (op.method !== 'GET') headers['Idempotency-Key'] = crypto.randomUUID()
      const response = await fetch('/api' + path, { method: op.method, headers, body: op.method === 'GET' ? undefined : JSON.stringify(input) })
      const data: unknown = await response.json()
      if(response.status===401)access.expired();if (!response.ok) throw new Error(message(data))
      setResult(data)
    } catch (e) { setError(e instanceof Error ? e.message : '요청 실패') }
    finally { setBusy(false) }
  }
  async function invokeCommerce(op: CommerceOperation) {
    setBusy(true); setError(''); setResult(null)
    try {
      const payload: Record<string,unknown> = {}
      for (const f of op.request_fields) { const value=values[op.id+':'+f.name]??'';payload[f.name]=f.data_type==='boolean'?value==='true':value }
      if(op.request_fields.some(f=>f.name==='lines_json'))payload.lines_json=JSON.stringify(orderLines[op.id]??[emptyLine()])
      const response=await fetch('/api'+op.path,{method:op.method,headers:{...access.headers(),'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:op.method==='GET'?undefined:JSON.stringify(payload)})
      const data: unknown=await response.json()
      if(response.status===401)access.expired();if(!response.ok)throw new Error(message(data))
      setResult(data)
    }catch(e){setError(e instanceof Error?e.message:'요청 실패')}finally{setBusy(false)}
  }
  async function invokeDomain(op:DomainOperation,start=0){
    setBusy(true);setError('');setResult(null)
    try{
      const data:Record<string,unknown>={}
      for(const f of op.fields.filter(f=>op.action!=='transition'||f.primary)){
        const v=values[op.id+':'+f.name]??''
        data[f.name]=!v&&!f.required?null:f.data_type==='boolean'?v==='true':f.data_type==='integer'?Number(v):v
      }
      const response=await fetch('/api'+op.path+(op.action==='list'?'?'+new URLSearchParams({q:queries[op.id]??'',offset:String(start),limit:'21'}):''),{method:op.method,headers:{...access.headers(),'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:op.method==='GET'?undefined:JSON.stringify(data)})
      const result=await response.json();if(response.status===401)access.expired();if(!response.ok)throw Error(message(result));setResult(result);setLastDomain(op);setPage(start)
    }catch(e){setError(e instanceof Error?e.message:'요청 실패')}finally{setBusy(false)}
  }
  return <main>
    <h1>{domain ? '설계 기반 시스템' : commerce ? '상품·주문·반품 업무 시스템' : stock ? '재고 업무 시스템' : '기준정보 업무 시스템'}</h1>
    <nav>{contract.screens.filter(s=>access.can(s.actor_roles)).map(s => <button data-screen={s.id} disabled={busy} key={s.id} onClick={() => { setScreen(s.id); setResult(null); setError(''); if (!(window as unknown as { spectonPreview?: boolean }).spectonPreview) history.replaceState(null, '', s.route) }}>{s.name}</button>)}</nav>
    <h2>{selected?.name}</h2>
    {!result && !busy && !error && <p>{selected?.empty_state}</p>}
    {commerce && <p>기본 시연 · 당일 {commerce.cutoff_hour}시 전 주문 수정·취소 · 반품 경고 {commerce.return_warning_percent}% · 유통기한 {commerce.expiry_days}일 이내 알림</p>}
    {commerce?.operations.filter(op=>selected?.api_ids.includes(op.id)&&access.can(op.actor_roles)).map(op=><form data-api={op.id} key={op.id} onSubmit={e=>{e.preventDefault();void invokeCommerce(op)}}>
      <h3>{op.title}</h3>
      {op.request_fields.filter(f=>f.name!=='lines_json').map(f=><label key={f.name} style={{display:'block',marginBlock:8}}>{labels[f.name]??f.name} {f.data_type==='boolean'?<select data-field={f.name} value={values[op.id+':'+f.name]??'false'} onChange={e=>setValues(v=>({...v,[op.id+':'+f.name]:e.target.value}))}><option value="false">아니오</option><option value="true">예</option></select>:<input data-field={f.name} required={!['barcode','note'].includes(f.name)} type={f.data_type==='date'?'date':'text'} value={values[op.id+':'+f.name]??''} onChange={e=>setValues(v=>({...v,[op.id+':'+f.name]:e.target.value}))}/>}</label>)}
      {op.request_fields.some(f=>f.name==='lines_json')&&<fieldset><legend>주문 상품</legend>
        {(orderLines[op.id]??[emptyLine()]).map((line,index)=><div key={index} style={{display:'flex',flexWrap:'wrap',gap:8,marginBottom:12}}>
          {(['product_id','unit','quantity','price'] as const).map(field=><label key={field}>{labels[field]}<input data-line={index+':'+field} required style={{display:'block',maxWidth:160}} value={line[field]} onChange={e=>setOrderLines(old=>({...old,[op.id]:(old[op.id]??[emptyLine()]).map((r,n)=>n===index?{...r,[field]:e.target.value}:r)}))}/></label>)}
          {index>0&&<button type="button" onClick={()=>setOrderLines(old=>({...old,[op.id]:old[op.id].filter((_,n)=>n!==index)}))}>상품 제외</button>}
        </div>)}
        <button type="button" disabled={(orderLines[op.id]?.length??1)>=50} onClick={()=>setOrderLines(old=>({...old,[op.id]:[...(old[op.id]??[emptyLine()]),emptyLine()]}))}>주문 상품 추가</button>
      </fieldset>}

      <button type="submit" disabled={busy||!token}>{op.title}</button>
    </form>)}
    {domain&&<CommandForms operations={domain.operations.filter(o=>selected?.api_ids.includes(o.id))} busy={busy} onBusy={setBusy} onError={setError} onResult={value=>{setLastDomain(null);setResult(value)}}/>}
    {domain?.operations.filter(o=>!['command','calculation'].includes(o.action)&&selected?.api_ids.includes(o.id)&&access.can(o.actor_roles)).map(op=><form data-api={op.id} key={op.id} onSubmit={e=>{e.preventDefault();void invokeDomain(op)}}>
      <h3>{op.label} · {({insert:'등록',list:'목록 조회',update:'수정',transition:'상태 변경'} as Record<string,string>)[op.action]}</h3>
      {op.action==='list'&&<label>목록 검색<input disabled={busy} maxLength={100} value={queries[op.id]??''} onChange={e=>{setQueries(v=>({...v,[op.id]:e.target.value}));setResult(null);setLastDomain(null);setPage(0)}}/></label>}
      {op.action!=='list'&&op.action!=='transition'&&domain&&<RelationPicker op={op} domain={domain} locked={!!locked[op.id]} onSelect={row=>setValues(v=>({...v,...Object.fromEntries(Object.entries(row).map(([k,value])=>[op.id+':'+k,String(value??'')]))}))}/>}
      {op.action!=='list'&&op.fields.filter(f=>op.action!=='transition'||f.primary).map(f=><label key={f.name} style={{display:'block',marginBlock:8}}>{f.label}{f.primary?' (키)':''} {f.data_type==='boolean'?<select data-field={f.name} required={f.required} disabled={op.action==='update'&&!!locked[op.id]&&f.primary} value={values[op.id+':'+f.name]??''} onChange={e=>setValues(v=>({...v,[op.id+':'+f.name]:e.target.value}))}><option value="">선택</option><option value="true">예</option><option value="false">아니오</option></select>:<input data-field={f.name} readOnly={op.action==='update'&&!!locked[op.id]&&f.primary} maxLength={f.length??undefined} required={f.required} type={f.data_type==='date'?'date':f.data_type==='datetime'?'datetime-local':'text'} value={values[op.id+':'+f.name]??''} onChange={e=>setValues(v=>({...v,[op.id+':'+f.name]:e.target.value}))}/>}</label>)}
      <button type="submit" disabled={busy||!token}>실행</button>
      {op.action==='update'&&locked[op.id]&&<button type="button" onClick={()=>{setLocked(v=>({...v,[op.id]:false}));setValues(v=>Object.fromEntries(Object.entries(v).filter(([k])=>!k.startsWith(op.id+':'))))}}>선택 해제</button>}
    </form>)}
    {operations.map(op => <form data-api={op.api_id} key={op.api_id} onSubmit={e => { e.preventDefault(); void invoke(op) }}>
      <h3>{actionNames[op.action]}</h3>
      {op.action === 'get' ? <label>{op.key.name} <input required value={values[op.api_id + ':key'] ?? ''} onChange={e => setValues(v => ({ ...v, [op.api_id + ':key']: e.target.value }))} /></label> : op.action === 'list' ? <p>기본키 순서로 최대 100건을 조회합니다.</p> : op.fields.map(f => <label key={f.id} style={{ display: 'block' }}>{f.name} {f.data_type === 'boolean' ? <select aria-label={f.name} required={f.required} value={values[op.api_id + ':' + f.name] ?? ''} onChange={e => setValues(v => ({ ...v, [op.api_id + ':' + f.name]: e.target.value }))}><option value="">선택</option><option value="true">예</option><option value="false">아니오</option></select> : <input required={f.required} type={f.data_type === 'integer' ? 'number' : 'text'} step="1" maxLength={f.length ?? undefined} value={values[op.api_id + ':' + f.name] ?? ''} onChange={e => setValues(v => ({ ...v, [op.api_id + ':' + f.name]: e.target.value }))} />}</label>)}
      <button disabled={busy || !token}>{actionNames[op.action]}</button>
    </form>)}
    {stock?.operations.filter(op => selected?.api_ids.includes(op.id)&&access.can(op.actor_roles)).map(op => <form data-api={op.id} key={op.id} onSubmit={e => { e.preventDefault(); void invokeStock(op) }}>
      <h3>{actionNames[op.action]}</h3>
      {op.path.includes('{key}') && <label>입출고 ID <input required value={values[op.id + ':key'] ?? ''} onChange={e => setValues(v => ({ ...v, [op.id + ':key']: e.target.value }))} /></label>}
      {op.request_fields.filter(f => f.name !== 'key').map(f => <label key={f.name} style={{ display: 'block' }}>{f.name} {f.name === 'kind' ? <select aria-label={f.name} required value={values[op.id + ':kind'] ?? ''} onChange={e => setValues(v => ({ ...v, [op.id + ':kind']: e.target.value }))}><option value="">선택</option><option value="receive">입고</option><option value="issue">출고</option></select> : <input required inputMode={f.data_type === 'decimal' ? 'decimal' : 'text'} value={values[op.id + ':' + f.name] ?? ''} onChange={e => setValues(v => ({ ...v, [op.id + ':' + f.name]: e.target.value }))} />}</label>)}
      <button disabled={busy || !token}>{actionNames[op.action]}</button>
    </form>)}
    {busy && <p role="status">{selected?.loading_state}</p>}
    {error && <p role="alert">{selected?.error_state}: {error}</p>}
    {commerce && result !== null && (JSON.parse((result as {result_json:string}).result_json) as {warning?:boolean}).warning && <p role="status">반품 금액이 월 구매 금액 대비 경고 비율을 초과했습니다.</p>}
    {result!==null&&lastDomain&&domain&&<section aria-label="조회 결과"><Records value={result} op={lastDomain} onEdit={domain.operations.some(o=>o.table_id===lastDomain.table_id&&o.action==='update'&&access.can(o.actor_roles))?row=>{const op=domain.operations.find(o=>o.table_id===lastDomain.table_id&&o.action==='update'&&access.can(o.actor_roles))!;setValues(v=>({...v,...Object.fromEntries(Object.entries(row).map(([k,value])=>[op.id+':'+k,String(value??'')]))}));setLocked(v=>({...v,[op.id]:true}));document.querySelector(`[data-api="${op.id}"]`)?.scrollIntoView({block:'start'});}:undefined}/>
      {lastDomain.action==='list'&&<div className="pager"><button disabled={busy||page===0} onClick={()=>void invokeDomain(lastDomain,page-20)}>이전 페이지</button><span>{page/20+1} 페이지</span><button disabled={busy||!Array.isArray(result)||result.length<=20} onClick={()=>void invokeDomain(lastDomain,page+20)}>다음 페이지</button></div>}</section>}
    {result!==null&&access.mode==='session'&&!lastDomain&&<p role="status">요청을 처리했습니다.</p>}
    {result !== null && <details open={access.mode!=='session'}><summary>응답 상세</summary><pre data-result style={{overflowWrap:"anywhere",whiteSpace:"pre-wrap"}}>{JSON.stringify(commerce ? JSON.parse((result as {result_json:string}).result_json) : result, null, 2)}</pre></details>}
  </main>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><CustomerAccess><App /></CustomerAccess></React.StrictMode>)

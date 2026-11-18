import React, { useState } from 'react'
import { message, useAccess } from './customer'

export type Field={name:string;label:string;column_id:string;data_type:string;required:boolean;primary:boolean;length?:number|null}
export type Operation={id:string;label:string;table_id:string;action:string;method:string;path:string;actor_roles:string[];fields:Field[]}
type Relation={id:string;table_id:string;columns:string[];parent_table_id:string;parent_columns:string[]}
export type Domain={operations:Operation[];foreign_keys:Relation[]}

export function RelationPicker({op,domain,onSelect,locked}:{op:Operation;domain:Domain;onSelect:(values:Record<string,unknown>)=>void;locked:boolean}){
  return <>{domain.foreign_keys.filter(f=>f.table_id===op.table_id).map(f=><Lookup key={f.id} relation={f} op={op} domain={domain} onSelect={onSelect} locked={locked}/>)}</>
}
function Lookup({relation,op,domain,onSelect,locked}:{relation:Relation;op:Operation;domain:Domain;onSelect:(values:Record<string,unknown>)=>void;locked:boolean}){
  const access=useAccess(),parent=domain.operations.find(o=>o.table_id===relation.parent_table_id&&o.action==='list')
  const [query,setQuery]=useState(''),[rows,setRows]=useState<Record<string,unknown>[]>([]),[offset,setOffset]=useState(0),[loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const fields=relation.columns.map(id=>op.fields.find(f=>f.column_id===id)!)
  if(!parent||!access.can(parent.actor_roles)||locked&&fields.some(f=>f.primary))return null
  async function load(start:number){setBusy(true);setError('')
    try{const r=await fetch('/api'+parent!.path+'?'+new URLSearchParams({q:query,limit:'21',offset:String(start)}),{headers:access.headers()});const data=await r.json()
      if(r.status===401)access.expired();if(!r.ok)throw Error(message(data));setRows(data);setOffset(start);setLoaded(true)
    }catch(e){setError(e instanceof Error?e.message:'연결 목록을 불러오지 못했습니다.')}finally{setBusy(false)}
  }
  return <fieldset className="relation"><legend>{parent.label} 선택</legend>
    <label>연결 데이터 검색<input maxLength={100} value={query} onChange={e=>{setQuery(e.target.value);setRows([]);setLoaded(false);setOffset(0)}}/></label>
    <button type="button" disabled={busy||!access.enabled} onClick={()=>void load(0)}>연결 목록 검색</button>
    {loaded&&<><select aria-label={parent.label+' 연결'} data-relation={relation.id} value="" onChange={e=>{if(e.target.value==='')return;const row=rows[Number(e.target.value)];onSelect(Object.fromEntries(fields.map((f,i)=>[f.name,row[parent.fields.find(p=>p.column_id===relation.parent_columns[i])!.name]])))}}>
      <option value="">{rows.length?'연결할 항목 선택':'검색 결과 없음'}</option>{rows.slice(0,20).map((row,i)=><option key={i} value={i}>{parent.fields.filter(f=>f.primary||f.data_type==='string').map(f=>String(row[f.name]??'')).join(' · ')}</option>)}</select>
      <button type="button" disabled={busy||offset===0} onClick={()=>void load(offset-20)}>연결 이전</button><button type="button" disabled={busy||rows.length<=20} onClick={()=>void load(offset+20)}>연결 다음</button></>}
    {busy&&<p role="status">연결 목록을 불러오는 중…</p>}{error&&<p role="alert">{error}</p>}
  </fieldset>
}

export function Records({value,op,onEdit}:{value:unknown;op:Operation;onEdit?:(row:Record<string,unknown>)=>void}){
  const rows=(Array.isArray(value)?value:[value]) as Record<string,unknown>[]
  if(!rows.length)return <p role="status">검색 결과가 없습니다.</p>
  return <div className="table-wrap"><table><caption>{op.label} 조회 결과</caption><thead><tr>{op.fields.map(f=><th key={f.name}>{f.label}</th>)}{onEdit&&<th>작업</th>}</tr></thead><tbody>{rows.slice(0,20).map((row,i)=><tr key={i}>{op.fields.map(f=><td key={f.name}>{row[f.name]===null?'—':typeof row[f.name]==='boolean'?(row[f.name]?'예':'아니오'):String(row[f.name]??'')}</td>)}{onEdit&&<td><button type="button" onClick={()=>onEdit(row)}>수정할 행 선택</button></td>}</tr>)}</tbody></table></div>
}

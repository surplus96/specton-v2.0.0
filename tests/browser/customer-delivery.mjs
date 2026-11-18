import http from 'node:http'
import fs from 'node:fs'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
const input=JSON.parse(fs.readFileSync(0,'utf8'))
const config=input.config,ops=config.domain.operations,table=input.parent,childTable=input.child
const server=http.createServer(async(req,res)=>{
  try{const chunks=[];for await(const chunk of req)chunks.push(chunk)
    const headers={...req.headers};delete headers.host
    const reply=await fetch('http://application:8080'+req.url,{method:req.method,headers,body:['GET','HEAD'].includes(req.method)?undefined:Buffer.concat(chunks),redirect:'manual'})
    res.writeHead(reply.status,{'content-type':reply.headers.get('content-type')??'text/plain',...(reply.headers.getSetCookie().length?{'set-cookie':reply.headers.getSetCookie()}:{}),'cache-control':'no-store'})
    res.end(Buffer.from(await reply.arrayBuffer()))
  }catch{res.writeHead(502);res.end('proxy failed')}
})
await new Promise(resolve=>server.listen(4173,'127.0.0.1',resolve))
const browser=await chromium.launch({headless:true,args:['--disable-dev-shm-usage']})
const page=await browser.newPage({viewport:{width:1360,height:960}})
page.setDefaultTimeout(10000)
const errors=[];page.on('pageerror',e=>errors.push(e.message))
const checks=[]
const operation=(name,action)=>ops.find(o=>o.table===name&&o.action===action)
async function form(op){const screen=config.screens.find(s=>s.api_ids.includes(op.id)&&s.actor_roles.includes('ROLE-user'));await page.locator(`[data-screen="${screen.id}"]`).click();return page.locator(`[data-api="${op.id}"]`)}
async function submit(f,op,status=200){const waiting=page.waitForResponse(r=>new URL(r.url()).pathname==='/api'+op.path&&r.request().method()===op.method);await f.locator('button[type=submit]').click();const reply=await waiting;assert.equal(reply.status(),status);return reply.json()}
async function login(username,password=input.password){await page.getByLabel('아이디',{exact:true}).fill(username);await page.getByLabel('비밀번호',{exact:true}).fill(password);await page.getByRole('button',{name:'로그인',exact:true}).click()}
async function raw(path,method='GET',body){return page.evaluate(async({path,method,body})=>{const session=await(await fetch('/api/auth/session')).json();const response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':session.user?.csrf??'','Idempotency-Key':crypto.randomUUID()},body:body?JSON.stringify(body):undefined});return {status:response.status,body:await response.json()}},{path,method,body})}
try{
  await page.goto('http://127.0.0.1:4173')
  await login('operator','incorrect');await page.getByRole('alert').waitFor();checks.push('invalid password rejected')
  await login('operator');await page.getByRole('button',{name:'로그아웃',exact:true}).waitFor()
  const cookie=(await page.context().cookies()).find(c=>c.name==='specton_customer_session')
  assert(cookie?.httpOnly);assert.equal(cookie.sameSite,'Strict')
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0)
  await page.reload();await page.getByRole('button',{name:'로그아웃',exact:true}).waitFor();checks.push('HttpOnly session survives reload without browser storage')
  const insert=operation(table,'insert'),list=operation(table,'list')
  let f=await form(insert)
  await f.locator('[data-field=id]').fill('M00');await f.locator('[data-field=name]').fill('고객 설비 00')
  assert.deepEqual(await submit(f,insert),{id:'M00',name:'고객 설비 00'})
  for(let i=1;i<25;i++)assert.equal((await raw(insert.path,'POST',{id:'M'+String(i).padStart(2,'0'),name:'고객 설비 '+String(i).padStart(2,'0')})).status,200)
  f=await form(list);await submit(f,list)
  assert.equal(await page.locator('tbody tr').count(),20)
  let wait=page.waitForResponse(r=>r.url().includes(list.path)&&r.url().includes('offset=20'))
  await page.getByRole('button',{name:'다음 페이지',exact:true}).click();await wait
  await page.getByText('2 페이지',{exact:true}).waitFor();assert.equal(await page.locator('tbody tr').count(),5)
  await f.getByLabel('목록 검색',{exact:true}).fill('설비 24');await submit(f,list)
  assert.equal(await page.locator('tbody tr').count(),1);assert.match(await page.locator('tbody').innerText(),/M24/)
  await f.getByLabel('목록 검색',{exact:true}).fill('no-result');await submit(f,list);await page.getByText('검색 결과가 없습니다.',{exact:true}).waitFor()
  checks.push('25 records, paging, search and empty state')
  const add=operation(childTable,'insert'),read=operation(childTable,'list'),update=operation(childTable,'update')
  f=await form(add)
  await f.getByRole('button',{name:'연결 목록 검색',exact:true}).click()
  await f.locator('[data-relation]').selectOption('0')
  assert.equal(await f.locator('[data-field=parent_id]').inputValue(),'M00')
  for(const [key,value] of Object.entries({sequence:'1',scheduled:'2026-11-16',status:'pending',amount:'12.50'}))await f.locator(`[data-field=${key}]`).fill(value)
  await f.locator('[data-field=parent_id]').fill('missing');await submit(f,add,409);await page.getByRole('alert').waitFor()
  await f.locator('[data-field=parent_id]').fill('M00');const record=await submit(f,add);assert.equal(record.amount,'12.50')
  f=await form(read);await submit(f,read)
  await page.getByRole('button',{name:'수정할 행 선택',exact:true}).click()
  f=page.locator(`[data-api="${update.id}"]`)
  assert.equal(await f.locator('[data-field=parent_id]').getAttribute('readonly'),'')
  assert.equal(await f.locator('[data-field=sequence]').getAttribute('readonly'),'')
  await f.locator('[data-field=amount]').fill('9.00');assert.equal((await submit(f,update)).amount,'9.00')
  checks.push('relation selection, failure retry, row edit with preserved composite key')
  await page.screenshot({path:'/out/customer-desktop.png',fullPage:true})
  await page.setViewportSize({width:390,height:844});await page.reload();await page.getByRole('button',{name:'로그아웃',exact:true}).waitFor()
  f=await form(read);await submit(f,read)
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
  await page.screenshot({path:'/out/customer-mobile.png',fullPage:true});checks.push('desktop and mobile layout')
  await page.getByRole('button',{name:'로그아웃',exact:true}).click();await page.getByLabel('아이디',{exact:true}).waitFor()
  assert.equal((await raw(list.path)).status,401)
  await login('reader');await page.getByRole('button',{name:'로그아웃',exact:true}).waitFor()
  assert.equal(await page.locator(`[data-api="${insert.id}"]`).count(),0)
  assert.equal((await raw(insert.path,'POST',{id:'forbidden',name:'거절'})).status,403)
  assert.equal((await raw(read.path)).body[0].amount,'9.00')
  checks.push('logout denies reuse; reader can read but cannot write')
  assert.deepEqual(errors,[])
  fs.writeFileSync('/out/report.json',JSON.stringify({status:'passed',checks,customer_auth:'real',database:'real',external_google:'not_used',external_llm:'not_used',records:25,child_amount:'9.00'},null,2))
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}

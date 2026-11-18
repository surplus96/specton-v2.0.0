import http from 'node:http'
import fs from 'node:fs'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const input=JSON.parse(fs.readFileSync(0,'utf8'))
const config=input.config,ops=config.domain.operations
const server=http.createServer(async(req,res)=>{
  try{
    const chunks=[];for await(const chunk of req)chunks.push(chunk)
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
const operation=(table,action)=>ops.find(o=>o.table===table&&o.action===action)
async function login(username){
  await page.getByLabel('아이디',{exact:true}).fill(username)
  await page.getByLabel('비밀번호',{exact:true}).fill(input.password)
  await page.getByRole('button',{name:'로그인',exact:true}).click()
  await page.getByRole('button',{name:'로그아웃',exact:true}).waitFor()
}
async function logout(){await page.getByRole('button',{name:'로그아웃',exact:true}).click();await page.getByLabel('아이디',{exact:true}).waitFor()}
async function raw(path,method='GET',body){return page.evaluate(async({path,method,body})=>{
  const session=await(await fetch('/api/auth/session')).json()
  const response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':session.user?.csrf??'','Idempotency-Key':crypto.randomUUID()},body:body?JSON.stringify(body):undefined})
  return {status:response.status,body:await response.json()}
},{path,method,body})}
const command=ops.find(o=>o.action==='command')
const form=page.locator(`[data-api="${command.id}"]`)
async function submit(status){
  const waiting=page.waitForResponse(r=>new URL(r.url()).pathname==='/api'+command.path&&r.request().method()==='POST')
  await form.getByRole('button',{name:'함께 실행·결과 확인',exact:true}).click()
  const reply=await waiting;assert.equal(reply.status(),status)
  const key=reply.request().headers()['idempotency-key'];assert(key)
  return {body:await reply.json(),key}
}
try{
  await page.goto('http://127.0.0.1:4173')
  await login('administrator')
  assert.equal((await raw(operation(input.parent,'insert').path,'POST',{id:'one',name:'fixture',amount:'5.00'})).status,200)
  await logout();await login('operator')
  const screen=config.screens.find(s=>s.api_ids.includes(command.id))
  await page.locator(`[data-screen="${screen.id}"]`).click()
  for(const [key,value] of Object.entries({id:'one',sequence:'1',scheduled:'2030-01-01',amount:'6.00'}))await form.locator(`[data-field=${key}]`).fill(value)
  const failed=await submit(409);assert.equal(failed.body.detail,'RULE_VIOLATION')
  await page.getByRole('alert').waitFor()
  checks.push('after-write condition failure shown in command form')
  await form.locator('[data-field=amount]').fill('2.00')
  const success=await submit(200);assert.deepEqual(success.body,{amount:'3.00',status:'posted'})
  assert.notEqual(success.key,failed.key)
  const replay=await submit(200);assert.deepEqual(replay,success)
  checks.push('corrected request succeeds; identical resubmission reuses committed key and result')
  assert.equal((await raw(operation(input.parent,'update').path,'POST',{id:'one',name:'bypass',amount:'100.00'})).status,403)
  checks.push('operator direct record write rejected by real session roles')
  await page.screenshot({path:'/out/command-desktop.png',fullPage:true})
  await page.setViewportSize({width:390,height:844})
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
  await page.screenshot({path:'/out/command-mobile.png',fullPage:true})
  await form.getByRole('button',{name:'새 요청 작성',exact:true}).click()
  assert.equal(await form.locator('[data-field=id]').inputValue(),'')
  checks.push('desktop/mobile form; new-request clears previous inputs')
  await logout();await login('administrator')
  assert.deepEqual((await raw(operation(input.parent,'list').path)).body,[{id:'one',name:'fixture',amount:'3.00'}])
  assert.deepEqual((await raw(operation(input.child,'list').path)).body,[{parent_id:'one',sequence:1,scheduled:'2030-01-01',status:'posted',amount:'2.00'}])
  checks.push('real DB shows one committed change and one history row after failure and retry')
  assert.deepEqual(errors,[])
  fs.writeFileSync('/out/report.json',JSON.stringify({status:'passed',checks,customer_auth:'real',database:'real',external_google:'not_used',external_llm:'not_used'},null,2))
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}

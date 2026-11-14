// Produce a self-contained, opaque-origin iframe. All network access goes through the owner bridge.
import fs from 'node:fs'
const root='/workspace/frontend/dist'
const index=fs.readFileSync(root+'/index.html','utf8')
const match=index.match(/src="([^"]+\.js)"/)
if (!match) throw Error('Missing bundle')
const script=fs.readFileSync(root+'/'+match[1].replace(/^\.\//,''),'utf8')
const bootstrap=`window.spectonPreview=true;const pending=new Map();let serial=0;
window.fetch=(path,options={})=>new Promise((resolve,reject)=>{const id=++serial;
const timer=setTimeout(()=>{pending.delete(id);reject(Error('미리보기 요청 시간 초과'))},15000);
pending.set(id,{resolve,reject,timer});parent.postMessage({type:'specton-preview-request',id,path:String(path),method:options.method||'GET',body:options.body||null,command_key:options.headers?.['Idempotency-Key']||null},'*')});
addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='specton-preview-response')return;
const entry=pending.get(event.data.id);if(!entry)return;clearTimeout(entry.timer);pending.delete(event.data.id);
entry.resolve(new Response(event.data.body,{status:event.data.status,headers:{'Content-Type':'application/json'}}))});`
const html=`<!doctype html><html lang="ko"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"><div id="root"></div><script>${bootstrap}</script><script type="module">${script.replace(/<\/script/gi,tag=>tag.replace('/','\\/'))}</script></html>`
fs.writeFileSync('/workspace/preview.html',html)

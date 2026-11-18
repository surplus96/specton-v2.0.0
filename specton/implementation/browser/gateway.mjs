// Fixed upstream only. This trusted gateway is the only container with a loopback-published port.
import http from 'node:http'
import crypto from 'node:crypto'
const token=Buffer.from('Bearer '+process.env.PREVIEW_TOKEN)
const server=http.createServer(async(req,res)=>{
  const auth=Buffer.from(req.headers.authorization??'')
  if(auth.length!==token.length||!crypto.timingSafeEqual(auth,token)){res.writeHead(403);res.end('{}');return}
  if(!['GET','POST','PATCH'].includes(req.method)||!req.url.startsWith('/')||req.url.startsWith('//')){res.writeHead(400);res.end('{}');return}
  try{
    const chunks=[];let size=0
    for await(const chunk of req){size+=chunk.length;if(size>16384)throw Error('body limit');chunks.push(chunk)}
    const reply=await fetch('http://application:8000'+req.url,{method:req.method,redirect:'error',signal:AbortSignal.timeout(5000),
      headers:{Authorization:req.headers.authorization,'Content-Type':'application/json','Idempotency-Key':req.headers['idempotency-key']??''},
      body:req.method==='GET'?undefined:Buffer.concat(chunks)})
    const data=await reply.text();if(data.length>256*1024)throw Error('response limit')
    res.writeHead(reply.status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(data)
  }catch{res.writeHead(502);res.end('{}')}
})
server.listen(8000,'0.0.0.0')
setTimeout(()=>process.exit(0),1020*1000).unref()

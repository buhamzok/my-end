"use client";import {useEffect,useState} from "react";
const API=process.env.NEXT_PUBLIC_API||"http://localhost:8000";
export default function Page(){
 const [t,setT]=useState<any[]>([]);
 const load=()=>fetch(`${API}/api/tickets`).then(r=>r.json()).then(setT);
 useEffect(()=>{load();const i=setInterval(load,3000);return()=>clearInterval(i)},[]);
 const close=(id:number)=>fetch(`${API}/api/tickets/${id}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:"closed"})}).then(load);
 return(<main style={{fontFamily:"system-ui",padding:24,maxWidth:900,margin:"0 auto"}}>
  <h1>Clinic / CHW Dashboard — sorted by urgency</h1>
  <p>Human closes every ticket. Rules engine decides tier, not LLM.</p>
  <table border={1} cellPadding={8} style={{width:"100%",borderCollapse:"collapse"}}>
   <thead><tr><th>ID</th><th>Tier</th><th>Caller</th><th>Symptoms</th><th>Reason</th><th>Status</th><th></th></tr></thead>
   <tbody>{t.map(x=><tr key={x.id} style={{background:x.tier==="emergency"?"#fdd":x.tier==="urgent"?"#ffd":"#dfd"}}>
    <td>{x.id}</td><td><b>{x.tier}</b></td><td>{x.caller}</td><td>{x.symptoms}</td><td>{x.reason}</td><td>{x.status}</td>
    <td>{x.status==="open"&&<button onClick={()=>close(x.id)}>Close</button>}</td></tr>)}</tbody>
  </table></main>);
}

const fallbackMethods=[
  {id:'impulse',name:'DataImpulse',description:'Sticky port range scanner',configured:false,fields:['proxy_username','proxy_password','proxy_host','proxy_mode','country','city','asn','start_port','end_port','target_prefix','max_workers','request_timeout','execution_duration','batch_delay'],defaults:{proxy_host:'gw.dataimpulse.com',proxy_mode:'combined',country:'az',city:'baku',asn:'',start_port:10000,end_port:20000,target_prefix:'185.30.88.',max_workers:2,request_timeout:5,execution_duration:200,batch_delay:.25}},
  {id:'oxy',name:'Oxylabs',description:'Sequential session rotation',configured:false,fields:['proxy_username','proxy_password','proxy_host','proxy_port','proxy_mode','country','city','asn','session_prefix','session_minutes','start_session','target_prefix','max_workers','request_timeout','execution_duration','batch_delay'],defaults:{proxy_host:'pr.oxylabs.io',proxy_port:7777,proxy_mode:'location',country:'tr',city:'',asn:9121,session_prefix:'t01q',session_minutes:30,start_session:1,target_prefix:'88.230.184.',max_workers:25,request_timeout:5,execution_duration:200,batch_delay:.25}},
  {id:'royale',name:'IPRoyal',description:'Random sticky SOCKS sessions',configured:false,fields:['proxy_username','proxy_password','proxy_host','proxy_port','proxy_scheme','country','city','session_prefix','session_minutes','target_prefix','max_workers','request_timeout','execution_duration','batch_delay'],defaults:{proxy_host:'geo.iproyal.com',proxy_port:32325,proxy_scheme:'socks5',country:'az',city:'baku',session_prefix:'m18m',session_minutes:30,target_prefix:'185.30.88.',max_workers:25,request_timeout:5,execution_duration:200,batch_delay:.25}}
];
const state={methods:fallbackMethods,jobs:{},results:[],sort:{key:'timestamp',dir:-1},backendOnline:false};
const $=s=>document.querySelector(s), esc=s=>String(s??'').replaceAll('\u2014','-').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={proxy_username:'Username',proxy_password:'Password',proxy_host:'Proxy host',proxy_port:'Proxy port',proxy_mode:'Target mode',proxy_scheme:'Protocol',country:'Country',city:'City',asn:'ASN',start_port:'Start port',end_port:'End port',session_prefix:'Session prefix',session_minutes:'Session lifetime',start_session:'Start session',target_prefix:'Target IP prefix',max_workers:'Workers',request_timeout:'Request timeout',execution_duration:'Duration (sec)',batch_delay:'Batch delay'};
const numeric=new Set(['proxy_port','asn','start_port','end_port','session_minutes','start_session','max_workers','request_timeout','execution_duration','batch_delay']);
function field(method,name){
  const value=method.defaults[name]??'',id=`${method.id}-${name}`;
  const type=numeric.has(name)?'number':name==='proxy_password'?'password':'text';
  const label=`<label for="${id}">${labels[name]}`;
  if(name==='proxy_mode'){
    const opts=method.id==='impulse'?['combined','location','asn']:['location','asn'];
    return `<div class="field">${label}</label><select id="${id}" name="${name}">${opts.map(x=>`<option ${x===value?'selected':''}>${x}</option>`)}</select></div>`;
  }
  if(name==='proxy_scheme')return `<div class="field">${label}</label><select id="${id}" name="${name}"><option>socks5</option><option ${value==='socks5h'?'selected':''}>socks5h</option></select></div>`;
  const secret=name==='proxy_username'||name==='proxy_password',optional=['asn','city','country'].includes(name);
  const placeholder=optional?'Opsional':secret&&method.configured?'Kosongkan untuk memakai kredensial tersimpan':'Required';
  return `<div class="field ${['proxy_username','proxy_password','target_prefix'].includes(name)?'wide':''}">${label}${optional?' (opsional)':''}</label><input id="${id}" name="${name}" type="${type}" value="${secret?'':esc(value)}" placeholder="${placeholder}" ${type==='number'?'step="any"':''} ${secret?`autocomplete="${name==='proxy_password'?'current-password':'username'}"`:''}></div>`;
}
function renderCards(){
  $('#cards').innerHTML=state.methods.map(m=>`<article class="card" id="card-${m.id}" aria-labelledby="title-${m.id}">
    <div class="card-head"><div><div class="method-id">${esc(m.protocol||(m.id==='royale'?'SOCKS5':'HTTP'))}</div><h3 id="title-${m.id}">${esc(m.name)}</h3><p>${esc(m.description)}</p></div><span class="badge" data-status>Idle</span></div>
    <div class="method-body"><details><summary>Konfigurasi pencarian<span class="sr-only"> ${esc(m.name)}</span></summary><form class="form" aria-label="${esc(m.name)} configuration">${m.fields.map(n=>field(m,n)).join('')}</form></details>
    <div class="progress" role="progressbar" aria-label="${esc(m.name)} search progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i></i></div><div class="job-message" role="status">${m.configured?'Kredensial tersimpan. Siap untuk mencari.':'Buka konfigurasi untuk mengisi kredensial.'}</div></div>
    <div class="controls"><button data-start onclick="runMethod('${m.id}')" aria-label="Start search ${esc(m.name)}">Start search</button><button data-cancel class="secondary danger" onclick="cancelMethod('${m.id}')" aria-label="Cancel ${esc(m.name)} search" disabled>Cancel</button></div></article>`).join('');
  document.querySelectorAll('.form').forEach(form=>form.addEventListener('submit',event=>{event.preventDefault();runMethod(form.closest('.card').id.replace('card-',''));}));
}
function cardError(card,message){
  const label=card.querySelector('.job-message');label.textContent=message;label.classList.add('error');show(message);
}
async function runMethod(id){
  const card=$(`#card-${id}`),start=card.querySelector('[data-start]');
  if(start.disabled)return;
  const config=Object.fromEntries(new FormData(card.querySelector('form')).entries());
  start.disabled=true;start.textContent='Starting...';card.querySelector('.job-message').classList.remove('error');
  try{
    const r=await fetch(`/api/methods/${id}/run`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config})}),d=await r.json();
    if(!r.ok)throw Error(d.error||`HTTP ${r.status}`);
    state.jobs[id]=d;setBackendStatus(true);updateCard(d);collect();poll();
  }catch(e){
    cardError(card,state.backendOnline?e.message:'Backend sedang offline. Tampilan ini hanya mode pratinjau.');
    const badge=card.querySelector('[data-status]');badge.textContent=state.backendOnline?'Error':'Offline';badge.className='badge failed';
    card.querySelector('details').open=true;start.disabled=false;
  }finally{start.textContent='Start search';}
}
async function cancelMethod(id){
  const j=state.jobs[id];if(!j)return;
  const card=$(`#card-${id}`),button=card.querySelector('[data-cancel]');button.disabled=true;button.textContent='Cancelling...';
  try{
    const r=await fetch(`/api/jobs/${j.id}/cancel`,{method:'POST'}),d=await r.json();
    if(!r.ok)throw Error(d.error||`HTTP ${r.status}`);
    state.jobs[id]=d;updateCard(d);collect();
  }catch(e){cardError(card,e.message);button.disabled=false;}
  finally{button.textContent='Cancel';}
}
function updateCard(j){
  const card=$(`#card-${j.method}`),active=['queued','running'].includes(j.status),badge=card.querySelector('[data-status]');
  badge.textContent=j.status;badge.className=`badge ${j.status}`;
  const progress=Math.max(0,Math.min(100,j.progress||0));
  card.querySelector('.progress i').style.transform=`scaleX(${progress/100})`;
  card.querySelector('.progress').setAttribute('aria-valuenow',progress);
  const message=card.querySelector('.job-message');message.classList.toggle('error',j.status==='failed');
  message.textContent=`${j.message} (${j.elapsed||0}s, ${j.results.length} IP)`;
  card.querySelector('[data-start]').disabled=active;card.querySelector('[data-cancel]').disabled=!active||j.cancel_requested;
}
let polling=false;
async function poll(){
  if(polling)return;polling=true;
  try{
    while(Object.values(state.jobs).some(j=>['queued','running'].includes(j.status))){
      await new Promise(r=>setTimeout(r,state.backendOnline?700:2000));
      try{
        const response=await fetch('/api/jobs');if(!response.ok)throw Error(`HTTP ${response.status}`);
        const jobs=await response.json();if(!Array.isArray(jobs))throw Error('Respons job tidak valid');
        setBackendStatus(true);
        jobs.forEach(j=>{if(state.jobs[j.method]?.id===j.id){state.jobs[j.method]=j;updateCard(j);}});collect();
      }catch{
        setBackendStatus(false);
        Object.values(state.jobs).filter(j=>['queued','running'].includes(j.status)).forEach(j=>{
          const message=$(`#card-${j.method} .job-message`);message.textContent='Koneksi terputus. Mencoba menghubungkan kembali...';message.classList.add('error');
        });
      }
    }
  }finally{polling=false;collect();}
}
function collect(){state.results=Object.values(state.jobs).flatMap(j=>j.results||[]);renderRows();$('#runningCount').textContent=Object.values(state.jobs).filter(j=>['queued','running'].includes(j.status)).length;$('#foundCount').textContent=state.results.filter(r=>!['not_found','not_match'].includes(r.status_code)).length;$('#updatedAt').textContent=new Date().toLocaleTimeString('id-ID')}
function visible(){let q=$('#search').value.toLowerCase(),a=state.results.filter(r=>Object.values(r).join(' ').toLowerCase().includes(q)),{key,dir}=state.sort;return a.sort((x,y)=>String(x[key]??'').localeCompare(String(y[key]??''),undefined,{numeric:true})*dir)}
function renderRows(){
  const rows=visible();$('#resultCount').textContent=`${rows.length} ${rows.length===1?'entry':'entries'}`;
  $('#copyAll').disabled=!rows.length;$('#exportCsv').disabled=!rows.length;
  $('#rows').innerHTML=rows.length?rows.map(r=>`<tr><td class="ip">${esc(r.ip)}</td><td>${esc(r.port==='\u2014'?r.session:r.port)}</td><td>${esc(r.protocol)}</td><td class="${r.status_code==='complete'?'status-ok':''}">${esc(r.status)}</td><td>${esc(r.source)}<small>ASN: ${esc(r.asn||'Data tidak tersedia')}<br>City: ${esc(r.city||'Data tidak tersedia')} / Country: ${esc(r.country||'Data tidak tersedia')}</small></td><td>${esc(r.latency??'Data tidak tersedia')}</td><td>${new Date(r.timestamp).toLocaleString('id-ID')}</td><td><button class="secondary copy" data-copy="${esc(r.ip)}">Copy</button></td></tr>`).join(''):`<tr><td colspan="8" class="empty"><strong>${state.results.length?'No matching results.':'Your search starts here.'}</strong><span>${state.results.length?'Coba kata pencarian lain atau kosongkan filter.':'Atur konfigurasi provider, lalu pilih Start search untuk menemukan IP.'}</span></td></tr>`;
  $('#rows').querySelectorAll('[data-copy]').forEach(button=>button.onclick=()=>copyText(button.dataset.copy));
}
async function copyText(t){try{await navigator.clipboard.writeText(t);show('Copied to clipboard');}catch{show('Clipboard tidak tersedia. Salin IP secara manual.');}}
function show(t){let e=$('#toast');e.textContent=t;e.classList.add('show');setTimeout(()=>e.classList.remove('show'),2200)}
$('#search').addEventListener('input',renderRows);document.querySelectorAll('th[data-sort]').forEach(th=>th.querySelector('button').onclick=()=>{let key=th.dataset.sort;state.sort={key,dir:state.sort.key===key?-state.sort.dir:1};document.querySelectorAll('th[data-sort]').forEach(cell=>cell.setAttribute('aria-sort',cell.dataset.sort===key?(state.sort.dir===1?'ascending':'descending'):'none'));renderRows()});$('#copyAll').onclick=()=>copyText(visible().map(r=>r.port==='\u2014'?r.ip:`${r.ip}:${r.port}`).join('\n'));$('#exportCsv').onclick=()=>{let cols=['ip','port','protocol','status','source','latency','timestamp','city','isp','session'],csv=[cols.join(','),...visible().map(r=>cols.map(c=>`"${String(r[c]??'').replaceAll('"','""')}"`).join(','))].join('\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));a.download='proxy-results.csv';a.click();URL.revokeObjectURL(a.href)};
function setBackendStatus(online){state.backendOnline=online;let live=$('.live');live.classList.toggle('offline',!online);live.innerHTML=`<i></i> Integration server ${online?'online':'offline · preview mode'}`}
renderCards();
renderRows();
$('#methodCount').textContent=state.methods.length;
fetch('/api/methods').then(r=>{if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json()}).then(m=>{if(!Array.isArray(m)||!m.length)throw Error('Respons metode tidak valid');state.methods=m;state.backendOnline=true;renderCards();$('#methodCount').textContent=m.length;setBackendStatus(true)}).catch(()=>setBackendStatus(false));

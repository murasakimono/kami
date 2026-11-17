"""Kami Deck telefon sayfasi (/deck): Stream Deck benzeri tus izgarasi + profil duzenleme + uzaktan indirme yonetimi."""

DECK_HTML = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="theme-color" content="#0D0A14">
<title>Kami Deck</title>
<style>
:root{--bg:#0D0A14;--card:#171222;--card2:#211932;--line:#2E2346;--tx:#EDE9F6;--mut:#9A90AB;--ac:#9D6BFF;--ok:#2EE6A6;--bad:#FF4D6A}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:radial-gradient(circle at top,#1C132D 0%,var(--bg) 60%);color:var(--tx);font:15px "Segoe UI Variable",system-ui,-apple-system,sans-serif;padding:env(safe-area-inset-top) 14px calc(92px + env(safe-area-inset-bottom))}
header{display:flex;align-items:center;gap:10px;padding:12px 0}
header h1{font-size:19px;margin:0;flex:1;letter-spacing:.03em}header h1 b{color:var(--ac)}
button,select,input{font:inherit;color:var(--tx);background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;min-height:44px}
button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--ac);outline-offset:2px}
button:active{transform:translateY(1px) scale(.97)}
.tabs{display:flex;gap:8px;overflow-x:auto;padding-bottom:10px;scrollbar-width:none}
.tabs button{white-space:nowrap;min-height:40px;padding:7px 14px;border-radius:999px;font-weight:600;font-size:13.5px}
.tabs button.on{background:var(--ac);border-color:var(--ac);color:#fff;box-shadow:0 4px 16px rgba(157,107,255,.35)}
.grid{display:grid;gap:11px;margin-top:6px}
.key{aspect-ratio:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;border-radius:18px;
 background:linear-gradient(165deg,var(--card2),var(--card));border:1px solid var(--line);font-size:12px;text-align:center;padding:8px;
 box-shadow:0 6px 0 #08050D,0 10px 20px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.12);user-select:none;position:relative;overflow:hidden;cursor:pointer;transition:transform .08s,box-shadow .08s}
.key:active{transform:translateY(3px) scale(.97);box-shadow:0 2px 0 #08050D,0 4px 10px rgba(0,0,0,.45)}
.key i{font-style:normal;font-size:28px;line-height:1;filter:drop-shadow(0 2px 6px rgba(0,0,0,.4))}
.key span{color:var(--tx);font-weight:600;font-size:11.5px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:.9}
.key.ok{box-shadow:0 0 0 2px var(--ok),0 0 20px rgba(46,230,166,.35)}
.key.err{box-shadow:0 0 0 2px var(--bad),0 0 20px rgba(255,77,106,.35)}
.edit .key:not(.add){animation:wob .32s infinite alternate}@keyframes wob{from{transform:rotate(-1.2deg)}to{transform:rotate(1.2deg)}}
.key .x{position:absolute;top:5px;right:7px;color:var(--bad);font-size:16px;display:none;background:rgba(13,10,20,.8);width:22px;height:22px;border-radius:50%;line-height:22px}.edit .key .x{display:block}
.add{border-style:dashed;background:rgba(255,255,255,.02);box-shadow:none;color:var(--mut)}
nav{position:fixed;left:0;right:0;bottom:0;display:flex;background:rgba(13,10,20,.94);backdrop-filter:blur(10px);border-top:1px solid var(--line);
 padding:8px 12px calc(8px + env(safe-area-inset-bottom))}
nav button{flex:1;margin:0 4px;border:0;background:none;color:var(--mut);min-height:44px;font-weight:600}
nav button.on{color:var(--ac)}
.dl{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin:10px 0;display:grid;gap:8px}
.dl-top{display:flex;gap:12px;align-items:center}
.dl-ring{width:42px;height:42px;flex-shrink:0;position:relative;display:grid;place-items:center}
.dl-ring svg{transform:rotate(-90deg)}
.dl-ring b{position:absolute;font-size:10px;color:var(--tx)}
.dl-meta{flex:1;min-width:0}
.dl .t{font-size:14px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dl .m{font-size:12px;color:var(--mut);margin-top:2px}
.dl .b{display:flex;gap:8px;flex-wrap:wrap}
.dl .b button{min-height:44px;min-width:44px;padding:0 14px;font-size:14px;font-weight:600;flex:1}
.sheet{position:fixed;inset:0;background:rgba(5,4,8,.72);display:none;align-items:flex-end;z-index:9}.sheet.on{display:flex}
.sheet>div{background:var(--card);width:100%;max-height:82vh;overflow:auto;border-radius:20px 20px 0 0;padding:16px;border-top:1px solid var(--line)}
.cat{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.cat .key{font-size:11px;box-shadow:0 3px 0 #08050D}.cat .key i{font-size:22px}
h3{margin:14px 0 6px;font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
#msg{position:fixed;left:50%;bottom:96px;transform:translateX(-50%);background:#0B0812ee;border:1px solid var(--ac);padding:9px 16px;border-radius:999px;font-size:13px;display:none;z-index:20}
.row{display:flex;gap:8px;align-items:center;margin:8px 0}.row input{flex:1;min-width:0}
</style></head><body>
<header><h1>Kami <b>Deck</b></h1><button id="bEdit" aria-label="Düzenle">✎</button></header>
<div id="keyBox" class="row" style="display:none"><input id="k" placeholder="Anahtar (Kami > Ayarlar > Telefon)"><button id="kOk">Kaydet</button></div>
<section id="pDeck"><div class="tabs" id="tabs"></div><div class="grid" id="grid"></div></section>
<section id="pDl" hidden>
 <div class="row"><button id="pa">⏸ Hepsi</button><button id="ra">▶ Hepsi</button>
 <select id="lim" aria-label="Hız sınırı"><option value="0">Sınırsız</option><option value="512">512 KB/s</option><option value="1024">1 MB/s</option>
 <option value="2048">2 MB/s</option><option value="5120">5 MB/s</option><option value="10240">10 MB/s</option></select></div>
 <div id="dls"></div>
 <h3>Link ekle</h3><div class="row"><input id="url" placeholder="https://…"><button id="addUrl">Ekle</button></div>
</section>
<nav><button class="on" data-p="pDeck">🎛 Deck</button><button data-p="pDl">⬇ İndirmeler</button></nav>
<div class="sheet" id="sheet"><div id="sheetIn"></div></div><div id="msg"></div>
<script>
const $=i=>document.getElementById(i);let D=null,P=0,EDIT=false,tmr=0;
const EN=(navigator.language||'tr').startsWith('en');
const L=(tr,en)=>EN?en:tr;
const key=()=>localStorage.kamiKey||new URLSearchParams(location.search).get('k')||'';
if(new URLSearchParams(location.search).get('k'))localStorage.kamiKey=new URLSearchParams(location.search).get('k');
const msg=(t,ms=1600)=>{const m=$('msg');m.textContent=t;m.style.display='block';clearTimeout(m._t);m._t=setTimeout(()=>m.style.display='none',ms)};
async function post(path,body={}){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Kami-Key':key()},body:JSON.stringify(body)});
 if(r.status===401){$('keyBox').style.display='flex';throw new Error(L('anahtar','key'))}return r.json()}
const catOf=a=>D.catalog.find(c=>c.id===a)||{label:a,icon:'•'};
function save(){post('/deck/save',{profiles:D.profiles,cols:D.cols}).then(r=>{D.profiles=r.profiles;D.cols=r.cols}).catch(()=>{})}
function render(){
 const t=$('tabs');t.innerHTML='';D.profiles.forEach((p,i)=>{const b=document.createElement('button');b.textContent=p.name;b.className=i===P?'on':'';
  b.onclick=()=>{if(!EDIT||i!==P){P=i;render();return}const n=prompt(L('Profil adı','Profile name'),p.name);if(n===null)return;if(!n){if(D.profiles.length>1&&confirm(L('Profili sil?','Delete profile?'))){D.profiles.splice(i,1);P=0}}else p.name=n;save();render()};t.appendChild(b)});
 if(EDIT&&!document.getElementById('hint')){const h=document.createElement('div');h.id='hint';h.style.cssText='font-size:12px;color:var(--mut);margin:4px 0';h.textContent=L('Düzenleme: profile dokun → yeniden adlandır · tuşa dokun → düzenle · ✕ sil · sürükle → sırala','Edit: tap profile → rename · tap key → edit · ✕ delete · drag → reorder');$('pDeck').insertBefore(h,$('grid'))}
 if(!EDIT)document.getElementById('hint')?.remove();
 if(EDIT){const b=document.createElement('button');b.textContent=L('+ Profil','+ Profile');b.onclick=()=>{D.profiles.push({name:L('Yeni','New'),buttons:[]});P=D.profiles.length-1;save();render()};t.appendChild(b);
  const c=document.createElement('select');[2,3,4,5,6].forEach(n=>{const o=new Option(n+' '+L('sütun','cols'),n);o.selected=n===D.cols;c.appendChild(o)});c.onchange=()=>{D.cols=+c.value;save();render()};t.appendChild(c)}
 const g=$('grid');g.className='grid'+(EDIT?' edit':'');g.style.gridTemplateColumns=`repeat(${D.cols||4},1fr)`;g.innerHTML='';
 const prof=D.profiles[P]||{buttons:[]};
 prof.buttons.forEach((b,i)=>{const c=catOf(b.a),k=document.createElement('button');k.type='button';k.className='key';if(b.color)k.style.background=b.color;
  k.innerHTML=`<b class="x">✕</b><i></i><span></span>`;k.querySelector('i').textContent=b.icon||c.icon;k.querySelector('span').textContent=b.label||c.label;
  k.onclick=e=>{if(EDIT){if(e.target.classList.contains('x')){prof.buttons.splice(i,1);save();render()}else pick(i);return}fire(b,k)};
  if(EDIT){k.draggable=true;k.ondragstart=e=>e.dataTransfer.setData('i',i);k.ondragover=e=>e.preventDefault();
   k.ondrop=e=>{const f=+e.dataTransfer.getData('i');const [m]=prof.buttons.splice(f,1);prof.buttons.splice(i,0,m);save();render()}}
  g.appendChild(k)});
 if(EDIT){const a=document.createElement('button');a.type='button';a.className='key add';a.innerHTML='<i>＋</i><span>'+L('Tuş ekle','Add key')+'</span>';a.onclick=()=>pick(-1);g.appendChild(a)}
}
async function fire(b,el){navigator.vibrate?.(15);
 try{const r=await post('/deck/run',{a:b.a,arg:b.arg||''});el.classList.add(r.ok?'ok':'err');if(!r.ok)msg('✕ '+(r.error||L('olmadı','failed')),2600)}
 catch(e){el.classList.add('err');msg('✕ '+e.message)}setTimeout(()=>el.classList.remove('ok','err'),500)}
function pick(i){const prof=D.profiles[P],cur=i>=0?prof.buttons[i]:null,groups={};D.catalog.forEach(c=>(groups[c.group]=groups[c.group]||[]).push(c));
 let h='';for(const[g,list]of Object.entries(groups)){h+=`<h3>${g}</h3><div class="cat">`+list.map(c=>`<button type="button" class="key" data-a="${c.id}"><i>${c.icon}</i><span>${c.label}</span></button>`).join('')+'</div>'}
 $('sheetIn').innerHTML=(cur?`<div class="row"><input id="eL" placeholder="${L('Etiket','Label')}" value="${(cur.label||'').replace(/"/g,'&quot;')}"><input id="eI" placeholder="${L('Simge','Icon')}" style="max-width:74px" value="${cur.icon||''}"></div>
  <div class="row"><input id="eA" placeholder="${catOf(cur.a).arg||L('argüman yok','no arg')}" value="${(cur.arg||'').replace(/"/g,'&quot;')}"><input id="eC" type="color" value="${cur.color||'#171222'}" style="max-width:60px"><button id="eS">${L('Kaydet','Save')}</button></div>
  <div class="row"><button id="eL1">◀ ${L('Sola','Left')}</button><button id="eR1">${L('Sağa','Right')} ▶</button></div>`:'')+h;
 $('sheet').classList.add('on');
 if(cur)$('eS').onclick=()=>{cur.label=$('eL').value;cur.icon=$('eI').value;cur.arg=$('eA').value;cur.color=$('eC').value==='#171222'?'':$('eC').value;save();close();render()};
 const mv=d=>{const j=i+d;if(j<0||j>=prof.buttons.length)return;[prof.buttons[i],prof.buttons[j]]=[prof.buttons[j],prof.buttons[i]];save();close();render()};
 if(cur){$('eL1').onclick=()=>mv(-1);$('eR1').onclick=()=>mv(1)}
 $('sheetIn').querySelectorAll('.cat .key').forEach(k=>k.onclick=()=>{const c=catOf(k.dataset.a);let arg='';
  if(c.arg){arg=prompt(c.label+': '+c.arg,cur?.arg||'');if(arg===null)return}
  const nb={a:c.id,arg};if(cur)Object.assign(cur,nb,{label:'',icon:''});else prof.buttons.push(nb);save();close();render()})}
const close=()=>$('sheet').classList.remove('on');$('sheet').onclick=e=>{if(e.target.id==='sheet')close()};
$('bEdit').onclick=()=>{EDIT=!EDIT;$('bEdit').textContent=EDIT?'✓':'✎';render()};
$('kOk').onclick=()=>{localStorage.kamiKey=$('k').value.trim();$('keyBox').style.display='none';load()};
function dlRing(pct){const p=Math.min(100,Math.max(0,+pct||0)),c=2*Math.PI*16;
 return `<div class="dl-ring"><svg width="42" height="42" viewBox="0 0 42 42"><circle cx="21" cy="21" r="16" fill="none" stroke="#241B33" stroke-width="4"/><circle cx="21" cy="21" r="16" fill="none" stroke="${p>=100?'#2EE6A6':'#9D6BFF'}" stroke-width="4" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c*(1-p/100)).toFixed(1)}" stroke-linecap="round"/></svg><b>${Math.round(p)}%</b></div>`}
function renderDl(list){$('dls').innerHTML='';if(!list.length){$('dls').innerHTML=`<p style="color:var(--mut)">${L('İndirme yok.','No downloads.')}</p>`;return}
 for(const d of list){const e=document.createElement('div');e.className='dl';const pct=d.percent||0;
  e.innerHTML=`<div class="dl-top">${dlRing(pct)}<div class="dl-meta"><div class="t"></div><div class="m"></div></div></div><div class="b"></div>`;
  e.querySelector('.t').textContent=d.name||('#'+d.id);e.querySelector('.m').textContent=d.label||'';
  const B=e.querySelector('.b'),btn=(t,a,x={})=>{const b=document.createElement('button');b.textContent=t;b.onclick=async()=>{
   if(a==='remove'&&!confirm(L('Listeden kaldırılsın mı?','Remove from list?')))return;const r=await post('/dl/action',{id:d.id,action:a,...x});if(r.downloads)renderDl(r.downloads);else msg(r.ok?'✓':'✕')};B.appendChild(b)};
  if(d.can_pause)btn('⏸','pause');if(d.can_resume)btn('▶','resume');if(d.can_top)btn('⇡ '+L('Öne','Top'),'top');btn('✕','remove');$('dls').appendChild(e)}}
async function load(){try{D=await post('/deck/data');if(P>=D.profiles.length)P=0;render();renderDl(D.downloads||[]);$('lim').value=String(D.limit||0)}catch(e){}}
async function pollDl(){if($('pDl').hidden)return;try{const r=await post('/deck/data');renderDl(r.downloads||[])}catch(e){}}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x===b));
 ['pDeck','pDl'].forEach(p=>$(p).hidden=p!==b.dataset.p);clearInterval(tmr);if(b.dataset.p==='pDl'){pollDl();tmr=setInterval(pollDl,2000)}});
$('pa').onclick=()=>post('/deck/run',{a:'dl:pause_all'}).then(pollDl);$('ra').onclick=()=>post('/deck/run',{a:'dl:resume_all'}).then(pollDl);
$('lim').onchange=()=>post('/deck/run',{a:'dl:limit',arg:$('lim').value}).then(r=>msg(r.ok?'✓ '+L('Hız sınırı','Speed limit'):'✕'));
$('addUrl').onclick=async()=>{const u=$('url').value.trim();if(!u)return;const r=await fetch('/send',{method:'POST',headers:{'Content-Type':'application/json','X-Kami-Key':key()},body:JSON.stringify({text:u})}).then(r=>r.json());
 msg(r.message||(r.ok?'✓':'✕'),2600);if(r.ok){$('url').value='';setTimeout(pollDl,800)}};
if(!key())$('keyBox').style.display='flex';else load();
</script></body></html>"""

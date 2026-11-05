'use strict';
/* Archipelago Game Hub - shared game catalog and round planning frontend. */
const $ = id => document.getElementById(id);
const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const s = {data:null,tab:'library',round:'',authMode:'login',query:'',genre:'',poll:null};
let toastTimeout;
function toast(message,bad=false){
  const t=$('toast');t.textContent=message;t.classList.remove('hidden');t.classList.toggle('error',bad);
  clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>t.classList.add('hidden'),5000);
}
async function api(path,config={}){
  const opts={credentials:'same-origin',...config,headers:{...(config.headers||{})}};
  if(opts.body && !(opts.body instanceof FormData)){
    opts.headers['Content-Type']='application/json';
    if(typeof opts.body!=='string')opts.body=JSON.stringify(opts.body);
  }
  if(['POST','DELETE','PUT','PATCH'].includes(opts.method)&&s.data?.csrf) opts.headers['X-CSRF-Token']=s.data.csrf;
  let response;
  try{response=await fetch(path,opts);}catch(e){throw new Error('Server nicht erreichbar: '+e.message);}
  const type=response.headers.get('Content-Type')||'';
  const body=type.includes('application/json')?await response.json():await response.text();
  if(!response.ok)throw new Error(body?.error||'HTTP-Fehler '+response.status);
  return body;
}
async function refresh(){
  try{
    const d=await api('/api/state');
    s.data=d;
    $('auth').classList.add('hidden');$('shell').classList.remove('hidden');
    document.body.classList.toggle('is-admin',!!d.user.admin);
    $('userName').textContent=d.user.username;$('roleBadge').textContent=d.user.admin?'HOST':'SPIELER';
    $('sideStatus').textContent=d.config.generator_available?'Generator verbunden':'Generator nicht verbunden';
    if(!d.rounds.some(r=>r.id===s.round))s.round=d.rounds[0]?.id||'';
    render();
  }catch(e){
    if(/anmelden|401/.test(e.message)){s.data=null;$('auth').classList.remove('hidden');$('shell').classList.add('hidden');}
    else toast(e.message,true);
  }
}
function tab(next){
  s.tab=next;
  document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===next));
  document.querySelectorAll('[data-view]').forEach(v=>v.classList.toggle('hidden',v.dataset.view!==next));
  $('crumb').textContent=({library:'SPIELEBIBLIOTHEK',round:'MEINE RUNDE',seed:'SEED & HOSTING',setup:'INSTALLATION'})[next];
}
const round=()=>s.data?.rounds.find(r=>r.id===s.round);
const game=id=>s.data?.games.find(g=>g.id===id);
const pick=()=>s.data?.picks.find(p=>p.round_id===s.round&&p.user_id===s.data.user.id);
const editable=g=>s.data&&(s.data.user.admin||s.data.user.id===g.author_id);
const picks=()=>s.data?.picks.filter(p=>p.round_id===s.round)||[];
function card(g){
  const cover=g.has_cover?'<img loading="lazy" src="/api/games/'+g.id+'/cover" alt="'+esc(g.title)+'">':
    '<div class="cover-fallback">'+esc(g.title.slice(0,1).toUpperCase())+'</div>';
  const selected=pick()?.game_id===g.id;
  const flags=g.has_apworld?'Custom APWorld':'In Archipelago integriert*';
  const disable=s.round?'':' disabled title="Host muss zuerst eine Runde erstellen"';
  return '<article class="game-card"><div class="cover">'+cover+'</div><div class="game-card-body">'+
    '<h3>'+esc(g.title)+'</h3><div class="meta">'+esc(g.genre||g.ap_game)+'</div>'+
    '<p>'+esc(g.description||'YAML-Vorlage und Setup-Informationen vorhanden.')+'</p>'+
    '<span class="note-pill">'+flags+'</span><div class="card-actions">'+
    '<button class="btn '+(selected?'secondary':'primary')+'" data-action="pick" data-id="'+g.id+'"'+disable+'>'+
    (selected?'✓ Ausgewählt':'＋ Auswählen')+'</button>'+
    '<button class="ghost" data-action="detail" data-id="'+g.id+'">Details</button>'+
    (editable(g)?'<button class="ghost" data-action="edit" data-id="'+g.id+'">✎</button>':'')+
    '</div></div></article>';
}
function renderLibrary(){
  const d=s.data;if(!d)return;
  $('gameCount').textContent=d.games.length+' SPIELE';
  const genres=[...new Set(d.games.map(x=>x.genre).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'de'));
  $('genreFilter').innerHTML='<option value="">Alle Genres</option>'+genres.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');
  $('genreFilter').value=s.genre;
  const list=d.games.filter(g=>(!s.genre||g.genre===s.genre)&&(!s.query||[g.title,g.genre,g.ap_game,g.description].join(' ').toLowerCase().includes(s.query)));
  $('gameGrid').innerHTML=list.length?list.map(card).join(''):'<div class="empty"><b>Keine Spiele gefunden</b>Suche ändern oder Spiel hinzufügen.</div>';
}
function renderRound(){
  const d=s.data;if(!d)return;
  $('roundSelect').innerHTML=d.rounds.length?d.rounds.map(r=>'<option value="'+r.id+'">'+esc(r.title)+'</option>').join(''):'<option value="">Noch keine Runde</option>';
  $('roundSelect').value=s.round;
  $('roundName').textContent=round()?.title||'Noch keine Runde';
  $('roomUrl').value=round()?.room_url||'';
  $('playersList').innerHTML=!s.round?'<div class="empty">Der Host muss zunächst eine Runde erstellen.</div>':
    d.players.map(u=>{
      const p=d.picks.find(x=>x.round_id===s.round&&x.user_id===u.id);
      const g=p&&game(p.game_id),own=u.id===d.user.id;
      const selection=own?'<select class="player-select" data-own-pick aria-label="Spiel wählen"><option value="">Spiel auswählen</option>'+
        d.games.map(x=>'<option value="'+x.id+'" '+(x.id===p?.game_id?'selected':'')+'>'+esc(x.title)+'</option>').join('')+
        '</select>':'<span class="status">'+(g?'Gewählt':'Offen')+'</span>';
      return '<div class="player-row"><div class="avatar">'+esc(u.username.charAt(0).toUpperCase())+'</div>'+
        '<div class="player-name"><strong>'+esc(u.username)+'</strong><small>'+(own?'Du':u.admin?'Host':'Mitspieler')+'</small></div>'+
        '<div class="player-pick">'+(g?'<div class="pick-name">'+esc(g.title)+'</div><div class="pick-sub">'+esc(g.ap_game)+' · Slot: '+esc(u.username)+'</div>':
        '<div class="pick-empty">Noch keine Auswahl</div>')+'</div>'+selection+'</div>';
    }).join('');
  $('roundProgress').textContent=picks().length+' VON '+d.players.length;
  $('downloadBundle').disabled=!s.round||!picks().length;
  $('toSeed').disabled=!s.round;
}
function renderSeed(){
  if(!s.data)return;
  $('seedSummary').innerHTML=round()?(picks().map(p=>{
    const u=s.data.players.find(u=>u.id===p.user_id),g=game(p.game_id);
    return '<div class="seed-item"><strong>'+esc(u?.username||'?')+'</strong><small>'+esc(g?.title||'?')+(g?.has_apworld?' · Custom APWorld':'')+'</small></div>';
  }).join('')||'<div class="warning">Noch keine Spiele ausgewählt.</div>'):'<div class="warning">Erstelle zuerst eine Runde.</div>';
  $('generateBtn').disabled=!round()||!picks().length||!s.data.config.generator_available||!!s.data.generation_active;
  $('archipelagoDir').value=s.data.config.archipelago_dir||'';
  $('generatorStatus').textContent=s.data.config.generator_available?'Verbunden mit '+s.data.config.archipelago_dir:'Generator nicht gefunden. Bitte Archipelago installieren und Pfad angeben.';
  $('roomLinkView').innerHTML=round()?.room_url?'<a target="_blank" rel="noopener noreferrer" href="'+esc(round().room_url)+'">↗ Raum öffnen</a>':'';
  const builds=s.data.builds.filter(b=>b.round_id===s.round);
  $('buildList').innerHTML=builds.length?builds.map(b=>{
    return '<div class="build-row"><div><strong>'+new Date(b.created*1000).toLocaleString('de-DE')+'</strong> <span class="status '+esc(b.status)+'">'+esc(b.status)+'</span></div><div class="build-info">'+
      '<button class="btn secondary" data-action="log" data-id="'+b.id+'">Protokoll</button>'+
      (b.status==='success'?'<a class="btn primary" href="/api/builds/'+b.id+'/download">↓ Seed-ZIP</a>':'')+'</div></div>';
  }).join(''):'<div class="empty">Noch keine Seed-Generierung.</div>';
  if(s.data.generation_active&&!s.poll){s.poll=setInterval(async()=>{await refresh();if(!s.data?.generation_active){clearInterval(s.poll);s.poll=null;}},3500);}
  if(!s.data.generation_active&&s.poll){clearInterval(s.poll);s.poll=null;}
}
function renderSetup(){
  if(!s.data)return;
  $('setupList').innerHTML=picks().length?picks().map(p=>{
    const u=s.data.players.find(x=>x.id===p.user_id),g=game(p.game_id);if(!g)return '';
    return '<article class="setup-card"><div class="eyebrow">'+esc(u?.username||'')+' · '+esc(g.ap_game)+'</div>'+
      '<h2>'+esc(g.title)+'</h2><p>'+esc(g.description||'')+'</p>'+
      (g.guide?'<div class="guide-text">'+esc(g.guide)+'</div>':'<div class="warning">Noch keine Setup-Anleitung vorhanden.</div>')+
      '<div class="setup-links">'+(g.setup_url?'<a class="btn secondary" target="_blank" rel="noopener noreferrer" href="'+esc(g.setup_url)+'">↗ Setup-Guide</a>':'')+
      (g.mod_url?'<a class="btn secondary" target="_blank" rel="noopener noreferrer" href="'+esc(g.mod_url)+'">↗ Mod/Client</a>':'')+
      '</div></article>';
  }).join(''):'<div class="empty">Wähle zuerst ein Spiel in der Runde.</div>';
}
function render(){renderLibrary();renderRound();renderSeed();renderSetup();tab(s.tab);}
function editGame(g){
  const f=$('gameForm');f.reset();
  $('gameId').value=g?.id||'';$('modalTitle').textContent=g?'Spiel bearbeiten':'Neues Spiel hinzufügen';
  ['title','genre','description','guide','setup_url','mod_url'].forEach(k=>{f.elements.namedItem(k).value=g?.[k]||'';});
  f.elements.namedItem('yaml').required=!g;
  $('removeFiles').classList.toggle('hidden',!g);
  $('gameModal').showModal();
}
function details(g){
  $('detailsTitle').textContent=g.title;
  $('detailsBody').innerHTML=(g.has_cover?'<div class="detail-cover"><img src="/api/games/'+g.id+'/cover" alt="'+esc(g.title)+'"></div>':'')+
  '<p>'+esc(g.description||'Keine Beschreibung.')+'</p><p class="tiny">World: '+esc(g.ap_game)+'</p>'+
  (g.warning?'<div class="warning">'+esc(g.warning)+'</div>':'')+
  '<h3>Einrichtung</h3>'+(g.guide?'<div class="guide-text">'+esc(g.guide)+'</div>':'<div class="warning">Keine Anleitung hinterlegt.</div>')+
  '<div class="detail-actions">'+(g.setup_url?'<a class="btn secondary" href="'+esc(g.setup_url)+'" target="_blank" rel="noopener noreferrer">Setup</a>':'')+
  (g.mod_url?'<a class="btn secondary" href="'+esc(g.mod_url)+'" target="_blank" rel="noopener noreferrer">Mod</a>':'')+
  (editable(g)?'<button class="btn secondary" data-action="edit" data-id="'+g.id+'">Bearbeiten</button><button class="btn secondary" data-action="delete" data-id="'+g.id+'">Löschen</button>':'')+'</div>';
  $('detailsModal').showModal();
}
async function fileData(file,max){
  if(!file)return null;
  if(file.size>max)throw new Error(file.name+' ist zu groß.');
  const data=await new Promise((resolve,reject)=>{
    const reader=new FileReader();reader.onerror=()=>reject(new Error('Datei konnte nicht gelesen werden.'));
    reader.onload=()=>resolve(reader.result);reader.readAsDataURL(file);
  });
  return {name:file.name,data:String(data).split(',')[1]};
}
async function saveGame(event){
  event.preventDefault();
  const f=$('gameForm'),id=$('gameId').value,payload={};
  for(const k of ['title','genre','description','guide','setup_url','mod_url'])payload[k]=f.elements.namedItem(k).value;
  for(const [kind,max] of [['yaml',512*1024],['apworld',20*1024*1024],['cover',3*1024*1024]]){
    payload[kind]=await fileData(f.elements.namedItem(kind).files[0],max);
  }
  payload.remove_apworld=f.elements.namedItem('remove_apworld').checked;
  payload.remove_cover=f.elements.namedItem('remove_cover').checked;
  try{
    await api(id?'/api/games/'+id:'/api/games',{method:'POST',body:payload});
    $('gameModal').close();toast('Spiel für alle Mitspieler gespeichert.');await refresh();
  }catch(e){toast(e.message,true);}
}
async function choose(id){
  if(!s.round){toast('Host muss zuerst eine Runde erstellen.',true);return;}
  try{await api('/api/picks',{method:'POST',body:{round_id:s.round,game_id:id}});await refresh();toast('Auswahl gespeichert.');}
  catch(e){toast(e.message,true);}
}
async function clickAction(event){
  const target=event.target.closest('[data-action]');if(!target)return;
  const action=target.dataset.action,id=target.dataset.id,g=game(id);
  try{
    if(action==='pick')return choose(id);
    if(action==='detail'&&g)return details(g);
    if(action==='edit'&&g){$('detailsModal').close();return editGame(g);}
    if(action==='delete'&&g){
      if(!confirm('Spiel "'+g.title+'" wirklich löschen?'))return;
      await api('/api/games/'+id,{method:'DELETE'});$('detailsModal').close();await refresh();return toast('Spiel gelöscht.');
    }
    if(action==='log'){
      const log=await api('/api/builds/'+id+'/log');
      $('detailsTitle').textContent='Generator-Protokoll';
      $('detailsBody').innerHTML='<p>Status: '+esc(log.status)+'</p><pre>'+esc(log.log||'Noch keine Ausgabe')+'</pre>';
      $('detailsModal').showModal();
    }
  }catch(e){toast(e.message,true);}
}
function authMode(next){
  s.authMode=next;
  $('loginToggle').classList.toggle('active',next==='login');
  $('registerToggle').classList.toggle('active',next==='register');
  $('authSubmit').textContent=next==='login'?'Anmelden':'Konto erstellen';
  $('joinWrap').classList.toggle('hidden',next!=='register');
}
function bind(){
  document.querySelectorAll('[data-tab]').forEach(x=>x.addEventListener('click',()=>tab(x.dataset.tab)));
  document.body.addEventListener('click',clickAction);
  $('search').addEventListener('input',e=>{s.query=e.target.value.toLowerCase();renderLibrary();});
  $('genreFilter').addEventListener('change',e=>{s.genre=e.target.value;renderLibrary();});
  $('addBtn').addEventListener('click',()=>editGame(null));
  $('gameForm').addEventListener('submit',saveGame);
  $('closeModal').addEventListener('click',()=>$('gameModal').close());
  $('cancelModal').addEventListener('click',()=>$('gameModal').close());
  $('closeDetails').addEventListener('click',()=>$('detailsModal').close());
  $('roundSelect').addEventListener('change',e=>{s.round=e.target.value;render();});
  $('playersList').addEventListener('change',e=>{if(e.target.matches('[data-own-pick]'))choose(e.target.value);});
  $('newRound').addEventListener('click',async()=>{
    const name=prompt('Name für die neue Runde:','Archipelago '+new Date().toLocaleDateString('de-DE'));
    if(name===null)return;
    try{const r=await api('/api/rounds',{method:'POST',body:{title:name}});s.round=r.id;await refresh();tab('round');toast('Runde erstellt.');}catch(e){toast(e.message,true);}
  });
  $('downloadBundle').addEventListener('click',()=>{if(s.round)location.href='/api/rounds/'+s.round+'/bundle';});
  $('toSeed').addEventListener('click',()=>tab('seed'));
  $('generateBtn').addEventListener('click',async()=>{
    try{
      const custom=picks().some(p=>game(p.game_id)?.has_apworld);
      if(custom&&!$('apConsent').checked)throw new Error('Bitte die Custom-APWorlds vorab prüfen und bestätigen.');
      if(!confirm('Seed für '+picks().length+' Spieler generieren?'))return;
      await api('/api/rounds/'+s.round+'/generate',{method:'POST',body:{approve_custom_worlds:custom&&$('apConsent').checked}});
      toast('Seed-Generierung gestartet.');await refresh();
    }catch(e){toast(e.message,true);}
  });
  $('saveRoomBtn').addEventListener('click',async()=>{
    try{await api('/api/rounds/'+s.round+'/room',{method:'POST',body:{url:$('roomUrl').value}});await refresh();toast('Raumlink gespeichert.');}catch(e){toast(e.message,true);}
  });
  $('saveDir').addEventListener('click',async()=>{
    try{await api('/api/settings',{method:'POST',body:{directory:$('archipelagoDir').value}});await refresh();toast('Generatorpfad gespeichert.');}catch(e){toast(e.message,true);}
  });
  $('logoutBtn').addEventListener('click',async()=>{
    try{await api('/api/auth/logout',{method:'POST',body:{}});}catch(e){}
    s.data=null;await refresh();
  });
  $('loginToggle').addEventListener('click',()=>authMode('login'));
  $('registerToggle').addEventListener('click',()=>authMode('register'));
  $('authForm').addEventListener('submit',async event=>{
    event.preventDefault();const f=event.target;
    try{
      await api('/api/auth/'+s.authMode,{method:'POST',body:{
        username:f.elements.namedItem('username').value,password:f.elements.namedItem('password').value,
        join_code:f.elements.namedItem('join_code').value
      }});
      f.reset();await refresh();
    }catch(e){toast(e.message,true);}
  });
}
bind();refresh();

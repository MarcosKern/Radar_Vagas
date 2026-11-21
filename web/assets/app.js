'use strict';
// Radar de vagas v9.1 — event handlers explicitamente vinculados, sem onclick embutido.
const $=id=>document.getElementById(id);
const escapeHTML=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let db={jobs:[],runs:[],settings:{},scan:{},ai:{}},activePage='dashboard',editingId=null,managingId=null,sourceDraft={},tagDraft={},menuDraft=[],titleDraft={},pollTimer=null,latestAISeen='',executionList=[],selectedExecutionId=null,lastExecutionStatus={},toasts=[],exclusionDraft={},exclusionCustomDraft=[],activeConfigTab='rules';
const STATUS=['Nova','Salva','Candidatada','Triagem','Entrevista','Teste técnico','Proposta','Aprovada','Rejeitada','Descartada'];
const APPLICATION_STATUSES=['Candidatada','Triagem','Entrevista','Teste técnico','Proposta','Aprovada','Rejeitada'];
const DEFAULT_BRAND='Radar de vagas';
const STATUS_RANK={Nova:0,Salva:1,Candidatada:2,Triagem:3,Entrevista:4,'Teste técnico':5,Proposta:6,Aprovada:7,Rejeitada:1,Descartada:0};
const PAGE_DEFAULTS={dashboard:['Visão geral','Acompanhe oportunidades e candidaturas em um só lugar.'],vagas:['Oportunidades','Explore vagas encontradas nas fontes e cadastradas manualmente.'],candidaturas:['Candidaturas','Anotações, etapas, contatos e próximos acompanhamentos.'],bloqueados:['Vagas bloqueadas','Oportunidades bloqueadas de novas buscas e alertas; reative quando quiser.'],config:['Fontes e filtros','Personalize fontes, termos, identidade visual e busca com IA.'],relatorios:['Histórico de buscas','Transparência sobre coletas, duplicatas e falhas.']};
const SOURCES=[
 {label:'Brasil e agregadores',items:[['gupy','Gupy','Vagas de empresas brasileiras (endpoint não oficial)'],['adzuna','Adzuna','Agregador no Brasil (requer APP_ID e APP_KEY)'],['arbeitnow','Arbeitnow','Feed internacional aberto de vagas']]},
 {label:'Remoto internacional',items:[['himalayas','Himalayas','Pesquisa de empregos remotos'],['jobicy','Jobicy','Feed público de vagas remotas'],['remotive','Remotive','Anúncios remotos globais'],['remoteok','Remote OK','Feed internacional de oportunidades'],['weworkremotely','We Work Remotely','Feed RSS oficial']]},
 {label:'Plataformas de recrutamento (ATS)',items:[['greenhouse','Greenhouse','Consulta boards cadastrados'],['lever','Lever','Consulta empresas cadastradas'],['ashby','Ashby','Consulta boards cadastrados'],['smartrecruiters','SmartRecruiters','Consulta empresas cadastradas'],['workable','Workable','Consulta boards cadastrados'],['recruitee','Recruitee','Consulta empresas cadastradas']]},
];
const TAGS=[
 ['gupy_queries','Buscas no Brasil','Cargos e temas usados na Gupy (até 40)'],
 ['remote_queries','Buscas internacionais','Cargos em inglês para fontes remotas (até 40)'],
 ['blocked_companies','Empresas bloqueadas','Empresas que não devem aparecer nas coletas'],
 ['local_cities','Cidades preferenciais','Municípios usados no filtro regional'],
 ['greenhouse_boards','Greenhouse — empresas','slug | Nome da empresa'],
 ['lever_boards','Lever — empresas','slug | Nome da empresa'],
 ['ashby_boards','Ashby — empresas','slug | Nome da empresa'],
 ['smartrecruiters_boards','SmartRecruiters — empresas','slug | Nome da empresa'],
 ['workable_boards','Workable — empresas','slug | Nome da empresa'],
 ['recruitee_boards','Recruitee — empresas','slug | Nome da empresa'],
];
const EXCLUSION_PRESETS=[
 ['senior','Sênior / Senior / Sr.','Senior Cloud Engineer'],
 ['pleno','Pleno / Mid-level / Intermediate','Analista de Infraestrutura Pleno'],
 ['lead','Lead / Tech Lead / Líder','Tech Lead'],
 ['staff','Staff / Principal','Staff Engineer'],
 ['manager','Gerente / Manager / Diretor','Engineering Manager'],
 ['architect','Architect / Arquiteto','Cloud Architect'],
 ['intern','Estágio / Internship','Estagiário de TI'],
 ['junior','Júnior / Entry-level','Junior Analyst']
];
const DEFAULT_EXCLUSION_LEVELS=Object.fromEntries(EXCLUSION_PRESETS.map(([k])=>[k,!['intern','junior'].includes(k)]));
const DEFAULT_EXCLUSION_TERMS=['Tech Lead','Head of','Coordinator'];
function showConfigTab(tab){
 const available=['rules','exclusions','sources','terms','ai','resume','appearance','backup','updates'];
 if(!available.includes(tab))tab='rules';
 activeConfigTab=tab;
 document.querySelectorAll('[data-config-tab]').forEach(btn=>{
  const selected=btn.dataset.configTab===tab;
  btn.classList.toggle('active',selected);btn.setAttribute('aria-selected',String(selected));
 });
 document.querySelectorAll('[data-config-panel]').forEach(panel=>{panel.hidden=panel.dataset.configPanel!==tab});
}
function initExclusions(){
 const cfg=db.settings||{};
 exclusionDraft={...DEFAULT_EXCLUSION_LEVELS,...(cfg.exclude_seniority||{})};
 exclusionCustomDraft=[...(cfg.exclude_custom_terms||DEFAULT_EXCLUSION_TERMS)];
 renderExclusions();
}
function renderExclusions(){
 const grid=$('excludeLevelGrid');if(!grid)return;
 grid.innerHTML=EXCLUSION_PRESETS.map(([key,label,example])=>`<label class="exclusion-item ${exclusionDraft[key]?'is-selected':''}"><input type="checkbox" data-exclusion-level="${key}" ${exclusionDraft[key]?'checked':''}><span class="exclusion-item-content"><strong>${escapeHTML(label)}</strong><small>${escapeHTML(example)}</small></span><span class="exclusion-state">${exclusionDraft[key]?'EXCLUIR':'PERMITIR'}</span></label>`).join('');
 const custom=$('excludedTerms');
 custom.innerHTML=exclusionCustomDraft.length?exclusionCustomDraft.map((term,i)=>`<span class="exclusion-chip"><span>${escapeHTML(term)}</span><button type="button" data-exclusion-remove="${i}" aria-label="Remover ${escapeHTML(term)}" title="Remover expressão">×</button></span>`).join(''):'<span class="exclusion-empty">Nenhum termo adicional cadastrado.</span>';
 $('exclusionCustomCount').textContent=`${exclusionCustomDraft.length}/40 termos`;const count=Object.values(exclusionDraft).filter(Boolean).length;
 $('exclusionSummary').textContent=`${count} ${count===1?'categoria ativa':'categorias ativas'} · ${exclusionCustomDraft.length} termos`;
}
function addExclusionTerm(){
 const input=$('exclusionCustomInput');const term=input.value.trim();if(!term)return;
 if(term.length>65||term.length<2){showToast('Use um termo de 2 a 65 caracteres.','warning');return}
 if(exclusionCustomDraft.length>=40){showToast('Limite de 40 expressões atingido.','warning');return}
 if(!exclusionCustomDraft.some(x=>x.toLocaleLowerCase()===term.toLocaleLowerCase()))exclusionCustomDraft.push(term);
 input.value='';renderExclusions();input.focus();
}
async function previewExclusion(ev){
 ev.preventDefault();const title=$('exclusionPreviewTitle').value.trim();if(!title)return;
 const result=$('exclusionPreviewResult');result.textContent='Validando regras...';
 try{const data=await api('exclusions/preview','POST',{title,company:$('exclusionPreviewCompany').value.trim(),exclude_seniority:exclusionDraft,exclude_custom_terms:exclusionCustomDraft});result.className=data.excluded?'preview-excluded':'preview-allowed';result.textContent=data.excluded?`Excluída · ${data.reason.reason} (${data.reason.where.toLowerCase()})`:'Permitida · nenhuma exclusão identificada';}
 catch(e){result.className='preview-excluded';result.textContent='Não foi possível testar: '+e.message}
}
const MAN_FIELDS={title:'manTitle',company:'manCompany',url:'manUrl',location:'manLocation',mode:'manMode',level:'manLevel',salary:'manSalary',published:'manPublished',eligible:'manEligible',status:'manStatus',followup:'manFollowup',notes:'manNotes',description:'manDescription',contract_type:'manContract',recruiter:'manRecruiter'};
async function api(path,method='GET',data=null){
 const options={method,headers:{'Accept':'application/json'}};
 if(data!==null){options.headers['Content-Type']='application/json';options.body=JSON.stringify(data)}
 const r=await fetch('/api/'+path,options);let value;try{value=await r.json()}catch(_){throw Error('Resposta inesperada do servidor ('+r.status+')')}
 if(!r.ok||value?.ok===false)throw Object.assign(Error(value.error||value.message||'Falha HTTP '+r.status),{existing_id:value.existing_id});return value;
}
function status(msg,error=false){const e=$('alertLine');e.textContent=msg;e.classList.toggle('error',Boolean(error))}
function showPage(name){
 if(!PAGE_DEFAULTS[name])name='dashboard';
 activePage=name;
 document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id==='page-'+name));
 document.querySelectorAll('.navlink').forEach(x=>x.classList.toggle('active',x.dataset.page===name));
 $('pageTitle').textContent=db.settings?.ui_titles?.[name]||PAGE_DEFAULTS[name][0];
 $('pageSubtitle').textContent=PAGE_DEFAULTS[name][1];
 if(name==='config')fillSettings();
 if(name==='vagas')renderJobs();
 if(name==='bloqueados')renderBlocked();
 if(name==='candidaturas')renderApplications();
 closeMenu();
}
function renderNav(){
 const menu=(db.settings?.ui_menu||[]);
 const nav=$('sideNav');
 for(const spec of menu){
  const element=Array.from(nav.querySelectorAll('[data-page]')).find(n=>n.dataset.page===spec.id);
  if(!element)continue;
  const icon=element.querySelector('span');const badge=element.querySelector('em');
  element.replaceChildren(icon,document.createTextNode(' '+spec.label+' '));
  if(badge)element.append(badge);
  element.hidden=(!spec.visible && !['config','bloqueados'].includes(spec.id));
  nav.append(element);
 }
 $('brandTitle').textContent=(db.settings?.ui_brand||DEFAULT_BRAND).toUpperCase();
 document.title=(db.settings?.ui_brand||DEFAULT_BRAND)+' · '+(db.settings?.ui_titles?.[activePage]||PAGE_DEFAULTS[activePage][0]);
 $('pageTitle').textContent=db.settings?.ui_titles?.[activePage]||PAGE_DEFAULTS[activePage][0];
 const profileName=(db.settings?.profile_name||db.settings?.resume_profile?.full_name||'').trim();
 const userName=document.querySelector('.sidebar-bottom b');
 const avatar=document.querySelector('.sidebar-bottom .userdot');
 if(userName)userName.textContent=profileName||'Perfil não configurado';
 if(avatar)avatar.textContent=profileName?profileName.split(/\s+/).slice(0,2).map(x=>x[0]||'').join('').toUpperCase():'RV';
}
function openMenu(){$('sidebar').classList.add('open');$('scrim').classList.add('visible')}
function closeMenu(){$('sidebar').classList.remove('open');$('scrim').classList.remove('visible')}
function fillOptions(){for(const id of ['manStatus','manageStatus','statusFilter','appliedStatus']){const s=$(id),prev=s.value;s.innerHTML=(['statusFilter','appliedStatus'].includes(id)?'<option value="all">Todas as etapas</option>':'')+STATUS.map(x=>`<option value="${escapeHTML(x)}">${escapeHTML(x)}</option>`).join('');if(prev&&[...s.options].some(o=>o.value===prev))s.value=prev}}
function isApplied(j){return APPLICATION_STATUSES.includes(j.status)}
function dateFmt(x){if(!x)return 'Data não informada';const d=new Date(String(x).slice(0,10)+'T12:00:00Z');return Number.isNaN(d.getTime())?'Data não informada':d.toLocaleDateString('pt-BR',{timeZone:'UTC'})}
function statusRank(status){return STATUS_RANK[status]??0}
function nextApplicationStage(status){const order=['Candidatada','Triagem','Entrevista','Teste técnico','Proposta'];const i=order.indexOf(status);if(i===-1)return null;return order[i+1]||null}
function safeJobUrl(raw){
 try{
  const parsed=new URL(String(raw||'').trim());
  return ['http:','https:'].includes(parsed.protocol)?parsed.href:'';
 }catch(_){return ''}
}
function renderJob(j,context='default'){
 const skills=(j.skills||[]).slice(0,4);
 const tags=[j.mode,j.status,j.source,...skills].filter(Boolean);
 const score=Math.max(0,Math.min(100,Number(j.score)||0));
 const blockBtn=j.ignored?`<button class="btn btn-outline-light" type="button" data-action="restore" data-id="${escapeHTML(j.id)}" aria-label="Reativar ${escapeHTML(j.title)}">↻ Reativar</button>`:`<button class="btn btn-danger-subtle" type="button" data-action="block" data-id="${escapeHTML(j.id)}" aria-label="Bloquear ${escapeHTML(j.title)}">⊘ Bloquear</button>`;
 const nextStage=nextApplicationStage(j.status);
 const quickActions=context==='applied'?`<button class="btn btn-outline-light" type="button" data-action="advance" data-id="${escapeHTML(j.id)}" ${!nextStage?'disabled':''}>⇢ Avançar etapa</button><button class="btn btn-danger-subtle" type="button" data-action="reject" data-id="${escapeHTML(j.id)}" ${j.status==='Rejeitada'?'disabled':''}>✕ Registrar rejeição</button>`:'';
 const url=safeJobUrl(j.url);
 const urlSection=url?`<div class="job-linkline"><span class="job-link-label">Link da vaga</span><a class="job-link" href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer" title="${escapeHTML(url)}">${escapeHTML(url)}</a></div>`:'<div class="job-linkline job-link-empty"><span class="job-link-label">Link da vaga</span><span>Não informado</span></div>';
 const openBtn=url?`<a class="btn btn-outline-light" target="_blank" rel="noopener noreferrer" href="${escapeHTML(url)}" aria-label="Abrir anúncio de ${escapeHTML(j.title)}">↗ Abrir vaga</a>`:'<button class="btn btn-outline-light" type="button" disabled title="Este registro não possui URL de anúncio">↗ Abrir vaga</button>';
 const applied=APPLICATION_STATUSES.includes(j.status);
 const canApply=['Nova','Salva'].includes(j.status)&&!j.ignored;
 const applyButton=context!=='applied'?`<button class="btn btn-primary" type="button" data-action="apply" data-id="${escapeHTML(j.id)}" ${!canApply?'disabled':''} title="${applied?'Candidatura já registrada':j.ignored?'Reative a vaga antes de registrar a candidatura':'Registrar candidatura enviada fora do Radar'}">${applied?'✓ Candidatura registrada':'＋ Registrar candidatura'}</button>`:'';
 const resumeBtn=`<button type="button" class="btn resume-card-btn" data-action="resume" data-id="${escapeHTML(j.id)}" aria-label="Gerar currículo para ${escapeHTML(j.title)}" title="Gerar currículo alinhado a esta vaga"><span class="resume-btn-content">▤ Currículo</span></button>`;
 return `<article class="job resume-job-card ${j.ignored?'ignored':''}"><div class="job-upper"><div><h3>${escapeHTML(j.title)}</h3><div class="job-company">${escapeHTML(j.company)}</div><div class="job-meta"><span>⌖ ${escapeHTML(j.location||'Local não informado')}</span><span>◷ ${dateFmt(j.published||j.first_seen)}</span>${j.salary?`<span>${escapeHTML(j.salary)}</span>`:''}</div></div><div class="job-score">${score}<span>ADERÊNCIA</span></div></div><div class="job-tags">${tags.map(t=>`<span class="tag ${t==='Remoto'?'green':t==='Rejeitada'||j.ignored?'red':''}">${escapeHTML(t)}</span>`).join('')}${j.ignored?'<span class="tag red">Bloqueada</span>':''}</div>${urlSection}<div class="job-footer"><small>${j.notes?'✎ Possui anotações · ':''}${j.followup?'Próximo acompanhamento '+dateFmt(j.followup):'Registre o andamento no painel'}</small><div class="job-action-group">${resumeBtn}${openBtn}<button class="btn btn-outline-light" type="button" data-action="save" data-id="${escapeHTML(j.id)}">${j.saved?'★ Salva':'☆ Salvar'}</button>${applyButton}${quickActions}${blockBtn}<button class="btn btn-outline-light" type="button" data-action="manage" data-id="${escapeHTML(j.id)}">Gerenciar</button></div></div></article>`;
}

const noJobs=(msg='Nenhuma oportunidade encontrada para estes filtros.')=>`<div class="empty"><b>Sem vagas neste grupo</b><p>${escapeHTML(msg)}</p></div>`;
function displayJobs(list,id,context='default'){$(id).innerHTML=list.length?list.map(x=>renderJob(x,context)).join(''):noJobs()}
function updateOpportunityFilterCount(){
 const count=[
  !!$('searchInput').value.trim(),
  $('modeFilter').value!=='all', $('statusFilter').value!=='all',
  $('sourceFilter').value!=='all', $('viewFilter').value!=='active',
  $('sortFilter').value!=='new', $('hideProcessed').checked
 ].filter(Boolean).length;
 const badge=$('opportunityFiltersCount');if(!badge)return;
 badge.hidden=count===0;
 badge.textContent=`${count} filtro${count===1?' ativo':'s ativos'}`;
}
function renderJobs(){
 const jobs=[...(db.jobs||[])];const q=($('searchInput').value||'').trim().toLowerCase(),mode=$('modeFilter').value,src=$('sourceFilter').value,st=$('statusFilter').value,view=$('viewFilter').value;
 let result=jobs.filter(j=>{
   if(view==='active'&&(j.ignored||j.auto_excluded)||view==='ignored'&&!j.ignored||view==='saved'&&!j.saved||view==='unprocessed'&&(j.ignored||j.auto_excluded||j.status!=='Nova'||j.saved))return false;
   if($('hideProcessed').checked&&['Candidatada','Triagem','Entrevista','Teste técnico','Proposta','Aprovada','Rejeitada','Descartada'].includes(j.status))return false;
   if(mode==='remote'&&j.mode!=='Remoto')return false;if(mode==='local'&&j.mode==='Remoto')return false;
   if(src!=='all'&&j.source!==src)return false;if(st!=='all'&&j.status!==st)return false;
   if(q&&!([j.title,j.company,j.location,j.description,(j.skills||[]).join(' ')].join(' ').toLowerCase().includes(q)))return false;
   return true;
 });
 const seen=new Set();
 const unique=result.filter(job=>{
   const group=job.opportunity_group||job.id;
   if(seen.has(group))return false;
   seen.add(group);
   return true;
 });
 const sort=$('sortFilter').value;
 unique.sort(sort==='score'?(a,b)=>b.score-a.score:sort==='title'?(a,b)=>a.title.localeCompare(b.title,'pt-BR'):(a,b)=>String(b.published||b.first_seen).localeCompare(String(a.published||a.first_seen)));
 $('jobsCount').textContent=`${unique.length} oportunidades`;
 updateOpportunityFilterCount();
 displayJobs(unique,'jobsList');
}
function renderBlocked(){
 const blocked=(db.jobs||[]).filter(j=>!!j.ignored).sort((a,b)=>String(b.ignored_at||b.first_seen).localeCompare(String(a.ignored_at||a.first_seen)));
 $('blockedTitle').textContent=`${blocked.length} vaga(s) bloqueada(s)`;
 displayJobs(blocked,'blockedList');
}
function todayLocal(){const now=new Date();return [now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-')}
function afterDays(n){const d=new Date(todayLocal()+'T12:00:00');d.setDate(d.getDate()+n);return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-')}
function refreshApplicationCompanyOptions(){
 const el=$('appliedCompany');const current=el.value;
 const companies=[...new Set((db.jobs||[]).filter(isApplied).map(j=>j.company).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR'));
 el.innerHTML='<option value="all">Todas as empresas</option>'+companies.map(x=>`<option value="${escapeHTML(x)}">${escapeHTML(x)}</option>`).join('');
 el.value=companies.includes(current)?current:'all';
}
function renderApplications(){
 const q=$('appliedSearch').value.trim().toLocaleLowerCase('pt-BR'),stage=$('appliedStatus').value,company=$('appliedCompany').value,mode=$('appliedMode').value;
 const follow=$('appliedFollowup').value,from=$('appliedFrom').value,to=$('appliedTo').value;
 const today=todayLocal(),week=afterDays(7);
 let result=(db.jobs||[]).filter(isApplied).filter(j=>{
  if(!$('appliedIncludeBlocked').checked&&j.ignored)return false;
  if(stage!=='all'&&j.status!==stage)return false;
  if(company!=='all'&&j.company!==company)return false;
  if(mode!=='all'&&(j.mode||'Não informado')!==mode)return false;
  if(q&&!([j.title,j.company,j.location,j.notes,j.recruiter,j.contract_type].join(' ').toLocaleLowerCase('pt-BR').includes(q)))return false;
  const date=String(j.applied_at||j.first_seen||'').slice(0,10);
  if(from&&date<from || to&&date>to)return false;
  const f=String(j.followup||'').slice(0,10);
  if(follow==='pending'&&(!f||f>today))return false;
  if(follow==='week'&&(!f||f<today||f>week))return false;
  if(follow==='future'&&(!f||f<=today))return false;
  if(follow==='without'&&f)return false;
  return true;
 });
 const sort=$('appliedSort').value;
 result.sort(sort==='score'?(a,b)=>(b.score||0)-(a.score||0):sort==='company'?(a,b)=>String(a.company).localeCompare(String(b.company),'pt-BR'):sort==='followup'?(a,b)=>(a.followup||'9999').localeCompare(b.followup||'9999'):sort==='stage'?(a,b)=>statusRank(b.status)-statusRank(a.status)||String(a.followup||'9999').localeCompare(String(b.followup||'9999'))||String(b.applied_at||b.first_seen).localeCompare(String(a.applied_at||a.first_seen)):(a,b)=>String(b.applied_at||b.first_seen).localeCompare(String(a.applied_at||a.first_seen)));
 const total=(db.jobs||[]).filter(isApplied).length;
 $('appliedFilterCount').textContent=`${result.length} de ${total} candidatura(s)`;
 displayJobs(result,'appliedList','applied');
}
function resetApplicationFilters(){
 $('appliedSearch').value='';$('appliedStatus').value='all';$('appliedCompany').value='all';$('appliedMode').value='all';$('appliedFollowup').value='all';$('appliedFrom').value='';$('appliedTo').value='';$('appliedSort').value='stage';$('appliedIncludeBlocked').checked=true;renderApplications();
}
function executionTone(state){return ({success:'success',warning:'warning',error:'error',interrupted:'warning',running:'running'})[state]||'pending'}
function executionTime(value){if(!value)return '';const d=new Date(value);return Number.isNaN(d.getTime())?String(value):d.toLocaleString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit',day:'2-digit',month:'2-digit'})}
function showToast(message,level='info'){
 const container=$('toastStack');if(!container)return;
 const id='toast-'+Date.now()+'-'+Math.floor(Math.random()*1e5),title=({error:'Falha na busca',warning:'Aviso da busca',success:'Consulta finalizada',info:'Status da busca'})[level]||'Atualização';
 const item=document.createElement('div');item.className='app-toast '+level;item.id=id;
 item.innerHTML=`<span class="toast-icon">${({error:'✕',warning:'!',success:'✓',info:'◌'})[level]||'◌'}</span><div><b>${escapeHTML(title)}</b><small>${escapeHTML(message)}</small></div><button type="button" aria-label="Fechar notificação" class="toast-close">×</button>`;
 item.querySelector('button').addEventListener('click',()=>item.remove());container.prepend(item);
 while(container.children.length>4)container.lastElementChild.remove();
}
function showExecution(id){selectedExecutionId=id;renderExecution()}
function renderExecution(){
 const wrapper=$('executionMonitor');if(!wrapper)return;
 const rows=executionList||[];
 const running=rows.find(x=>x.status==='running');
 const item=rows.find(x=>x.id===selectedExecutionId)||running||rows[0];
 if(!item){wrapper.hidden=true;return}
 wrapper.hidden=false;
 const types={ai:'Busca com IA · Gemini',scan:'Coleta de vagas · fontes públicas'},statuses={running:'Em andamento',success:'Concluída',warning:'Concluída com avisos',error:'Falhou',interrupted:'Interrompida'};
 $('executionTitle').textContent=types[item.type]||'Busca';
 $('executionTime').textContent='Iniciada em '+executionTime(item.started_at);
 $('executionBadge').textContent=statuses[item.status]||item.status;
 $('executionBadge').className='execution-badge '+executionTone(item.status);
 const progress=Math.min(100,Math.max(0,Number(item.progress)||0));
 $('executionPercent').textContent=progress+'% das etapas';
 const current=item.steps?.findIndex(x=>x.status==='running');
 const last=item.steps?.filter(x=>x.status==='success').length||0;
 $('executionStepText').textContent=item.status==='running'?`Etapa ${Math.max(1,current+1)} de ${item.steps.length}`:`${last} de ${item.steps.length} etapas concluídas`;
 $('executionProgressFill').style.width=progress+'%';$('executionProgress').setAttribute('aria-valuenow',String(progress));
 $('executionChoices').innerHTML=rows.slice(0,6).map(x=>`<button class="execution-choice ${x.id===item.id?'active':''}" type="button" data-execution-id="${escapeHTML(x.id)}">${x.type==='ai'?'✦ IA':'⌕ Busca'} · ${executionTime(x.started_at)} <span class="execution-dot ${executionTone(x.status)}"></span></button>`).join('');
 $('executionSteps').innerHTML=(item.steps||[]).map(x=>`<div class="execution-step ${escapeHTML(x.status)}"><span class="step-mark">${x.status==='success'?'✓':x.status==='error'?'×':x.status==='running'?'◌':'●'}</span>${escapeHTML(x.label)}</div>`).join('');
 $('executionLogs').innerHTML=(item.logs||[]).slice().reverse().map(x=>`<div class="execution-log ${escapeHTML(x.level)}"><span class="log-time">${escapeHTML(executionTime(x.at).split(' ').pop())}</span><span class="log-severity">${x.level==='success'?'✓':x.level==='warning'?'!':x.level==='error'?'×':'·'}</span><span>${escapeHTML(x.message)}</span></div>`).join('')||'<div class="execution-placeholder">Aguardando o primeiro evento registrado.</div>';
 $('executionLogCount').textContent=`${item.logs?.length||0} evento(s)`;
 const m=item.metrics||{};
 $('executionMetrics').textContent=`${m.sources_total?`${m.sources_done||0}/${m.sources_total} fontes · `:''}${m.fetched||0} anúncios · ${m.qualified||0} compatíveis · ${m.auto_excluded||0} excluídas por regra · ${m.new||0} novas vagas${m.tokens?` · ${m.tokens} tokens`:''}`;
}
async function refreshExecutions(){
 try{
 const res=await api('executions');const previous=executionList||[];executionList=res.executions||[];
 for(const item of executionList.slice(0,5)){
  const old=lastExecutionStatus[item.id];
  if(old&&old!==item.status&&item.status!=='running'){
    const logs=item.logs||[],msg=logs.slice().reverse().find(e=>e.level==='error'||e.level==='warning')?.message||`${item.type==='ai'?'Busca com IA':'Coleta'}: ${item.status==='success'?'concluída com sucesso':'finalizada com alertas'}.`;
    showToast(msg,item.status==='success'?'success':item.status==='error'?'error':'warning');
    if(item.type==='ai'&&item.status==='error')status(msg,true);
    refresh(true);
  }
  lastExecutionStatus[item.id]=item.status;
 }
 renderExecution();
 }catch(e){ /* O painel principal continua operando mesmo sem o journal. */ }
}
function renderRuns(){
 $('aiRunList').innerHTML=(db.ai_runs||[]).length?db.ai_runs.map(r=>{
  let terms={};let errors=[];try{terms=JSON.parse(r.queries||'{}')}catch(_){}try{errors=JSON.parse(r.errors||'[]')}catch(_){}
  return `<div class="run-item"><strong>${dateFmt(r.run_at)} · ${escapeHTML(r.model)} · ${r.inserted} nova(s)</strong><small>${r.fetched} anúncios analisados · ${r.tokens||0} tokens locais</small><small>BR: ${escapeHTML((terms.br||[]).join(' · '))} | Internacional: ${escapeHTML((terms.international||[]).join(' · '))}</small>${errors.length?`<details><summary>Avisos (${errors.length})</summary><small>${escapeHTML(errors.join(' | '))}</small></details>`:''}</div>`;
 }).join(''):noJobs('O histórico de IA aparecerá após uma busca local concluída.');
 $('runList').innerHTML=(db.runs||[]).length?db.runs.map(r=>{
   let sources={};try{sources=JSON.parse(r.sources||'{}')}catch(_){}
   let errs=[];try{errs=JSON.parse(r.errors||'[]')}catch(_){}
   return `<div class="run-item"><strong>${dateFmt(r.run_at)} · ${r.inserted} novas vagas</strong><small>${r.fetched} anúncios coletados · ${r.eligible} compatíveis · ${r.already_known||0} já conhecidos · ${r.excluded||0} ignorados</small><small>${Object.entries(sources).map(([k,v])=>`${escapeHTML(k)}: ${Number(v.received)||0}`).join(' · ')}</small>${errs.length?`<details><summary>${errs.length} aviso(s) nas fontes</summary><small>${errs.map(x=>escapeHTML(x)).join(' | ')}</small></details>`:''}</div>`;
 }).join(''):noJobs('O histórico surgirá depois da primeira busca automática.');
}
function render(){
 const js=db.jobs||[],active=js.filter(x=>!x.ignored),high=active.filter(x=>x.score>=72),applied=js.filter(isApplied),interviews=applied.filter(x=>['Entrevista','Teste técnico','Proposta','Aprovada'].includes(x.status));
 $('navCount').textContent=String(active.length);$('blockedCount').textContent=String(js.filter(x=>x.ignored).length);
 $('applicationsCount').textContent=String(applied.length);
 $('mTotal').textContent=active.length;$('mHigh').textContent=high.length;$('mApplied').textContent=applied.length;$('mInterviews').textContent=interviews.length;
 displayJobs([...active].sort((a,b)=>(b.score||0)-(a.score||0)).slice(0,5),'topJobs');
 $('scanState').textContent=db.scan?.running?'Buscando fontes...':'Pronto para nova busca';$('scanBtn').disabled=!!db.scan?.running;
 const scan=db.scan?.last_result;$('scanSummary').textContent=scan?scan.ok?`${scan.fetched} encontrados · ${scan.new} novos · ${scan.excluded||0} excluídos · ${(scan.errors||[]).length} aviso(s)`:scan.message:'Nenhuma busca nesta sessão.';
 const stats=[['Candidatada',applied.filter(x=>x.status==='Candidatada').length],['Triagem',applied.filter(x=>x.status==='Triagem').length],['Entrevista',applied.filter(x=>['Entrevista','Teste técnico'].includes(x.status)).length],['Proposta',applied.filter(x=>x.status==='Proposta').length],['Encerradas',applied.filter(x=>['Rejeitada','Aprovada'].includes(x.status)).length]];
 $('pipeline').innerHTML=stats.map(([stage,n])=>`<div class="pipeline-item"><span>${stage}</span><b>${n}</b></div>`).join('');
 refreshApplicationCompanyOptions();renderApplications();renderBlocked();renderRuns();
 const select=$('sourceFilter');const old=select.value;const sources=[...new Set(js.map(j=>j.source).filter(Boolean))].sort();select.innerHTML='<option value="all">Todas fontes</option>'+sources.map(v=>`<option value="${escapeHTML(v)}">${escapeHTML(v)}</option>`).join('');if(sources.includes(old))select.value=old;
 renderJobs();renderNav();
 const configured=!!db.ai?.cloud?.configured;const model=db.settings?.ai_model||'gemini-3.5-flash-lite';
 $('aiKeyStatus').textContent=configured?`Chave Gemini configurada (${db.ai.cloud.source}). Modelo: ${model}. Nenhuma chave é exibida neste painel.`:'Chave Gemini não configurada. Obtenha uma chave gratuita no Google AI Studio.';
 $('aiUsage').textContent=`${db.ai?.usage?.calls||0} consulta(s) hoje · ${db.ai?.usage?.tokens||0} tokens contabilizados pela API`;
 $('aiSearchBtn').disabled=!!db.scan?.ai_running;
 $('aiSearchBtn').textContent=db.scan?.ai_running?'✦ Pesquisando com IA...':'✦ Buscar com IA';
 const ai=db.scan?.ai_last_result;if(ai&&JSON.stringify(ai)!==latestAISeen){latestAISeen=JSON.stringify(ai);status(ai.ok?`Busca IA: ${ai.new} vagas novas; ${ai.fetched} anúncios verificados (${ai.model}).`:'Busca IA: '+ai.message,!ai.ok)}
}
async function refresh(quiet=false){
 try{const res=await api('state');db=res;render();if(!quiet)status('Painel sincronizado. Os dados são armazenados localmente.')}catch(e){status('Não foi possível consultar o servidor: '+e.message,true)}
}
async function startScan(){try{const run=await api('scan','POST',{});selectedExecutionId=run.id;status('Coleta iniciada — acompanhando cada fonte.');showToast('Coleta pública iniciada; os eventos aparecerão no monitor.');await refresh(true);await refreshExecutions()}catch(e){status(e.message,true);showToast(e.message,'error')}}
async function toggleSave(id){let j=db.jobs.find(x=>x.id===id);if(!j)return;try{await api('jobs/'+encodeURIComponent(id),'POST',{saved:!Boolean(j.saved)});await refresh(true)}catch(e){status(e.message,true)}}
let confirmActionHandler=null;
function openDialog(id){$(id).showModal()}
function closeDialog(id){$(id).close();if(id==='confirmActionDialog')confirmActionHandler=null}
function openConfirmDialog(title,text,confirmLabel,handler,variant='primary'){
 $('confirmActionTitle').textContent=title; $('confirmActionText').textContent=text; const btn=$('confirmActionBtn'); btn.textContent=confirmLabel; btn.className='btn '+(variant==='danger'?'btn-danger-subtle':'btn-primary'); confirmActionHandler=handler; openDialog('confirmActionDialog');
}
function formatHistoryDate(value){
 const d=new Date(value);
 if(Number.isNaN(d.getTime()))return 'Data não informada';
 return d.toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'medium'});
}
function historyStatusLabel(status){return status==='Candidatada'?'Candidatura':status||''}
function historyTitle(event){
 const before=historyStatusLabel(event.previous_status),after=historyStatusLabel(event.new_status);
 if(event.event_type==='application'&&(!before||before==='Nova'||before==='Salva'))return 'Candidatura';
 if(event.event_type==='initial')return 'Estado inicial registrado: '+after;
 return before?before+' → '+after:after;
}
async function loadManagedHistory(jobId){
 const list=$('manageHistoryList'),count=$('manageHistoryCount');
 if(!list||!count)return;
 list.setAttribute('aria-busy','true');list.innerHTML='<p class="application-history-empty">Consultando movimentações...</p>';
 count.textContent='Carregando...';
 try{
  const response=await api('jobs/'+encodeURIComponent(jobId)+'/history');
  if(managingId!==jobId)return;  // Ignore out-of-order responses for other jobs.
  const events=response.events||[];
  count.textContent=events.length+' '+(events.length===1?'evento':'eventos');
  list.innerHTML=events.length?events.map(event=>{
   const tone=event.new_status==='Rejeitada'?'history-rejected':event.new_status==='Aprovada'?'history-approved':'history-progress';
   const label=historyTitle(event);
   return `<div class="application-history-item ${tone}"><span class="history-dot" aria-hidden="true"></span><div class="history-copy"><strong>${escapeHTML(label)}</strong><span>${escapeHTML(formatHistoryDate(event.occurred_at))} · ${escapeHTML(event.source||'Painel')}</span></div></div>`;
  }).join(''):'<p class="application-history-empty">Nenhuma movimentação registrada ainda. O histórico inicia na v9.2; etapas anteriores não recebem datas estimadas.</p>';
 }catch(e){if(managingId===jobId){count.textContent='Indisponível';list.innerHTML=`<p class="application-history-empty">Não foi possível carregar o histórico: ${escapeHTML(e.message)}</p>`;}}
 finally{if(managingId===jobId)list.setAttribute('aria-busy','false')}
}
function openManage(id){
 const j=db.jobs.find(x=>x.id===id);if(!j){status('Registro não encontrado.',true);return}managingId=j.id;
 $('manageTitle').textContent=j.title;$('manageSubtitle').textContent=j.company+' · '+j.source+' · '+(j.location||'local desconhecido');
 $('manageStatus').value=j.status;$('manageFollowup').value=(j.followup||'').slice(0,10);$('manageNotes').value=j.notes||'';$('manageContract').value=j.contract_type||'';$('manageRecruiter').value=j.recruiter||'';$('manageError').textContent='';
 $('manageReasons').textContent=(j.reasons||[]).join(' · ')||'Pontuação estimada a partir do perfil.';
 $('manageIgnore').textContent=j.ignored?'↻ Reativar vaga':'⊘ Bloquear vaga';const editable=['Manual','Importação XLSX','Importação CSV'].includes(j.source);
 $('manageEdit').hidden=!editable;$('manageDelete').hidden=!editable;
 $('manageUrl').hidden=!j.url;$('manageUrl').href=j.url||'#';openDialog('manageDialog');
 loadManagedHistory(j.id);
}
async function saveManage(ev){ev.preventDefault();if(!managingId)return;let b=$('manageSave');b.disabled=true;$('manageError').textContent='';try{
 await api('jobs/'+encodeURIComponent(managingId),'POST',{status:$('manageStatus').value,followup:$('manageFollowup').value,notes:$('manageNotes').value,contract_type:$('manageContract').value,recruiter:$('manageRecruiter').value});await refresh(true);await loadManagedHistory(managingId);status('Alterações salvas e histórico de movimentações atualizado.')
}catch(e){$('manageError').textContent=e.message}finally{b.disabled=false}}
async function quickAdvance(id){const j=db.jobs.find(x=>x.id===id);if(!j)return;const next=nextApplicationStage(j.status);if(!next)return;openConfirmDialog('Avançar etapa',`Deseja mover a candidatura para "${next}"?`,`Avançar para ${next}`,async()=>{try{await api('jobs/'+encodeURIComponent(id),'POST',{status:next});closeDialog('confirmActionDialog');await refresh(true);showPage('candidaturas');status(`Candidatura movida para ${next}.`)}catch(e){status(e.message,true)}});}
async function quickReject(id){const j=db.jobs.find(x=>x.id===id);if(!j)return;openConfirmDialog('Registrar rejeição',`Deseja marcar a candidatura de "${j.title}" como rejeitada?`,'Registrar rejeição',async()=>{try{await api('jobs/'+encodeURIComponent(id),'POST',{status:'Rejeitada'});closeDialog('confirmActionDialog');await refresh(true);showPage('candidaturas');status('Rejeição registrada na candidatura.')}catch(e){status(e.message,true)}},'danger');}
async function registerApplication(id){
 const job=db.jobs.find(x=>x.id===id);
 if(!job||job.ignored||!['Nova','Salva'].includes(job.status))return;
 openConfirmDialog('Registrar candidatura no Radar',`Você já enviou sua candidatura para “${job.title}” na empresa ${job.company}? Esta ação apenas registra a etapa Candidatada no Radar; ela NÃO envia sua inscrição ao site externo.`,'Confirmar candidatura',async()=>{
  const button=$('confirmActionBtn');button.disabled=true;
  try{
   await api('jobs/'+encodeURIComponent(id),'POST',{status:'Candidatada',saved:true});
   closeDialog('confirmActionDialog');await refresh(true);
   status('Candidatura registrada. A vaga agora aparece em Candidaturas.');
   showToast('Candidatura marcada como enviada no Radar.','success');
  }catch(e){status(e.message,true);showToast(e.message,'error')}
  finally{button.disabled=false}
 });
}
async function ignoreManaged(){if(!managingId)return;const j=db.jobs.find(x=>x.id===managingId);if(!j)return;const msg=j.ignored?'Reativar esta vaga na lista?':'Bloquear esta vaga nas próximas buscas? As anotações e candidaturas serão preservadas.';if(!confirm(msg))return;try{await api('jobs/'+encodeURIComponent(j.id),'POST',{ignored:!Boolean(j.ignored)});closeDialog('manageDialog');await refresh(true);status(j.ignored?'Vaga reativada.':'Vaga bloqueada das próximas buscas.')}catch(e){status(e.message,true)}}
async function setBlockForCard(id,blocked){
 const j=(db.jobs||[]).find(x=>x.id===id);if(!j)return;
 if(blocked&&!confirm(`Bloquear a vaga "${j.title}" em ${j.company}? Ela não aparecerá nas próximas buscas.`))return;
 try{await api('jobs/'+encodeURIComponent(id),'POST',{ignored:blocked});await refresh(true);status(blocked?'Vaga bloqueada. Consulte o menu Bloqueados.':'Vaga reativada.');}
 catch(e){status(e.message,true)}
}
function openManual(id=null){
 editingId=id;$('manualForm').reset();$('manualError').textContent='';$('manualDialogTitle').textContent=id?'Editar vaga':'Cadastrar vaga';$('manualSubmit').textContent=id?'Salvar cadastro':'Cadastrar vaga';
 if(id){const j=db.jobs.find(x=>x.id===id);if(!j)return;for(const [key,elem] of Object.entries(MAN_FIELDS)){$(elem).value=key==='published'?(j[key]||'').slice(0,10):(j[key]??'')}}
 openDialog('manualDialog');$('manTitle').focus();
}
async function submitManual(ev){ev.preventDefault();const btn=$('manualSubmit');btn.disabled=true;$('manualError').textContent='';const form={saved:true};for(const [key,elem] of Object.entries(MAN_FIELDS))form[key]=$(elem).value.trim();try{
 await api(editingId?'manual/'+encodeURIComponent(editingId):'manual','POST',form);closeDialog('manualDialog');await refresh(true);showPage('vagas');$('sourceFilter').value='all';$('viewFilter').value='active';renderJobs();status(editingId?'Cadastro atualizado.':'Vaga cadastrada e salva.');editingId=null;
}catch(e){$('manualError').textContent=e.message+(e.existing_id?' (verifique o cadastro existente)':'')}finally{btn.disabled=false}}
async function deleteManaged(){if(!managingId||!confirm('Excluir definitivamente esta vaga e suas anotações?'))return;try{await api('manual/'+encodeURIComponent(managingId),'DELETE');closeDialog('manageDialog');await refresh(true);status('Cadastro removido.')}catch(e){status(e.message,true)}}
function initTagDraft(){for(const [k] of TAGS)tagDraft[k]=[...(db.settings[k]||[])]}
function renderSourceGroups(){
 $('sourceGroups').innerHTML=SOURCES.map(group=>`<div class="source-category"><h4>${escapeHTML(group.label)}</h4><div class="source-list">${group.items.map(([key,title,desc])=>`<label class="source-item"><span><strong>${escapeHTML(title)}</strong><small>${escapeHTML(desc)}</small></span><input type="checkbox" data-source="${key}" ${sourceDraft[key]?'checked':''} aria-label="Ativar ${escapeHTML(title)}"></label>`).join('')}</div></div>`).join('');
}
function renderTagGroups(){
 $('tagGroups').innerHTML=TAGS.map(([key,title,helper])=>`<div class="tag-group" data-group="${key}"><h4>${escapeHTML(title)}</h4><p>${escapeHTML(helper)}</p><div class="tag-inputrow"><input class="input" data-tag-input="${key}" placeholder="Digite e pressione Enter" maxlength="120"><button class="btn btn-subtle" type="button" data-tag-add="${key}">Adicionar</button></div><div class="chips">${(tagDraft[key]||[]).map((t,i)=>`<span class="chip">${escapeHTML(t)}<button type="button" data-tag-remove="${key}" data-index="${i}" aria-label="Remover termo">×</button></span>`).join('')}</div></div>`).join('');
}
function addTag(key){const el=document.querySelector(`[data-tag-input="${key}"]`);if(!el)return;const term=el.value.trim();if(!term)return;if(term.length>120){status('O termo não pode ter mais de 120 caracteres.',true);return}if(tagDraft[key].length>=40){status('Limite de 40 termos atingido.',true);return}if(!tagDraft[key].some(x=>x.toLocaleLowerCase()===term.toLocaleLowerCase()))tagDraft[key].push(term);renderTagGroups();const next=document.querySelector(`[data-tag-input="${key}"]`);next?.focus()}
function initMenuDraft(){
 const base=db.settings?.ui_menu||[];
 menuDraft=base.map(x=>({...x}));
 titleDraft={...(db.settings?.ui_titles||{})};
}
function renderMenuCustomizer(){
 const wrap=$('menuCustomizer');if(!wrap)return;
 wrap.innerHTML=menuDraft.map((item,index)=>`<div class="menu-custom-row" data-custom-menu="${escapeHTML(item.id)}"><div class="menu-custom-heading"><strong>${escapeHTML(PAGE_DEFAULTS[item.id]?.[0]||item.id)}</strong><span>${escapeHTML(item.id)}</span></div><label class="form-field">Nome no menu<input class="input" data-menu-label="${escapeHTML(item.id)}" maxlength="38" value="${escapeHTML(item.label)}"></label><label class="form-field">Título da página<input class="input" data-page-title="${escapeHTML(item.id)}" maxlength="65" value="${escapeHTML(titleDraft[item.id]||PAGE_DEFAULTS[item.id][0])}"></label><label class="menu-visible"><input data-menu-visible="${escapeHTML(item.id)}" type="checkbox" ${item.visible?'checked':''} ${['config','bloqueados'].includes(item.id)?'disabled':''}> Visível</label><div class="reorder-buttons"><button class="btn btn-outline-light" type="button" data-menu-up="${escapeHTML(item.id)}" ${index===0?'disabled':''} aria-label="Mover para cima">↑</button><button class="btn btn-outline-light" type="button" data-menu-down="${escapeHTML(item.id)}" ${index===menuDraft.length-1?'disabled':''} aria-label="Mover para baixo">↓</button></div></div>`).join('');
}
function moveMenu(id,dir){const at=menuDraft.findIndex(x=>x.id===id);const to=at+dir;if(at<0||to<0||to>=menuDraft.length)return;[menuDraft[at],menuDraft[to]]=[menuDraft[to],menuDraft[at]];renderMenuCustomizer()}
const RESUME_CONTACT_FIELDS={full_name:'resumeFullName',email:'resumeEmail',phone:'resumePhone',location:'resumeLocation',linkedin:'resumeLinkedin',github:'resumeGithub'};
const RESUME_LONG_FIELDS=[['headline','Título profissional','Professional headline',false],['summary','Resumo profissional','Professional summary',true],['skills','Competências (separe por ponto e vírgula)','Skills (separate with semicolon)',true],['experience','Experiências profissionais','Work experience',true],['education','Formação acadêmica','Education',true],['certifications','Certificações','Certifications',true],['projects','Projetos técnicos','Technical projects',true],['languages','Idiomas','Languages',false]];
const RESUME_SECTIONS=['summary','skills','experience','education','certifications','projects','languages'];
const RESUME_SECTION_LABELS={summary:'Resumo profissional',skills:'Competências',experience:'Experiência',education:'Formação',certifications:'Certificações',projects:'Projetos',languages:'Idiomas'};
const RESUME_LAYOUT_DEFAULTS={layout_preset:'classic',page_size:'A4',margin_mm:17,body_font_pt:9,name_font_pt:17,section_font_pt:10,line_spacing:1.12,section_spacing_pt:5,header_alignment:'left',section_order:[...RESUME_SECTIONS]};
const RESUME_LAYOUT_FIELDS={layout_preset:'resumeLayoutPreset',page_size:'resumePageSize',margin_mm:'resumeMargin',body_font_pt:'resumeBodySize',name_font_pt:'resumeNameSize',section_font_pt:'resumeSectionSize',line_spacing:'resumeLineSpacing',section_spacing_pt:'resumeSectionSpacing',header_alignment:'resumeHeaderAlignment'};
let resumeOrderDraft=[...RESUME_SECTIONS];
let resumeJobId=null;
function fillResumeSettings(){
 const profile=db.settings?.resume_profile||{};
 for(const [key,id] of Object.entries(RESUME_CONTACT_FIELDS))$(id).value=profile[key]||'';
 for(const lang of ['pt','en']){
  const container=$('resumeFields'+(lang==='pt'?'Pt':'En'));
  container.innerHTML=RESUME_LONG_FIELDS.map(([key,titlePt,titleEn,multi])=>`<label class="form-field resume-long-field">${escapeHTML(lang==='pt'?titlePt:titleEn)}${multi?`<textarea class="input" data-resume-field="${key}_${lang}" rows="${key==='experience'?11:3}" maxlength="12000"></textarea>`:`<input class="input" data-resume-field="${key}_${lang}" maxlength="5000">`}</label>`).join('');
  container.querySelectorAll('[data-resume-field]').forEach(el=>{el.value=profile[el.dataset.resumeField]||''});
 }
 const options=db.settings?.resume_template||{};
 $('resumeDefaultLanguage').value=options.default_language||'pt';$('resumeFont').value=options.font||'Arial';$('resumeAccent').value=options.accent||'#5367A4';
 $('resumeMaxSkills').value=options.max_skills??18;$('resumeMaxBullets').value=options.max_bullets_per_job??4;
 $('resumeIncludeProjects').checked=options.include_projects!==false;
 $('resumeIncludeCertifications').checked=options.include_certifications!==false;
 $('resumeIncludeLanguages').checked=options.include_languages!==false;
 const layout={...RESUME_LAYOUT_DEFAULTS,...options};
 for(const [key,id] of Object.entries(RESUME_LAYOUT_FIELDS))$(id).value=String(layout[key]);
 resumeOrderDraft=Array.isArray(layout.section_order)&&layout.section_order.length===RESUME_SECTIONS.length?[...layout.section_order]:[...RESUME_SECTIONS];
 $('resumePreviewLanguage').value=options.default_language||'pt';
 renderResumeSectionOrder();updateResumePagePreview();
}
function collectResumeSettings(){
 const profile={};for(const [key,id] of Object.entries(RESUME_CONTACT_FIELDS))profile[key]=$(id).value.trim();
 document.querySelectorAll('[data-resume-field]').forEach(el=>profile[el.dataset.resumeField]=el.value.trim());
 const template={default_language:$('resumeDefaultLanguage').value,font:$('resumeFont').value,accent:$('resumeAccent').value,
   max_skills:Number($('resumeMaxSkills').value),max_bullets_per_job:Number($('resumeMaxBullets').value),
   include_projects:$('resumeIncludeProjects').checked,include_certifications:$('resumeIncludeCertifications').checked,include_languages:$('resumeIncludeLanguages').checked,
   layout_preset:$('resumeLayoutPreset').value,page_size:$('resumePageSize').value,margin_mm:Number($('resumeMargin').value),
   body_font_pt:Number($('resumeBodySize').value),name_font_pt:Number($('resumeNameSize').value),section_font_pt:Number($('resumeSectionSize').value),
   line_spacing:Number($('resumeLineSpacing').value),section_spacing_pt:Number($('resumeSectionSpacing').value),
   header_alignment:$('resumeHeaderAlignment').value,section_order:[...resumeOrderDraft]};
 if(!profile.full_name||!profile.email)throw Error('Informe nome e e-mail para gerar o currículo.');
 return {resume_profile:profile,resume_template:template};
}
function renderResumeSectionOrder(){
 const box=$('resumeSectionOrder');if(!box)return;
 box.innerHTML=resumeOrderDraft.map((key,i)=>`<div class="resume-order-row"><span class="resume-order-grip">☷</span><span>${escapeHTML(RESUME_SECTION_LABELS[key])}</span><div><button type="button" class="resume-order-move" data-resume-order="up" data-resume-index="${i}" ${!i?'disabled':''} aria-label="Mover ${escapeHTML(RESUME_SECTION_LABELS[key])} para cima">↑</button><button type="button" class="resume-order-move" data-resume-order="down" data-resume-index="${i}" ${i===resumeOrderDraft.length-1?'disabled':''} aria-label="Mover ${escapeHTML(RESUME_SECTION_LABELS[key])} para baixo">↓</button></div></div>`).join('');
}
function moveResumeSection(index,direction){
 const target=index+direction;if(target<0||target>=resumeOrderDraft.length)return;
 [resumeOrderDraft[index],resumeOrderDraft[target]]=[resumeOrderDraft[target],resumeOrderDraft[index]];
 renderResumeSectionOrder();updateResumePagePreview();
}
function updateResumePagePreview(){
 const el=$('resumePagePreview');if(!el)return;
 const lang=$('resumePreviewLanguage').value==='en'?'en':'pt';
 const profile={};for(const [key,id] of Object.entries(RESUME_CONTACT_FIELDS))profile[key]=$(id).value.trim();
 document.querySelectorAll('[data-resume-field]').forEach(input=>profile[input.dataset.resumeField]=input.value.trim());
 const val=(id,def)=>Number($(id).value)||def;
 const accent=$('resumeAccent').value,scale=0.86,body=val('resumeBodySize',9),name=val('resumeNameSize',17),section=val('resumeSectionSize',10),margin=val('resumeMargin',17);
 const paper=$('resumePageSize').value;
 el.style.setProperty('--preview-accent',accent);
 el.style.setProperty('--preview-font',$('resumeFont').value);
 el.style.setProperty('--preview-body',`${body*scale}px`);
 el.style.setProperty('--preview-name',`${name*scale}px`);
 el.style.setProperty('--preview-section',`${section*scale}px`);
 el.style.setProperty('--preview-margin',`${margin*.9}px`);
 el.style.setProperty('--preview-line',String(val('resumeLineSpacing',1.12)));
 el.style.setProperty('--preview-section-gap',`${val('resumeSectionSpacing',5)*scale}px`);
 el.style.setProperty('--preview-head-align',$('resumeHeaderAlignment').value);
 el.className=`resume-page-preview resume-style-${$('resumeLayoutPreset').value}`;
 el.style.aspectRatio=paper==='Letter'?'8.5 / 11':'210 / 297';
 const sections={
 summary:profile['summary_'+lang]||'',skills:(profile['skills_'+lang]||'').split(';').slice(0,val('resumeMaxSkills',18)).join('  •  '),
 experience:(profile['experience_'+lang]||'').split('\n').filter(Boolean).slice(0,8).join('\n'),
 education:profile['education_'+lang]||'',certifications:profile['certifications_'+lang]||'',
 projects:profile['projects_'+lang]||'',languages:profile['languages_'+lang]||''
 };
 const titles=lang==='en'?{summary:'PROFESSIONAL SUMMARY',skills:'TECHNICAL SKILLS',experience:'WORK EXPERIENCE',education:'EDUCATION',certifications:'CERTIFICATIONS',projects:'PROJECTS',languages:'LANGUAGES'}:{summary:'RESUMO PROFISSIONAL',skills:'COMPETÊNCIAS',experience:'EXPERIÊNCIA PROFISSIONAL',education:'FORMAÇÃO',certifications:'CERTIFICAÇÕES',projects:'PROJETOS',languages:'IDIOMAS'};
 const enabled={projects:$('resumeIncludeProjects').checked,certifications:$('resumeIncludeCertifications').checked,languages:$('resumeIncludeLanguages').checked};
 const html=resumeOrderDraft.filter(key=>enabled[key]!==false).map(key=>`<section class="preview-doc-section"><h5>${titles[key]}</h5><p>${escapeHTML(sections[key]||'—').replace(/\n/g,'<br>')}</p></section>`).join('');
 el.innerHTML=`<div class="preview-doc-head"><strong>${escapeHTML(profile.full_name||'Nome profissional')}</strong><span>${escapeHTML(profile['headline_'+lang]||'Título profissional')}</span><small>${escapeHTML([profile.phone,profile.email,profile.location].filter(Boolean).join('  |  '))}</small><small>${escapeHTML([profile.linkedin,profile.github].filter(Boolean).join('  |  '))}</small></div>${html}`;
}
function resetResumeLayout(){
 for(const [key,id] of Object.entries(RESUME_LAYOUT_FIELDS))$(id).value=String(RESUME_LAYOUT_DEFAULTS[key]);
 resumeOrderDraft=[...RESUME_SECTIONS];renderResumeSectionOrder();updateResumePagePreview();
}
async function openResume(id){
 const job=(db.jobs||[]).find(j=>String(j.id)===String(id));if(!job)return;
 resumeJobId=String(id);$('resumeJobText').textContent=job.title+' · '+job.company;
 $('resumeLanguage').value=db.settings?.resume_template?.default_language||'pt';
 openDialog('resumeDialog');await updateResumePreview();
}
async function updateResumePreview(){
 if(!resumeJobId)return;
 const lang=$('resumeLanguage').value;
 $('resumeDownloadBtn').href='/api/resume/docx?job='+encodeURIComponent(resumeJobId)+'&lang='+encodeURIComponent(lang);
 $('resumeMatchInfo').textContent='Comparando competências declaradas com o texto da vaga...';$('resumeMatchChips').innerHTML='';
 try{
  const details=await api('resume/match?job='+encodeURIComponent(resumeJobId)+'&lang='+encodeURIComponent(lang));
  $('resumeMatchInfo').textContent=details.has_description?
    (details.matched.length?details.matched.length+' competência(s) identificada(s) no anúncio. Serão priorizadas no currículo.':'Nenhuma correspondência direta identificada. O currículo será gerado com o perfil cadastrado.'):
    'Anúncio sem descrição detalhada: a priorização será limitada ao título e nível da vaga.';
  $('resumeMatchChips').innerHTML=(details.matched||[]).slice(0,12).map(x=>`<span class="tag green">${escapeHTML(x)}</span>`).join('');
 }catch(e){$('resumeMatchInfo').textContent='Não foi possível conferir a aderência: '+e.message}
}
function fillSettings(){
 const c=db.settings||{};sourceDraft={...c.sources};initTagDraft();initMenuDraft();initExclusions();renderSourceGroups();renderTagGroups();renderMenuCustomizer();fillResumeSettings();showConfigTab(activeConfigTab);$('cfgBrand').value=c.ui_brand||DEFAULT_BRAND;
 const number=[['cfgAge','max_age_days',7],['cfgScore','min_score',48],['cfgAlert','notify_score',72],['cfgMaxQueries','max_queries_per_source',10],['cfgAiCap','ai_daily_cap',2],['cfgAiTokens','ai_max_output_tokens',320]];
 for(const [id,key,def] of number)$(id).value=c[key]??def;
 $('cfgRemoteEnabled').checked=!!c.include_remote;$('cfgLocalEnabled').checked=!!c.include_local;$('cfgStrict').checked=!!c.strict_brazil_eligibility;$('cfgQueryCombos').checked=!!c.query_combinations;$('cfgAiModel').value=c.ai_model||'gemini-3.5-flash-lite';$('cfgAiWebSearch').checked=false;$('cfgAiWebSearch').disabled=true;refreshFreeModels();
}
// Mostra só modelos de texto gratuitos; com chave, cruza a lista com a API.
async function refreshFreeModels(){
 const select=$('cfgAiModel'),message=$('aiModelsMessage');if(!select||!message)return;
 const previous=select.value||db.settings?.ai_model||'gemini-3.5-flash-lite';
 message.textContent='Verificando modelos gratuitos disponíveis...';
 try{
  const response=await api('ai/models');const models=response.models||[];
  select.innerHTML=models.map(x=>`<option value="${escapeHTML(x.id)}">${escapeHTML(x.label)}</option>`).join('');
  if(models.some(x=>x.id===previous))select.value=previous;
  else if(models.length)select.value=models[0].id;
  select.disabled=models.length===0;
  message.textContent=response.message+(response.verified?' Lista validada com a chave atual.':'');
 }catch(e){
  select.innerHTML='';select.disabled=true;
  message.textContent='Não foi possível validar os modelos com a chave configurada: '+e.message+'. Tente novamente.';
 }
}

async function saveSettings(){
 const sourceInputs=document.querySelectorAll('[data-source]');const src={};for(const box of sourceInputs)src[box.dataset.source]=box.checked;
 try{
 const settings={max_age_days:Number($('cfgAge').value),min_score:Number($('cfgScore').value),notify_score:Number($('cfgAlert').value),max_queries_per_source:Number($('cfgMaxQueries').value),ai_daily_cap:Number($('cfgAiCap').value),ai_max_output_tokens:Number($('cfgAiTokens').value),ai_model:$('cfgAiModel').value||db.settings?.ai_model||'gemini-3.5-flash-lite',ai_web_search:false,include_remote:$('cfgRemoteEnabled').checked,include_local:$('cfgLocalEnabled').checked,strict_brazil_eligibility:$('cfgStrict').checked,query_combinations:$('cfgQueryCombos').checked,sources:src,ui_brand:$('cfgBrand').value.trim()||DEFAULT_BRAND,ui_menu:menuDraft.map(x=>({...x})),ui_titles:{...titleDraft},exclude_seniority:{...exclusionDraft},exclude_custom_terms:[...exclusionCustomDraft],...tagDraft,...collectResumeSettings()};
 await api('settings','POST',settings);await refresh(true);status('Preferências e modelo de currículo salvos.')}catch(e){status('Erro ao salvar: '+e.message,true)}
}
async function saveAIKey(){
 const value=$('cfgGeminiKey').value.trim();if(!value){status('Cole a chave Gemini no campo para salvar.',true);return}
 try{await api('ai/key','POST',{key:value});$('cfgGeminiKey').value='';await refresh(true);await refreshFreeModels();status('Chave Gemini salva apenas no computador.');}catch(e){status(e.message,true)}
}
async function testAIKey(){
 const button=$('testAiKeyBtn');button.disabled=true;try{const out=await api('ai/test','POST',{});status(out.message,!out.ok);await refresh(true)}catch(e){status(e.message,true)}finally{button.disabled=false}
}
async function clearAIKey(){
 if(!confirm('Remover a chave Gemini armazenada neste computador?'))return;
 try{await api('ai/key','POST',{clear:true});$('cfgGeminiKey').value='';await refresh(true);await refreshFreeModels();status('Chave armazenada removida.');}catch(e){status(e.message,true)}
}
async function searchAI(){try{const run=await api('ai/run','POST',{});selectedExecutionId=run.id;status('Busca Gemini iniciada; acompanhe o monitor em tempo real.');showToast('Busca com IA iniciada. Verificando chave e cotas.');await refresh(true);await refreshExecutions()}catch(e){status(e.message,true);showToast(e.message,'error')}}
async function importWorkbook(ev){
 ev.preventDefault();const file=$('xlsxFile').files?.[0];const result=$('importResult');
 if(!file){result.textContent='Selecione um arquivo XLSX ou CSV.';return}
 const ext=file.name.toLowerCase().split('.').pop();
 if(!['xlsx','csv'].includes(ext)){result.textContent='Formato inválido. Selecione XLSX ou CSV.';return}
 if(file.size>12e6){result.textContent='Arquivo maior que 12 MB.';return}
 const btn=$('importSubmit');btn.disabled=true;result.textContent='Lendo registros e verificando duplicatas...';
 try{
  const resp=await fetch('/api/import.'+ext,{method:'POST',headers:{'Content-Type':ext==='xlsx'?'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'text/csv'},body:file});
  const value=await resp.json();if(!resp.ok)throw Error(value.error||'Falha ao importar');
  result.textContent=`Importação concluída: ${value.inserted} novas, ${value.updated} atualizadas, ${value.skipped} ignoradas (${value.skipped_nova||0} com status Nova).\n${(value.warnings||[]).slice(0,6).join('\n')}`;
  await refresh(true);status('Importação concluída. Confira a seção Candidaturas.');
 }catch(e){result.textContent='Não foi possível importar: '+e.message}
 finally{btn.disabled=false}
}
const EXPORT_FIELDS=['exportScope','exportStatus','exportCompany','exportMode','exportQuery','exportDateField','exportDateFrom','exportDateTo','exportIncludeBlocked'];
let exportPreviewTimer=null;
function exportParams(){
 const params=new URLSearchParams({
  scope:$('exportScope').value,status:$('exportStatus').value,company:$('exportCompany').value,
  mode:$('exportMode').value,q:$('exportQuery').value.trim(),date_field:$('exportDateField').value,
  date_from:$('exportDateFrom').value,date_to:$('exportDateTo').value,
  include_blocked:String($('exportIncludeBlocked').checked)
 });
 return params;
}
function prepareExportOptions(){
 const company=$('exportCompany'),old=company.value;
 const companies=[...new Set((db.jobs||[]).map(j=>String(j.company||'').trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR'));
 company.innerHTML='<option value="">Todas as empresas</option>'+companies.map(x=>`<option value="${escapeHTML(x)}">${escapeHTML(x)}</option>`).join('');
 company.value=companies.includes(old)?old:'';
 const statusEl=$('exportStatus'),previous=statusEl.value;
 statusEl.innerHTML='<option value="all">Todas as etapas</option>'+STATUS.map(x=>`<option value="${escapeHTML(x)}">${escapeHTML(x)}</option>`).join('');
 statusEl.value=STATUS.includes(previous)?previous:'all';
}
function resetExportFilters(){
 $('exportScope').value='applications';$('exportStatus').value='all';$('exportCompany').value='';$('exportMode').value='all';
 $('exportQuery').value='';$('exportDateField').value='applied_at';$('exportDateFrom').value='';$('exportDateTo').value='';
 $('exportIncludeBlocked').checked=true;queueExportPreview();
}
async function updateExportPreview(){
 const countEl=$('exportPreviewCount'),infoEl=$('exportPreviewBreakdown');
 countEl.textContent='Calculando seleção...';infoEl.textContent='';
 try{
  const res=await api('export/preview?'+exportParams().toString());
  countEl.textContent=`${res.count} vaga(s) selecionada(s)`;
  infoEl.textContent=Object.entries(res.status_counts||{}).map(([x,n])=>`${x}: ${n}`).join(' · ')||'Nenhuma vaga corresponde aos filtros';
  $('exportXlsxBtn').disabled=$('exportCsvBtn').disabled=res.count===0;
 }catch(e){countEl.textContent='Não foi possível calcular a prévia';infoEl.textContent=e.message;$('exportXlsxBtn').disabled=$('exportCsvBtn').disabled=true}
}
function queueExportPreview(){clearTimeout(exportPreviewTimer);exportPreviewTimer=setTimeout(updateExportPreview,160)}
function openExportFilters(){prepareExportOptions();resetExportFilters();openDialog('exportDialog')}
function downloadFilteredExport(ext){
 const dates=[$('exportDateFrom').value,$('exportDateTo').value];
 if(dates[0]&&dates[1]&&dates[0]>dates[1]){status('A data inicial deve ser anterior à data final.',true);return}
 window.location.href='/api/export.'+ext+'?'+exportParams().toString();
}
async function importSettingsJson(ev){
 ev.preventDefault();const file=$('settingsJsonFile').files?.[0],result=$('settingsImportResult');
 if(!file||!file.name.toLowerCase().endsWith('.json')){result.textContent='Selecione um arquivo JSON válido.';return}
 if(file.size>500000){result.textContent='O arquivo deve ter até 500 KB.';return}
 if(!confirm('Importar configurações? Fontes, filtros, aparência e currículo serão substituídos. Candidaturas e chave Gemini não serão alteradas.'))return;
 $('importSettingsJsonBtn').disabled=true;result.textContent='Validando configurações...';
 try{
  const resp=await fetch('/api/settings/import.json',{method:'POST',headers:{'Content-Type':'application/json'},body:file});
  const value=await resp.json();if(!resp.ok)throw Error(value.error||'Falha ao importar configurações');
  await refresh(true);showPage('config');showConfigTab('backup');
  result.textContent=`Configurações importadas: ${value.imported_count} seções. Candidaturas e chave Gemini preservadas.`;
  status('Configurações restauradas via JSON.');
 }catch(e){result.textContent='Falha na importação do JSON: '+e.message}
 finally{$('importSettingsJsonBtn').disabled=false}
}
async function handleClick(ev){
 const action=ev.target.closest('[data-action]');if(action){const id=action.dataset.id;if(action.dataset.action==='save')await toggleSave(id);if(action.dataset.action==='manage')openManage(id);if(action.dataset.action==='block')await setBlockForCard(id,true);if(action.dataset.action==='restore')await setBlockForCard(id,false);if(action.dataset.action==='advance')await quickAdvance(id);if(action.dataset.action==='reject')await quickReject(id);if(action.dataset.action==='apply')await registerApplication(id);if(action.dataset.action==='resume')await openResume(id);return}
 const go=ev.target.closest('[data-go]');if(go)showPage(go.dataset.go);
 const add=ev.target.closest('[data-tag-add]');if(add){addTag(add.dataset.tagAdd);return}
 const remove=ev.target.closest('[data-tag-remove]');if(remove){const k=remove.dataset.tagRemove;tagDraft[k].splice(Number(remove.dataset.index),1);renderTagGroups();return}
 const up=ev.target.closest('[data-menu-up]');if(up){moveMenu(up.dataset.menuUp,-1);return}const down=ev.target.closest('[data-menu-down]');if(down){moveMenu(down.dataset.menuDown,1);return}
 const removeExclusion=ev.target.closest('[data-exclusion-remove]');
 if(removeExclusion){exclusionCustomDraft.splice(Number(removeExclusion.dataset.exclusionRemove),1);renderExclusions();return}
 const close=ev.target.closest('[data-close]');if(close)closeDialog(close.dataset.close);
}
function setup(){
 fillOptions();document.querySelectorAll('.navlink').forEach(el=>el.addEventListener('click',()=>showPage(el.dataset.page)));
 document.addEventListener('click',handleClick);document.addEventListener('keydown',e=>{const inp=e.target.closest('[data-tag-input]');if(inp&&e.key==='Enter'){e.preventDefault();addTag(inp.dataset.tagInput)}});
 $('menuBtn').addEventListener('click',openMenu);$('scrim').addEventListener('click',closeMenu);$('executionChoices').addEventListener('click',event=>{const target=event.target.closest('[data-execution-id]');if(target)showExecution(target.dataset.executionId)});
 $('scanBtn').addEventListener('click',startScan);$('manualBtn').addEventListener('click',()=>openManual());$('manualForm').addEventListener('submit',submitManual);
 $('manageForm').addEventListener('submit',saveManage);$('manageIgnore').addEventListener('click',ignoreManaged);$('manageEdit').addEventListener('click',()=>{const id=managingId;closeDialog('manageDialog');openManual(id)});$('manageDelete').addEventListener('click',deleteManaged);
 $('importBtn').addEventListener('click',()=>{$('importForm').reset();$('importResult').textContent='';openDialog('importDialog')});$('importForm').addEventListener('submit',importWorkbook);
 $('openExportDialog').addEventListener('click',openExportFilters);
 for(const id of EXPORT_FIELDS)$(id).addEventListener('input',queueExportPreview);
 $('exportResetBtn').addEventListener('click',resetExportFilters);
 $('exportXlsxBtn').addEventListener('click',()=>downloadFilteredExport('xlsx'));
 $('exportCsvBtn').addEventListener('click',()=>downloadFilteredExport('csv'));
 $('downloadTemplateBtn').addEventListener('click',()=>location.href='/api/template.xlsx');
 $('exportSettingsJsonBtn').addEventListener('click',()=>location.href='/api/settings/export.json');
 $('settingsImportForm').addEventListener('submit',importSettingsJson);
 for(const id of ['searchInput','modeFilter','statusFilter','sourceFilter','viewFilter','sortFilter','hideProcessed'])$(id).addEventListener('input',renderJobs);
 $('opportunityFiltersToggle').addEventListener('click',()=>{
  const body=$('opportunityFiltersBody'),expanded=body.hidden;
  body.hidden=!expanded;
  $('opportunityFiltersToggle').setAttribute('aria-expanded',String(expanded));
 });
 $('resetFilters').addEventListener('click',()=>{$('searchInput').value='';for(const id of ['modeFilter','statusFilter','sourceFilter'])$(id).value='all';$('viewFilter').value='active';$('sortFilter').value='new';$('hideProcessed').checked=false;renderJobs()});
 $('configTabs').addEventListener('click',event=>{const btn=event.target.closest('[data-config-tab]');if(btn)showConfigTab(btn.dataset.configTab)});
 $('excludeTermsAdd').addEventListener('click',addExclusionTerm);
 $('exclusionCustomInput').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();addExclusionTerm()}});
 $('excludeLevelGrid').addEventListener('change',event=>{const checkbox=event.target.closest('[data-exclusion-level]');if(checkbox){exclusionDraft[checkbox.dataset.exclusionLevel]=checkbox.checked;renderExclusions();}});
 $('resetExclusions').addEventListener('click',()=>{exclusionDraft={...DEFAULT_EXCLUSION_LEVELS};exclusionCustomDraft=[...DEFAULT_EXCLUSION_TERMS];renderExclusions();$('exclusionPreviewResult').textContent='Padrões restaurados. Clique em Salvar preferências para aplicar.'});
 $('exclusionPreviewForm').addEventListener('submit',previewExclusion);
 $('saveSettingsBtn').addEventListener('click',saveSettings);$('resumeSaveSettings').addEventListener('click',saveSettings);
 $('resumeLayoutEditor').addEventListener('click',e=>{const btn=e.target.closest('[data-resume-order]');if(btn)moveResumeSection(Number(btn.dataset.resumeIndex),btn.dataset.resumeOrder==='up'?-1:1)});
 $('resumeLayoutEditor').addEventListener('input',updateResumePagePreview);
 $('resumeFieldsPt').addEventListener('input',updateResumePagePreview);$('resumeFieldsEn').addEventListener('input',updateResumePagePreview);
 $('resumeLayoutEditor').addEventListener('change',updateResumePagePreview);
 $('resumePreviewLanguage').addEventListener('change',updateResumePagePreview);
 $('resumeResetLayout').addEventListener('click',resetResumeLayout);
 $('resumeFont').addEventListener('change',updateResumePagePreview);$('resumeAccent').addEventListener('input',updateResumePagePreview);$('resumeDefaultLanguage').addEventListener('change',()=>{$('resumePreviewLanguage').value=$('resumeDefaultLanguage').value;updateResumePagePreview()});
 for(const id of [...Object.values(RESUME_CONTACT_FIELDS),'resumeMaxSkills','resumeMaxBullets','resumeIncludeProjects','resumeIncludeCertifications','resumeIncludeLanguages'])$(id).addEventListener('input',updateResumePagePreview);
 $('resumeLanguage').addEventListener('change',updateResumePreview);$('resumeConfigureBtn').addEventListener('click',()=>{closeDialog('resumeDialog');showPage('config');showConfigTab('resume')});
 $('resumeDownloadPt').addEventListener('click',()=>location.href='/api/resume/template?lang=pt');$('resumeDownloadEn').addEventListener('click',()=>location.href='/api/resume/template?lang=en');$('aiSearchBtn').addEventListener('click',searchAI);$('saveAiKeyBtn').addEventListener('click',saveAIKey);$('testAiKeyBtn').addEventListener('click',testAIKey);$('clearAiKeyBtn').addEventListener('click',clearAIKey);
 for(const id of ['appliedSearch','appliedStatus','appliedCompany','appliedMode','appliedFollowup','appliedFrom','appliedTo','appliedSort','appliedIncludeBlocked'])$(id).addEventListener('input',renderApplications);
 $('appliedReset').addEventListener('click',resetApplicationFilters);$('appliedToggle').addEventListener('click',()=>{const body=$('appliedFiltersBody');const willOpen=body.hidden;body.hidden=!willOpen;$('appliedToggle').setAttribute('aria-expanded',String(willOpen));$('appliedToggle').textContent=(willOpen?'Ocultar':'Mostrar')+' filtros '+(willOpen?'▴':'▾')});
 $('menuCustomizer').addEventListener('input',e=>{const label=e.target.closest('[data-menu-label]'),title=e.target.closest('[data-page-title]'),visible=e.target.closest('[data-menu-visible]');if(label){const item=menuDraft.find(x=>x.id===label.dataset.menuLabel);if(item)item.label=label.value}if(title)titleDraft[title.dataset.pageTitle]=title.value;if(visible){const item=menuDraft.find(x=>x.id===visible.dataset.menuVisible);if(item)item.visible=visible.checked}});
 document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d)d.close()}));$('confirmActionBtn').addEventListener('click',async()=>{if(confirmActionHandler)await confirmActionHandler()});
 $('refreshAiModelsBtn').addEventListener('click',refreshFreeModels);
 refresh().then(refreshExecutions);
 setInterval(async()=>{if(!document.hidden){await refreshExecutions();if(db.scan?.running||db.scan?.ai_running)await refresh(true)}},1700);
}
document.addEventListener('DOMContentLoaded',setup);

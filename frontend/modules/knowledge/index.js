import {api, all, escape as e} from '../../shared/api.js';
import {state, runtime, notice} from '../../shared/context.js';
import {badge, field, area, button, head, empty, modal, date} from '../../shared/ui.js';

let previewResult = null;
const typeOptions = selected => `<label>Type<select name="document_type" aria-label="Type">${['service','case_study','experience','other'].map(type=>`<option value="${type}" ${type===selected?'selected':''}>${type.replaceAll('_',' ')}</option>`).join('')}</select></label>`;
const demoField = value => `<label>Material<select name="demo" aria-label="Material"><option value="false" ${!value?'selected':''}>Real agency facts</option><option value="true" ${value?'selected':''}>Fictional demo — for testing</option></select></label>`;

export async function knowledgeView(id){
  if(!state.agency)return empty('Add your agency first','Knowledge belongs to your agency.');
  const rows=await all('/knowledge?include_inactive=true');
  if(rows.some(row=>['queued','running'].includes(row.index_status)))runtime.timer=setTimeout(()=>runtime.render(),1500);
  let detail='';
  if(id){
    const row=await api(`/knowledge/${id}`),v=row.current_version;
    const job=row.index_job_id?await api(`/jobs/${row.index_job_id}`):null;
    detail=`<section class="card spaced"><div class="card-top"><h2>${e(v.title)}</h2>${badge(`Version ${v.version}`)}</div><p class="hint">${v.demo?'Fictional demo material. ':''}${row.approved?'Approved':'Needs your review'} · ${e(row.index_status.replaceAll('_',' '))} · ${row.index_status==='completed'?'Ready to use':'Not ready yet'}</p><details><summary>View document</summary><pre>${e(v.text)}</pre></details>${job?.errors.length?`<p class="hint">${job.errors.map(error=>e(error.message)).join(' ')}</p>`:''}<div class="actions">${button('Edit','knowledge-edit',id)}${row.approved?button('Remove approval','knowledge-unapprove',id):button('Review & approve','knowledge-approve',id)}${row.active&&row.approved&&!['queued','running'].includes(row.index_status)?button('Prepare for use','knowledge-index',id,'primary'):''}${['queued','running'].includes(row.index_status)?button('Cancel indexing','cancel-job',row.index_job_id):''}${button(row.active?'Archive':'Activate','knowledge-toggle',id)}</div><details><summary>Version history (${row.versions.length})</summary>${row.versions.map(version=>`<p>Version ${version.version}: ${e(version.title)} · ${e(date(version.created_at))}${version.demo?' · Demo':''}</p>`).join('')}</details></section>`;
  }
  const groups = new Map();
  for(const source of previewResult?.sources||[]){if(!groups.has(source.document_id))groups.set(source.document_id,[]);groups.get(source.document_id).push(source);}
  const results=previewResult?`<section class="card spaced"><h2>Knowledge preview</h2><p>${previewResult.sources.length?`${groups.size} relevant document${groups.size===1?'':'s'} found.`:'No relevant approved knowledge found.'}</p><details><summary>View sources (${previewResult.sources.length} passages)</summary>${[...groups.values()].map(items=>`<article><h3>${e(items[0].title)} ${items[0].demo?badge('Fictional demo',true):''}</h3>${items.map(source=>`<p>${e(source.text)}</p><small>Version ${source.version} ? ${(source.similarity*100).toFixed(1)}% text similarity</small>`).join('')}</article>`).join('')}<p class="hint">These are source passages. Similarity does not prove this experience applies to a particular company.</p></details>${previewResult.excluded_incompatible?'<p class="hint">Some documents need preparing again before use.</p>':''}</section>`:'';
  return head('Agency knowledge','Save your services and past experience for preparing outreach.',`<div class="actions">${button('Add knowledge','knowledge-add','','primary')}${button('Upload text','knowledge-upload')}</div>`)+`<section class="card"><p>Save your facts, review them, then prepare them for use. Editing requires a fresh review.</p><details><summary>Advanced: test knowledge search</summary><p class="hint">Optional preview of the facts that outreach can use.</p>${button('Try retrieval','knowledge-preview')}</details></section>`+detail+(rows.length?`<div class="grid spaced">${rows.map(row=>`<section class="card"><div class="card-top"><h3>${e(row.current_version.title)}</h3>${badge(row.active?'Active':'Archived',!row.active)}</div><p class="hint">${e(row.current_version.document_type.replaceAll('_',' '))} ? Version ${row.current_version.version}${row.current_version.demo?' ? Fictional demo':''}</p><p>${row.approved?'Approved':'Needs review'} ? ${row.index_status==='completed'?'Ready to use':e(row.index_status.replaceAll('_',' '))}</p>${button('View & manage','knowledge-open',row.id)}</section>`).join('')}</div>`:empty('No knowledge saved yet','Add an honest service description or case study.'))+results;
}

export async function knowledgeAction(name,id){
  if(name==='knowledge-open'){location.hash=`knowledge/${id}`;return;}
  if(name==='knowledge-add'||name==='knowledge-edit'){
    const row=id?await api(`/knowledge/${id}`):null,v=row?.current_version||{};
    return modal(id?'Edit knowledge':'Add agency knowledge',field('title','Title',v.title,'text',true)+typeOptions(v.document_type)+demoField(v.demo)+area('text','Agency facts',v.text,true)+`<p class="hint full">Use your own facts. Saving leaves this version unapproved so you can review it first.</p>`,async f=>{
      const saved=await api(`/knowledge${id?'/'+id:''}`,{method:id?'PATCH':'POST',revision:row?.revision,body:{...f,demo:f.demo==='true'}});
      previewResult=null;location.hash=`knowledge/${saved.id}`;
    });
  }
  if(name==='knowledge-upload')return modal('Upload agency knowledge',field('title','Title','','text',true)+typeOptions('other')+demoField(false)+`<label class="full">UTF-8 text file (up to 1 MB)<input name="file" type="file" accept=".txt,text/plain" required></label>`,async f=>{
    const body=new FormData();for(const [key,value] of Object.entries(f))body.append(key,value);
    const saved=await api('/knowledge/uploads',{method:'POST',body});previewResult=null;location.hash=`knowledge/${saved.id}`;
  });
  if(name==='knowledge-preview')return modal('Find relevant agency facts',area('query_text','Describe the company or its needs',previewResult?.query_text||'',true)+`<label>Relevant service (optional)<select name="service_id" aria-label="Relevant service (optional)"><option value="">No service selected</option>${state.services.filter(s=>s.active).map(s=>`<option value="${e(s.id)}">${e(s.name)}</option>`).join('')}</select></label><label>Fictional demo material<select name="include_demo" aria-label="Fictional demo material"><option value="false">Exclude demo material</option><option value="true">Include demo material for testing</option></select></label><p class="hint full">Only current, active, approved documents with completed compatible indexes can appear. Keep the query short.</p>`,async f=>{
    previewResult=await api('/knowledge/retrieval-preview',{method:'POST',body:{query_text:f.query_text,service_id:f.service_id||null,include_demo:f.include_demo==='true'}});
    location.hash='knowledge';
  },'Find sources');
  const row=await api(`/knowledge/${id}`);
  if(name==='knowledge-approve')return modal('Review this version',`<p class="full">${e(row.current_version.title)}${row.current_version.demo?' — Fictional demo':''}</p><pre class="full">${e(row.current_version.text)}</pre><p class="hint full">Approve only if the facts are accurate, or clearly marked as a fictional demo.</p>`,async()=>{
    await api(`/knowledge/${id}`,{method:'PATCH',revision:row.revision,body:{approved:true}});previewResult=null;
  },'Approve this version');
  if(name==='knowledge-index'){
    await api(`/knowledge/${id}/index-jobs`,{method:'POST',key:crypto.randomUUID(),body:{version_id:row.current_version.id}});
    previewResult=null;notice('Indexing queued. The worker will prepare the passages.');
  }else{
    await api(`/knowledge/${id}`,{method:'PATCH',revision:row.revision,body:name==='knowledge-toggle'?{active:!row.active}:{approved:false}});
    previewResult=null;
  }
  await runtime.render();
}

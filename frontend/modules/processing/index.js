import {api, all, escape as e} from '../../shared/api.js';
import {state, stages, dialog, runtime, notice} from '../../shared/context.js';
import {badge, metric, select, button, date, list, head, empty, readable, modal} from '../../shared/ui.js';
import {businessView} from '../nlp/index.js';
import {scoreView} from '../scoring/index.js';
import {evidenceView} from '../evidence/index.js';
import {visualView} from '../computer_vision/index.js';
import {semanticView} from '../semantics/index.js';
import {outreachSection} from '../outreach/index.js';

export async function researchForm(id){
  const l=await api(`/leads/${id}`);const key=crypto.randomUUID();let receipt=null;let uploaded=null;
  modal(`Research ${l.company_name}`,`<label class="full">Evidence source<select name="mode" id="source-mode"><option value="live">Live website — collect text and screenshot</option><option value="uploaded">Saved files — upload text and/or screenshot</option><option value="cached">Cached files — previously collected website evidence</option></select></label><p class="hint full">Live research reads ${e(l.website)}. Some websites block collection; saved files are an alternative. The worker must be running.</p><div class="full" id="saved-fields" hidden><label>Website text (.txt, UTF-8, at most 1 MB)<input name="text_file" type="file" accept=".txt"></label><label>Website screenshot (PNG/JPEG, at most 10 MB)<input name="image_file" type="file" accept=".png,.jpg,.jpeg"></label><p class="hint">Upload at least one file. Use a real website screenshot and readable website text.</p></div><label class="full"><input name="supporting" type="checkbox">Also collect supporting pages during live research</label>`,async f=>{
    const body={mode:f.mode,include_supporting_pages:f.mode==='live'&&f.supporting==='on'};
    if(f.mode!=='live'){
      if(!uploaded){const form=new FormData();form.append('source_mode',f.mode);form.append('original_url',l.website);let files=0;for(const name of ['text_file','image_file'])if(f[name]?.size){form.append(name,f[name]);files++;}if(!files)throw new Error('Choose at least one saved file.');uploaded=await api(`/leads/${id}/saved-evidence`,{method:'POST',body:form});}
      body.upload_token=uploaded.upload_token;
    }
    receipt=await api(`/leads/${id}/analysis-jobs`,{method:'POST',body,key});location.hash=`lead/${id}`;notice('Research queued. Progress will appear below.');
  },'Start research');
  document.querySelector('#source-mode').onchange=event=>{document.querySelector('#saved-fields').hidden=event.target.value==='live';uploaded=null;};
}

export async function leadView(id,runId){
  const [l,history]=await Promise.all([api(`/leads/${id}`),api(`/leads/${id}/runs?page_size=100`)]);
  const run=runId?await api(`/runs/${runId}`):history.items[0];
  if(run&&run.lead_id!==id)throw new Error('This research attempt belongs to another company. Open it from that company’s history.');
  let evidence=[];if(run)evidence=(await api(`/runs/${run.id}/evidence?page_size=100`)).items;
  const job=run?.job;const active=job&&['queued','running'].includes(job.status);
  if(active){const poll=()=>{if(!location.hash.startsWith(`#lead/${id}`))return;if(dialog.open)runtime.timer=setTimeout(poll,2500);else runtime.render();};runtime.timer=setTimeout(poll,2500);}
  const campaign=state.campaigns.find(c=>c.id===l.campaign_id);
  const outreach=await outreachSection(id);
  return `<p class="eyebrow"><a href="#leads">← COMPANIES & RESEARCH</a></p>`+head(l.company_name,`${campaign?.name||'Campaign'} · ${l.website}`,`<div class="actions">${button('Edit details','lead',id)}${button('Start research','research',id,'primary')}</div>`)+`<div class="grid"><section class="card"><h2>Company details</h2>${metric('Industry',l.industry)}${metric('Country',l.country)}${metric('Employees',l.employee_count)}${metric('Contact',l.contact_email)}${metric('Pipeline',l.pipeline_state)}<p class="hint spaced">These facts were entered by you. Extracted facts appear in the research results.</p>${l.notes?`<p>${e(l.notes)}</p>`:''}<div class="actions">${button('Correction history','facts',id)}${button('Delete company','delete',id,'quiet danger')}</div></section>${scoreView(run?.score_result||l.score_detail)}</div>${job?`<section class="card spaced"><div class="card-top"><h2>${active?'Research in progress':'Research attempt'}</h2>${badge(job.status,['partial','cancelled'].includes(job.status),job.status==='failed')}</div><p class="hint">${e(stages[job.current_stage]||'Saved research results')} · ${job.progress.finished_stages} of ${job.progress.total_stages} stages · ${e(date(run.created_at))}</p><progress value="${job.progress.finished_stages}" max="${job.progress.total_stages}" aria-label="Research progress"></progress><div class="stage-list">${job.stages.map(s=>badge(`${stages[s.name]||s.name}: ${s.state}`,!['completed','succeeded'].includes(s.state),s.state==='failed')).join('')}</div>${job.errors.map(err=>`<p class="hint">${e(stages[err.stage]||err.stage)}: ${e(err.message)} <code>${e(err.code)}</code></p>`).join('')}${job.warnings.length?`<details><summary>Research warnings (${job.warnings.length})</summary>${job.warnings.map(w=>`<p class="hint">${e(w)}</p>`).join('')}</details>`:''}<div class="actions">${active?button('Cancel research','cancel-job',job.id):button('Run another attempt','research',id)}</div></section>`:empty('Ready for your first research run','Start research to collect website evidence and analyze this company.')}<div class="grid spaced">${businessView(run?.business_analysis)}${semanticView(run?.semantic_result)}${visualView(run?.visual_analysis)}</div><div class="page-head spaced"><h2>Website evidence</h2>${badge(`${evidence.length} saved sources`)}</div>${evidenceView(evidence,l.company_name)}<section class="card spaced"><h2>Research history</h2><p class="hint">Each attempt keeps its own inputs, evidence and results. Showing up to 100 recent attempts.</p>${history.items.map(r=>`<div class="health-row"><div><a href="#lead/${id}/${r.id}">${e(date(r.created_at))} · ${e(r.evidence_mode)}</a><small>${r.is_current?'Current inputs':'Historical or outdated inputs'}</small></div>${badge(r.job.status,r.job.status==='partial')}</div>`).join('')||'<p class="muted">No attempts yet.</p>'}</section>`+outreach;
}

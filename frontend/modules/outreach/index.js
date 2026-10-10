import {api, escape as e} from '../../shared/api.js';
import {state, runtime, notice} from '../../shared/context.js';
import {button, badge, field, area, select, modal, date} from '../../shared/ui.js';

export async function outreachSection(leadId){
  const result=await api(`/leads/${leadId}/drafts`);
  const jobs=await api(`/leads/${leadId}/outreach-status`);
  const active=jobs.job&&['queued','running'].includes(jobs.job.status);
  if(active)runtime.timer=setTimeout(()=>runtime.render(),1500);
  return `<section class="card spaced"><div class="card-top"><h2>Outreach drafts</h2>${button('Prepare draft','outreach-prepare',leadId,'primary')}</div><p class="hint">Prepare a message using company research and your agency facts, then review it before copying.</p>${active?`<p>${badge('Preparing draft')}</p>${button('Cancel preparation','cancel-job',jobs.job.id)}`:jobs.job?.errors.length?`<p class="hint">${jobs.job.errors.map(x=>e(x.message)).join(' ')}</p>${button('Try again','outreach-prepare',leadId)}`:''}${result.items.map(d=>{const r=d.current_revision;return `<article class="step"><div><h3>${e(r.subject)}</h3><p>${badge(r.state)} ${d.provenance.method==='service_template'?badge('Basic service introduction',true):''} ${d.stale_reasons.length?badge('Sources changed — prepare a new draft',true):''}</p>${d.provenance.method==='service_template'?'<p class="hint">The AI response could not be validated. This introduction uses your saved service description and still needs your review.</p>':''}<p class="draft-body">${e(r.body).replaceAll('\n','<br>')}</p>${r.unresolved_claims.length?`<p class="hint">${r.unresolved_claims.map(e).join(' ')}</p>`:''}<div class="actions">${button('Edit','outreach-edit',d.id)}${button('Review','outreach-review',d.id)}${r.state==='Approved'?button('Copy approved text','outreach-copy',d.id,'primary'):''}</div><details><summary>View sources and factual claims</summary><p class="hint">Check meaning as well as quotes. A matching quote alone does not prove a claim.</p>${r.claims.map(c=>`<p><strong>${e(c.text)}</strong><br>Source: ${e(d.sources.find(s=>s.source_id===c.source_id)?.title||'Unresolved')}<br>“${e(c.quote)}”</p>`).join('')}${d.sources.map(s=>`<details><summary>${e(s.title)}</summary><p>${e(s.text)}</p></details>`).join('')}</details><details><summary>Revision history (${d.history.length})</summary>${d.history.map(h=>`<details><summary>${e(h.state)} · ${e(date(h.created_at))}${h.reviewer?` · ${e(h.reviewer)}`:''}</summary><h4>${e(h.subject)}</h4><p>${e(h.body)}</p>${h.reason?`<p>${e(h.reason)}</p>`:''}</details>`).join('')}</details></div></article>`;}).join('')||'<p>No drafts yet. Complete company research, then prepare your first message.</p>'}</section>`;
}

export async function outreachAction(name,id){
  if(name==='outreach-prepare'){
    const services=state.services.filter(s=>s.active);
    if(!services.length)return notice('Add an active agency service first.');
    return modal('Prepare outreach',select('service_id','Service to offer',services)+`<label class="full"><input name="limited" type="checkbox">If business analysis is missing, use my saved company description and show a limited-context warning.</label><p class="hint full">Only current research and approved real agency knowledge are used. This creates a draft for review.</p>`,async f=>{
      await api(`/leads/${id}/outreach-jobs`,{method:'POST',key:crypto.randomUUID(),body:{service_id:f.service_id,acknowledge_missing_analysis:f.limited==='on'}});
      notice('Preparing your draft. It will appear below when ready.');
    },'Prepare draft');
  }
  const d=await api(`/drafts/${id}`),r=d.current_revision;
  if(name==='outreach-edit'){
    const claims=[...r.claims,{text:'',source_id:'',quote:''}];
    const mappings=claims.map((c,i)=>area(`claim_${i}`,'Factual statement',c.text)+`<label>Supporting source<select name="source_${i}"><option value="">Choose a source</option>${d.sources.map(s=>`<option value="${e(s.source_id)}" ${s.source_id===c.source_id?'selected':''}>${e(s.title)}</option>`).join('')}</select></label>`+area(`quote_${i}`,'Exact supporting excerpt',c.quote)).join('');
    return modal('Edit outreach draft',field('subject','Subject',r.subject,'text',true)+area('body','Message',r.body,true)+`<details class="full"><summary>Factual statements and supporting sources</summary><p class="hint">If you change a factual statement, update its wording here and copy an exact excerpt from a source. Remove claims you removed from the message.</p>${mappings}</details>`,async f=>{
      const updated=claims.map((_,i)=>({text:f[`claim_${i}`].trim(),source_id:f[`source_${i}`],quote:f[`quote_${i}`].trim()})).filter(c=>c.text);
      await api(`/drafts/${id}/revisions`,{method:'POST',revision:d.revision,body:{subject:f.subject,body:f.body,claims:updated}});
    },'Save new revision');
  }
  if(name==='outreach-review')return modal('Review outreach draft',`<p class="full"><strong>${e(r.subject)}</strong></p><p class="full">${e(r.body).replaceAll('\n','<br>')}</p>${r.claims.map(c=>`<p class="full">Claim: ${e(c.text)}<br>Source: ${e(d.sources.find(s=>s.source_id===c.source_id)?.title||'Unresolved')}<br>Excerpt: ${e(c.quote)}</p>`).join('')}<label>Decision<select name="decision"><option>Approved</option><option>Rejected</option></select></label>`+field('reviewer','Your name','','text',true)+area('reason','Reason (required for rejection)')+`<label class="full"><input name="ack" type="checkbox">I checked all factual claims against their sources and reviewed the message. Approval does not send it.</label>`,async f=>{
    await api(`/drafts/${id}/review`,{method:'POST',revision:d.revision,body:{decision:f.decision,reviewer:f.reviewer,reason:f.reason||null,factual_review_acknowledged:f.ack==='on'}});
  },'Save review');
  if(name==='outreach-copy'){
    const text=await api(`/drafts/${id}/approved-text`);
    if(text.stale_reasons.length)return modal('Approved text — sources have changed',area('text','Saved approved text',`${text.subject}\n\n${text.body}`)+`<p class="hint full">Prepare and review a new draft before using this historical text.</p>`,async()=>{},'Close');
    try{await navigator.clipboard.writeText(`${text.subject}\n\n${text.body}`);notice('Approved text copied. No message was sent.');}
    catch{return modal('Copy approved text',area('text','Select and copy',`${text.subject}\n\n${text.body}`),async()=>{},'Close');}
  }
}

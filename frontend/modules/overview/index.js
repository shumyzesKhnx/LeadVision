import {api, escape as e} from '../../shared/api.js';
import {state, runtime} from '../../shared/context.js';
import {badge, button, num} from '../../shared/ui.js';

export function healthView() {
  const names={database:'Database',worker:'Research worker',ollama:'Local AI runtime',generation_model:'Business analysis model',embedding_model:'Similarity model'};
  return `<section class="card"><h2>System readiness</h2>${state.health?Object.entries(names).map(([key,label])=>`<div class="health-row"><div>${label}<small>${e(state.health[key]?.message)}</small></div>${badge(state.health[key]?.status||'Unknown',!['ready','available'].includes(state.health[key]?.status))}</div>`).join('')+`<small class="spaced">Backend ${e(state.health.version)} · Schema ${e(state.health.schema_version)}</small>`:'<p class="muted">Health check unavailable. Refresh to try again.</p>'}</section>`;
}

export async function overview() {
  const leads=state.agency?await api('/leads?page_size=1'): {total:0};
  return `<section class="hero"><p class="eyebrow">FROM COMPANIES TO CLARITY</p><h1>Your next client starts<br>with better research.</h1><p>Define who you want to work with, add companies, and review what their websites tell you. Everything in one place.</p><div class="actions"><a class="button primary" href="#leads">Explore your companies →</a><a class="button quiet" href="#flow">See how it works</a></div></section><div class="grid stats">${[['Agency',state.agency?1:0,'agency'],['Active services',state.services.filter(x=>x.active).length,'agency'],['Campaigns',state.campaigns.filter(x=>!x.archived).length,'campaigns'],['Companies',leads.total,'leads']].map(([label,n,route])=>`<a class="card" href="#${route}"><small>${label}</small><strong class="stat-number">${n}</strong><small>View details ↗</small></a>`).join('')}</div><div class="grid"><section class="card"><h2>Your research journey</h2>${[['Agency & services','Explain your business and what you offer.','agency'],['Customer profile (ICP)','Describe your ideal client.','profiles'],['Campaign','Group companies with the same target profile.','campaigns'],['Companies & research','Add websites, run research, then review the evidence and score.','leads']].map(([title,text,route],i)=>`<a class="step" href="#${route}"><span class="step-num">${i+1}</span><div><h3>${title}</h3><p>${text}</p></div></a>`).join('')}</section>${healthView()}</div>`;
}

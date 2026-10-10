// Entry point: navigation and connecting feature screens.
import {content} from './shared/context.js';
import {load} from './shared/data.js';
import {api, errorText} from './shared/api.js';
import {state, runtime, notice} from './shared/context.js';
import {button, empty} from './shared/ui.js';
import {overview} from './modules/overview/index.js';
import {agencyView, agencyForm, serviceForm} from './modules/agency/index.js';
import {profilesView, profileForm} from './modules/icp/index.js';
import {campaignsView, campaignForm} from './modules/campaigns/index.js';
import {leadsView, leadForm, importForm, leadAction} from './modules/leads/index.js';
import {researchForm, leadView} from './modules/processing/index.js';
import {flowView} from './modules/flow/index.js';
import {reviewEvidence} from './modules/evidence/index.js';
import {knowledgeView, knowledgeAction} from './modules/knowledge/index.js';
import {outreachAction} from './modules/outreach/index.js';

let generation = 0;

async function action(name,id){
  if(name.startsWith('outreach-'))return outreachAction(name,id);
  if(name.startsWith('knowledge-'))return knowledgeAction(name,id);
  if(name==='agency')return agencyForm();if(name==='service')return serviceForm(id);if(name==='profile')return profileForm(id);if(name==='campaign')return campaignForm(id);if(name==='lead')return leadForm(id);if(name==='import')return importForm();if(name==='research')return researchForm(id);
  if(name==='lead-open'){location.hash=`lead/${id}`;return;}
  if(name==='campaign-open'){state.campaign=id;state.page=1;location.hash='leads';if(location.hash==='#leads')await render();return;}
  if(name==='next'||name==='previous'){state.page+=name==='next'?1:-1;await render();return;}
  if(['service-toggle','profile-toggle','campaign-toggle'].includes(name)){
    const kind=name.split('-')[0];const rows=kind==='service'?state.services:kind==='profile'?state.profiles:state.campaigns;const row=rows.find(x=>x.id===id);
    await api(`/${kind==='profile'?'icps':kind==='service'?'services':'campaigns'}/${id}`,{method:'PATCH',revision:row.revision,body:kind==='service'?{active:!row.active}:{archived:!row.archived}});
    await load();await render();return;
  }
  if(['delete','facts'].includes(name))return leadAction(name,id);
  if(name==='cancel-job'){await api(`/jobs/${id}/cancel`,{method:'POST',body:{}});await render();return;}
  if(name==='evidence-review')return reviewEvidence(id);
}

async function render(){
  clearTimeout(runtime.timer);const current=++generation;const [route,id,runId]=(location.hash.slice(1)||'overview').split('/');
  const title={overview:'Overview',agency:'Agency & services',profiles:'Customer profiles',campaigns:'Campaigns',leads:'Companies & research',lead:'Company research',knowledge:'Agency knowledge',flow:'How it works'}[route]||'Overview';
  document.querySelector('#location').textContent=title;document.title=`${title} · Lead Vision`;
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.hash===`#${route==='lead'?'leads':route}`));
  try{
    const html=route==='agency'?agencyView():route==='profiles'?profilesView():route==='campaigns'?campaignsView():route==='leads'?await leadsView():route==='lead'?await leadView(id,runId):route==='knowledge'?await knowledgeView(id):route==='flow'?flowView():await overview();
    if(current!==generation)return;content.innerHTML=html;
    const filters=document.querySelector('#filters');if(filters)filters.onsubmit=event=>{event.preventDefault();const f=Object.fromEntries(new FormData(filters));Object.assign(state,{campaign:f.campaign,query:f.query,priority:f.priority,page:1});render();};
  }catch(error){if(current===generation)content.innerHTML=empty('Could not load this screen',errorText(error),'<button data-action="refresh">Try again</button>');}
}

content.addEventListener('click',async event=>{const target=event.target.closest('[data-action]');if(!target)return;target.disabled=true;try{if(target.dataset.action==='refresh'){await load();await render();}else await action(target.dataset.action,target.dataset.id);}catch(error){notice(errorText(error));}finally{target.disabled=false;}});
document.querySelector('#refresh').onclick=async()=>{try{await load();await render();notice('Workspace refreshed.');}catch(error){notice(errorText(error));}};
window.addEventListener('hashchange',()=>{notice('');render();});
runtime.load=load;runtime.render=render;
try{await load();await render();}catch(error){content.innerHTML=empty('Cannot open the workspace',errorText(error));}

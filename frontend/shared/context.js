export const content = document.querySelector('#content');
export const dialog = document.querySelector('#dialog');
export const state = {agency:null, services:[], profiles:[], campaigns:[], health:null, campaign:'', query:'', priority:'', page:1};
export const stages = {validate_inputs:'Check inputs', acquire_text:'Collect website text', acquire_image:'Capture screenshot', preprocess_text:'Prepare text', business_analysis:'Business analysis', visual_metrics:'Visual measurements', semantic_match:'Compare with your target', score:'Calculate score', finalize:'Save results'};
export const runtime = {load:null, render:null, timer:null};
export function notice(message) {
  const node=document.querySelector('#notice'); node.replaceChildren();
  if(!message)return;
  const close=document.createElement('button');close.className='notice-close';close.textContent='×';close.setAttribute('aria-label','Dismiss message');close.onclick=()=>notice('');
  node.append(close,document.createTextNode(message));
}

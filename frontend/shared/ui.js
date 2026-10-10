import {escape as e, errorText} from './api.js';
import {dialog, runtime} from './context.js';

export const badge = (text, warn=false, bad=false) => `<span class="badge ${bad?'bad':warn?'warn':''}">${e(text)}</span>`;
export const metric = (name,value) => `<div class="metric"><span class="muted">${e(name)}</span><span>${e(value ?? 'Unknown')}</span></div>`;
export const field = (name,label,value='',type='text',required=false) => `<label>${e(label)}<input name="${name}" type="${type}" value="${e(value)}" ${required?'required':''} ${type==='number'?'min="0" step="1"':''}></label>`;
export const area = (name,label,value='',required=false) => `<label class="full">${e(label)}<textarea name="${name}" aria-label="${e(label)}" ${required?'required':''}>${e(value)}</textarea></label>`;
export const options = (items,selected,label='name') => items.map(item=>`<option value="${e(item.id)}" ${item.id===selected?'selected':''}>${e(item[label])}${item.archived?' (archived)':''}</option>`).join('');
export const select = (name,label,items,selected) => `<label>${e(label)}<select name="${name}" required>${options(items,selected)}</select></label>`;
export const button = (label,action,id='',style='quiet') => `<button class="${style}" data-action="${action}" data-id="${e(id)}">${e(label)}</button>`;
export const date = value => value ? new Date(value).toLocaleString() : 'Unknown';
export const num = value => typeof value==='number' ? value.toFixed(1) : '—';
export const list = text => text.split(',').map(v=>v.trim()).filter(Boolean);

export function head(title,subtitle,action='') {return `<div class="page-head"><div><p class="eyebrow">YOUR WORKSPACE</p><h1>${e(title)}</h1><p>${e(subtitle)}</p></div>${action}</div>`;}

export function empty(title,text,action='') {return `<div class="empty"><h2>${e(title)}</h2><p>${e(text)}</p>${action}</div>`;}

export function readable(value){if(value===null||value===undefined)return 'Unknown';if(typeof value==='object')return Array.isArray(value)?value.map(readable).join(', '):Object.entries(value).map(([k,v])=>`${k.replaceAll('_',' ')}: ${readable(v)}`).join(' · ');return String(value);}

export function measurements(title,data,help){
  const r=data?.result;let body='<p class="muted">No result available yet.</p>';
  if(r&&!r.available)body=`<p class="hint">Unavailable: ${e(r.reason||'Missing evidence')}</p>`;
  else if(r?.normalized_similarity!==undefined)body=`<p class="value">${num(r.normalized_similarity)} <span class="hint">/ 100 similarity</span></p><p class="hint">${e(r.interpretation)}</p>`;
  else if(r?.metrics){const m=r.metrics;body=metric('Screenshot dimensions',`${m.original_width} × ${m.original_height}`)+metric('Average brightness',`${Math.round(m.brightness_mean*100)}%`)+metric('Edge density',`${(m.edge_density*100).toFixed(1)}%`)+metric('Areas with little variation',`${Math.round(m.low_variation_area_fraction*100)}%`)+`<details><summary>Technical measurements</summary>${Object.entries(m).map(([k,v])=>metric(k.replaceAll('_',' '),readable(v))).join('')}</details>`;}
  return `<section class="card"><h2>${e(title)}</h2><p class="hint">${e(help)}</p>${body}</section>`;
}

export function modal(title,fields,submit,submitLabel='Save'){
  document.querySelector('#dialog-body').innerHTML=`<div class="dialog-head"><h2>${e(title)}</h2><button type="button" id="close-dialog" aria-label="Close form">×</button></div><form id="edit-form"><div class="form-grid">${fields}</div><div class="form-error" role="alert"></div><div class="actions"><button class="primary" type="submit">${e(submitLabel)}</button><button type="button" id="cancel-dialog" class="quiet">Cancel</button></div></form>`;
  dialog.showModal();
  document.querySelector('#close-dialog').onclick=document.querySelector('#cancel-dialog').onclick=()=>dialog.close();
  document.querySelector('#edit-form').onsubmit=async event=>{
    event.preventDefault();const form=event.currentTarget;const controls=[...form.querySelectorAll('button')];controls.forEach(b=>b.disabled=true);
    try{await submit(Object.fromEntries(new FormData(form)),form);dialog.close();await runtime.load();await runtime.render();}
    catch(error){form.querySelector('.form-error').textContent=errorText(error);}
    finally{controls.forEach(b=>b.disabled=false);}
  };
}

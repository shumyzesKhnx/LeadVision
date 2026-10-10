import {api, all} from './api.js';
import {state} from './context.js';

export async function load() {
  const health = api('/health').then(v=>state.health=v).catch(()=>state.health=null);
  try {state.agency=await api('/agency');} catch(error) {if(error.status!==404)throw error;state.agency=null;}
  if(state.agency) [state.services,state.profiles,state.campaigns]=await Promise.all([all('/services?include_inactive=true'),all('/icps?include_archived=true'),all('/campaigns?include_archived=true')]);
  else state.services=state.profiles=state.campaigns=[];
  await health;
}

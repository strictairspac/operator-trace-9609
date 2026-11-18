import {api,post} from './client.js';
export const datasets={list:()=>api('/datasets'),save:(d,id)=>post('/datasets'+(id?'/'+id:''),d,id?'PUT':'POST')};
export const plans={list:()=>api('/plans'),save:(d,id)=>post('/plans'+(id?'/'+id:''),d,id?'PUT':'POST')};
export const traces={list:()=>api('/traces'),run:d=>post('/traces',d),detail:id=>api('/traces/'+id)};
export const replays={
 list:()=>api('/replays'),
 detail:id=>api('/replays/'+id),
 precheck:(base_trace_id,target_trace_id)=>post('/replays/precheck',{base_trace_id,target_trace_id}),
 run:d=>post('/replays',d),
 resume:id=>post('/replays/'+id+'/resume',{}),
};

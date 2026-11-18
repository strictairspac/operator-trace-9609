import {store} from '../stores/business.js';
import {esc} from '../utils/html.js';
import {table} from '../components/common/table.js';
import {replays} from '../api/business.js';
import {feedback} from '../components/common/feedback.js';
import {REPLAY_JOB_STATUSES,REPLAY_TRIAL_STATUSES} from '../constants/enums.js';

const rstatus=s=>`<span class="status replay-${s}">${REPLAY_JOB_STATUSES[s]||s}</span>`;
const tstatus=s=>`<span class="status trial-${s}">${REPLAY_TRIAL_STATUSES[s]||s}</span>`;
let openDetailId=null;
let prefillTargetId=null;
export function prefillReplay(traceId){prefillTargetId=traceId;openDetailId=null;}

function traceOption(t,selectedId=null){return `<option value="${t.id}"${t.id===selectedId?' selected':''}>#${t.id} ${esc(t.name)}（${esc(t.plan_id?('计划'+t.plan_id):'')}）</option>`;}

export function replaysPage(){
 const canWrite=store.user.role!=='viewer';
 const completedOnly=store.traces.filter(t=>t.status==='completed');
 const baseDefault=completedOnly.find(t=>t.id!==prefillTargetId)?.id ?? completedOnly[0]?.id ?? null;
 return `<div class="split">
  <section>
   <h2>最少换掉哪些传感器的采样</h2>
   <p>从两次已完成存档取数；算子序列与传感器表相同才受理。每次整组替换候选传感器的采样，再用原算子试算，比对最终输出 SHA-256。</p>
   <form id="replay-form" ${canWrite?'':'aria-disabled'}>
    <label>试算名称<input name="name" required placeholder="课次复现-20261118" value="${prefillTargetId?('复现-存档'+prefillTargetId):''}" ${canWrite?'':'disabled'}></label>
    <label>前一次存档（基准）<select name="base_trace_id" ${canWrite?'':'disabled'}>${completedOnly.map(t=>traceOption(t,baseDefault)).join('')}</select></label>
    <label>后一次存档（复现目标）<select name="target_trace_id" ${canWrite?'':'disabled'}>${completedOnly.map(t=>traceOption(t,prefillTargetId)).join('')}</select></label>
    <button type="button" id="replay-precheck" class="quiet" ${canWrite?'':'disabled'}>预检受理条件</button>
    <div id="precheck-box" class="precheck" hidden></div>
    <button type="submit" ${canWrite?'':'disabled'}>发起试算 →</button>
   </form>
   <ol class="steps">
    <li>比对算子序列与传感器表，列出有改动的传感器（≤8）</li>
    <li>按替换数量从小到大枚举组合，最多 64 种，每个只扣一次额度</li>
    <li>整组替换后用原算子执行，校验最终输出 checksum</li>
    <li>更小组合未排除前只标「候选」，全部排除后才标「已证最小」</li>
   </ol>
  </section>
  <section>
   <h2>试算任务 <em>${store.replays.length}</em></h2>
   ${table(['任务 / 存档','状态','进度','动作'],store.replays.map(j=>[
     `<b>${esc(j.name)}</b><small>前 #${j.base_trace_id} → 后 #${j.target_trace_id}</small><small>改动传感器 ${(j.changed_sensor_ids||[]).map(esc).join(', ')||'无'}</small>`,
     rstatus(j.status),
     `<b>${j.executed_combinations} / ${j.total_combinations}</b><small>组合试算进度</small>${j.proven_sensor_ids?`<small class="ok">已证最小：${esc((j.proven_sensor_ids||[]).join(', '))}</small>`:j.candidate_sensor_ids?`<small class="warn">候选：${esc((j.candidate_sensor_ids||[]).join(', '))}（最小未证）</small>`:''}`,
     `<button class="quiet" data-replay-detail="${j.id}">查看组合 →</button>${(j.status==='failed'||j.status==='running')?` <button class="quiet" data-replay-resume="${j.id}">恢复试算 ↻</button>`:''}`
   ]))}
   <aside class="note">试算中断后，已完成组合不会重跑、不重复扣额度；点「恢复试算」把中断中的组合退回待试算并从原进度继续。64 种预算用尽仍未找到可复现组合时标记「预算耗尽」。</aside>
   <div id="replay-detail">${openDetailId!=null?detailPlaceholder(openDetailId):''}</div>
  </section>
 </div>`;
}

function detailPlaceholder(id){return `<div class="loading-detail" data-open-id="${id}"><small>正在载入任务 #${id} 的组合明细…</small></div>`;}

export function bindReplays(){
 const pc=document.getElementById('replay-precheck');
 pc?.addEventListener('click',async()=>{
  const f=document.getElementById('replay-form');
  const base=Number(f.elements.base_trace_id.value),target=Number(f.elements.target_trace_id.value);
  const box=document.getElementById('precheck-box');
  try{
   const r=await replays.precheck(base,target);
   box.hidden=false;
   box.className='precheck'+(r.admissible?' ok':' warn');
   box.innerHTML=`改动传感器 <b>${r.changed_count}</b> 个（上限 ${r.max_changed_sensors}）：${esc(r.changed_sensor_ids.join(', ')||'无')}<br>计划试算组合 <b>${r.planned_combinations}</b> 种（上限 ${r.max_combinations}）<br>${r.admissible?'<span class="ok">符合受理条件，可发起试算。</span>':'<span class="warn">改动传感器超过 8 个，不予受理。</span>'}`;
  }catch(e){box.hidden=false;box.className='precheck warn';box.textContent=e.message;}
 });
 document.getElementById('replay-form')?.addEventListener('submit',async e=>{
  e.preventDefault();
  const f=e.target,d=Object.fromEntries(new FormData(f));
  try{
   const r=await replays.run({name:d.name,base_trace_id:Number(d.base_trace_id),target_trace_id:Number(d.target_trace_id)});
   prefillTargetId=null;
   feedback('试算已入队，页面会自动刷新进度。');
   openDetailId=r.id;showDetail(r.id);
  }catch(err){feedback(err.message,true);}
 });
 document.querySelectorAll('[data-replay-detail]').forEach(b=>b.onclick=()=>{openDetailId=Number(b.dataset.replayDetail);showDetail(openDetailId);});
 document.querySelectorAll('[data-replay-resume]').forEach(b=>b.onclick=async()=>{
  try{await replays.resume(Number(b.dataset.replayResume));feedback('已从原进度恢复试算。');}
  catch(e){feedback(e.message,true);}
 });
 const pending=document.querySelector('.loading-detail');
 if(pending)showDetail(Number(pending.dataset.openId));
}

async function showDetail(id){
 const box=document.getElementById('replay-detail');
 if(!box)return;
 let d;
 try{d=await replays.detail(id);}catch(e){feedback(e.message,true);return;}
 store.replayDetail=d;
 const rows=(d.trials||[]).map(t=>[
   `#${t.combo_idx} <small>规模 ${t.set_size}</small>`,
   esc((t.sensor_ids||[]).length?('传感器 '+t.sensor_ids.join(', ')):'（不替换）'),
   tstatus(t.status),
   t.matched===1?'<span class="ok">✔ 复现一致</span>':t.matched===0?'<span class="muted">不一致</span>':'—',
   `<small>${t.attempts} 次尝试</small>${t.checksum?`<small class="checksum">${esc(t.checksum.slice(0,16))}…</small>`:''}`
 ]);
 box.innerHTML=`<h3>任务「${esc(d.name)}」组合明细 ${rstatus(d.status)}</h3>
  <div class="metrics">
   <div><small>已试算组合</small><strong>${d.executed_combinations}<em>/ ${d.total_combinations}</em></strong></div>
   <div><small>候选组合</small><strong>${esc((d.candidate_sensor_ids||[]).join(',')||'—')}</strong></div>
   <div><small>已证最小组合</small><strong>${esc((d.proven_sensor_ids||[]).join(',')||'—')}</strong></div>
  </div>
  ${d.error?`<div class="feedback error">${esc(d.error)}</div>`:''}
  ${table(['组合','替换传感器','状态','复现结果','尝试/校验'],rows)}`;
}

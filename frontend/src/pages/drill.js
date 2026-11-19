import {research} from '../stores/research.js';
import {session} from '../stores/session.js';
import {trailsApi} from '../api/trails.js';
import {sourceOptions} from '../components/common/business.js';
import {status} from '../components/common/status.js';
import {esc,fmt,formObject} from '../utils/format.js';
import {action,toast,bind} from '../hooks/actions.js';

const BATCH_SIZE=5000,PAGE=100;

function trailLedger(){
  if(!research.trails.length)return '<div class="empty">还没有编辑演练。选择一个已冻结的来源，先创建演练。</div>';
  return '<div class="ledger">'+research.trails.map(t=>'<a href="#" data-trail="'+t.id+'" class="'+(t.id===research.trailId?'active':'')+'"><small>#'+t.id+'</small><strong>'+esc(t.title)+'</strong>'+status(t.state)+'<time>'+(t.route_count??'—')+' 条 / '+(t.total_steps??'—')+' 步</time></a>').join('')+'</div>';
}

const state={trail:null,routes:[],coverage:[],coverTotal:0,coverCovered:0};

function stepCell(step,i){
  return '<li><span class="step-no">'+(i+1)+'</span><code>'+esc(step.from)+' → '+esc(step.to)+'</code>'+(step.repeat?'<em class="repeat-flag" title="为衔接重复走，仍有实测依据">重复</em>':'')+'<small>实测 '+step.count+' 次</small></li>';
}

function routeBlock(route){
  const repeats=route.steps.filter(s=>s.repeat).length;
  const steps='<ol class="route-steps">'+route.steps.map(stepCell).join('')+'</ol>';
  const body=route.step_count>40
    ?'<details class="route-detail"><summary>展开 '+route.step_count+' 步明细（含 '+repeats+' 个重复步）</summary>'+steps+'</details>'
    :steps;
  const preview=route.nodes.length>32?route.nodes.slice(0,32).map(esc).join(' <b>›</b> ')+' <b>›</b> … 共 '+route.nodes.length+' 个章节':route.nodes.map(esc).join(' <b>›</b> ');
  return '<article class="trail-route'+(route.closed?' closed':'')+'"><header><h3>路线 '+route['index']+'</h3>'+(route.closed?'<span class="status approved">闭环</span>':'<span class="status queued">开放</span>')+'<small>'+route.step_count+' 步 · 经过 '+route.nodes.length+' 个章节'+(repeats?' · 重复 '+repeats+' 步':'')+'</small></header><p class="route-nodes">'+preview+'</p>'+body+'</article>';
}

function coverageTable(rows){
  if(!rows.length)return '<p class="empty">暂无覆盖记录。</p>';
  return '<div class="table-wrap"><table><thead><tr><th>实测接续</th><th>实测次数</th><th>走到次数</th><th>榜单</th><th>核对</th></tr></thead><tbody>'+rows.map(r=>'<tr class="'+(r.covered?'covered':'missing')+'"><td>'+esc(r.from)+' → '+esc(r.to)+'</td><td>'+fmt(r.count)+'</td><td>'+fmt(r.walked)+'</td><td>'+(r.on_board?'榜内':'<b>榜外</b>')+'</td><td>'+(r.covered?'✓ 已走到':'✗ 未走到')+'</td></tr>').join('')+'</tbody></table></div>';
}

function summaryBlock(t){
  const allWalked=t.complete&&state.coverTotal>0&&state.coverCovered===state.coverTotal;
  return '<dl class="metrics"><div><dt>冻结会话</dt><dd>'+fmt((t.meta||{}).frozen_sessions??'—')+'</dd></div><div><dt>实测接续</dt><dd>'+fmt(t.continuation_count??'—')+'</dd></div><div><dt>路线数</dt><dd>'+fmt(t.route_count??'—')+'</dd></div><div><dt>总步数</dt><dd>'+fmt(t.total_steps??'—')+'</dd></div></dl>'+
    '<p class="fine">闭环 '+(t.closed_routes??0)+' 条 · 榜外接续 '+fmt(t.off_board??0)+' 条，已覆盖 '+fmt(t.off_board_covered??0)+' 条 · 受理峰值 '+fmt(t.intake_peak_mb??'—')+'MB · 求解峰值 '+fmt(t.solve_peak_mb??'—')+'MB（限 '+fmt(t.memory_limit_mb??192)+'MB）· 目录 SHA256 <code>'+esc(t.catalog_sha256||'')+'</code></p>'+
    (allWalked?'<div class="trail-complete"><strong>核对完成</strong><p>全部 '+state.coverTotal+' 条实测接续都走到了，本次演练完成。</p></div>':'<div class="pending"><strong>尚未完成</strong><p>覆盖核对 '+state.coverCovered+' / '+state.coverTotal+'；仍有接续没走到，不显示完成。</p></div>');
}

function batchPanel(t){
  if(!session.writable||t.state==='completed')return '';
  return '<aside class="entry-sheet"><h2>分批受理并合齐求解</h2><p class="fine">本次演练已从冻结会话展开 '+fmt(t.continuation_count??0)+' 种实测接续（含榜外）。点击后自动按每批 '+BATCH_SIZE+' 条分批受理，合齐后统一求解。</p><button id="run-drill" '+(t.batch_count?'':'')+'>从冻结会话分批受理并求解 →</button><p class="fine" id="batch-progress"></p><button id="solve-trail" class="secondary" '+(t.batch_count?'':'disabled')+'>仅合齐现有批次求解 →</button><details class="manual-batch"><summary>手动粘贴接续（JSONL）</summary><form id="batch-form"><label>每行一条：<code>{"from":"序章","to":"材料","count":3}</code><textarea name="rows" rows="6" required></textarea></label><button type="submit">分批受理 →</button></form></details><p class="fine">路线数最少优先，其次总步数最少；并发追加会话不改变本次冻结演练。</p></aside>';
}

function createPanel(){
  if(!session.writable)return '';
  return '<details class="create-trail"><summary>新建编辑演练（冻结当前来源的全部会话）</summary><form id="trail-form"><label>演练来源<select name="source_id">'+sourceOptions(research.sources,research.sourceId)+'</select></label><label>演练名称<input name="title" required value="十一月编辑演练"></label><div class="parameter-fields"><label>最少接续次数<input type="number" step="1" name="min_count" value="3" required></label><label>保留接续规则数<input type="number" step="1" name="top_n" value="20" required></label></div><p class="fine">创建即冻结该来源当前全部会话；之后追加的会话不会改写本次演练。</p><button type="submit">冻结并创建演练 →</button></form></details>';
}

export async function drillPage(){
  let t=null;
  state.routes=[];state.coverage=[];state.coverTotal=0;state.coverCovered=0;
  if(research.trailId){
    try{
      t=await trailsApi.get(research.trailId);
      if(t.state==='completed'){
        const [routes,cover]=await Promise.all([trailsApi.routes(t.id,0,PAGE),trailsApi.coverage(t.id,0,PAGE)]);
        state.routes=routes.rows;state.coverage=cover.rows;
        state.coverTotal=cover.total;state.coverCovered=cover.covered;state.coverOffset=PAGE;
      }
    }catch(e){t=null}
  }
  state.trail=t;
  const head='<section class="page-heading"><p class="eyebrow">07 / EDITORIAL DRILL</p><h1>用尽量少的路线，走遍每一条实测接续。</h1><p>从冻结会话取全部相邻章节，榜外接续同样覆盖；路线可以重复走同一接续，每一步都有实测依据。先让路线数最少，再让总步数最少，闭环算一条。</p></section>';
  const body=t
    ?'<div class="run-title"><h2>'+esc(t.title)+'</h2>'+status(t.state)+'<small>#'+t.id+' · 来源 #'+t.source_id+'</small></div><p class="fine">受理批次 '+fmt(t.batch_count??0)+' 批 · 每批上限 '+BATCH_SIZE+' 条 · 受理与求解各限 '+fmt(t.memory_limit_mb??192)+'MB</p>'+
      summaryBlock(t)+
      (t.state==='failed'?'<div class="failure"><h2>本次求解未完成</h2><p>'+esc(t.error)+'</p><p>核对批次后可重新合齐求解。</p></div>':'')+
      (t.state==='completed'
        ?'<h2>路线逐条展示 <small>共 '+t.route_count+' 条，闭环算一条</small></h2><div class="trail-routes" id="trail-routes">'+state.routes.map(routeBlock).join('')+'</div>'+(t.route_count>state.routes.length?'<p><button id="more-routes" class="secondary">加载更多路线（已 '+state.routes.length+' / '+t.route_count+'）</button></p>':'')
         :'<div class="empty">尚未求解。先分批受理全部接续，再合齐统一求解。</div>')+
      (t.state==='completed'?'<h2>覆盖核对 <small>全部 '+state.coverTotal+' 条实测接续逐条核对</small></h2><div id="trail-coverage">'+coverageTable(state.coverage)+'</div>'+(state.coverTotal>state.coverage.length?'<p><button id="more-cover" class="secondary">加载更多核对（已 '+state.coverage.length+' / '+state.coverTotal+'）</button></p>':''):'')+
      '<div class="split drill-split"><section>'+createPanel()+'</section>'+batchPanel(t)+'</div>'
    :'<div class="empty">还没有演练记录。'+createPanel()+'</div>';
  return head+'<div class="split drill-split"><section>'+trailLedger()+'</section><aside class="method-sheet"><p class="eyebrow">DRILL RULES</p><p>只统计同一会话内的相邻章节，跨会话不拼接。榜内榜外全部覆盖；重复步只用于衔接，且每一步都是实测接续。</p></aside></div>'+body;
}

function updateCompletion(){
  const t=state.trail;if(!t||t.state!=='completed')return;
  const box=document.querySelector('.trail-complete, .pending');
  if(!box)return;
  const all=state.coverTotal>0&&state.coverCovered===state.coverTotal;
  const html=all?'<strong>核对完成</strong><p>全部 '+state.coverTotal+' 条实测接续都走到了，本次演练完成。</p>':'<strong>尚未完成</strong><p>覆盖核对 '+state.coverCovered+' / '+state.coverTotal+'；仍有接续没走到，不显示完成。</p>';
  box.className=all?'trail-complete':'pending';box.innerHTML=html;
}

function appendCoverage(rows){
  document.getElementById('trail-coverage').insertAdjacentHTML('beforeend',coverageTable(rows).replace('<div class="table-wrap"><table>','').replace(/<\/table><\/div>$/,''));
  const button=document.getElementById('more-cover');
  if(button){
    const loaded=document.getElementById('trail-coverage').querySelectorAll('tbody tr').length;
    if(loaded>=state.coverTotal)button.remove();else button.textContent='加载更多核对（已 '+loaded+' / '+state.coverTotal+'）';
  }
}

export function bindDrill(refresh){
  const progress=document.getElementById('batch-progress');
  bind('#batch-file','change',async e=>{
    const file=e.target.files&&e.target.files[0];if(!file)return;
    const text=await file.text();const area=document.querySelector('#batch-form textarea');if(area)area.value=text;
  });
  action('#trail-form',async form=>{
    const data=formObject(form);
    const t=await trailsApi.create({source_id:Number(data.source_id),title:data.title,parameters:{min_count:Number(data.min_count),top_n:Number(data.top_n)}});
    research.trailId=t.id;await refresh();toast('演练已冻结创建，请分批受理接续');
  });
  action('#batch-form',async form=>{
    let rows;
    try{rows=formObject(form).rows.trim().split(/\n+/).filter(Boolean).map(line=>JSON.parse(line))}
    catch(e){throw Error('JSONL 解析失败：'+e.message)}
    if(!rows.length)throw Error('没有可受理的接续');
    let accepted=0;
    for(let i=0;i<rows.length;i+=BATCH_SIZE){
      const receipt=await trailsApi.batch(research.trailId,{continuations:rows.slice(i,i+BATCH_SIZE)});
      accepted+=receipt.accepted;
      if(progress)progress.textContent='已受理 '+Math.ceil((i+1)/BATCH_SIZE)+' 批 · '+accepted+' 条接续 · 受理峰值 '+(receipt.intake_peak_mb??'—')+'MB';
    }
    await refresh();toast('已受理 '+accepted+' 条接续；合齐后可统一求解');
  });
  bind('#run-drill','click',async()=>{
    const total=state.trail?state.trail.continuation_count:0;
    let offset=0,accepted=0,batches=0;
    while(offset<total){
      const page=await trailsApi.catalog(research.trailId,offset,500);
      if(!page.rows.length)break;
      const receipt=await trailsApi.batch(research.trailId,{continuations:page.rows});
      accepted+=receipt.accepted;batches++;offset+=page.rows.length;
      if(progress)progress.textContent='已受理 '+batches+' 批 · '+accepted+' 条接续 · 受理峰值 '+(receipt.intake_peak_mb??'—')+'MB';
    }
    if(!accepted)throw Error('冻结目录为空');
    try{await trailsApi.solve(research.trailId);toast('已合齐并统一求解')}
    finally{await refresh()}
  });
  bind('#solve-trail','click',async()=>{
    try{await trailsApi.solve(research.trailId);await refresh();toast('已合齐并统一求解')}
    catch(e){toast(e.message,true);await refresh()}
  });
  bind('#more-routes','click',async()=>{
    const result=await trailsApi.routes(research.trailId,state.routes.length,PAGE);
    document.getElementById('trail-routes').insertAdjacentHTML('beforeend',result.rows.map(routeBlock).join(''));
    state.routes=state.routes.concat(result.rows);
    const button=document.getElementById('more-routes');
    if(state.routes.length>=state.trail.route_count)button.remove();else button.textContent='加载更多路线（已 '+state.routes.length+' / '+state.trail.route_count+'）';
  });
  bind('#more-cover','click',async()=>{
    const result=await trailsApi.coverage(research.trailId,state.coverage.length,PAGE);
    appendCoverage(result.rows);
    state.coverage=state.coverage.concat(result.rows);
    state.coverCovered=result.covered;
    updateCompletion();
  });
  for(const a of document.querySelectorAll('[data-trail]'))a.onclick=async e=>{
    e.preventDefault();research.trailId=Number(a.dataset.trail);await refresh();
  };
}

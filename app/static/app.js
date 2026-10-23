"use strict";
const $ = id => document.getElementById(id);
const paths = {
plus:"M12 5v14M5 12h14",chat:"M21 11a8 8 0 0 1-8 8H7l-5 3 2-6a9 9 0 1 1 17-5Z",book:"M3 4h7a3 3 0 0 1 2 2v15a4 4 0 0 0-4-2H3ZM21 4h-7a3 3 0 0 0-2 2v15a4 4 0 0 1 4-2h5Z",
brain:"M12 18v-12M12 6c-3-6-7 0-5 2-5 0-5 7-2 8-1 6 6 7 7 2M12 6c3-6 7 0 5 2 5 0 5 7 2 8 1 6-6 7-7 2M7 8l1 3m9-3-1 3M5 16l3-1m11 1-3-1",
clock:"M12 8v5l3 2M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0",settings:"m9 3-1 3-3 1-2 4 2 3 1 4 4 2 3-1 4-1 2-4-1-3-1-4-4-2ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
menu:"M4 6h16M4 12h16M4 18h16",panel:"M3 4h18v16H3ZM15 4v16",chart:"M4 3v17h17M8 14l4-5 4 2 4-7",
wave:"M2 12h3l3-8 5 16 4-8h5",shield:"M12 2 3 6v6c0 6 9 10 9 10s9-4 9-10V6ZM8 12l3 3 5-6",check:"m5 12 4 4L19 6",
link:"m9 15 6-6M10 6l2-2a5 5 0 0 1 7 7l-2 2M14 18l-2 2a5 5 0 0 1-7-7l2-2",spark:"m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z",
arrow:"M12 19V5m-6 6 6-6 6 6",chevron:"m7 10 5 5 5-5",close:"m6 6 12 12M6 18 18 6",download:"M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
search:"m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",sidebar:"M3 4h18v16H3ZM9 4v16",more:"M5 12h.01M12 12h.01M19 12h.01",pin:"m8 3 8 0-1 6 4 4v2H5v-2l4-4-1-6ZM12 15v6",edit:"m16 3 5 5-12 12-6 1 1-6L16 3ZM13 6l5 5",trash:"M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7",
eye:"M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",eyeOff:"m3 3 18 18M10.6 5.1 12 5c6 0 10 7 10 7s-1.3 2.2-3.6 4.2M6.1 6.1C3.5 8.2 2 12 2 12s4 7 10 7c1.9 0 3.6-.6 5-1.4M10 10a3 3 0 0 0 4 4",
mic:"M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0ZM5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8",copy:"M9 8V3h12v14h-5M3 8h13v14H3"
};
function icon(name) { const ns="http://www.w3.org/2000/svg",e=document.createElementNS(ns,"svg"),p=document.createElementNS(ns,"path");e.setAttribute("viewBox","0 0 24 24");e.setAttribute("class","icon");e.setAttribute("aria-hidden","true");p.setAttribute("d",paths[name]||paths.check);e.append(p);return e; }
document.querySelectorAll("[data-icon]").forEach(e=>{const name=e.dataset.icon;e.removeAttribute("data-icon");e.append(icon(name));});
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined&&text!==null)n.textContent=String(text);if(cls)n.className=cls;return n;}
function button(text,fn,cls){const e=el("button",text,cls);e.type="button";e.onclick=fn;return e;}
function action(label,name,fn){const b=button("",fn);b.append(icon(name),document.createTextNode(label));return b;}
const passwordButtons=new WeakMap();
let passwordFieldCount=0;
function setPasswordVisible(input,visible){
  input.type=visible?"text":"password";
  const toggle=passwordButtons.get(input);
  if(toggle){const label=visible?"隐藏密码":"显示密码";toggle.setAttribute("aria-label",label);toggle.title=label;toggle.setAttribute("aria-pressed",String(visible));toggle.replaceChildren(icon(visible?"eyeOff":"eye"));}
}
function attachPasswordToggle(input){
  if(passwordButtons.has(input))return;
  if(!input.id)input.id="password-field-"+(++passwordFieldCount);
  const wrap=el("div",null,"password-field");
  input.replaceWith(wrap);wrap.append(input);
  const toggle=button("",()=>setPasswordVisible(input,input.type==="password"),"password-toggle");
  toggle.setAttribute("aria-controls",input.id);
  wrap.append(toggle);passwordButtons.set(input,toggle);setPasswordVisible(input,false);
}
const normalPasswordHelp="密码至少8位，包含大写字母、小写字母、数字和特殊字符，且不能包含空白";
function checkNewPassword(value,admin=false){
  if(admin){if(value.length<12||value.length>256)throw Error("管理员密码需12至256位");return;}
  if(value.length<8||value.length>256||!/^[^\s]+$/.test(value)||!/[a-z]/.test(value)||!/[A-Z]/.test(value)||!/[0-9]/.test(value)||!/[!-/:-@\[-`{-~]/.test(value))throw Error(normalPasswordHelp);
}
document.querySelectorAll('input[type="password"]').forEach(attachPasswordToggle);
function toast(text){$("toast").textContent=text;$("toast").hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$("toast").hidden=true,4500);}
let workspaceKind="analysis";
let conversationId=null,tasks=[],selectedTask=null,inspectorTab="run",sending=false,healthData={},liveController=null;
const labels={planner:"拆解分析任务",supervisor:"调度下一步工具",search_process_docs:"检索工艺依据",query_batch_data:"读取批次数据",check_process_limits:"计算参数偏差",process_statistics:"描述统计",simulate_heating:"升温过程仿真",validate_evidence:"独立验证证据",finalize:"生成分析报告",human_review:"人工复核",runtime_error:"执行异常",retrieval_retry:"补充检索",answer_question:"生成模型回答"};
const statuses={queued:"等待执行",running:"正在分析",completed:"分析完成",pending_review:"等待人工复核",completed_reviewed:"已发布限制性说明",rejected:"已驳回报告",failed:"执行失败"};
const parameterNames={temperature_c:"温度",pressure_mpa:"压力",viscosity_pas:"黏度"};
let currentUser=null,selectedDocumentIds=[],authMode="login",authEpoch=0,projectChoices=[];
function setAuthMode(mode){
  authMode=mode;const registering=mode==="register";
  $("auth-login").classList.toggle("selected",!registering);$("auth-register").classList.toggle("selected",registering);$("auth-login").setAttribute("aria-pressed",String(!registering));$("auth-register").setAttribute("aria-pressed",String(registering));
  $("auth-title").textContent=registering?"创建你的分析账号":"登录你的分析空间";$("auth-description").textContent=registering?"注册后即可使用工艺分析、数据问数与复核功能。个人分析记录按账号保存。":"连接工艺知识、计算工具与审核流程。登录后即可开始分析。";
  $("register-confirm").hidden=!registering;$("register-help").hidden=!registering;$("register-password-confirm").required=registering;$("register-password-confirm").value="";$("login-password").value="";$("login-password").minLength=registering?8:1;$("login-password").autocomplete=registering?"new-password":"current-password";$("login-username").maxLength=registering?60:80;$("login-username").minLength=registering?2:1;
  setPasswordVisible($("login-password"),false);setPasswordVisible($("register-password-confirm"),false);
  $("login-submit").textContent=registering?"注册并进入工作空间":"登录工作空间";$("login-error").textContent="";
}
$("auth-login").onclick=()=>setAuthMode("login");$("auth-register").onclick=()=>setAuthMode("register");
function showLogin(preserveInput=false){resetHistoryUI();currentUser=null;if(!preserveInput||authMode!=="login")setAuthMode("login");$("auth-screen").hidden=false;$("sidebar").inert=true;$("app").inert=true;if($("modal").open)$("modal").close();if($("analysis-options").open)$("analysis-options").close();closeComposerMenus();}
function showWorkspace(user){currentUser=user;applySidebarPreferences();$("auth-screen").hidden=true;$("sidebar").inert=false;$("app").inert=false;$("settings").querySelector(".avatar").textContent=user.username[0].toUpperCase();const name=$("settings").children[1];name.replaceChildren(document.createTextNode(user.username),el("small",user.role==="admin"?"管理员":"普通用户"));}
async function request(path,options={}){
  const r=await fetch(path,{...options,credentials:"same-origin",headers:{"Content-Type":"application/json","X-Proclab-Request":"1",...(options.headers||{})}});
  if(r.status===401){showLogin();throw Error("请登录后使用");}
  if(!r.ok){let error;try{error=await r.json();}catch{error={detail:"服务暂时不可用"};}const e=Error(typeof error.detail==="string"?error.detail:"请检查输入参数");e.payload=error;e.status=r.status;throw e;}
  return r;
}
async function api(path,options={}){const r=await request(path,options);return r.status===204?null:r.json();}
function modal(title){$("modal-title").textContent=title;$("modal-body").replaceChildren();if(!$("modal").open)$("modal").showModal();return $("modal-body");}
$("modal-close").onclick=()=>$("modal").close();
$("modal").addEventListener("click",e=>{if(e.target===$("modal")){const r=$("modal").getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$("modal").close();}});
function setSending(value){sending=value;$("voice-input").disabled=value;$("send").disabled=value;$("question").disabled=value;$("send").setAttribute("aria-label",value?"任务执行中":"发送分析任务");if(typeof syncVoiceControls==='function')syncVoiceControls();}
function setWorkspace(kind){
  workspaceKind=kind;const query=kind==='analytics';
  $('nav-chat').classList.toggle('active',!query);$('nav-analytics').classList.toggle('active',query);
  $('workspace-title').textContent=query?'数据查询':'工艺分析';$('question').placeholder=query?'例如：各设备的超限批次比例是多少？':'直接描述问题，系统自动选择分析步骤…';
  $('welcome').hidden=query||tasks.length>0;$('analytics-welcome').hidden=!query||tasks.length>0;
}
function newChat(kind=workspaceKind){
  closeHistoryMenu();
  if(typeof cancelVoice==='function')cancelVoice();
  selectedDocumentIds=[];$("attached-evidence").hidden=true;
  $("toast").hidden=true;
  if(liveController)liveController.abort();liveController=null;conversationId=null;tasks=[];selectedTask=null;
  setSending(false);$("conversation-title").textContent="新的分析";$("welcome").hidden=false;$("messages").hidden=true;$("messages").replaceChildren();$("inspector").hidden=true;closeMobileSidebar();$("question").value="";$("batch").value="";$("intent").value=kind==="analytics"?"analytics":"auto";$("fault").value="none";if($("analysis-options").open)$("analysis-options").close();closeComposerMenus();setWorkspace(kind);updateIntent();refreshHistory().catch(()=>{});
}
$("new-chat").onclick=()=>newChat(workspaceKind);$("nav-chat").onclick=()=>newChat("analysis");$("menu").onclick=toggleSidebar;
document.addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"){e.preventDefault();newChat();$("question").focus();}});
$("question").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!sending)$("composer").requestSubmit();}});
function updateIntent(){const visible=['simulation','composite'].includes($('intent').value);$('heating-inputs').hidden=!visible;$('toggle-heating').setAttribute('aria-expanded',String(visible));}
$('analysis-mode').onchange=()=>{const mode=$('analysis-mode').value,label=mode==='thinking'?'深度思考':'快速';$('mode-label').textContent=label;$('mode-toggle').setAttribute('aria-label','思考强度：'+label);document.querySelectorAll('[data-analysis-mode]').forEach(b=>b.setAttribute('aria-checked',String(b.dataset.analysisMode===mode)));};
$('toggle-heating').onclick=()=>{$('heating-inputs').hidden=!$('heating-inputs').hidden;$('toggle-heating').setAttribute('aria-expanded',String(!$('heating-inputs').hidden));};
$("intent").onchange=updateIntent;
document.querySelectorAll("[data-scenario]").forEach(b=>b.onclick=()=>{
  const scenarios={anomaly:["分析 B-102 批次热压成型参数，指出超限项，给出描述统计与证据引用。","batch","B-102"],
  simulation:["用一阶热模型模拟升温过程，计算达到 180 ℃ 需要的时间，并独立验证结果。","simulation",""],
  review:["分析 B-103 批次，数据不完整时进入人工复核，不要猜测缺失值。","batch","B-103"],
  knowledge:["热压成型的温度、压力和黏度参数要求是什么？请引用现行模拟规范，并区分公开资料。","knowledge",""]};
  setWorkspace("analysis");const s=scenarios[b.dataset.scenario];$("question").value=s[0];$("intent").value=s[1];$("batch").value=s[2];$("fault").value="none";updateIntent();$("question").focus();
});
async function refreshHistory(){
  const epoch=++historyRequestVersion,user=currentUser?.id;
  const history=await api("/api/conversations");
  if(epoch!==historyRequestVersion||user!==currentUser?.id)return;
  renderHistory(history);
}
async function loadConversation(id){
  if(typeof cancelVoice==='function')cancelVoice();
  if(liveController)liveController.abort();liveController=null;setSending(false);
  const c=await api("/api/conversations/"+id);conversationId=id;tasks=c.tasks.sort((a,b)=>a.created_at.localeCompare(b.created_at));selectedTask=tasks.at(-1)||null;
  $("conversation-title").textContent=c.title;closeMobileSidebar();setWorkspace(selectedTask?.intent==="analytics"?"analytics":"analysis");$("intent").value=workspaceKind==="analytics"?"analytics":"auto";$("analysis-mode").value=selectedTask?.analysis_mode||"fast";$("analysis-mode").onchange();renderMessages();renderInspector();refreshHistory().catch(()=>{});
  const running=tasks.find(t=>["queued","running"].includes(t.status));if(running){setSending(true);watch(running).catch(e=>toast(e.message));}
}
function renderMessages(){
  $("welcome").hidden=tasks.length>0||workspaceKind==="analytics";$("analytics-welcome").hidden=tasks.length>0||workspaceKind!=="analytics";$("messages").hidden=!tasks.length;const scroll=$("chat-scroll"),nearBottom=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<140;$("messages").replaceChildren();
  for(const t of tasks){const pair=el("article",null,"message-pair");pair.dataset.taskId=t.task_id;pair.append(el("div",t.question,"user-message"));
    const head=el("div",null,"assistant-heading");head.append(el("span","p·","assistant-logo"),el("strong","ProcLab"),el("span",new Date(t.created_at).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"}),"assistant-time"));pair.append(head);
    const body=el("div",null,"report-content");
    if(t.status==="pending_review")renderReview(body,t);
    else if(t.status==="failed"){body.append(el("span","执行失败","result-status bad"),el("p","本次任务未能完成。错误类型："+t.error+"。可查看执行过程，再检查依赖服务与模型配置。"));body.append(action("查看执行过程","panel",()=>openInspector(t)));}
    else if(t.report)renderReport(body,t);
    else{const busy=el("div",null,"busy-label"),last=(t.trace||[]).at(-1);busy.append(el("span",null,"busy-dot"),document.createTextNode(last?(labels[last.node]||last.detail)+"…":"正在规划分析任务…"));body.append(busy,action("查看执行过程","panel",()=>openInspector(t)));}
    if(t.permissions?.analyze!==false&&(["failed","rejected","completed_reviewed"].includes(t.status)||t.answer_metadata?.status==="fallback"))body.append(action("修复或重试","clock",()=>showTaskRepair(t)));
    if(t.design_loop&&!t.report)renderHeatingDesign(body,t);
    pair.append(body);$("messages").append(pair);
  }
  if(nearBottom)requestAnimationFrame(()=>{scroll.scrollTop=scroll.scrollHeight;});
}
function renderReview(body,t){
  if(t.permissions?.review===false){body.append(el("p","当前项目权限仅允许查看此复核记录。","report-notice"),action("查看证据缺口","panel",()=>openInspector(t)));if(t.permissions?.analyze)body.append(action("补充证据并重算","plus",()=>showTaskRepair(t)));return;}
  body.append(el("span","需要人工复核","result-status warn"));
  const box=el("div",null,"review-box");box.append(el("strong","当前证据不足，暂不发布完整结论"),el("p",t.review_reason));
  const note=el("input");note.placeholder="填写复核备注（不会修正原始证据）";note.setAttribute("aria-label","人工复核备注");note.maxLength=500;box.append(note);
  const row=el("div",null,"button-row");
  for(const [approved,label] of [[true,"发布限制性说明"],[false,"驳回并补充证据"]])row.append(button(label,async()=>{
    row.querySelectorAll("button").forEach(b=>b.disabled=true);
    try{const result=await api("/api/tasks/"+t.task_id+"/review",{method:"POST",body:JSON.stringify({approved,note:note.value})});updateTask(result);toast(approved?"已发布限制性说明":"已驳回，保留执行记录");}catch(e){toast(e.message);row.querySelectorAll("button").forEach(b=>b.disabled=false);}
  },approved?"primary-button":"secondary-button"));
  box.append(row);body.append(box,action("查看证据缺口","panel",()=>openInspector(t)));if(t.permissions?.analyze!==false)body.append(action("补充证据并重算","plus",()=>showTaskRepair(t)),action("重试此任务","clock",()=>retryTask(t)));
}
function table(headers,rows){
  const wrap=el("div",null,"table-scroll"),tab=el("table"),thead=el("thead"),tr=el("tr");headers.forEach(h=>tr.append(el("th",h)));thead.append(tr);tab.append(thead);const tbody=el("tbody");
  rows.forEach(row=>{const tr=el("tr");row.forEach(cell=>tr.append(el("td",cell)));tbody.append(tr);});tab.append(tbody);wrap.append(tab);return wrap;
}
function renderReport(body,t){
  const r=t.report;
  body.append(el("span",(t.intent==="chat"?"回答完成":statuses[t.status])+(t.validation==="passed"?(t.batch_id||t.report.simulation||t.report.design?" · 独立校验通过":" · 来源版本已核对"):""),"result-status"+(t.status==="rejected"?" bad":t.status==="completed_reviewed"?" warn":"")));
  if(t.parent_task_id)body.append(el("p","修复版本 R"+t.repair_version+" · 原任务 "+t.parent_task_id.slice(0,8)+" 的记录已保留","lineage-note"));
  body.append(el("p",r.summary));
  if(r.answer_metadata){const a=r.answer_metadata;body.append(el("small",a.status==="success"?"模型："+a.model+" · "+a.latency_ms+" ms":"模型回答未完成，已显示降级说明","report-notice"));}
  if(t.batch_id){const stats=el("div",null,"findings-summary");for(const [value,label] of [[r.readings.length,"条测量记录"],[r.findings.length,"个超限参数项"],[r.missing.length,"个缺失参数"]]){const tile=el("div",null,"stat-tile");tile.append(el("strong",value),el("small",label));stats.append(tile);}body.append(stats);}
  if(r.findings.length){body.append(el("h3","参数偏差"));body.append(table(["数据行","参数","实测值","允许范围"],r.findings.map(f=>[f.row_id,parameterNames[f.parameter]||f.parameter,f.actual+" "+f.unit,f.allowed.join("–")+" "+f.unit])));}
  if(r.missing.length){body.append(el("h3","缺失数据"),el("p",r.missing.map(m=>"第 "+m.row_id+" 行："+(parameterNames[m.parameter]||m.parameter)).join("；")));}
  if(r.statistics&&r.statistics.parameters.length){const details=el("details");details.append(el("summary","查看描述统计"));details.append(table(["参数","均值","范围","样本标准差"],r.statistics.parameters.map(p=>[parameterNames[p.parameter]||p.parameter,p.mean+" "+p.unit,p.min+"–"+p.max,p.sample_std??"—"])));details.append(el("p",r.statistics.note,"report-notice"));body.append(details);}
  if(r.analytics)renderAnalyticsResult(body,r.analytics);
  if(r.design)renderHeatingDesign(body,t);
  if(t.business_verdict)body.append(el("p","业务判定："+verdictLabel(t.business_verdict)+" · 计划 V"+(t.plan_version||1),"lineage-note"));
  if(r.simulation){const s=r.simulation;body.append(el("h3","升温轨迹与目标反算"),simulationChart(s),el("p",s.recommendation),el("p",s.assumptions,"report-notice"));}
  if((r.documents||[]).length||r.readings.length)body.append(el("h3","证据来源"));const refs=el("div",null,"citation-list");
  (r.documents||[]).forEach((d,i)=>refs.append(button("["+(i+1)+"] "+d.doc_id+" "+d.revision,()=>showDocument(d),"citation")));
  if(r.readings.length)refs.append(button("批次记录 · "+r.readings.length+" 行",()=>{const m=modal("原始批次记录 · "+t.batch_id);m.append(table(["行号","温度 ℃","压力 MPa","黏度 Pa·s"],r.readings.map(row=>[row.row_id,row.temperature_c||"缺失",row.pressure_mpa||"缺失",row.viscosity_pas||"缺失"])));},"citation"));
  if((r.documents||[]).length||r.readings.length)body.append(refs);if(t.intent!=="chat")body.append(el("p",r.warning,"report-notice"));
  const actions=el("div",null,"report-actions");actions.append(action("执行过程","panel",()=>openInspector(t)),action("导出报告","download",()=>download(t,"markdown")),action("原始 JSON","copy",()=>download(t,"json")));
  if(t.status==="completed"&&t.validation==="passed"&&(t.validation_details?.independent_numeric_check===true||t.validation_details?.simulation_verified===true))actions.append(action("存入长期记忆","brain",async()=>{try{await api("/api/tasks/"+t.task_id+"/remember",{method:"POST"});toast("已保存，后续相关分析可以召回此结论");}catch(e){toast(e.message);}}));if(t.orchestration==="superagent")actions.append(action("结果版本","clock",()=>showResultVersions(t)));body.append(actions);
}
function simulationChart(s){
  const box=el("div",null,"simulation-chart"),legend=el("div",null,"chart-legend");legend.append(el("strong","温度 / ℃"),el("span","RK4 实线 · 解析解点线"));box.append(legend);
  const ns="http://www.w3.org/2000/svg",svg=document.createElementNS(ns,"svg");svg.setAttribute("viewBox","0 0 580 230");svg.setAttribute("role","img");svg.setAttribute("aria-label","升温曲线：末端温度 "+s.final_c+" 摄氏度");
  function node(name,attrs,text){const e=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text)e.textContent=text;svg.append(e);return e;}
  const min=Math.floor(Math.min(s.parameters.initial_c,0)/20)*20,max=Math.ceil(s.parameters.oven_c/20)*20,duration=s.parameters.duration_s;
  const x=t=>40+t/duration*520,y=t=>195-(t-min)/(max-min)*175;
  for(let i=0;i<=4;i++){const temp=min+(max-min)*i/4;node("line",{x1:40,x2:560,y1:y(temp),y2:y(temp),stroke:"#e7edde","stroke-dasharray":"3 4"});node("text",{x:31,y:y(temp)+3,"text-anchor":"end",fill:"#9ba98d","font-size":9},Math.round(temp).toString());}
  node("line",{x1:40,x2:560,y1:y(s.parameters.target_c),y2:y(s.parameters.target_c),stroke:"#c6a974","stroke-dasharray":"5 5"});node("text",{x:560,y:y(s.parameters.target_c)-6,"text-anchor":"end",fill:"#b79b6c","font-size":9},"目标 "+s.parameters.target_c+" ℃");
  const line=s.curve.map((p,i)=>(i?"L":"M")+x(p.time_s)+","+y(p.temperature_c)).join(" ");node("path",{d:line,fill:"none",stroke:"#7d9c64","stroke-width":2.5});
  s.curve.filter((_,i)=>i%4===0).forEach(p=>node("circle",{cx:x(p.time_s),cy:y(p.analytical_c),r:2,fill:"#527442"}));
  for(let i=0;i<=4;i++)node("text",{x:x(duration*i/4),y:218,"text-anchor":"middle",fill:"#9ba98d","font-size":9},Math.round(duration*i/4)+" s");
  box.append(svg);return box;
}
function showDocument(d){const m=modal(d.title);m.append(el("span",d.origin==="admin_published"?"管理员发布 · 已核对":d.origin==="user_supplied_reviewed"?"用户上传 · 已审核":d.origin==="synthetic"?"自制模拟规范":d.origin==="project_authored"?"项目自编说明":"公开资料概述","source-tag"),el("p",d.doc_id+" "+d.revision+" §"+d.section),el("p",d.content));
  if(d.source&&/^https:\/\//.test(d.source)){const a=el("a","查看公开来源");a.href=d.source;a.target="_blank";a.rel="noopener noreferrer";m.append(a);}
  if(d.limits&&Object.keys(d.limits).length)m.append(table(["参数","下限","上限","单位"],Object.entries(d.limits).map(([k,v])=>[parameterNames[k]||k,v.min,v.max,v.unit])));
}
function openInspector(t){selectedTask=t;$("inspector").hidden=false;renderInspector();}
$("toggle-inspector").onclick=()=>{if(!selectedTask){toast("开始分析后，这里会展示执行过程与证据");return;}$("inspector").hidden=!$("inspector").hidden;renderInspector();};
$("close-inspector").onclick=()=>$("inspector").hidden=true;
$("tab-run").onclick=()=>{inspectorTab="run";renderInspector();};$("tab-evidence").onclick=()=>{inspectorTab="evidence";renderInspector();};
function renderInspector(){
  if(!selectedTask)return;const t=selectedTask,content=$("inspector-content");content.replaceChildren();$("tab-run").classList.toggle("selected",inspectorTab==="run");$("tab-evidence").classList.toggle("selected",inspectorTab==="evidence");
  content.append(el("div",statuses[t.status]||t.status,"inspector-status"),el("div","TASK "+t.task_id,"task-meta"),el("div","调度："+({native_tools:"模型原生工具选择",direct_model:"直接模型回答",retrieval_pipeline:"检索后回答",rules_fallback:"规则降级",rules:"确定性规则"}[t.plan_provider]||t.plan_provider)+" · "+(t.completed_steps||[]).length+"/"+(t.plan||[]).length+" 步","task-meta"));
  if(t.retrieval)content.append(el("div","检索："+t.retrieval.backend+(t.retrieval.embedding==="hash"?"（演示哈希向量）":""),"task-meta"));
  $("tab-team").classList.toggle("selected",inspectorTab==="team");$("tab-sql").classList.toggle("selected",inspectorTab==="sql");
  if(inspectorTab==="team"){renderTeam(content,t);return;}
  if(inspectorTab==="sql"){if(t.analytics)renderAnalyticsResult(content,t.analytics,true);else content.append(el("p","本任务没有指标查询。可在工业数据问数入口查询历史批次。"));return;}
  if(inspectorTab==="evidence"){content.append(el("p","有效资料","inspector-section"));if(!(t.docs||[]).length)content.append(el("p","尚未取得可引用资料。"));(t.docs||[]).forEach(d=>{const card=el("div",null,"source-card");card.append(el("h4",d.title),el("span",d.origin==="admin_published"?"管理员发布 · 已核对":d.origin==="user_supplied_reviewed"?"用户上传 · 已审核":d.origin==="synthetic"?"模拟规范":d.origin==="project_authored"?"项目说明":"公开资料","source-tag"),el("p",d.content.slice(0,130)+"…"),button(d.doc_id+" "+d.revision,()=>showDocument(d),"citation"));content.append(card);});if(t.validation_details){content.append(el("p","独立校验","inspector-section"),el("pre",JSON.stringify(t.validation_details,null,2),"trace-extra"));}return;}
  if(t.orchestration==="superagent"){const team=el("div",null,"harness-card");team.append(el("strong","SuperAgent · 计划 V"+(t.plan_version||"规划中")),el("div",Object.keys(t.execution_plan?.team||{}).length+" 项专业能力 · 按依赖执行"),button("查看任务分工与进度",()=>{inspectorTab="team";renderInspector();},"citation"));content.append(team);}
  if(t.harness){const h=t.harness,card=el("div",null,"harness-card");card.append(el("strong","执行保障 · Harness"),el("div","工具白名单 · SQL检查点 · 引用与数值校验"),el("div","调用预算 "+h.max_tool_calls+" 次 · 步骤边界超时 "+h.step_boundary_timeout_seconds+" 秒"),el("div","修复版本 "+(t.repair_version||0)+" / "+h.max_repair_versions));content.append(card);}
  content.append(el("p","执行记录","inspector-section"));
  const trace=(t.trace||[]).filter(x=>x.node!=="supervisor");if(!trace.length)content.append(el("p","等待任务规划…"));
  trace.forEach(x=>{const step=el("div",null,"execution-step");step.append(el("span",x.error?"!":"✓","step-dot"),el("strong",labels[x.node]||x.node),el("p",x.detail));if(x.tool_args)step.append(el("div",JSON.stringify(x.tool_args),"trace-extra"));const decision=(t.trace||[]).find(v=>v.node==="supervisor"&&v.detail.endsWith(x.node));if(decision)step.append(el("div",decision.provider==="native_tool_call"?"模型已选择工具 · "+decision.tool_call_id:decision.provider==="rules_fallback"?"模型调用失败，已使用规则调度":"规则调度","task-meta"));content.append(step);});
}
function updateTask(t){const index=tasks.findIndex(x=>x.task_id===t.task_id);if(index<0)tasks.push(t);else tasks[index]=t;selectedTask=t;renderMessages();renderInspector();}
async function download(t,format){try{const r=await request("/api/tasks/"+t.task_id+"/report?format="+format);const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download="ProcLab-"+(t.batch_id||"simulation")+"-"+t.task_id.slice(0,8)+(format==="json"?".json":".md");a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){toast(e.message);}}
async function watch(task){
  const id=task.conversation_id;liveController=new AbortController();
  try{
    const r=await request("/api/tasks/"+task.task_id+"/events",{signal:liveController.signal});
    const reader=r.body.getReader(),decoder=new TextDecoder();let buffer="";
    while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let split;
      while((split=buffer.indexOf("\n\n"))>=0){const block=buffer.slice(0,split);buffer=buffer.slice(split+2);if(block.startsWith("event: state")){const line=block.split("\n").find(x=>x.startsWith("data: "));if(line&&id===conversationId)updateTask(JSON.parse(line.slice(6)));}}
    }
  }catch(e){if(e.name!=="AbortError"){toast("连接中断，正在重新查询任务状态");for(let i=0;i<120;i++){await new Promise(r=>setTimeout(r,1000));if(id!==conversationId)break;const t=await api("/api/tasks/"+task.task_id);updateTask(t);if(!["queued","running"].includes(t.status))break;}}}
  finally{if(id===conversationId){setSending(false);refreshHistory().catch(()=>{});}}
}
$("composer").onsubmit=async e=>{
  e.preventDefault();if(sending)return;if(typeof voiceSession!=='undefined'&&voiceSession){stopVoice(true);return;}if($("project").selectedOptions[0]?.disabled){toast("当前项目仅可查看，请选择可分析项目");return;}const question=$("question").value.trim();if(!question.length)return;
  const payload={question,batch_id:$("batch").value,intent:$("intent").value,inject_timeout:$("fault").value,conversation_id:conversationId,evidence_document_ids:selectedDocumentIds};
  payload.project_id=$("project").value||null;payload.analysis_mode=$("analysis-mode").value;
  if(!$("heating-inputs").hidden)payload.simulation_params=Object.fromEntries(["initial_c","oven_c","target_c","tau_s","duration_s"].map(k=>[k,Number($(k).value)]));
  setSending(true);
  try{const t=await api("/api/tasks/submit",{method:"POST",body:JSON.stringify(payload)});conversationId=t.conversation_id;$("conversation-title").textContent=question.slice(0,35);$("question").value="";updateTask(t);if(!["chat","extract"].includes(t.intent))openInspector(t);$("chat-scroll").scrollTop=$("chat-scroll").scrollHeight;await watch(t);}
  catch(err){toast(err.message);setSending(false);}
};
async function showKnowledge(scope='company'){
 try{if(scope!=='personal')scope='company';
 const docs=await api('/api/knowledge'),releases=await api('/api/knowledge/releases'),m=modal('工艺知识库');
 const tabs=el('div',null,'button-row');tabs.append(button('公司共享库',()=>showKnowledge('company'),scope==='company'?'primary-button':'secondary-button'),button('我的个人库',()=>showKnowledge('personal'),scope==='personal'?'primary-button':'secondary-button'),button(currentUser.role==='admin'?'共享申请审核':'我的共享申请',showKnowledgeSubmissions,'secondary-button'));m.append(tabs);
 m.append(el('p',scope==='personal'?'你的上传资料仅本人可见。核对原文后自动用于本人的相关提问；主动提交共享申请时，管理员才能查看提交的固定版本。':'公司共享库包含公共工艺资料和管理员正式发布的文档，所有账号均可检索。个人上传不会自动公开，也不会替换现行工艺标准。','modal-description'));
 if(scope==='personal'){
   m.append(button('上传个人资料',showDocumentCenter,'primary-button'));
   const owned=await api('/api/documents');if(!owned.length)m.append(el('p','还没有个人资料。上传后请核对原文，再用于个人检索。'));
   for(const d of owned){const c=el('div',null,'source-card');c.append(el('h4',d.filename),el('span',d.status==='approved'?'个人可检索 · 仅本人可见':'待核对或修订 · 仅本人可见','source-tag'),el('p',(d.text||'').slice(0,160)),button('查看与核对',()=>showDocumentJob(d.id),'secondary-button'));m.append(c);}
 }else{
   if(currentUser.role==='admin')m.append(button('上传公司资料',showDocumentCenter,'primary-button'));
   if(currentUser.role==='admin')for(const r of releases){const row=el('div',null,'source-card');row.append(el('strong',r.title+' · 公司已发布'),button('停用共享资料',async()=>{if(!confirm('停用后新任务不再检索此资料，历史任务保留引用。'))return;try{await api('/api/knowledge/'+r.id+'/withdraw',{method:'POST'});await showKnowledge();}catch(e){toast(e.message);}},'secondary-button'));m.append(row);}
   for(const d of docs.filter(d=>d.scope!=='personal')){const c=el('div',null,'source-card');c.append(el('h4',d.title),el('span',d.origin==='admin_published'?'公司共享 · 管理员已发布':d.status==='obsolete'?'历史废止':d.origin==='synthetic'?'模拟规范':d.origin==='project_authored'?'项目说明':'公开资料','source-tag'),el('p',d.content.slice(0,200)+(d.content.length>200?'…':'')),button(d.doc_id+' '+d.revision,()=>showDocument(d),'citation'));m.append(c);}
 }
 }catch(e){toast(e.message);}
}
$('knowledge').onclick=()=>showKnowledge();
function showKnowledgeSubmission(d){
 const m=modal('申请共享到公司库'),[label,title]=inputField('共享资料名称');title.value=d.filename;title.maxLength=120;
 const version=d.versions.find(v=>v.version===d.approved_version);
 m.append(el('p','提交后，管理员可查看当前R'+d.approved_version+'版本及核对记录。你的其他版本、后续修订和未提交的个人资料仍只对本人可见。审核通过后，这个固定版本将成为公司共享资料。','modal-description'),label,el('pre',version.text,'document-preview'),el('p','核对记录：'+(version.review?.note||''),'modal-description'));
 const submit=button('提交共享审核',async()=>{submit.disabled=true;try{await api('/api/knowledge/submissions',{method:'POST',body:JSON.stringify({document_id:d.id,title:title.value})});await showKnowledgeSubmissions();toast('已提交固定版本，等待管理员审核');}catch(e){toast(e.message);}finally{submit.disabled=false;}},'primary-button');m.append(submit);
}
async function showKnowledgeSubmissions(){
 try{const rows=await api('/api/knowledge/submissions'),isAdmin=currentUser.role==='admin',m=modal(isAdmin?'公司共享申请审核':'我的共享申请');
 m.append(el('p',isAdmin?'这里只能查看员工主动提交的版本。通过后发布固定文本到公司库，不修改员工原文件；未提交的个人资料不可访问。':'提交的版本保持固定。审核通过才对公司共享，后续修改需要重新核对并提交。','modal-description'));
 if(!rows.length)m.append(el('p','暂无共享申请。'));
 const status={pending_review:'待管理员审核',approved:'已发布公司库',rejected:'已驳回'};
 for(const row of rows){const c=el('div',null,'source-card');c.append(el('h4',row.title+' · R'+row.document_version),el('span',status[row.status]||row.status,'source-tag'),el('p','提交人：'+row.submitted_by),el('pre',row.snapshot.text,'document-preview'));
 if(row.review)c.append(el('p','审核说明：'+row.review.note));
 if(isAdmin&&row.status==='pending_review'){const [label,note]=inputField('共享审核说明');c.append(label);
 for(const [approved,text] of [[true,'审核通过并发布公司库'],[false,'驳回共享申请']]){const btn=button(text,async()=>{btn.disabled=true;try{await api('/api/knowledge/submissions/'+row.id+'/review',{method:'POST',body:JSON.stringify({approved,note:note.value})});await showKnowledgeSubmissions();toast(approved?'已发布固定版本到公司库':'共享申请已驳回');}catch(e){toast(e.message);}finally{btn.disabled=false;}},approved?'primary-button':'secondary-button');c.append(btn);}}
 m.append(c);}m.append(button('返回工艺知识库',()=>showKnowledge(),'secondary-button'));
 }catch(e){toast(e.message);}
}

$("memories").onclick=()=>showMemories().catch(e=>toast(e.message));
async function showMemories(){
  const list=await api("/api/memories"),m=modal("长期记忆");
  m.append(el("p","保存已核实的分析经验或手动备注，后续相关任务会检索召回。记忆只提供历史背景，不能替代当前规范与原始数据。","modal-description"));
  const input=el("textarea");input.placeholder="例如：分析热压批次时，优先核对传感器校准记录。";input.maxLength=1500;input.setAttribute("aria-label","新增长期记忆");m.append(input,button("保存记忆",async()=>{try{await api("/api/memories",{method:"POST",body:JSON.stringify({content:input.value})});showMemories();}catch(e){toast(e.message);}},"primary-button"));
  if(!list.length)m.append(el("p","还没有记忆。可在完成分析后保存已验证结论。","modal-description"));
  list.forEach(item=>{const c=el("div",null,"memory-card");c.append(button("删除",async()=>{try{await api("/api/memories/"+encodeURIComponent(item.id),{method:"DELETE"});showMemories();}catch(e){toast(e.message);}}),el("small",item.kind==="verified_result"?"已验证结论":"手动备注"),el("p",item.content));if(item.source_task_id)c.append(el("small","来源任务："+item.source_task_id));m.append(c);});
}
$("settings").onclick=()=>openSettings(false);
function openSettings(){
  if(!currentUser){showLogin();return;}
  const m=modal("工作空间设置");m.append(el("p","当前账号："+currentUser.username+" · "+(currentUser.role==="admin"?"管理员":"普通用户"),"modal-description"));
  m.append(el("p","模型由服务器统一配置，登录后直接使用。个人会话、记忆和上传资料按账号隔离；管理员通过提交快照审核公司共享申请。","modal-description"));
  if(currentUser.role==="admin")m.append(button("账号管理",showAccounts,"secondary-button"),button("项目权限管理",()=>showProjectPolicies(),"secondary-button"));
  m.append(button("退出登录",logout,"secondary-button"));if(currentUser.role!=="admin")return;m.append(el("h3","服务状态"));
  for(const [key,c] of Object.entries(healthData.components||{})){const row=el("div",null,"health-row");row.append(el("span",{database:"数据存储",short_memory:"短期记忆",knowledge:"知识检索"}[key]),el("span",c.backend+" · "+c.status));m.append(row);}
}
async function initialize(){
  const epoch=++authEpoch;
  try{const s=await fetch('/api/auth/status');if(s.ok){const status=await s.json();if(epoch!==authEpoch)return;$("auth-register").hidden=!status.registration;$("auth-footnote").textContent=status.registration?'没有账号？点击“注册账号”，注册后即可使用分析功能。':'请使用管理员提供的账号登录。';if(!status.registration&&authMode!=='login')setAuthMode('login');}}catch{}
  const response=await fetch('/api/auth/me',{credentials:'same-origin'});
  if(epoch!==authEpoch)return;
  if(!response.ok){showLogin(true);return;}
  const user=await response.json();if(epoch!==authEpoch)return;showWorkspace(user);
  try{const r=await fetch("/health");healthData=await r.json();$("model-label").replaceChildren(el("span",null,"status-dot"),document.createTextNode(healthData.model_configured?"工艺与项目助手":"本地规则演示"));$("model-label").title="运行时："+healthData.execution_engine;if(!healthData.ok)$("model-label").textContent="部分服务未就绪";await refreshHistory();
    await refreshProjectChoices();
    const documents=await api("/api/knowledge");$("knowledge-count").textContent=documents.length;
    const batches=await api("/api/batches");$("batch").replaceChildren(el("option","不指定，从问题和上下文识别"));$("batch").firstChild.value="";
    batches.forEach(b=>{const o=el("option",b.batch_id+" · "+b.row_count+"条");o.value=b.batch_id;$("batch").append(o);});

    const count=$("dataset-caption");if(count)count.textContent=(healthData.dataset?.measurement_rows||0)+"条模拟测量 · "+batches.length+"个批次";
  }catch(e){if(!$("modal").open)toast(e.message);}
}
initialize();


$("login-form").onsubmit=async e=>{
  e.preventDefault();++authEpoch;const registering=authMode==="register";if(registering&&$("login-password").value!==$("register-password-confirm").value){$("login-error").textContent="两次输入的密码不一致";return;}if(registering){try{checkNewPassword($("login-password").value);}catch(err){$("login-error").textContent=err.message;return;}}$("login-submit").disabled=true;$("auth-login").disabled=true;$("auth-register").disabled=true;$("login-error").textContent="";
  try{const r=await fetch(registering?'/api/auth/register':'/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Proclab-Request':'1'},body:JSON.stringify({username:$("login-username").value.trim(),password:$("login-password").value})});
    if(!r.ok){const err=await r.json();throw Error(typeof err.detail==='string'?err.detail:(registering?'请检查账号格式及密码长度':'登录失败'));}
    $("login-password").value="";$("register-password-confirm").value="";newChat();await initialize();
  }catch(e){$("login-error").textContent=e.message;}finally{$("login-submit").disabled=false;$("auth-login").disabled=false;$("auth-register").disabled=false;}
};
async function logout(){
  ++authEpoch;
  if(typeof cancelVoice==='function')cancelVoice();
  if(liveController)liveController.abort();
  await fetch('/api/auth/logout',{method:'POST',credentials:'same-origin',headers:{'X-Proclab-Request':'1'}});
  conversationId=null;tasks=[];selectedTask=null;setSending(false);$("history").replaceChildren();$("messages").replaceChildren();showLogin();
}
$("logout").onclick=logout;
function inputField(label,type='text'){const wrap=el('label',label),input=el('input');input.type=type;input.setAttribute('aria-label',label);wrap.append(input);if(type==='password')attachPasswordToggle(input);return [wrap,input];}
async function retryTask(t,extra={}){
  if(t.permissions?.analyze===false){toast("当前项目权限不允许重新分析");return;}
  try{const child=await api('/api/tasks/'+t.task_id+'/retry',{method:'POST',body:JSON.stringify(extra)});if($("modal").open)$("modal").close();await loadConversation(child.conversation_id);toast('已启动修复版本 R'+child.repair_version);}catch(e){toast(e.message);}
}
function showTaskRepair(t){
  if(t.permissions?.analyze===false){toast("当前项目权限不允许补证");return;}
  if(t.intent==="optimization")return showDesignRepair(t);
  const m=modal('补充证据与修复');m.append(el('p','原任务和缺失记录会保留。补充测量先提交审核，审核通过后用新证据创建分析版本。','modal-description'));
  const missing=t.analysis?.missing||[];
  if(missing.length){const form=el('div',null,'repair-form'),fields=[];
    for(const f of missing){const [label,input]=inputField('第 '+f.row_id+' 行 · '+(parameterNames[f.parameter]||f.parameter),'number');input.step='any';const unit={temperature_c:'℃',pressure_mpa:'MPa',viscosity_pas:'Pa·s'}[f.parameter];label.append(el('small',unit));fields.push([f,input,unit]);form.append(label);}
    const [label,note]=inputField('补充测量的来源与时间');form.append(label,button('提交补充证据',async()=>{try{
      if(fields.some(([,i])=>!i.value.trim()))throw Error('请填写全部补充值');
      await api('/api/tasks/'+t.task_id+'/supplements',{method:'POST',body:JSON.stringify({source_note:note.value,corrections:fields.map(([f,i,unit])=>({row_id:f.row_id,parameter:f.parameter,value:Number(i.value),unit}))})});
      await showReviewCenter();toast('补证已提交，请核对后审核');}catch(e){toast(e.message);}},'primary-button'));m.append(form);
  }
  m.append(button('保持原输入，限次重试',()=>retryTask(t),'secondary-button'));
  if(t.batch_id){const [label,input]=inputField('如批次选错，填写正确批次编号');input.value=t.batch_id;m.append(label,button('按所填批次重试',()=>retryTask(t,{batch_id:input.value.trim()}),'secondary-button'));}
  m.append(button('上传或修复来源文档',showDocumentCenter,'secondary-button'));
}
async function showDocumentCenter(){
  try{const cap=await api('/api/capabilities'),list=await api('/api/documents'),m=modal('上传与解析资料');
    m.append(el('p','支持 PDF、图片、Word、TXT 和 Markdown。PDF/图片当前只解析前2页；Word提取正文和表格，TXT/Markdown提取全文（最多3万字，不识别Word内嵌图片）。核对并审核后可用于本次提问，管理员还可发布到共享知识库。','modal-description'));
    const form=el('div',null,'repair-form'),file=el('input');file.type='file';file.accept='.pdf,.png,.jpg,.jpeg,.docx,.txt,.md';file.setAttribute('aria-label','选择工艺文档');
    const mode=el('select');mode.setAttribute('aria-label','文档解析方式');for(const [value,label] of [['precision','自动解析（推荐）'],['fallback','OCR 1.5 · 图片兜底'],['complex','Qwen3-VL · 图片转写']]){const o=el('option',label);o.value=value;mode.append(o);}
    const submit=button('开始解析',async()=>{const f=file.files[0];if(!f){toast('请先选择文件');return;}if(f.size>cap.documents.max_bytes){toast('文件超过大小限制');return;}submit.disabled=true;submit.textContent='正在解析…';
      try{const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(f);});
        const result=await api('/api/documents/parse',{method:'POST',body:JSON.stringify({filename:f.name,content_base64:encoded,mode:mode.value})});await showDocumentJob(result.id);
      }catch(e){if(e.payload?.document_id)await showDocumentJob(e.payload.document_id);else toast(e.message);}finally{submit.disabled=false;submit.textContent='开始解析';}
    },'primary-button');form.append(file,mode,submit);m.append(form);
    for(const d of list){const card=el('div',null,'source-card');card.append(el('h4',d.filename),el('p',d.status+' · 解析尝试 '+d.attempts+' 次'),button('查看、修订与审核',()=>showDocumentJob(d.id),'secondary-button'));m.append(card);}
  }catch(e){toast(e.message);}
}
$('parse-document').onclick=()=>{closeComposerMenus();showDocumentCenter();};
function showKnowledgePublish(d){const m=modal('发布共享资料'),[label,title]=inputField('资料名称');title.value=d.filename;m.append(el('p','仅发布当前已核对的文本。所有注册用户都可以通过提问检索此资料；不会自动替换工艺参数标准。','modal-description'),label,button('确认发布',async()=>{try{await api('/api/knowledge/publish',{method:'POST',body:JSON.stringify({document_id:d.id,title:title.value})});$('knowledge-count').textContent=(await api('/api/knowledge')).length;await showKnowledge();toast('已发布，普通用户提问时可自动检索');}catch(e){toast(e.message);}},'primary-button'));}
function showUsage(){closeComposerMenus();const m=modal('发送问题后，系统会做什么？');
 m.append(el('p','你只需描述目标。系统先判断问题需要哪种处理；不会让所有专业模块每次都运行。','modal-description'));
 const items=[['普通问题','例如“这个平台能做什么”：直接交给问答模型回答，不启动一整套工艺分析。'],['问工艺资料','例如“热压温度有哪些要求”：检索工艺知识库和你附加的已审核文件，依据原文回答并检查引用。'],['分析一个生产批次','例如“B-102 有哪些异常”：识别批次和项目 → 规划需要的专业模块 → 读取测量数据、检索工艺规范 → 比较参数和统计 → 核对来源并独立复算 → 输出报告。'],['查询统计数字','例如“各设备有多少批次超限”：识别指标与范围 → 生成受控只读查询 → 查询数据 → 按发布口径独立复算 → 展示结果和依据。'],['发现资料缺失或冲突','保留缺口并提示补充、复核，不猜测缺失数值。报告中的“任务分工与进度”展示这一次实际运行了哪些步骤。'],['快速与深度思考','决定模型投入程度。快速沿用各任务对应的模型；深度思考使用推理模型，通常更慢。两种模式的工艺核验步骤都保留。'],['＋中的资料和设置','上传文件后提取文字，核对审核后用于提问；资料记录可修订或重试。管理员还可发布共享知识。批次从问题识别，项目通常沿用本人项目；需要时可手动切换。'],['语音输入','点击麦克风开始听写，声波随音量变化。左侧叉号取消本次听写，停止听写后转成文字供核对；右侧发送按钮会停止听写、完成转写后提交。最长听写 60 秒，按 Esc 也可取消。']];
 for(const [title,text] of items)m.append(el('h3',title),el('p',text,'modal-description'));
}
$('usage-help').onclick=showUsage;$('query-help').onclick=showUsage;
document.querySelectorAll('[data-query]').forEach(b=>b.onclick=()=>{$('question').value=b.dataset.query;$('question').focus();});
async function showDocumentJob(id){
  try{const d=await api('/api/documents/'+id),m=modal('文档 · '+d.filename);m.append(el('p','状态：'+d.status+' · 文件摘要 '+d.sha256.slice(0,16),'modal-description'));
    if(d.failure)m.append(el('p',d.failure.message),el('p',d.failure.actions.join('；'),'report-notice'));
    const form=el('div',null,'repair-form'),text=el('textarea');text.value=d.text||'';text.rows=12;text.setAttribute('aria-label','解析文本');const [label,note]=inputField('修订或审核说明');form.append(text,label);
    form.append(button('保存文本修订',async()=>{try{await api('/api/documents/'+id+'/correct',{method:'POST',body:JSON.stringify({text:text.value,note:note.value})});await showDocumentJob(id);}catch(e){toast(e.message);}},'secondary-button'));
    if(d.status==='awaiting_review')for(const [approved,label] of [[true,'核对原文并用于个人库'],[false,'驳回当前文本']])form.append(button(label,async()=>{try{await api('/api/documents/'+id+'/review',{method:'POST',body:JSON.stringify({approved,note:note.value})});await showDocumentJob(id);}catch(e){toast(e.message);}},approved?'primary-button':'secondary-button'));
    if(d.status==='approved'&&currentUser.role==='admin')form.append(button('发布到公司共享库',()=>showKnowledgePublish(d),'primary-button'));
    if(d.status==='approved'&&currentUser.role!=='admin')form.append(button('申请共享到公司库',()=>showKnowledgeSubmission(d),'secondary-button'));
    if(d.status==='approved')form.append(button('将已审核文档用于提问',()=>{setAttachedDocuments([d]);$("intent").value='knowledge';$("batch").value='';updateIntent();$("modal").close();$("question").focus();},'primary-button'));
    form.append(button('抽取文本中的候选字段',()=>{$("question").value='请提取以下文档的工艺参数字段，保留原文证据：\n'+text.value.slice(0,11000);$("intent").value='extract';$("batch").value='';selectedDocumentIds=[];updateIntent();$("modal").close();},'secondary-button'));
    if(['needs_repair','awaiting_review'].includes(d.status)){
      const mode=el('select');mode.setAttribute('aria-label','修复解析方式');for(const value of ['precision','fallback','complex']){const o=el('option',value);o.value=value;mode.append(o);}form.append(mode,button('更换方式重新解析',async()=>{try{await api('/api/documents/'+id+'/retry',{method:'POST',body:JSON.stringify({mode:mode.value})});await showDocumentJob(id);}catch(e){toast(e.message);await showDocumentJob(id);}},'secondary-button'));
    }
    m.append(form,el('p','每次修订保留历史文本。审核只确认本次资料的使用范围，不会自动改写现行SOP。','report-notice'));
    for(const v of d.versions||[]){const details=el('details');details.append(el('summary','R'+v.version+' · '+v.origin+(v.review?.approved?' · 已审核':'')),el('pre',v.text,'document-preview'));m.append(details);}
  }catch(e){toast(e.message);}
}
async function showReviewCenter(){
  try{const data=await api('/api/reviews'),m=modal('审核与修复');m.append(el('p','查看本人任务及个人资料的核对记录。公司共享申请单独处理。','modal-description'));if(currentUser.role==='admin')m.append(button('查看审计记录',showAudit,'secondary-button'));m.append(button(currentUser.role==='admin'?'公司共享申请审核':'我的共享申请',showKnowledgeSubmissions,'secondary-button'));
    m.append(el('h3','待审核的补充测量'));
    const pending=data.supplements.filter(s=>s.status==='pending_review');if(!pending.length)m.append(el('p','暂无待审核补证。','modal-description'));
    for(const s of pending){if(s.permissions?.analyze===false){m.append(el('p',s.batch_id+' · 当前项目只可查看，不能审核补证并重算','report-notice'));continue;}const card=el('div',null,'repair-form');card.append(el('strong',s.batch_id+' · 补充证据'),el('p',s.source_note));for(const c of s.corrections)card.append(el('p','第 '+c.row_id+' 行 '+(parameterNames[c.parameter]||c.parameter)+'：'+(c.original_value||'缺失')+' → '+c.value+' '+c.unit));const [label,note]=inputField('补证审核说明');card.append(label);
      for(const [approved,label] of [[true,'确认补证并重新分析'],[false,'驳回补证']])card.append(button(label,async()=>{try{const result=await api('/api/supplements/'+s.id+'/review',{method:'POST',body:JSON.stringify({approved,note:note.value})});if(result.new_task){$("modal").close();await loadConversation(result.new_task.conversation_id);toast('已创建带审核证据的修复版本');}else {await showReviewCenter();if(result.launch_error)toast(result.launch_error);}}catch(e){toast(e.message);}},approved?'primary-button':'secondary-button'));m.append(card);}
    for(const s of data.supplements.filter(s=>s.status==='approved'&&!s.new_task_id&&s.permissions?.analyze!==false)){const card=el('div',null,'source-card');card.append(el('h4',s.batch_id+' · 已审核补证待重算'),el('p',s.launch_error||'尚未创建新分析版本'),button('使用该补证重新分析',async()=>{const t=await api('/api/tasks/'+s.parent_task_id);await retryTask(t,{evidence_bundle_id:s.id});},'secondary-button'));m.append(card);}
    m.append(el('h3','待复核的分析任务'));for(const t of data.tasks){const card=el('div',null,'source-card');card.append(el('h4',t.question),el('p',t.review_reason),button('查看并补充证据',()=>showTaskRepair(t),'secondary-button'),button('打开任务',async()=>{$("modal").close();await loadConversation(t.conversation_id);},'secondary-button'));m.append(card);}
    m.append(el('h3','文档审核'));for(const d of data.documents.filter(d=>['needs_repair','awaiting_review'].includes(d.status))){const card=el('div',null,'source-card');card.append(el('h4',d.filename),el('p',d.status),button('查看文档版本',()=>showDocumentJob(d.id),'secondary-button'));m.append(card);}
  }catch(e){toast(e.message);}
}
$("review-center").onclick=showReviewCenter;
async function showAudit(){if(currentUser?.role!=='admin'){toast('只有管理员可以查看审计记录');return;}try{const events=await api('/api/audit'),m=modal('审计记录');m.append(table(['时间','操作','对象','执行账号'],events.map(e=>[new Date(e.created_at).toLocaleString(),e.action,e.target.slice(0,16),e.actor.slice(0,16)])));}catch(e){toast(e.message);}}
async function showAccounts(){
  if(currentUser?.role!=='admin'){toast('只有管理员可以管理账号');return;}
  try{const m=modal('账号管理'),tools=el('div',null,'account-filters');
    const [searchLabel,search]=inputField('搜索账号');const status=el('select');status.setAttribute('aria-label','账号状态筛选');
    for(const [v,label] of [['','全部状态'],['true','已激活'],['false','已封禁']]){const o=el('option',label);o.value=v;status.append(o);}
    const list=el('div',null,'account-list');tools.append(searchLabel,status,button('查询账号',load,'secondary-button'),button('创建账号',()=>showAccountEditor(null),'primary-button'));
    m.append(el('p','可查询、创建、修改、封禁、激活或删除账号。修改密码和封禁会立即撤销该账号的登录会话。','modal-description'),tools,list);
    async function load(){try{const query=new URLSearchParams({q:search.value.trim()});if(status.value)query.set('active',status.value);const users=await api('/api/admin/users?'+query);list.replaceChildren();
      if(!users.length)list.append(el('p','没有匹配的账号。','modal-description'));
      for(const u of users){const card=el('div',null,'account-card');card.dataset.accountId=u.id;card.dataset.username=u.username;
        card.append(el('strong',u.username),el('span',(u.role==='admin'?'管理员':'普通用户')+' · '+(u.active?'已激活':'已封禁'),'source-tag'));
        const actions=el('div',null,'button-row');actions.append(button('查看详情',()=>showAccountDetail(u.id),'secondary-button'),button('修改账号',()=>showAccountEditor(u),'secondary-button'));
        if(u.role!=='admin'){actions.append(button(u.active?'封禁账号':'激活账号',async()=>{try{await api('/api/admin/users/'+u.id,{method:'PATCH',body:JSON.stringify({active:!u.active})});await load();toast(u.active?'已封禁并撤销登录':'已激活账号');}catch(e){toast(e.message);}},'secondary-button'),button('删除账号',async()=>{
          if(!window.confirm('确认删除账号 '+u.username+'？该账号将无法登录，分析与审计记录会保留。'))return;
          try{await api('/api/admin/users/'+u.id,{method:'DELETE'});await load();toast('账号已删除');}catch(e){toast(e.message);}
        },'danger-button'));}card.append(actions);list.append(card);}
    }catch(e){toast(e.message);}}
    await load();
  }catch(e){toast(e.message);}
}
async function showAccountDetail(id){if(currentUser?.role!=='admin')return;try{const u=await api('/api/admin/users/'+id),m=modal('账号详情');m.append(table(['字段','内容'],[['账号',u.username],['权限',u.role==='admin'?'管理员':'普通用户'],['状态',u.active?'已激活':'已封禁'],['创建时间',new Date(u.created_at).toLocaleString()],['账号ID',u.id]]),button('返回账号管理',showAccounts,'secondary-button'));}catch(e){toast(e.message);}}
function showAccountEditor(u){if(currentUser?.role!=='admin')return;const isAdmin=u?.role==='admin',m=modal(u?'修改账号':'创建账号'),form=el('div',null,'repair-form'),[nameLabel,name]=inputField('账号名称'),[passwordLabel,password]=inputField(u?'新密码（留空保留）':'初始密码（至少8位）','password');name.value=u?.username||'';name.maxLength=60;password.autocomplete='new-password';password.minLength=isAdmin?12:8;password.maxLength=256;
  form.append(el('p',isAdmin?'管理员密码需12至256位。':normalPasswordHelp+'。','modal-description'));
  form.append(nameLabel,passwordLabel,el('p',u?'修改账号名称或密码后，原登录会话将被撤销。':'新建账号仅具有本人体验空间的权限。','modal-description'),button('保存账号',async()=>{try{
    if(!name.value.trim())throw Error('请填写账号');const data={username:name.value.trim()};if(password.value)data.password=password.value;else if(!u)throw Error('请填写初始密码');
    if(data.password)checkNewPassword(data.password,isAdmin);
    await api('/api/admin/users'+(u?'/'+u.id:''),{method:u?'PATCH':'POST',body:JSON.stringify(data)});
    if(u&&u.id===currentUser.id){showLogin();toast('账号已更新，请重新登录');}else{await showAccounts();toast('账号已保存');}
  }catch(e){toast(e.message);}},'primary-button'),button('返回账号管理',showAccounts,'secondary-button'));m.append(form);
}
$("workflow").onclick=showUsage;

let activeComposerMenu=null,uploadInProgress=false,attachedDocuments=[];
function closeComposerMenus(restoreFocus=false){const old=activeComposerMenu;activeComposerMenu=null;for(const [menu,trigger] of [['attachment-menu','composer-add'],['mode-menu','mode-toggle']]){$(menu).hidden=true;$(trigger).setAttribute('aria-expanded','false');}if(restoreFocus&&old)$(old==='mode-menu'?'mode-toggle':'composer-add').focus();}
function openComposerMenu(menuId,triggerId){if(activeComposerMenu===menuId){closeComposerMenus(true);return;}closeComposerMenus();const menu=$(menuId),trigger=$(triggerId);menu.hidden=false;menu.style.visibility='hidden';const r=trigger.getBoundingClientRect(),box=menu.getBoundingClientRect();menu.style.left=Math.max(8,Math.min(r.left,innerWidth-box.width-8))+'px';menu.style.top=Math.max(8,Math.min(r.top-box.height-10,innerHeight-box.height-8))+'px';menu.style.visibility='';trigger.setAttribute('aria-expanded','true');activeComposerMenu=menuId;(menu.querySelector('[aria-checked="true"]')||menu.querySelector('button'))?.focus();}
$('composer-add').onclick=()=>openComposerMenu('attachment-menu','composer-add');$('mode-toggle').onclick=()=>openComposerMenu('mode-menu','mode-toggle');
for(const id of ['attachment-menu','mode-menu'])$(id).addEventListener('keydown',e=>{const items=[...$(id).querySelectorAll('button:not(:disabled)')],current=items.indexOf(document.activeElement);if(e.key==='Escape'){e.preventDefault();closeComposerMenus(true);}else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?items.length-1:(current+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next]?.focus();}});
document.addEventListener('pointerdown',e=>{if(activeComposerMenu&&!$(activeComposerMenu).contains(e.target)&&!$('composer-add').contains(e.target)&&!$('mode-toggle').contains(e.target))closeComposerMenus();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&activeComposerMenu){e.preventDefault();closeComposerMenus(true);}});
window.addEventListener('resize',()=>closeComposerMenus());$('chat-scroll').addEventListener('scroll',()=>closeComposerMenus());
document.querySelectorAll('[data-analysis-mode]').forEach(b=>b.onclick=()=>{$('analysis-mode').value=b.dataset.analysisMode;$('analysis-mode').onchange();closeComposerMenus(true);});
$('composer-settings').onclick=()=>{closeComposerMenus();$('analysis-options').showModal();};
$('close-analysis-options').onclick=$('apply-analysis-options').onclick=()=>{$('analysis-options').close();$('question').focus();};
$('reset-analysis-options').onclick=()=>{$('project').value=$('project').dataset.defaultProject||'';$('batch').value='';$('intent').value=workspaceKind==='analytics'?'analytics':'auto';$('fault').value='none';for(const [id,value] of Object.entries({initial_c:25,oven_c:210,target_c:180,tau_s:180,duration_s:600}))$(id).value=value;updateIntent();};
function setAttachedDocuments(documents){attachedDocuments=[...new Map(documents.map(d=>[d.id,d])).values()].slice(0,3);selectedDocumentIds=attachedDocuments.map(d=>d.id);const preview=$('attached-evidence');preview.replaceChildren();preview.hidden=!selectedDocumentIds.length;for(const d of attachedDocuments){const chip=el('div',null,'attached-file'),remove=button('',()=>setAttachedDocuments(attachedDocuments.filter(item=>item.id!==d.id)),'attachment-remove');remove.append(icon('close'));remove.setAttribute('aria-label','移除资料 '+d.filename);chip.append(icon('book'),el('span',d.filename),remove);preview.append(chip);}}
async function selectReviewedDocuments(){closeComposerMenus();try{const docs=(await api('/api/documents')).filter(d=>d.status==='approved'),m=modal('选择已审核资料');m.append(el('p','最多附加3份，作为本次提问的资料依据。不会自动公开给其他账号。','modal-description'));if(!docs.length)m.append(el('p','暂无已审核资料，请先上传并核对文件。'));for(const d of docs){const card=el('div',null,'source-card');card.append(el('strong',d.filename),button('添加到本次提问',()=>{if(selectedDocumentIds.includes(d.id)){toast('这份资料已附加');return;}if(selectedDocumentIds.length>=3){toast('最多附加3份资料');return;}setAttachedDocuments([...attachedDocuments.filter(item=>selectedDocumentIds.includes(item.id)),d]);$('intent').value='knowledge';$('batch').value='';updateIntent();$('modal').close();$('question').focus();},'secondary-button'));m.append(card);}}catch(e){toast(e.message);}}
$('select-reviewed').onclick=selectReviewedDocuments;
$('upload-file').onclick=()=>{closeComposerMenus();$('composer-file').value='';$('composer-file').click();};
$('composer-file').onchange=async()=>{const file=$('composer-file').files[0];if(!file||uploadInProgress)return;uploadInProgress=true;$('composer-add').disabled=true;try{const cap=await api('/api/capabilities');if(file.size>cap.documents.max_bytes)throw Error('文件超过大小限制，请拆分后上传');const m=modal('正在解析资料');m.append(el('p',file.name,'modal-description'),el('p','PDF/图片当前识别前2页；Word提取正文和表格，TXT/Markdown最多3万字。完成后请核对文本并审核。','report-notice'));const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});const result=await api('/api/documents/parse',{method:'POST',body:JSON.stringify({filename:file.name,content_base64:encoded,mode:'precision'})});await showDocumentJob(result.id);}catch(e){if(e.payload?.document_id)await showDocumentJob(e.payload.document_id);else{toast(e.message);if($('modal-title').textContent==='正在解析资料')$('modal').close();}}finally{uploadInProgress=false;$('composer-add').disabled=false;}};

function verdictLabel(value){return {conforming:"所检参数符合",nonconforming:"存在参数不符合",indeterminate:"证据不足，无法判断",not_applicable:"不适用工艺符合性判定"}[value]||value;}

function nodeStatus(value){return {pending:"等待依赖",running:"执行中",succeeded:"完成",completed_with_gaps:"存在缺口",skipped:"未触发"}[value]||value;}

$("tab-team").onclick=()=>{inspectorTab="team";renderInspector();};

$("tab-sql").onclick=()=>{inspectorTab="sql";renderInspector();};

function startAnalytics(){newChat("analytics");$("intent").value="analytics";$("question").value="按设备统计全部模拟批次的超限批次比例，并说明指标口径与数据水位。";updateIntent();$("question").focus();}

$("nav-analytics").onclick=startAnalytics;$("start-analytics").onclick=startAnalytics;

$("start-composite").onclick=()=>{newChat("analysis");$("intent").value="composite";$("batch").value="B-102";$("question").value="分析 B-102 参数，对比近30天各设备的超限批次比例，并用一阶热模型模拟升温到目标温度。";updateIntent();$("question").focus();};

function renderTeam(content,t){

  const plan=t.execution_plan;if(!plan){content.append(el("p","正在理解任务并生成执行计划。"));return;}

  content.append(el("h3","任务分工与执行进度"),el("p","查看任务如何拆分、各步骤的处理职责，以及已完成、进行中和待补充的内容。","modal-description"),el("p",t.project_profile?.goal||t.question,"modal-description"));

  const meta=el("div",null,"harness-card");meta.append(el("strong","本次执行范围"),el("div",t.scope.factory_id+" · "+t.scope.project_id),el("div","剩余工具预算："+t.tool_budget+" / "+plan.budget.max_tool_calls),el("div","计划依据与团队版本已冻结"));content.append(meta);

  const list=el("div",null,"agent-team");for(const n of plan.nodes){const d=plan.team[n.capability],card=el("div",null,"agent-node "+(t.step_states[n.id]||"pending"));

    card.append(el("div",d.display_name,"agent-name"),el("span",nodeStatus(t.step_states[n.id]||"pending"),"source-tag"),el("small",n.capability+" · v"+n.agent_version),el("small",n.depends_on.length?"依赖："+n.depends_on.join("、"):"执行入口"));list.append(card);}

  content.append(list,button("查看完整调用与溯源",()=>showExecution(t),"secondary-button"),button("查看结果版本",()=>showResultVersions(t),"secondary-button"));

  if(t.permissions?.analyze!==false&&t.status==="pending_review"&&t.tool_budget>0&&plan.version<3)content.append(button("在剩余预算内重规划",()=>showReplan(t),"secondary-button"));

}

function renderAnalyticsResult(parent,a,showSql=false){

  const card=el("section",null,"analytics-result");card.append(el("h3",a.metric.name),el("p",a.metric.definition,"report-notice"));

  card.append(table(["分组","结果 "+a.metric.unit,"分子 / 分母","缺失参数项"],a.rows.map(r=>[r.dimension,r.value===null?"无可用分母":r.value,r.numerator+" / "+r.denominator,r.missing_parameters])));

  card.append(el("p","时间范围：["+a.time_range.start_inclusive+", "+a.time_range.end_exclusive+") · "+a.time_range.timezone,"report-notice"),el("p","源数据截至 "+a.manifest.watermark+" · "+a.manifest.row_count+"条模拟测量 · 口径 "+a.semantic_version,"report-notice"));

  const details=el("details");details.open=showSql;details.append(el("summary","查询 SQL 与证据"),el("pre",a.sql,"trace-extra"),el("pre",JSON.stringify(a.bindings,null,2),"trace-extra"),el("p","只读查询 · 可信权限绑定 · 查询超时限制 · 结果快照 "+a.query_id,"report-notice"),el("p","结果摘要 "+a.result_sha256,"report-notice"));card.append(details,el("p",a.warning,"report-notice"));parent.append(card);

}

async function showExecution(t){

  try{const d=await api('/api/tasks/'+t.task_id+'/execution'),m=modal('完整执行与证据溯源');

    m.append(el('p','计划、调用、工具、证据、规则核验与结果版本均来自本次持久化执行记录。','modal-description'));

    m.append(el('h3','Agent 调用'),table(['专业能力','状态','尝试','版本'],(d.agent_calls||[]).map(x=>[x.payload.agent.display_name,x.status,x.payload.attempts.length,x.payload.agent.version])));

    m.append(el('h3','工具调用'),table(['工具','状态','耗时 ms','尝试'],(d.tool_calls||[]).map(x=>[x.payload.tool,x.status,x.payload.latency_ms??'—',x.payload.attempt])));

    for(const [key,label] of [['plan_versions','计划版本'],['handoffs','交接请求'],['evidence','证据定位与摘要'],['harness_runs','独立规则核验'],['query_snapshots','查询快照'],['result_revisions','结果版本']]){const detail=el('details');detail.append(el('summary',label+' · '+(d[key]||[]).length),el('pre',JSON.stringify(d[key]||[],null,2),'trace-extra'));m.append(detail);}

  }catch(e){toast(e.message);}

}

async function showResultVersions(t){try{const list=await api('/api/tasks/'+t.task_id+'/results'),m=modal('正式结果与修复版本');if(!list.length)m.append(el('p','当前任务尚未形成结果版本。'));for(const row of list){const r=row.payload,c=el('div',null,'source-card');c.append(el('h3','R'+r.version+' · '+({published:'已发布',limited:'限制性说明',rejected:'已驳回'}[r.publication]||r.publication)),el('p',verdictLabel(r.verdict)),el('small',r.created_at),el('p',r.report.summary),el('small','计划 V'+r.plan_version+' · 核验 '+(r.harness_id||'未完成')),el('small','结果摘要 '+r.report_sha256));m.append(c);}}catch(e){toast(e.message);}}

function showReplan(t){if(t.permissions?.analyze===false){toast('当前项目权限不允许重规划');return;}const m=modal('修订执行计划'),note=el('textarea');note.placeholder='说明重新执行的原因，例如补充了资料或需要再次检索';note.minLength=4;note.maxLength=500;m.append(el('p','原计划和调用记录保留。新计划继续使用剩余工具预算；证据变化仍需重新核验。','modal-description'),note,button('创建新计划版本',async()=>{try{const result=await api('/api/tasks/'+t.task_id+'/replan',{method:'POST',body:JSON.stringify({note:note.value})});$('modal').close();updateTask(result);setSending(true);await watch(result);}catch(e){toast(e.message);}},'primary-button'));}


$("workflow").onclick=showUsage;

// A domain task entry and persisted experiment results; no simulated thinking display.
$("start-design").onclick=()=>{
  newChat("analysis");$("intent").value="optimization";$("batch").value="";
  $("question").value="设计升温方案：初温25℃，目标180℃，时间常数180秒，炉温范围190至220℃，时限300秒，先验证200℃方案，在达温时限内尽量降低炉温。";
  updateIntent();$("question").focus();
};
function renderHeatingDesign(parent,t){
  const d=t.design_loop||t.report?.design;if(!d)return;
  const card=el("section",null,"heating-design-result");card.append(el("h3","升温方案比较"));
  if(d.constraints){
    const p=d.constraints,goal=p.objective==="fastest_within_bounds"?"在范围内尽快达温":"在时限内尽量降低炉温";
    card.append(el("p",goal+" · 初温 "+p.initial_c+" ℃ → "+p.target_c+" ℃ · 时限 "+p.deadline_s+" 秒 · 炉温 "+p.oven_min_c+"–"+p.oven_max_c+" ℃ · 时间常数 "+p.tau_s+" 秒","report-notice"));
  }
  if(d.trials.length){
    card.append(table(["方案","炉温 ℃","时限末温 ℃","达温时间 s","结果"],d.trials.map(x=>{
      const r=x.result,hit=r.reached_at_s;return [x.id,r.input.oven_c,r.final_c.toFixed(3),hit===null?"时限内未达温":hit.toFixed(2),x.id===d.selected_trial?"已选可行候选":hit===null?"未满足":"满足时限"];
    })));
    const solver=d.trials[0].result.solver;
    card.append(el("p","计算工具："+solver.name+" · SciPy "+solver.version+" · 结果经独立解析计算核验","report-notice"));
    const inverse=d.trials[0].result.inverse_design;
    if(inverse)card.append(el("p","反算工具："+inverse.tool+" · "+(inverse.minimum_oven_c===null?"当前模型与范围内无法满足时限":"当前模型满足时限的炉温参考下界约 "+inverse.minimum_oven_c.toFixed(3)+" ℃，候选仍需正向验证"),"report-notice"));
  }
  if(d.decisions.length){
    const details=el("details");details.open=true;details.append(el("summary","实际行动与反馈"));
    for(const a of d.decisions){
      const row=el("div",null,"design-decision");
      const source={native_function:"模型决策",rules:"规则降级",rules_fallback:"模型不可用，规则降级"}[a.provider]||a.provider;
      row.append(el("strong","第 "+a.index+" 次 · "+source+" · "+({simulate:"调用计算",finish:"结束比较",clarify:"请求补充"}[a.action]||a.action)),
        el("p",a.reason),el("small",a.observed_trials.length?"已读取方案 "+a.observed_trials.join("、")+" 的实际结果":"尚无试算结果"));
      if(a.status==="rejected")row.append(el("span","此行动未通过参数检查，未执行","report-notice"));
      details.append(row);
    }card.append(details);
  }
  if(d.stop_reason){
    const reasons={agent_finished:"已根据计算结果结束",trial_limit:"已达到本次试算次数上限",missing_inputs:"等待补充设计条件",
      tool_budget_reserved:"已保留独立核验所需预算",invalid_model_action:"候选行动未通过约束检查",solver_failed:"计算工具未完成",
      decision_failed:"决策调用未完成",missing_specification:"缺少适用规范",out_of_specification:"设计范围超出规范",clarification_requested:"等待条件澄清"};
    card.append(el("p","停止原因："+(reasons[d.stop_reason]||d.stop_reason),"lineage-note"));
  }
  card.append(el("p","仅比较已试方案，不证明全局最优。"+d.assumptions,"report-notice"));
  if(t.permissions?.analyze!==false&&!["queued","running"].includes(t.status))card.append(button("修改条件后创建新版本",()=>showDesignRepair(t),"secondary-button"));
  parent.append(card);
}
function showDesignRepair(t){
  if(t.permissions?.analyze===false){toast('当前项目权限不允许修改分析条件');return;}
  const m=modal("补充或修改升温设计条件"),form=el("form",null,"repair-form"),fields={};
  m.append(el("p","补充条件后重新计算，原任务与原方案保留。时间常数必须由你提供，本工具不会假定设备标定结果。","modal-description"));
  const spec=[["initial_c","初温 ℃",-20,100],["target_c","目标温度 ℃",180,219],["tau_s","时间常数 秒",10,3600],
    ["deadline_s","达温时限 秒",1,14400],["oven_min_c","炉温下限 ℃",180,220],["oven_max_c","炉温上限 ℃",180,220],["baseline_c","基准炉温 ℃（可选）",180,220]];
  for(const [key,name,min,max] of spec){
    const [label,input]=inputField(name,"number");input.step="any";input.min=min;input.max=max;input.required=key!=="baseline_c";
    if(t.design_params?.[key]!=null)input.value=t.design_params[key];fields[key]=input;form.append(label);
  }
  const label=el("label","优化目标"),goal=el("select");goal.setAttribute("aria-label","优化目标");
  for(const [value,text] of [["lowest_oven_meeting_deadline","在时限内降低炉温"],["fastest_within_bounds","在范围内缩短达温时间"]]){const o=el("option",text);o.value=value;goal.append(o);}
  goal.value=t.design_params?.objective||"lowest_oven_meeting_deadline";label.append(goal);form.append(label);
  const submit=el("button","创建新计算版本","primary-button");submit.type="submit";form.append(submit);
  form.onsubmit=e=>{
    e.preventDefault();if(!form.reportValidity())return;
    const params={objective:goal.value};for(const [key,input] of Object.entries(fields))params[key]=input.value.trim()?Number(input.value):null;
    retryTask(t,{design_params:params});
  };m.append(form);
}


async function refreshProjectChoices(){
  projectChoices=await api('/api/projects');const select=$('project'),previous=select.value;select.replaceChildren();
  for(const p of projectChoices){const suffix=p.stage==='archived'?'已归档':p.stage==='review'?'仅可复核':p.permissions?.analyze?'可分析':'仅可查看';const o=el('option',p.name+' · '+suffix);o.value=p.id;o.disabled=!p.permissions?.analyze;select.append(o);}
  const preferred=projectChoices.find(p=>p.id===previous&&p.permissions?.analyze)||projectChoices.find(p=>p.created_by===currentUser.id&&p.permissions?.analyze)||projectChoices.find(p=>p.permissions?.analyze);
  select.value=preferred?.id||'';select.dataset.defaultProject=select.value;
}
async function showProjectPolicies(projectId){
  if(currentUser?.role!=='admin')return;
  try{
    const [projects,users]=await Promise.all([api('/api/projects'),api('/api/admin/users')]),m=modal('项目权限管理');
    m.append(el('p','由管理员设置项目阶段与成员权限。授权项目不开放员工的个人会话、资料和记忆。成员之间的私人任务仍按账号隔离。','modal-description'));
    const project=el('select');project.setAttribute('aria-label','管理项目');
    for(const p of projects){const o=el('option',p.name);o.value=p.id;project.append(o);}if(projectId)project.value=projectId;
    const details=el('div',null,'repair-form');m.append(project,details);project.onchange=load;
    async function load(){
      const id=project.value,p=projects.find(p=>p.id===id);details.replaceChildren(el('p','正在加载成员权限…','modal-description'));const rows=await api('/api/projects/'+encodeURIComponent(id)+'/members');
      if(project.value!==id)return;details.replaceChildren();
      const stage=el('select');stage.setAttribute('aria-label','项目阶段');for(const [v,text] of [['analysis','分析中'],['review','仅复核'],['archived','已归档']]){const o=el('option',text);o.value=v;stage.append(o);}stage.value=p.stage;
      details.append(el('h3','项目阶段'),stage,button('保存项目阶段',()=>save({stage:stage.value}),'secondary-button'));
      details.append(el('h3','已分配的成员'),table(['账号','项目权限','账号状态'],rows.map(r=>[r.username,{owner:'本人项目',analyst:'可分析',reviewer:'可复核',viewer:'仅查看',revoked:'已撤销'}[r.role]||r.role,r.active?'正常':'已停用'])));
      const member=el('select');member.setAttribute('aria-label','项目成员账号');
      for(const u of users.filter(u=>u.active&&u.id!==p.created_by)){const o=el('option',u.username);o.value=u.id;member.append(o);}
      const role=el('select');role.setAttribute('aria-label','成员项目权限');for(const [v,text] of [['analyst','可分析'],['reviewer','可复核'],['viewer','仅查看'],['revoked','撤销访问']]){const o=el('option',text);o.value=v;role.append(o);}
      const grant=button('保存成员权限',()=>save({member:member.value,role:role.value}),'primary-button');grant.disabled=!member.options.length;
      details.append(el('h3','分配或调整成员'),member,role,grant,el('p','可分析：创建分析、补证、重试与重规划；可复核：处理本人已有的待复核任务；仅查看：读取本人已有记录。归档后停止分析与复核。','modal-description'));
      for(const row of rows.filter(r=>r.role!=='owner'&&r.role!=='revoked'))details.append(button('撤销 '+row.username+' 的项目访问',()=>save({member:row.id,role:'revoked'}),'secondary-button'));
      async function save(data){try{await api('/api/projects/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify(data)});await refreshProjectChoices();await showProjectPolicies(id);toast('项目权限已更新');}catch(e){toast(e.message);}}
    }
    await load();
  }catch(e){toast(e.message);}
}

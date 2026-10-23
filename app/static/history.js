"use strict";
// Persistent account-scoped history, with browser-specific sidebar preferences.
let historyRequestVersion=0,historyMenu=null,historyMenuTrigger=null;
let searchRequestVersion=0,searchTimer=null,searchController=null;
let sidebarResize=null;
const sidebarMedia=window.matchMedia("(max-width: 700px)");
function preferenceKey(name){return "proclab.sidebar."+name+"."+(currentUser?.id||"guest");}
function readPreference(name){try{return localStorage.getItem(preferenceKey(name));}catch{return null;}}
function savePreference(name,value){try{localStorage.setItem(preferenceKey(name),String(value));}catch{}}
function sidebarBounds(){return {min:224,max:Math.max(224,Math.min(440,innerWidth-480))};}
function setSidebarWidth(value,persist=false){
  const bounds=sidebarBounds(),width=Math.round(Math.min(bounds.max,Math.max(bounds.min,Number(value)||246)));
  document.documentElement.style.setProperty("--sidebar-width",width+"px");
  const handle=$("sidebar-resizer");handle.setAttribute("aria-valuenow",String(width));handle.setAttribute("aria-valuemax",String(bounds.max));
  if(persist)savePreference("width",width);
}
function updateSidebarControls(){
  const visible=sidebarMedia.matches?$("sidebar").classList.contains("open"):!document.body.classList.contains("sidebar-collapsed");
  for(const id of ["sidebar-toggle","menu"]){const b=$(id),text=visible?"隐藏侧边栏":"显示侧边栏";b.setAttribute("aria-expanded",String(visible));b.setAttribute("aria-label",text);b.title=text;}
}
function applySidebarPreferences(){
  setSidebarWidth(readPreference("width"));
  document.body.classList.toggle("sidebar-collapsed",readPreference("collapsed")==="true");
  closeMobileSidebar();updateSidebarControls();
}
function closeMobileSidebar(){$("sidebar").classList.remove("open");updateSidebarControls();}
function toggleSidebar(){
  closeHistoryMenu();
  if(sidebarMedia.matches){$("sidebar").classList.toggle("open");}
  else{document.body.classList.toggle("sidebar-collapsed");savePreference("collapsed",document.body.classList.contains("sidebar-collapsed"));}
  updateSidebarControls();
  if(!sidebarMedia.matches&&document.body.classList.contains("sidebar-collapsed"))$("menu").focus();
}
function resetHistoryUI(){
  ++historyRequestVersion;++searchRequestVersion;clearTimeout(searchTimer);searchController?.abort();closeHistoryMenu();
  if($("history-search-dialog").open)$("history-search-dialog").close();
  $("history-search-input").value="";$("history-search-results").replaceChildren();
  closeMobileSidebar();
}
function historyIconButton(name,label,callback,cls=""){
  const b=button("",callback,"history-control "+cls);b.append(icon(name));b.setAttribute("aria-label",label);b.title=label;return b;
}
function renderHistory(items){
  const list=$("history"),existing=new Map([...list.querySelectorAll(".history-row")].map(row=>[row.dataset.conversationId,row]));
  if(!items.length){closeHistoryMenu();list.replaceChildren(el("p","从一个工艺问题开始","muted history-empty"));return;}
  list.querySelectorAll(".history-empty").forEach(n=>n.remove());
  for(const [index,c] of items.entries()){
    let row=existing.get(c.id);
    if(!row){
      row=el("div");row.dataset.conversationId=c.id;
      const open=button("",()=>loadConversation(c.id).catch(e=>toast(e.message)),"history-title");
      const more=historyIconButton("more","",()=>openHistoryMenu(row.historyData,more),"history-more");more.setAttribute("aria-haspopup","menu");more.setAttribute("aria-expanded","false");
      const pin=historyIconButton("pin","",()=>changeHistoryPin(row.historyData,pin),"history-pin");row.append(open,more,pin);
    }
    const [open,more,pin]=row.children,previous=row.historyData;
    if(historyMenuTrigger===more&&previous&&(previous.title!==c.title||previous.pinned!==c.pinned))closeHistoryMenu();
    row.historyData=c;row.className="history-row"+(c.id===conversationId?" selected":"")+(c.pinned?" pinned":"");
    open.textContent=c.title;open.title=c.title;if(c.id===conversationId)open.setAttribute("aria-current","page");else open.removeAttribute("aria-current");
    more.setAttribute("aria-label","更多操作："+c.title);more.title="更多操作："+c.title;
    const pinLabel=(c.pinned?"取消置顶：":"置顶：")+c.title;pin.setAttribute("aria-label",pinLabel);pin.title=pinLabel;pin.setAttribute("aria-pressed",String(c.pinned));
    if(list.children[index]!==row)list.insertBefore(row,list.children[index]||null);
    existing.delete(c.id);
  }
  for(const row of existing.values()){if(row.contains(historyMenuTrigger))closeHistoryMenu();row.remove();}
}
function closeHistoryMenu(focus=false){
  const trigger=historyMenuTrigger;historyMenu?.remove();historyMenu=null;historyMenuTrigger=null;
  trigger?.setAttribute("aria-expanded","false");if(focus&&trigger?.isConnected)trigger.focus();
}
function openHistoryMenu(c,trigger){
  if(historyMenuTrigger===trigger){closeHistoryMenu(true);return;}
  closeHistoryMenu();closeComposerMenus();
  const menu=el("div",null,"history-actions-menu");menu.setAttribute("role","menu");menu.setAttribute("aria-label","分析操作");
  for(const [label,name,fn] of [["重命名","edit",()=>renameHistory(c)],[c.pinned?"取消置顶":"置顶","pin",()=>changeHistoryPin(c)],["删除","trash",()=>deleteHistory(c)]]){
    const item=action(label,name,()=>{closeHistoryMenu();fn();});item.setAttribute("role","menuitem");if(name==="trash")item.classList.add("danger");menu.append(item);
  }
  document.body.append(menu);historyMenu=menu;historyMenuTrigger=trigger;trigger.setAttribute("aria-expanded","true");
  const r=trigger.getBoundingClientRect(),m=menu.getBoundingClientRect();menu.style.left=Math.max(8,Math.min(r.left,innerWidth-m.width-8))+"px";menu.style.top=Math.max(8,Math.min(r.bottom+4,innerHeight-m.height-8))+"px";
  menu.addEventListener("keydown",e=>{if(["ArrowDown","ArrowUp","Home","End"].includes(e.key)){e.preventDefault();const items=[...menu.querySelectorAll("button")],i=items.indexOf(document.activeElement);items[e.key==="Home"?0:e.key==="End"?items.length-1:(i+(e.key==="ArrowDown"?1:-1)+items.length)%items.length].focus();}});
  menu.firstElementChild.focus();
}
async function changeHistoryPin(c,trigger){
  if(trigger)trigger.disabled=true;
  try{await api("/api/conversations/"+c.id,{method:"PATCH",body:JSON.stringify({pinned:!c.pinned})});await refreshHistory();toast(c.pinned?"已取消置顶":"已置顶");}
  catch(e){toast(e.message);}finally{if(trigger?.isConnected)trigger.disabled=false;}
}
function renameHistory(c){
  const body=modal("重命名分析"),form=el("form"),label=el("label","分析名称"),input=el("input"),error=el("p",null,"history-form-error");input.id="history-rename-input";label.htmlFor=input.id;input.value=c.title;input.required=true;input.maxLength=120;error.setAttribute("role","alert");
  const actions=el("div",null,"history-dialog-actions"),cancel=button("取消",()=>$("modal").close(),"secondary-button"),save=button("保存",null,"primary-button");save.type="submit";actions.append(cancel,save);form.append(label,input,error,actions);body.append(form);
  form.onsubmit=async e=>{e.preventDefault();if(!input.value.trim()){error.textContent="请输入分析名称";return;}save.disabled=true;try{const updated=await api("/api/conversations/"+c.id,{method:"PATCH",body:JSON.stringify({title:input.value.trim()})});if(conversationId===c.id)$("conversation-title").textContent=updated.title;$("modal").close();await refreshHistory();toast("名称已更新");}catch(e){error.textContent=e.message;}finally{save.disabled=false;}};
  input.focus();input.select();
}
function deleteHistory(c){
  const body=modal("删除分析"),title=el("p","删除“"+c.title+"”？"),note=el("p","将从最近分析和搜索中移除。执行与审核记录按审计要求保留。","modal-description"),error=el("p",null,"history-form-error"),actions=el("div",null,"history-dialog-actions");error.setAttribute("role","alert");
  const remove=button("删除",async()=>{remove.disabled=true;try{await api("/api/conversations/"+c.id,{method:"DELETE"});$("modal").close();if(conversationId===c.id)newChat();await refreshHistory();toast("分析已删除");}catch(e){error.textContent=e.message;}finally{remove.disabled=false;}},"primary-button danger-button");
  const cancel=button("取消",()=>$("modal").close(),"secondary-button");actions.append(cancel,remove);body.append(title,note,error,actions);cancel.focus();
}
function searchExcerpt(text,query){
  if(!text)return "";const i=text.toLocaleLowerCase().indexOf(query.toLocaleLowerCase()),start=Math.max(0,i-24);return (start?"…":"")+text.slice(start,start+150)+(text.length>start+150?"…":"");
}
async function searchHistory(){
  const version=++searchRequestVersion,user=currentUser?.id,q=$("history-search-input").value.trim();searchController?.abort();searchController=new AbortController();
  $("history-search-results").replaceChildren();$("history-search-status").textContent="正在查找…";
  try{
    const list=await api("/api/conversations?q="+encodeURIComponent(q),{signal:searchController.signal});
    if(version!==searchRequestVersion||user!==currentUser?.id||!$("history-search-dialog").open)return;
    $("history-search-status").textContent=list.length?(q?"找到 "+list.length+" 条分析":"最近的分析")+(list.length===100?" · 最多显示 100 条，请补充关键词":""):(q?"没有找到相关分析，试试其他关键词":"还没有分析记录");
    for(const c of list){
      const b=button("",async()=>{try{await loadConversation(c.id);$("history-search-dialog").close();}catch(e){toast(e.message);}},"history-search-result");b.dataset.conversationId=c.id;
      const heading=el("span",null,"history-result-title");heading.append(icon(c.pinned?"pin":"chat"),el("strong",c.title));b.append(heading);
      if(c.matched_question)b.append(el("span",searchExcerpt(c.matched_question,q),"history-result-excerpt"));
      b.append(el("small",new Date(c.updated_at).toLocaleString("zh-CN")));$("history-search-results").append(b);
    }
  }catch(e){if(version===searchRequestVersion&&e.name!=="AbortError")$("history-search-status").textContent=e.message;}
}
function openHistorySearch(){
  closeHistoryMenu();closeComposerMenus();if($("modal").open)$("modal").close();if($("analysis-options").open)$("analysis-options").close();
  $("history-search-input").value="";$("history-search-dialog").showModal();$("history-search-input").focus();searchHistory();
}
document.addEventListener("DOMContentLoaded",()=>{
  $("history-search").onclick=openHistorySearch;$("sidebar-toggle").onclick=toggleSidebar;
  $("history-search-close").onclick=()=>$("history-search-dialog").close();
  $("history-search-dialog").addEventListener("close",()=>{++searchRequestVersion;clearTimeout(searchTimer);searchController?.abort();});
  $("history-search-input").addEventListener("input",()=>{++searchRequestVersion;clearTimeout(searchTimer);searchController?.abort();$("history-search-results").replaceChildren();$("history-search-status").textContent="正在查找…";searchTimer=setTimeout(searchHistory,220);});
  $("history-search-input").addEventListener("keydown",e=>{if(e.key==="ArrowDown"){e.preventDefault();$("history-search-results").querySelector("button")?.focus();}if(e.key==="Enter"){e.preventDefault();clearTimeout(searchTimer);searchHistory();}});
  document.addEventListener("pointerdown",e=>{if(historyMenu&&!historyMenu.contains(e.target)&&!historyMenuTrigger?.contains(e.target))closeHistoryMenu();});
  document.addEventListener("focusin",e=>{if(historyMenu&&!historyMenu.contains(e.target)&&!historyMenuTrigger?.contains(e.target))closeHistoryMenu();});
  document.addEventListener("keydown",e=>{if(e.key==="Escape"){if(historyMenu){e.preventDefault();closeHistoryMenu(true);}else if($("history-search-dialog").open){e.preventDefault();$("history-search-dialog").close();}else if(sidebarMedia.matches&&!document.querySelector("dialog[open]"))closeMobileSidebar();}});
  $("history").addEventListener("scroll",()=>closeHistoryMenu());
  const handle=$("sidebar-resizer");
  handle.addEventListener("pointerdown",e=>{if(e.button!==0||sidebarMedia.matches)return;e.preventDefault();closeHistoryMenu();sidebarResize={id:e.pointerId};handle.setPointerCapture(e.pointerId);document.body.classList.add("sidebar-resizing");});
  handle.addEventListener("pointermove",e=>{if(sidebarResize?.id===e.pointerId)setSidebarWidth(e.clientX);});
  function finishResize(e){if(sidebarResize?.id!==e.pointerId)return;sidebarResize=null;document.body.classList.remove("sidebar-resizing");savePreference("width",handle.getAttribute("aria-valuenow"));}
  handle.addEventListener("pointerup",finishResize);handle.addEventListener("pointercancel",finishResize);handle.addEventListener("lostpointercapture",finishResize);
  handle.addEventListener("dblclick",()=>setSidebarWidth(246,true));
  handle.addEventListener("keydown",e=>{if(["ArrowLeft","ArrowRight","Home","End"].includes(e.key)){e.preventDefault();const b=sidebarBounds(),width=Number(handle.getAttribute("aria-valuenow"));setSidebarWidth(e.key==="Home"?b.min:e.key==="End"?b.max:width+(e.key==="ArrowRight"?1:-1)*(e.shiftKey?32:8),true);}});
  window.addEventListener("resize",()=>{closeHistoryMenu();setSidebarWidth(readPreference("width"));updateSidebarControls();});
  sidebarMedia.addEventListener("change",()=>{closeMobileSidebar();updateSidebarControls();});
  setSidebarWidth(readPreference("width"));updateSidebarControls();
});

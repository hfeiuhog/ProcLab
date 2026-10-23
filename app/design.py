"""Goal-driven heating experiments: model decisions, scientific tools and independent proof."""
import copy
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .orchestration.contracts import digest
from .steps import event

MAX_TRIALS=3
DEMO_QUESTION="设计升温方案：初温25℃，目标180℃，时间常数180秒，炉温范围190至220℃，时限300秒，先验证200℃方案，在达温时限内尽量降低炉温。"
LABELS={"initial_c":"初温（℃）","target_c":"目标温度（℃）","tau_s":"时间常数（秒）",
        "deadline_s":"达温时限（秒）","objective":"优化目标（降低炉温或缩短达温时间）","oven_min_c":"炉温下限（℃）","oven_max_c":"炉温上限（℃）"}

class HeatingDesignInput(BaseModel):
    model_config=ConfigDict(extra="forbid",allow_inf_nan=False)
    initial_c:float=Field(ge=-20,le=100)
    target_c:float=Field(ge=180,le=219)
    tau_s:float=Field(ge=10,le=3600)
    deadline_s:float=Field(ge=1,le=14400)
    oven_min_c:float=Field(ge=180,le=220)
    oven_max_c:float=Field(ge=180,le=220)
    objective:Literal["lowest_oven_meeting_deadline","fastest_within_bounds"]
    baseline_c:float|None=Field(default=None,ge=180,le=220)
    @model_validator(mode="after")
    def ordered(self):
        if self.oven_min_c>self.oven_max_c:raise ValueError("炉温下限不能高于上限")
        if self.baseline_c is not None and not self.oven_min_c<=self.baseline_c<=self.oven_max_c:
            raise ValueError("基准炉温必须在指定范围内")
        return self

class Action(BaseModel):
    model_config=ConfigDict(extra="forbid",allow_inf_nan=False)
    action:Literal["simulate","finish","clarify"]
    oven_c:float|None=None
    selected_trial:int|None=Field(default=None,ge=1,le=MAX_TRIALS)
    reason:str=Field(min_length=1,max_length=600)

def request_from_text(question,explicit=None):
    """Extract only supplied physical inputs; ambiguity stays visible to the user."""
    number=r"(-?\d+(?:\.\d+)?)"
    eq=r"\s*(?:为|是|=|:|：)?\s*"
    deg=r"\s*(?:℃|°[Cc]|摄氏度)"
    patterns={
        "initial_c":r"(?:初温|初始温度)"+eq+number+deg,
        "target_c":r"(?:目标温度|目标|升温到|升至|达到)"+eq+number+deg,
        "tau_s":r"(?:时间常数|tau|τ)"+eq+number+r"\s*(秒|分钟|s|min)\b?",
        "deadline_s":r"(?:时限|限时|最长时间|达温时限)"+eq+number+r"\s*(秒|分钟|s|min)\b?",
        "baseline_c":r"(?:基准炉温|先验证|先评估|先试)"+eq+number+deg}
    # Chinese units do not have a word boundary; retain explicit unit matching.
    patterns={k:v.replace(r"\b?","") for k,v in patterns.items()}
    found={};gaps=[]
    for key,pattern in patterns.items():
        values=[]
        for match in re.finditer(pattern,question,re.I):
            value=float(match.group(1))
            if key in ("tau_s","deadline_s") and match.group(2).lower() in ("分钟","min"):value*=60
            values.append(value)
        if len(set(values))>1:gaps.append(LABELS.get(key,"基准炉温")+"存在多个不同值，请明确")
        elif values:found[key]=values[0]
    if "deadline_s" not in found:
        matches=list(re.finditer(number+r"\s*(秒|分钟|s|min)\s*(?:内|以内)",question,re.I))
        vals={float(m.group(1))*(60 if m.group(2).lower() in ("分钟","min") else 1) for m in matches}
        if len(vals)==1:found["deadline_s"]=vals.pop()
        elif len(vals)>1:gaps.append("达温时限存在歧义")
    ranges=list(re.finditer(r"炉温(?:范围)?"+eq+number+r"\s*(?:℃|°[Cc])?\s*(?:至|到|[-–—~～])\s*"+number+deg,question))
    if len({(m.group(1),m.group(2)) for m in ranges})>1:gaps.append("炉温范围存在多个不同值")
    elif ranges:found.update(oven_min_c=float(ranges[0].group(1)),oven_max_c=float(ranges[0].group(2)))
    low=bool(re.search(r"降低炉温|最低炉温|炉温尽量低|尽量低的炉温",question))
    fast=bool(re.search(r"最短.{0,5}时间|缩短.{0,6}时间|尽快|最快",question))
    if low and fast:gaps.append("存在两个不同优化目标，请明确优先级")
    elif low:found["objective"]="lowest_oven_meeting_deadline"
    elif fast:found["objective"]="fastest_within_bounds"
    if explicit is not None:
        explicit=HeatingDesignInput.model_validate(explicit).model_dump()
        for key,value in found.items():
            if explicit.get(key) is not None and explicit[key]!=value:gaps.append(LABELS.get(key,"基准炉温")+"与结构化输入不一致")
        found={**found,**explicit}
    missing=[label for key,label in LABELS.items() if key not in found]
    gaps += ["请补充"+label for label in missing]
    if gaps:return None,gaps
    try:return HeatingDesignInput.model_validate(found).model_dump(),[]
    except ValueError as exc:
        return None,["设计条件无效："+str(exc).split("\n")[1][:180]]

def canonical_question(params):
    p=HeatingDesignInput.model_validate(params)
    baseline=f"，先验证{p.baseline_c:g}℃方案" if p.baseline_c is not None else ""
    goal="在达温时限内尽量降低炉温" if p.objective=="lowest_oven_meeting_deadline" else "在允许范围内尽快达温，缩短升温时间"
    return (f"设计升温方案：初温{p.initial_c:g}℃，目标{p.target_c:g}℃，时间常数{p.tau_s:g}秒，"
            f"炉温范围{p.oven_min_c:g}至{p.oven_max_c:g}℃，时限{p.deadline_s:g}秒{baseline}，{goal}。")

def scientific_solve(params,oven_c):
    p=HeatingDesignInput.model_validate(params)
    if not p.oven_min_c<=oven_c<=p.oven_max_c:raise ValueError("候选炉温超出冻结范围")
    payload={k:getattr(p,k) for k in ("initial_c","target_c","tau_s","deadline_s","oven_min_c","oven_max_c")}
    payload["oven_c"]=float(oven_c)
    child=subprocess.run([sys.executable,"-I","-B",str(Path(__file__).with_name("solver_worker.py"))],
        input=json.dumps(payload,allow_nan=False),text=True,capture_output=True,encoding="utf-8",timeout=12,check=False)
    if child.returncode:raise RuntimeError("ScientificSolverFailed:"+child.stderr[:80])
    result=json.loads(child.stdout)
    if not verify_trial(result,p.model_dump()):raise ArithmeticError("ScientificSolverIndependentCheckFailed")
    return result

def verify_trial(result,params):
    """Analytical check is independent of the SciPy process and of model claims."""
    try:
        p=HeatingDesignInput.model_validate(params);i=result["input"];oven=i["oven_c"]
        if not math.isfinite(oven) or not p.oven_min_c<=oven<=p.oven_max_c:return False
        if any(i[k]!=getattr(p,k) for k in ("initial_c","target_c","tau_s","deadline_s","oven_min_c","oven_max_c")):return False
        solver=result["solver"]
        if result["schema"]!="scipy-heating-1" or solver["name"]!="scipy.integrate.solve_ivp" or solver["success"] is not True:return False
        curve=result["curve"]
        if len(curve)!=61 or curve[0]["time_s"]!=0 or curve[-1]["time_s"]!=p.deadline_s:return False
        expected=lambda t:oven-(oven-p.initial_c)*math.exp(-t/p.tau_s)
        if any(not math.isfinite(point["temperature_c"]) or abs(point["time_s"]-j*p.deadline_s/60)>1e-7 or
               abs(point["temperature_c"]-expected(point["time_s"]))>1e-4 for j,point in enumerate(curve)):return False
        if not math.isfinite(result["final_c"]) or abs(result["final_c"]-expected(p.deadline_s))>1e-4:return False
        hit=-p.tau_s*math.log((oven-p.target_c)/(oven-p.initial_c)) if oven>p.target_c else None
        actual=result["reached_at_s"]
        if hit is not None and hit<=p.deadline_s:
            if actual is None or not math.isfinite(actual) or abs(actual-hit)>1e-3:return False
        elif actual is not None:return False
        inverse=result["inverse_design"]
        if inverse["tool"]!="scipy.optimize.brentq":return False
        alpha=math.exp(-p.deadline_s/p.tau_s)
        required=(p.target_c-p.initial_c*alpha)/(1-alpha)
        threshold=max(required,p.oven_min_c) if required<=p.oven_max_c else None
        actual_threshold=inverse["minimum_oven_c"]
        if threshold is None:
            if actual_threshold is not None or inverse["status"]!="not_reachable_in_bounds":return False
        elif actual_threshold is None or not math.isfinite(actual_threshold) or abs(actual_threshold-threshold)>1e-4:return False
        return True
    except (ValueError,KeyError,TypeError,OverflowError):return False

def feasible(result):return result["reached_at_s"] is not None and result["final_c"]>=result["input"]["target_c"]-1e-6

def best_trial(trials,objective="lowest_oven_meeting_deadline"):
    valid=[t for t in trials if feasible(t["result"])]
    if not valid:return None
    key=(lambda t:(t["result"]["reached_at_s"],t["id"])) if objective=="fastest_within_bounds" else (lambda t:(t["result"]["input"]["oven_c"],t["id"]))
    return min(valid,key=key)

def same_scientific_copy(left,right):
    """The JSON numeric copy may change by an ULP in MySQL; raw text is authoritative."""
    if isinstance(left,dict):
        return isinstance(right,dict) and left.keys()==right.keys() and all(same_scientific_copy(v,right[k]) for k,v in left.items())
    if isinstance(left,list):
        return isinstance(right,list) and len(left)==len(right) and all(same_scientific_copy(a,b) for a,b in zip(left,right))
    if isinstance(left,bool) or isinstance(right,bool):return type(left) is type(right) and left==right
    if isinstance(left,(float,int)) and isinstance(right,(float,int)):
        return math.isfinite(left) and math.isfinite(right) and abs(left-right)<=max(1e-10,abs(left)*1e-14)
    return type(left) is type(right) and left==right

def authoritative_design(loop):
    """Recover the exact tool result from lossless canonical JSON before proof or replay."""
    result=copy.deepcopy(loop)
    for trial in result.get("trials",[]):
        if "result_json" not in trial:
            # Legacy snapshots retain their original strict checks; no new proof is invented.
            continue
        raw=trial["result_json"]
        original=json.loads(raw)
        canonical=json.dumps(original,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
        if canonical!=raw or digest(original)!=trial["result_sha256"]:raise ValueError("ScientificRawSnapshotChanged")
        if not same_scientific_copy(original,trial["result"]):raise ValueError("ScientificStructuredCopyChanged")
        trial["result"]=original
    return result

def verify_design(loop,tool_calls=None):
    try:
        loop=authoritative_design(loop)
        params=HeatingDesignInput.model_validate(loop["constraints"]).model_dump()
        trials=loop["trials"]
        if not trials or len(trials)>MAX_TRIALS:return False
        for j,trial in enumerate(trials,1):
            if trial["id"]!=j or not verify_trial(trial["result"],params):return False
            if trial["result_sha256"]!=digest(trial["result"]):return False
            if tool_calls is not None:
                row=next((x for x in tool_calls if x["id"]==trial["tool_call_id"]),None)
                if not row or row["status"]!="succeeded" or row["payload"]["tool"]!="engineering.solve":return False
                if row["payload"]["output_sha256"]!=trial["result_sha256"]:return False
                if row["payload"].get("bound_action")!={"constraints":params,"oven_c":trial["result"]["input"]["oven_c"]}:return False
        for trial in trials:
            decision=next((d for d in loop["decisions"] if d["index"]==trial["decision_index"]),None)
            if not decision or decision["status"]!="accepted" or decision["action"]!="simulate":return False
            if not same_scientific_copy(decision["oven_c"],trial["result"]["input"]["oven_c"]) or decision["observed_trials"]!=list(range(1,trial["id"])):return False
            observations=[{"trial":t["id"],"oven_c":t["result"]["input"]["oven_c"],"final_c":t["result"]["final_c"],
                "reached_at_s":t["result"]["reached_at_s"],"meets_deadline":feasible(t["result"]),"inverse_design":t["result"]["inverse_design"]} for t in trials[:trial["id"]-1]]
            if decision["observation_sha256"]!=digest(observations):return False
        if len({t["result"]["input"]["oven_c"] for t in trials})!=len(trials):return False
        if params["baseline_c"] is not None and trials[0]["result"]["input"]["oven_c"]!=params["baseline_c"]:return False
        chosen=best_trial(trials,params["objective"])
        if loop.get("selected_trial")!=(chosen["id"] if chosen else None):return False
        return loop.get("status")=="finished"
    except (ValueError,KeyError,TypeError,StopIteration):return False

def rule_action(loop):
    p=loop["constraints"];trials=loop["trials"];best=best_trial(trials,p["objective"])
    if best:return {"action":"finish","oven_c":None,"selected_trial":best["id"],"reason":"规则降级：已找到经计算满足时限的候选；结束并保留方案对比，不声称全局最优。"}
    if not trials:
        oven=p["baseline_c"] if p["baseline_c"] is not None else (p["oven_min_c"]+p["oven_max_c"])/2
        return {"action":"simulate","oven_c":oven,"selected_trial":None,"reason":"规则降级：先执行基准炉温计算，取得实际温度与达温时间。"}
    tried={t["result"]["input"]["oven_c"] for t in trials}
    if p["oven_max_c"] not in tried:
        return {"action":"simulate","oven_c":p["oven_max_c"],"selected_trial":None,"reason":"规则降级：上一方案未满足时限，验证允许炉温上限的可达性。"}
    return {"action":"finish","oven_c":None,"selected_trial":None,"reason":"规则降级：已验证范围上限，结束并保留不可达的计算结果。"}

def model_action(platform,state,gateway,loop):
    from .orchestration.superagent import native_function
    from .models import task_settings
    from .orchestration.runtime import PolicyError
    observations=[{"trial":t["id"],"oven_c":t["result"]["input"]["oven_c"],"final_c":t["result"]["final_c"],
        "reached_at_s":t["result"]["reached_at_s"],"meets_deadline":feasible(t["result"]),"inverse_design":t["result"]["inverse_design"]} for t in loop["trials"]]
    meta={"provider":"rules","model":None}
    if platform.model_enabled(state):
        try:
            value,meta=gateway.invoke("model.decide",lambda:native_function(task_settings(platform.settings,state),
                "choose_heating_action","根据已执行工具观察决定下一步。只输出简短的行动说明，不输出内部推理。"
                "按constraints.objective优化：lowest_oven_meeting_deadline为降低炉温，fastest_within_bounds为缩短达温时间。simulate可选择范围内新的炉温；用户指定基准时首先计算基准。"
                "simulate时selected_trial必须为null；finish时oven_c必须为null，selected_trial选择已验证可行方案中最符合目标者；无可行方案可以结束但不得宣称全局最优。"
                "条件确实不足选clarify。必须根据观察调整行动，禁止编造计算结果或提前宣称未执行候选已达标。"
                "本模型在固定tau和时限下，末温与炉温呈线性关系。已有低炉温失败、高炉温成功时，"
                "可用这两次实际末温插值估算刚好达标的炉温，加少量正裕量后实算。"
                "优先使用工具inverse_design.minimum_oven_c的反算值，不要自行手算。可选略高于该值且在上限内的炉温作为安全裕量，再实际验证。",
                {"action":{"type":"string","enum":["simulate","finish","clarify"]},
                 "oven_c":{"type":["number","null"],"description":"仅simulate填写炉温；其他动作填null"},"selected_trial":{"type":["integer","null"],"description":"仅finish选择已执行的可行试算编号；simulate和clarify必须为null"},
                 "reason":{"type":"string","maxLength":600}},["action","oven_c","selected_trial","reason"],
                {"goal":loop["objective"]+"；至多3次实际试算；不证明全局最优",
                 "constraints":loop["constraints"],"model_definition":"dT/dt=(T_oven-T)/tau; T(t)=T_oven-(T_oven-T_initial)*exp(-t/tau)","observations":observations,"remaining_trials":MAX_TRIALS-len(loop["trials"]),
                 "allowed_actions":["simulate","finish","clarify"]}),
                input_details={"observation_sha256":digest(observations),"constraints":loop["constraints"]})
            return value,meta,digest(observations)
        except (PolicyError,PermissionError):raise
        except Exception as exc:meta={"provider":"rules_fallback","error":type(exc).__name__,"model":platform.settings.openai_model}
    return rule_action(loop),meta,digest(observations)

def design_summary(loop):
    p=loop.get("constraints") or {};chosen=best_trial(loop.get("trials",[]),p.get("objective"))
    if chosen:
        r=chosen["result"]
        label="最低炉温" if p["objective"]=="lowest_oven_meeting_deadline" else "最短达温时间"
        return (f"在给定的一阶热模型与输入假设下，已完成 {len(loop['trials'])} 次升温方案计算。已验证候选中，炉温 {r['input']['oven_c']:g} ℃ "
                f"可在 {r['reached_at_s']:.2f} 秒达到 {p['target_c']:g} ℃，满足 {p['deadline_s']:g} 秒时限。"
                f"这是已试方案中的{label}可行候选，未证明全局最优。")
    if loop.get("trials"):
        return f"在给定的一阶热模型与输入假设下，已完成 {len(loop['trials'])} 次升温方案计算，未找到满足给定时限的可行候选；不据此推断真实设备不可行。"
    return "升温方案尚未完成计算，请补充条件或处理执行缺口。"

def run_design(platform,state,gateway):
    params=state.get("design_params");gaps=state.get("design_gaps",[])
    loop=state.get("design_loop")
    if loop:
        loop=authoritative_design(loop)
        state["design_loop"]=loop
    if not loop:
        loop={"constraints":params,"objective":params["objective"] if params else None,"trials":[],"decisions":[],
              "status":"running","selected_trial":None,"stop_reason":None,
              "assumptions":"一阶集中参数热模型；恒定炉温与时间常数；未标定真实设备，不包含固化、压力及材料质量预测。"}
        state["design_loop"]=loop
    def save():
        state["design_loop"]=copy.deepcopy(loop)
        platform.repo.checkpoint(state)
    def stop(reason,review=None):
        loop.update(stop_reason=reason,status="needs_review" if review else "finished")
        chosen=best_trial(loop["trials"],(loop.get("constraints") or {}).get("objective"));loop["selected_trial"]=chosen["id"] if chosen else None
        if review:state["review_reason"]=review
        loop["summary"]=design_summary(loop)
        save()
    if gaps or not params:
        stop("missing_inputs","；".join(gaps) or "请提供初温、目标温度、时间常数、炉温范围与达温时限")
        return {"design_loop":loop,"review_reason":state["review_reason"]}
    p=HeatingDesignInput.model_validate(params)
    specs=[d for d in state.get("docs",[]) if d.get("doc_id")=="SOP-003" and d.get("status")=="active"]
    if len(specs)!=1:
        stop("missing_specification","升温方案设计需要唯一现行模拟SOP")
        return {"design_loop":loop,"review_reason":state["review_reason"]}
    limits=specs[0]["limits"]["temperature_c"]
    if p.oven_min_c<limits["min"] or p.oven_max_c>limits["max"]:
        stop("out_of_specification","设计范围超出现行模拟SOP温度边界")
        return {"design_loop":loop,"review_reason":state["review_reason"]}
    # Recover a completed node without reissuing model/solver calls.
    if loop["status"]=="finished":return {"design_loop":loop}
    while len(loop["trials"])<MAX_TRIALS:
        reserve=5 if platform.model_enabled(state) else 4
        if state.get("tool_budget",0)<reserve:
            stop("tool_budget_reserved","剩余预算不足以完成下一次试算及独立核验" if not loop["trials"] else None)
            break
        if loop.get("pending_action"):
            action=Action.model_validate(loop["pending_action"])
        else:
            try:
                raw,meta,observed=model_action(platform,state,gateway,loop)
                action=Action.model_validate(raw)
                # Some providers populate irrelevant optional fields. Ignore only a
                # selection attached to a SIMULATE action; it cannot publish a result.
                if action.action=="simulate" and action.selected_trial is not None:
                    meta={**meta,"action_normalizations":["ignored_selected_trial_for_simulate"],
                          "raw_selected_trial":action.selected_trial}
                    action=action.model_copy(update={"selected_trial":None})
            except Exception as exc:
                stop("decision_failed","决策调用未完成："+type(exc).__name__);break
            record={"index":len(loop["decisions"])+1,**action.model_dump(),"provider":meta.get("provider"),
                    "model_metadata":meta,"observation_sha256":observed,"observed_trials":[t["id"] for t in loop["trials"]],"status":"accepted"}
            loop["decisions"].append(record)
            loop["pending_action"]=action.model_dump()
            state["trace"].append(event("design_decision",action.reason,action=action.action,provider=record["provider"],observed_trials=record["observed_trials"]))
            save()
        rejection=None
        if action.action=="simulate":
            if action.oven_c is None or action.selected_trial is not None:rejection="试算动作缺少炉温或含无效选择"
            elif not p.oven_min_c<=action.oven_c<=p.oven_max_c:rejection="模型提出的炉温超出冻结范围"
            elif any(t["result"]["input"]["oven_c"]==action.oven_c for t in loop["trials"]):rejection="模型重复了已经执行的同一方案"
            elif not loop["trials"] and p.baseline_c is not None and action.oven_c!=p.baseline_c:rejection="首次试算须尊重用户指定的基准炉温"
        elif action.action=="finish":
            best=best_trial(loop["trials"],p.objective)
            if not loop["trials"]:rejection="没有实际工具结果，不能直接结束并生成方案"
            elif action.oven_c is not None or action.selected_trial!=(best["id"] if best else None):rejection="模型选择未验证的方案或遗漏已试方案中的较低可行炉温"
        if rejection:
            loop["decisions"][-1]["status"]="rejected";loop.pop("pending_action",None)
            stop("invalid_model_action",rejection);break
        if action.action=="clarify":
            loop.pop("pending_action",None);stop("clarification_requested",action.reason);break
        if action.action=="finish":
            loop.pop("pending_action",None);stop("agent_finished");break
        try:
            result=gateway.invoke("engineering.solve",lambda:scientific_solve(params,action.oven_c),
                                  input_details={"constraints":params,"oven_c":action.oven_c})
        except Exception as exc:
            stop("solver_failed","科学计算工具未完成："+type(exc).__name__);break
        trial={"id":len(loop["trials"])+1,"decision_index":loop["decisions"][-1]["index"],
               "tool_call_id":gateway.last_call_id,"result_sha256":digest(result),
               "result_json":json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False),
               "result":result}
        loop["trials"].append(trial);loop.pop("pending_action",None)
        state["trace"].append(event("engineering_trial",f"炉温 {action.oven_c:g} ℃：末温 {result['final_c']:.3f} ℃，"+("满足时限" if feasible(result) else "未满足时限"),trial=trial["id"],tool_call_id=trial["tool_call_id"]))
        save()
    if loop["status"]=="running":stop("trial_limit")
    loop["summary"]=design_summary(loop);save()
    patch={"design_loop":loop,"trace":state["trace"]}
    if loop["status"]=="needs_review":patch["review_reason"]=state["review_reason"]
    return patch

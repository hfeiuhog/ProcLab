import json


def markdown_report(state):
    r = state["report"]
    text = ["# " + r["title"], "", f"- 任务：{state['task_id']}", f"- 创建时间（UTC）：{state['created_at']}",
        f"- 状态：{state['status']}", f"- 校验：{state.get('validation', '')}", f"- 用户任务：{state['question']}", "",
        "## 分析结论", "", r["summary"], "", "## 参数偏差", "",
        "| 数据行 | 参数 | 实测值 | 模拟规范范围 | 单位 | 引用 |", "|---|---|---|---|---|---|"]
    for f in r["findings"]:
        text.append(f"| {f['row_id']} | {f['parameter']} | {f['actual']} | {f['allowed'][0]}–{f['allowed'][1]} | {f['unit']} | {f['citation']} |")
    if state.get('parent_task_id'):
        text += ['', '## 修复与补证来源', '', f"- 上一版本任务：{state['parent_task_id']}", f"- 修复版本：R{state.get('repair_version',0)}", f"- 审核补证：{state.get('evidence_bundle_id') or '无'}", '- 人工补证仅说明来源及审核，不等同于真实传感器数据认证。']
    if r["missing"]:
        text += ["", "## 缺失数据", "", json.dumps(r["missing"], ensure_ascii=False, indent=2)]
    if r.get("simulation"):
        s = r["simulation"]
        text += ["", "## 简化工程模型", "", s["formula"], "", s["assumptions"], "", s["recommendation"],
                 "", f"解析解/RK4最大误差：{s['max_error_c']:.10f} ℃"]
    if r.get("design"):
        d=r["design"]
        text += ["","## 升温方案试算与决策记录","",d.get("summary",""),
                 "",f"- 停止原因：{d['stop_reason']}",f"- 选中候选：{d['selected_trial']}",
                 f"- 优化目标：{{d['objective']}}；仅比较已试方案，不证明全局最优。",
                 "","### 冻结条件","",json.dumps(d["constraints"],ensure_ascii=False,indent=2),
                 "","| 试算 | 炉温 ℃ | 时限末温 ℃ | 达温时间 s | 工具调用 |",
                 "|---|---|---|---|---|"]
        for t in d["trials"]:
            v=t["result"]
            text.append(f"| {t['id']} | {v['input']['oven_c']} | {v['final_c']:.4f} | {v['reached_at_s']} | {t['tool_call_id']} |")
        text += ["","### 公开行动说明（非模型内部思维链）",""]
        for a in d["decisions"]:
            text.append(f"- 第{a['index']}次决策：{a['action']}；{a['reason']}；来源 {a['provider']}；已观察试算 {a['observed_trials']}。")
        text += ["",d["assumptions"]]
    if r.get("statistics"):
        text += ["", "## 描述统计", "", json.dumps(r["statistics"], ensure_ascii=False, indent=2)]
    text += ["", "## 证据来源", ""] + ["- " + x for x in r["sources"]]
    text += ["", "## 独立校验记录", "", json.dumps(r.get("validation"), ensure_ascii=False, indent=2)]
    text += ["", "## 后续建议", ""] + ["- " + x for x in r["recommendations"]]
    return "\n".join(text + ["", "## 适用边界", "", r["warning"], ""])

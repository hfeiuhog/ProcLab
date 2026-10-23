"""Single-process background runtime, durable checkpoints and resumable review."""
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .config import Settings
from .store import TaskStore, now
from .memory import Memory
from .rag import KnowledgeIndex
from .steps import (plan_step, search_step, query_step, analyze_step, statistics_step,
                    simulation_step, validate_step, report_step, event)
from .planner import infer_intent
from .control import ControlPlane, now as control_now
from .evidence import EvidenceService
from .harness import policy, classify_failure, boundary_reason, ALLOWED_TOOLS

TERMINAL = {"completed", "completed_reviewed", "rejected", "failed"}
STEPS = {"query_batch_data": query_step, "check_process_limits": analyze_step,
         "process_statistics": statistics_step, "simulate_heating": simulation_step, "validate_evidence": validate_step}


class TaskService:
    def __init__(self, runtime_dir, mode="auto", llm_enabled=False, settings=None):
        self.settings = settings or Settings(_env_file=None)
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.store = TaskStore(self.runtime_dir / "tasks.db", self.settings.database_url)
        self.control = ControlPlane(self.store.engine, self.settings)
        self.evidence = EvidenceService(self.control)
        from .knowledge_library import KnowledgeLibrary
        self.library=KnowledgeLibrary(self.control)
        self.memory = Memory(self.store, self.settings)
        self.knowledge = KnowledgeIndex(self.settings)
        self.llm_enabled = llm_enabled
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=self.settings.max_workers, thread_name_prefix="process-agent")
        self.slots = threading.BoundedSemaphore(16)
        self.active = set()
        self.mode = "fallback"
        if mode not in ("auto", "langgraph", "fallback"):
            raise ValueError("mode must be auto/langgraph/fallback")
        if mode != "fallback":
            try:
                from .checkpoint import SQLCheckpointSaver
                from .graph import build_graph
                self.checkpointer = SQLCheckpointSaver(self.store.engine)
                self.graph = build_graph(self.checkpointer, llm_enabled, self.settings, self.knowledge, self.evidence)
                self.mode = "langgraph"
            except ImportError:
                if mode == "langgraph":
                    raise RuntimeError("请执行 uv sync 安装锁定依赖")

        from .orchestration.supervisor import Platform
        self.platform = Platform(self)

    def close(self):
        self.executor.shutdown(wait=True)
        self.memory.close()
        self.knowledge.close()
        self.store.close()

    def _reserve(self, question, batch_id="", inject_timeout="none", conversation_id=None,
                 intent="auto", simulation_params=None, remember_result=False, owner_id="admin",
                 parent_task_id=None, repair_version=0, root_task_id=None, evidence_bundle_id=None,
                 evidence_document_ids=None, project_id=None, orchestration_mode="auto", analysis_mode="fast", design_params=None):
        if analysis_mode not in ("fast","thinking"):raise ValueError("无效分析模式")
        if inject_timeout not in ("none", "once", "always"):
            raise ValueError("Invalid fault injection")
        if inject_timeout != "none" and not self.settings.allow_fault_injection:
            raise ValueError("此环境已禁用故障注入")
        if conversation_id:
            self.control.require('conversation', conversation_id, owner_id)
        if conversation_id and not self.store.conversation(conversation_id):
            raise KeyError("会话不存在")
        document_versions = {}
        for ident in evidence_document_ids or []:
            doc = self.control.get('document',ident,owner_id)
            if doc['status']!='approved': raise ValueError('上传资料须先审核再参与工艺分析')
            document_versions[ident]=doc['approved_version']
        if orchestration_mode not in ("auto", "superagent", "legacy"):
            raise ValueError("无效执行模式")
        if orchestration_mode == "legacy" and owner_id != "admin":
            raise PermissionError("兼容模式仅供管理员维护")
        scope = self.platform.repo.scope(owner_id, project_id, write=True).model_dump()
        self.control.task_quota(owner_id)
        conversation_id = conversation_id or self.store.create_conversation()["id"]
        if self.control.owner('conversation', conversation_id) != owner_id and self.control.ids('conversation', owner_id) is None:
            raise ValueError('请在本人会话发起新任务；他人任务可通过审核处理')
        self.control.bind('conversation', conversation_id, owner_id)
        context = []
        for message in self.memory.context(conversation_id):
            previous = self.store.get(message.get("task_id"))
            if not previous: continue
            try:
                self.control.require("task", previous["task_id"], owner_id)
                self.platform.repo.scope(owner_id, previous.get("scope", {}).get("project_id"))
            except (KeyError, PermissionError):
                continue
            context.append(message)
        matches = re.findall(r"\bB-\d{3,8}\b", question.upper())
        if batch_id and matches and batch_id.upper() != matches[0]:
            raise ValueError("任务文字中的批次与所选批次不一致")
        batch_id = (batch_id or (matches[0] if matches else "")).upper()
        if not batch_id and re.search(r"刚才|上一[个次]|这个批次|该批次|继续", question) and not re.search(r"数据库|架构|技术栈|项目|工具调用|记忆", question):
            for m in reversed(context):
                previous = self.store.get(m.get("task_id"))
                if previous and previous.get("batch_id"):
                    batch_id = previous["batch_id"]
                    break
        resolved_intent = infer_intent(question, batch_id, intent)
        knowledge_versions=self.library.snapshot(owner_id)
        if resolved_intent=='chat' and intent=='auto':
            from .rag import retrieve
            if evidence_document_ids or retrieve(question,limit=1,catalog=self.library.documents(knowledge_versions,owner_id)):resolved_intent='knowledge' 
        if resolved_intent in ("knowledge", "chat", "extract", "reasoning", "analytics", "optimization"):
            batch_id = ""
        if resolved_intent == "batch" and not batch_id:
            raise ValueError("批次分析需要明确批次编号")
        design_gaps=[]
        if resolved_intent=="optimization":
            if not self.settings.superagent_enabled or orchestration_mode=="legacy":
                raise ValueError("升温方案设计需要启用专业执行运行时")
            from .design import request_from_text
            design_params,design_gaps=request_from_text(question,design_params)
        state = {"task_id": str(uuid.uuid4()), "conversation_id": conversation_id, "created_at": now(),
            "question": question, "batch_id": batch_id, "intent": resolved_intent,
            "analysis_mode":analysis_mode,"knowledge_versions":knowledge_versions,
            "simulation_params": simulation_params or {}, "design_params":design_params,"design_gaps":design_gaps,"remember_result": remember_result,
            "inject_timeout": inject_timeout, "trace": [], "status": "queued", "step_index": 0,
            "completed_steps": [], "tool_budget": self.settings.harness_max_tool_calls, "review_reason": None, "review": None,
            "validation": "", "context": context, "recalled_memories": self.memory.recall(question, self.control.ids('memory', owner_id)),
            "owner_id": owner_id, "parent_task_id": parent_task_id, "repair_version": repair_version,
            "root_task_id": root_task_id, "evidence_bundle_id": evidence_bundle_id,
            "evidence_document_ids": evidence_document_ids or [], "evidence_document_versions":document_versions, "harness": policy(self.settings),
            "scope":scope, "orchestration":("superagent" if self.settings.superagent_enabled and orchestration_mode != "legacy" and resolved_intent not in ("chat","extract") else "legacy"),
            "llm_enabled":self.llm_enabled}
        self.control.bind('task', state['task_id'], owner_id)
        self.store.save(state)
        self.control.audit(owner_id, owner_id, 'task_created', state['task_id'], {'intent': resolved_intent, 'parent_task_id': parent_task_id})
        self.store.add_message(conversation_id, "user", question, state["task_id"])
        self.memory.invalidate(conversation_id)
        return state

    def create(self, question, batch_id="", inject_timeout="none", **kwargs):
        with self.lock:
            state = self._reserve(question, batch_id, inject_timeout, **kwargs)
        return self._execute(state["task_id"])

    def submit(self, question, batch_id="", inject_timeout="none", **kwargs):
        if not self.slots.acquire(blocking=False):
            raise RuntimeError("任务队列已满，请稍后重试")
        try:
            with self.lock:
                state = self._reserve(question, batch_id, inject_timeout, **kwargs)
                self.active.add(state["task_id"])
            self.executor.submit(self._background, state["task_id"])
            return state
        except Exception:
            self.slots.release()
            raise

    def _background(self, task_id, resume=False):
        try:
            self._execute(task_id, resume=resume)
        finally:
            with self.lock:
                self.active.discard(task_id)
            self.slots.release()

    def recover(self):
        for state in self.store.list_tasks(statuses=["queued", "running"], limit=16):
            if self.slots.acquire(blocking=False):
                self.active.add(state["task_id"])
                self.executor.submit(self._background, state["task_id"], True)

    def _execute(self, task_id, resume=False):
        state = self.store.get(task_id)
        try:
            state["status"] = "running"
            state.setdefault("run_started_at", control_now())
            self.store.save(state)
            if state.get("orchestration") == "superagent":
                state = self.platform.execute(state)
            elif self.mode == "langgraph":
                config = {"configurable": {"thread_id": task_id}, "recursion_limit": 50}
                existing = self.graph.get_state(config)
                graph_input = None if resume and existing.values else state
                for values in self.graph.stream(graph_input, config, stream_mode="values"):
                    state = {k: v for k, v in values.items() if not k.startswith('__')}
                    self.store.save(state)
                snapshot = self.graph.get_state(config)
                state = dict(snapshot.values)
                if snapshot.interrupts:
                    state["status"] = "pending_review"
            else:
                state.update(plan_step(state, self.llm_enabled, self.settings))
                self.store.save(state)
                for name in state["plan"]:
                    if state.get("review_reason"):
                        break
                    reason = boundary_reason(state,self.settings)
                    if reason or name not in ALLOWED_TOOLS:
                        state['review_reason']=reason or '工具不在允许范围'
                        state['trace'].append(event('harness_guard',state['review_reason']))
                        break
                    state['tool_budget']-=1
                    fn = (lambda s: search_step(s, self.knowledge, self.evidence)) if name == "search_process_docs" else (lambda s: query_step(s, self.evidence)) if name == 'query_batch_data' else (lambda s: validate_step(s, self.evidence)) if name == 'validate_evidence' else STEPS[name]
                    state.update(fn(state))
                    state["completed_steps"].append(name)
                    self.store.save(state)
                if state.get("review_reason"):
                    state["status"], state["validation"] = "pending_review", "needs_review"
                else:
                    state.update(report_step(state, self.settings))
            self.store.save(state)
            self._finish(state)
        except Exception as exc:
            state = self.store.get(task_id) or state
            state.update(status="failed", error=type(exc).__name__, failure=classify_failure(exc))
            state["trace"] = state.get("trace", []) + [event("runtime_error", "执行失败；错误类型：" + type(exc).__name__)]
            self.store.save(state)
            self._finish(state)
        return state

    def _finish(self, state):
        if state["status"] in TERMINAL or state["status"] == "pending_review":
            self.control.audit(state.get('owner_id','admin'), state.get('owner_id','admin'), 'task_'+state['status'], state['task_id'], {'validation':state.get('validation'), 'repair_version':state.get('repair_version',0)})
            content = state.get("report", {}).get("summary") or state.get("review_reason") or "任务执行失败，请检查服务配置。"
            self.store.add_message(state["conversation_id"], "assistant", content, state["task_id"])
            self.memory.invalidate(state["conversation_id"])
            if state.get("remember_result") and state["status"] == "completed" and state.get("validation") == "passed" and (state.get("validation_details", {}).get("independent_numeric_check") is True or state.get("validation_details", {}).get("simulation_verified") is True):
                self.save_result_memory(state["task_id"])

    def get(self, task_id):
        return self.store.get(task_id)

    def save_result_memory(self, task_id):
        state = self.get(task_id)
        if not state:
            raise KeyError("任务不存在")
        if state["status"] != "completed" or state.get("validation") != "passed":
            raise ValueError("只允许保存通过独立校验的完整结果")
        details = state.get("validation_details", {})
        if not (details.get("independent_numeric_check") is True or details.get("simulation_verified") is True):
            raise ValueError("只有通过独立数值校验的批次或仿真结果可保存为已验证结论；其他内容请保存为手动备注")
        report = state["report"]
        content = report["summary"] + " 来源：" + "；".join(report["sources"]) + "。仅作为历史背景，不能替代当前证据。"
        item = self.store.remember(content, task_id, "verified_result")
        self.control.bind('memory', item['id'], state.get('owner_id', 'admin'))
        return item

    def review(self, task_id, approved, note="", actor="admin"):
        with self.lock:
            self.control.require('task', task_id, actor)
            state = self.get(task_id)
            if not state:
                raise KeyError("任务不存在")
            self.platform.repo.scope(actor, state.get("scope", {}).get("project_id"), review=True)
            if state["status"] != "pending_review":
                raise ValueError("Task is not waiting for review")
            rev = {"approved": approved, "note": note[:500], "actor": actor}
            if state.get("orchestration") == "superagent":
                state = self.platform.review(state, approved, note, actor)
            elif self.mode == "langgraph":
                from langgraph.types import Command
                config = {"configurable": {"thread_id": task_id}, "recursion_limit": 50}
                self.graph.invoke(Command(resume=rev), config)
                state = dict(self.graph.get_state(config).values)
            else:
                state["review"] = rev
                state["trace"] += [event("human_review", "批准限制性说明" if approved else "驳回报告")]
                state.update(report_step(state, self.settings))
            self.store.save(state)
            self._finish(state)
            self.control.audit(state.get('owner_id','admin'),actor,'review_task',task_id,{'approved':approved,'note':note[:500]})
            return state

    def retry(self, task_id, actor="admin", evidence_bundle_id=None, batch_id=None, evidence_document_ids=None, design_params=None):
        with self.lock:
            self.control.require('task', task_id, actor)
            parent = self.get(task_id)
            if not parent: raise KeyError('任务不存在')
            self.platform.repo.scope(actor, parent.get("scope", {}).get("project_id"), write=True)
            if parent['status'] in ('queued','running'): raise ValueError('任务仍在执行')
            root = parent.get('root_task_id') or parent['task_id']
            version = parent.get('repair_version',0)+1
            if version>self.settings.harness_max_repairs: raise ValueError('已达到修复版本上限')
            bundle = evidence_bundle_id or parent.get('evidence_bundle_id')
            owner = parent.get('owner_id','admin')
            if batch_id and batch_id != parent.get('batch_id'):
                bundle = None
            if bundle:
                candidate = self.control.get('supplement',bundle,owner)
                if candidate['status']!='approved' or (candidate['parent_task_id']!=parent['task_id'] and parent.get('evidence_bundle_id')!=bundle):
                    raise ValueError('补证尚未审核或不属于此任务')
            docs=evidence_document_ids if evidence_document_ids is not None else parent.get('evidence_document_ids',[])
            for ident in docs:
                if self.control.get('document',ident,owner)['status']!='approved': raise ValueError('文档尚未审核')
            self.control.consume('repair:'+root,self.settings.harness_max_repairs)
            question = parent['question']
            if design_params is not None:
                if parent.get("intent")!="optimization":raise ValueError("仅升温设计任务可补充设计条件")
                from .design import canonical_question
                question=canonical_question(design_params)
            if batch_id and parent.get('batch_id'):
                question = question.replace(parent['batch_id'],batch_id)
            child = self.submit(question, batch_id or parent.get('batch_id',''),
                conversation_id=parent['conversation_id'], intent=parent.get('intent','auto'),
                simulation_params=parent.get('simulation_params'), design_params=design_params or parent.get('design_params'), owner_id=owner, parent_task_id=parent['task_id'],
                repair_version=version,root_task_id=root,evidence_bundle_id=bundle,evidence_document_ids=docs,
                project_id=parent.get("scope",{}).get("project_id"),orchestration_mode=parent.get("orchestration","auto"),analysis_mode=parent.get("analysis_mode","fast"))
            self.control.audit(owner,actor,'repair_task',child['task_id'],{'parent_task_id':task_id,'version':version,'supplement_id':bundle})
            return child

    def replan(self, task_id, actor, note):
        with self.lock:
            self.control.require("task",task_id,actor)
            state=self.get(task_id)
            if not state or state.get("orchestration")!="superagent":raise ValueError("该任务不支持计划修订")
            if not self.slots.acquire(blocking=False):raise RuntimeError("任务队列已满")
            try:
                state=self.platform.prepare_replan(state,actor,note)
                self.active.add(task_id)
                self.executor.submit(self._background,task_id,True)
                return state
            except Exception:
                self.slots.release();raise

    def health(self):
        try:
            db = {"backend": self.store.ping(), "status": "ready"}
        except Exception as exc:
            db = {"status": "unavailable", "error": type(exc).__name__}
        components = {"database": db, "short_memory": self.memory.health(), "knowledge": self.knowledge.health()}
        ready = all(c["status"] in ("ready", "local") for c in components.values())
        return {"ok": ready, "execution_engine": self.mode, "model_planner_enabled": self.llm_enabled,
            "model_configured": bool(self.settings.openai_api_key and self.settings.openai_model),
            "model": self.settings.openai_model or None, "model_provider": self.settings.model_provider,
            "data_policy": "synthetic_measurements_and_attributed_public_summaries", "version": "3.0.0",
            "dataset": __import__("app.models", fromlist=["project_facts"]).project_facts()["data"],
            "components": {**components,"analytics":self.platform.health()}, "runtime": "single_process_executor",
            "orchestration_engine":"durable_dependency_dag" if self.settings.superagent_enabled else "legacy",
            "multi_agent":self.settings.superagent_enabled, "active_tasks": len(self.active)}

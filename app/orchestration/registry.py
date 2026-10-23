"""Published capability definitions and immutable version fingerprints."""
from pathlib import Path
import hashlib
from .contracts import digest

_APP=Path(__file__).resolve().parents[1]
BUILD_FINGERPRINT=hashlib.sha256(b"".join(p.read_bytes() for p in sorted(_APP.rglob("*.py"),key=lambda p:p.relative_to(_APP).as_posix()))).hexdigest()

REGISTRY = {
    "requirement.extract": ("requirement_planner", "需求规划", ("model.plan",), "hybrid"),
    "evidence.retrieve": ("retrieval_agent", "工艺检索", ("search_process_docs",), "tool_agent"),
    "process.data": ("process_data_agent", "批次数据", ("query_batch_data",), "tool_agent"),
    "process.assess": ("process_compliance_agent", "工艺分析", ("check_process_limits",), "tool_agent"),
    "process.statistics": ("statistics_agent", "描述统计", ("process_statistics",), "tool_agent"),
    "process.simulate": ("simulation_agent", "升温仿真", ("simulate_heating", "model.decide", "engineering.solve"), "hybrid"),
    "analytics.query": ("analytics_agent", "数据问数", ("analytics.query", "model.query"), "hybrid"),
    "evidence.analyze": ("evidence_agent", "证据语义分析", ("model.evidence",), "hybrid"),
    "evidence.conflict": ("conflict_agent", "证据冲突分析", (), "deterministic"),
    "evidence.verify": ("evidence_verifier", "来源与快照核验", ("verify_sources",), "deterministic"),
    "harness.evaluate": ("business_harness", "独立规则复算", ("validate_evidence",), "deterministic"),
}


def catalog():
    return [dict(capability=cap, agent_key=v[0], display_name=v[1], tools=list(v[2]),
                 runtime_type=v[3], version="1.0.0", published=True,
                 fingerprint=digest([cap, *v, BUILD_FINGERPRINT]), implementation_sha256=BUILD_FINGERPRINT) for cap, v in REGISTRY.items()]


def definition(capability):
    return next(a for a in catalog() if a["capability"] == capability)


ALLOWED_DEPENDENCIES = {
    "requirement.extract": set(),
    "evidence.retrieve": {"requirement.extract"},
    "process.data": {"requirement.extract"},
    "process.assess": {"evidence.retrieve", "process.data"},
    "process.statistics": {"evidence.retrieve", "process.data"},
    "process.simulate": {"evidence.retrieve"},
    "analytics.query": {"requirement.extract"},
    "evidence.analyze": set(REGISTRY) - {"evidence.analyze", "evidence.conflict", "evidence.verify", "harness.evaluate"},
    "evidence.conflict": {"evidence.analyze"},
    "evidence.verify": {"evidence.analyze", "evidence.conflict"},
    "harness.evaluate": {"evidence.verify"},
}

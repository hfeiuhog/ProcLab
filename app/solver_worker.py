"""Isolated, fixed scientific-tool entry point. JSON stdin/stdout; no user code."""
import json
import os
import sys

def solve(payload):
    import numpy as np
    import scipy
    from scipy.integrate import solve_ivp
    from scipy.optimize import brentq
    from pydantic import BaseModel, ConfigDict, Field
    class Request(BaseModel):
        model_config=ConfigDict(extra="forbid",allow_inf_nan=False)
        initial_c:float=Field(ge=-20,le=100)
        target_c:float=Field(ge=180,le=219)
        tau_s:float=Field(ge=10,le=3600)
        deadline_s:float=Field(ge=1,le=14400)
        oven_c:float=Field(ge=180,le=220)
        oven_min_c:float=Field(ge=180,le=220)
        oven_max_c:float=Field(ge=180,le=220)
    p=Request.model_validate(payload)
    def rhs(t,y):return [(p.oven_c-y[0])/p.tau_s]
    def reached(t,y):return y[0]-p.target_c
    reached.direction=1
    reached.terminal=False
    t=np.linspace(0,p.deadline_s,61)
    solution=solve_ivp(rhs,(0,p.deadline_s),[p.initial_c],method="RK45",
                       t_eval=t,events=reached,rtol=1e-9,atol=1e-10)
    if not solution.success:raise ArithmeticError("Scientific solver did not converge")
    def final_at(oven):
        value=solve_ivp(lambda t,y:[(oven-y[0])/p.tau_s],(0,p.deadline_s),[p.initial_c],
                        t_eval=[p.deadline_s],rtol=1e-9,atol=1e-10)
        if not value.success:raise ArithmeticError("Inverse solver integration failed")
        return float(value.y[0,-1])-p.target_c
    low,high=final_at(p.oven_min_c),final_at(p.oven_max_c)
    if low>=0:threshold=p.oven_min_c;inverse_status="lower_bound_feasible"
    elif high<0:threshold=None;inverse_status="not_reachable_in_bounds"
    else:
        threshold=float(brentq(final_at,p.oven_min_c,p.oven_max_c,xtol=1e-7,maxiter=32))
        inverse_status="root_found"
    inverse={"tool":"scipy.optimize.brentq","status":inverse_status,"minimum_oven_c":threshold,
             "scope":"fixed_model_and_deadline_only; candidate_requires_forward_verification"}
    return {"schema":"scipy-heating-1","input":p.model_dump(),"inverse_design":inverse,
        "solver":{"name":"scipy.integrate.solve_ivp","version":scipy.__version__,
                  "method":"RK45","nfev":solution.nfev,"success":bool(solution.success),"pid":os.getpid()},
        "final_c":float(solution.y[0,-1]),
        "reached_at_s":float(solution.t_events[0][0]) if len(solution.t_events[0]) else None,
        "curve":[{"time_s":float(x),"temperature_c":float(y)} for x,y in zip(solution.t,solution.y[0])]}
if __name__=="__main__":
    try:
        result=solve(json.loads(sys.stdin.buffer.read(8192).decode("utf-8")))
        sys.stdout.write(json.dumps(result,ensure_ascii=True,allow_nan=False))
    except Exception as exc:
        sys.stderr.write(type(exc).__name__)
        sys.exit(2)

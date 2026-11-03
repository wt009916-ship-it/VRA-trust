"""Reviewable model-authored work, with server-checked tool and source bindings."""
from typing import Any

from pydantic import Field, model_validator

from .schema import Contract


class WorkStep(Contract):
    step_id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,31}$')
    purpose: str = Field(min_length=5, max_length=300)
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict, max_length=12)
    depends_on: list[str] = Field(default_factory=list, max_length=8)


class WorkPlan(Contract):
    goal: str = Field(min_length=5, max_length=1000)
    steps: list[WorkStep] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def dependencies(self):
        seen = set()
        for step in self.steps:
            if step.step_id in seen or set(step.depends_on) - seen:
                raise ValueError('步骤ID须唯一，依赖只能引用前序步骤；不执行循环或前向依赖')
            seen.add(step.step_id)
        return self


class Direction(Contract):
    research_id: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=5, max_length=800)
    tradeoff: str = Field(min_length=5, max_length=800)


class Shortlist(Contract):
    goal: str = Field(min_length=5, max_length=1000)
    requirements: list[str] = Field(min_length=1, max_length=8)
    directions: list[Direction] = Field(min_length=1, max_length=6)

    @model_validator(mode='after')
    def distinct(self):
        if len({d.research_id for d in self.directions}) != len(self.directions):
            raise ValueError('候选来源不得重复')
        return self


class InputQuestion(Contract):
    question: str = Field(min_length=5, max_length=500)
    why_needed: str = Field(min_length=5, max_length=500)


META_TOOLS = {'engineering_work_plan', 'material_shortlist_propose', 'request_project_input'}

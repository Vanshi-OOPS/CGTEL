"""Config endpoint exposing weights, thresholds, and tool specifications."""
from typing import List
from fastapi import APIRouter

from cgtel.agent.llm_agent import _DECLARATIONS
from cgtel.config import DEFAULT_TOOL_POLICIES, DEFAULT_WEIGHTS, TAU_1, TAU_2
from server.chat_tools import CHAT_TOOLS
from server.models import ConfigResponse, ToolParam, ToolPolicyConfig, ToolSpec, WeightsConfig

router = APIRouter(tags=["config"])


def _build_tools_config() -> List[ToolSpec]:
    tools: List[ToolSpec] = []
    for decl in _DECLARATIONS:
        params_spec = decl.get("parameters", {})
        props = params_spec.get("properties", {})
        req_list = params_spec.get("required", [])
        params = [
            ToolParam(
                name=p_name,
                type=p_props.get("type", "STRING"),
                required=p_name in req_list,
            )
            for p_name, p_props in props.items()
        ]
        tools.append(
            ToolSpec(
                name=decl.get("name", ""),
                description=decl.get("description", ""),
                params=params,
            )
        )
    for tool in CHAT_TOOLS:
        properties = tool["parameters"].get("properties", {})
        required = tool["parameters"].get("required", [])
        tools.append(ToolSpec(
            name=tool["name"],
            description=tool["description"],
            params=[
                ToolParam(
                    name=name,
                    type=details.get("type", "string").upper(),
                    required=name in required,
                )
                for name, details in properties.items()
            ],
        ))
    return tools


@router.get("/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    return ConfigResponse(
        weights=WeightsConfig(
            w1=float(DEFAULT_WEIGHTS["w1"]),
            w2=float(DEFAULT_WEIGHTS["w2"]),
            w3=float(DEFAULT_WEIGHTS["w3"]),
        ),
        tau1=float(TAU_1),
        tau2=float(TAU_2),
        tools=_build_tools_config(),
        tool_policies={
            name: ToolPolicyConfig(**policy)
            for name, policy in DEFAULT_TOOL_POLICIES.items()
        },
    )

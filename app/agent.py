# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import logging
import os
import re
import json
from zoneinfo import ZoneInfo
from typing import Any, AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.adk.tools import AgentTool, ToolContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.workflow import Workflow, START
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.genai import types

from app.config import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cafeteria-assistant")

# Define MCP Toolset for local cafeteria server
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "python", "-m", "app.mcp_server"]
        )
    )
)


def request_order(items: str, tool_context: ToolContext) -> dict:
    """Request to place an order for the specified cafeteria items.
    
    Args:
        items: The cafeteria items to order (e.g. 'Salad and Coffee').
        
    Returns:
        A dict with the status of the order request.
    """
    tool_context.state["pending_order"] = items
    tool_context.state["order_status"] = "Pending Approval"
    return {"status": "success", "message": f"Order for '{items}' is pending approval."}


def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Security node to sanitize input and detect prompt injections.
    
    Args:
        node_input: The input message from the user.
    """
    # Extract text from input Content
    text = ""
    if node_input and node_input.parts:
        text = "".join(part.text for part in node_input.parts if part.text)
    
    logger.info(f"Security check on input: {text}")
    
    # 1. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions", 
        "system prompt", 
        "override instructions", 
        "reveal secrets", 
        "act as", 
        "forget rules"
    ]
    detected_injection = False
    for kw in injection_keywords:
        if kw in text.lower():
            detected_injection = True
            break
            
    if detected_injection:
        audit_log = {
            "timestamp": str(datetime.datetime.now()),
            "severity": "CRITICAL",
            "event": "PROMPT_INJECTION_DETECTED",
            "input": text
        }
        logger.error(f"AUDIT LOG: {json.dumps(audit_log)}")
        return Event(
            output="Prompt injection detected! Request blocked.", 
            route="SECURITY_EVENT"
        )
        
    # 2. PII Scrubbing
    # Credit cards
    cc_pattern = r"\b(?:\d[ -]*?){13,16}\b"
    # Phone numbers
    phone_pattern = r"\b(?:\+?\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b"
    
    sanitized_text = re.sub(cc_pattern, "[REDACTED_CREDIT_CARD]", text)
    sanitized_text = re.sub(phone_pattern, "[REDACTED_PHONE_NUMBER]", sanitized_text)
    
    # 3. Domain specific rule: check order quantity
    quantity_pattern = r"\b(2[1-9]|[3-9]\d|\d{3,})\s*(items|orders|cups|plates|bowls)\b"
    if re.search(quantity_pattern, sanitized_text, re.IGNORECASE):
        audit_log = {
            "timestamp": str(datetime.datetime.now()),
            "severity": "WARNING",
            "event": "EXCESSIVE_QUANTITY_REJECTED",
            "input": text
        }
        logger.warning(f"AUDIT LOG: {json.dumps(audit_log)}")
        return Event(
            output="Cafeteria orders are limited to a maximum of 20 items per request.",
            route="SECURITY_EVENT"
        )
    
    # Audit log success
    audit_log = {
        "timestamp": str(datetime.datetime.now()),
        "severity": "INFO",
        "event": "INPUT_SANITIZED",
        "original_length": len(text),
        "sanitized_length": len(sanitized_text)
    }
    logger.info(f"AUDIT LOG: {json.dumps(audit_log)}")
    
    # Write sanitized input to state for agents to read
    ctx.state["sanitized_input"] = sanitized_text
    
    return Event(output=sanitized_text, route="PASS")


def security_violation(node_input: str):
    """Handle security violation route."""
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=node_input)]))
    yield Event(output=node_input)


# Sub-agents
menu_recommendation = LlmAgent(
    name="menu_recommendation",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Menu & Recommendation Agent.
    Your job is to search the menu and provide personalized dish recommendations based on dietary preferences (e.g. vegetarian, vegan, low-carb, keto) or allergies.
    Always prioritize safety. Suggest healthy options where possible.
    """,
    tools=[mcp_toolset]
)

order_analytics = LlmAgent(
    name="order_analytics",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Order & Analytics Agent.
    Your job is to manage cafeteria orders, order tracking, inventory checks, and sales analytics.
    If the user requests to place an order, you must call the `request_order` tool.
    """,
    tools=[request_order, mcp_toolset]
)

orchestrator = LlmAgent(
    name="orchestrator",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Cafeteria Orchestrator. 
    Your role is to determine the user's intent and coordinate sub-agents to help them.
    You have access to two sub-agents as tools:
    1. menu_recommendation: Handles menu searches and recommendation queries.
    2. order_analytics: Handles order requests, tracking, inventory, and sales analytics.
    
    Always delegate to the sub-agent if the request is related to their specialty.
    If the request is general, you can answer it yourself.
    
    Ensure you use the tools to delegate when needed.
    """,
    tools=[AgentTool(menu_recommendation), AgentTool(order_analytics)]
)


def post_orchestrator_route(ctx: Context, node_input: Any) -> Event:
    """Route downstream from orchestrator based on order state changes."""
    if ctx.state.get("pending_order") and ctx.state.get("order_status") == "Pending Approval":
        return Event(output=node_input, route="needs_approval")
    return Event(output=node_input, route="end")


async def order_approval(ctx: Context, node_input: Any) -> AsyncGenerator[Event, None]:
    """Human-in-the-loop approval node."""
    # Check if we already have approval response
    if ctx.resume_inputs and "approve_order" in ctx.resume_inputs:
        decision = ctx.resume_inputs["approve_order"].lower().strip()
        if decision in ["yes", "y", "approve"]:
            ctx.state["order_status"] = "Approved"
            msg = f"Order for '{ctx.state['pending_order']}' has been approved and placed successfully!"
            ctx.state["pending_order"] = None
            yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]))
            yield Event(output=msg)
            return
        else:
            ctx.state["order_status"] = "Cancelled"
            msg = f"Order for '{ctx.state['pending_order']}' was cancelled."
            ctx.state["pending_order"] = None
            yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]))
            yield Event(output=msg)
            return

    # Yield RequestInput for HITL pause
    order_details = ctx.state.get("pending_order", "unknown items")
    yield RequestInput(
        interrupt_id="approve_order",
        message=f"Please confirm your order for: {order_details}. Type 'yes' to approve or 'no' to cancel."
    )


def final_output(node_input: Any):
    """Formats final response output for the user."""
    text = ""
    if isinstance(node_input, types.Content):
        text = "".join(part.text for part in node_input.parts if part.text)
    elif isinstance(node_input, str):
        text = node_input
    else:
        text = str(node_input)
        
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=text)]))
    yield Event(output=text)


# Workflow definition
edges = [
    (START, security_checkpoint),
    (security_checkpoint, {"SECURITY_EVENT": security_violation, "PASS": orchestrator}),
    (orchestrator, post_orchestrator_route),
    (post_orchestrator_route, {"needs_approval": order_approval, "end": final_output}),
    (order_approval, final_output),
    (security_violation, final_output)
]

root_agent = Workflow(
    name="cafeteria_workflow",
    edges=edges,
    description="Cafeteria Assistant workflow."
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True)
)

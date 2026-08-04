from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.models.schemas import AgentTraceRecord
from app.models.enums import StageName

logger = logging.getLogger("gyantra.agents")


class AgentRole(str, Enum):
    PARSER = "parser"
    CLASSIFIER = "classifier"
    EXTRACTOR = "extractor"
    PLANNER = "planner"
    CONTENT_WRITER = "content_writer"
    ACTIVITY_DESIGNER = "activity_designer"
    ASSESSOR = "assessor"
    DIAGNOSTICIAN = "diagnostician"
    VALIDATOR = "validator"
    PUBLISHER = "publisher"


class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    FEEDBACK = "feedback"


@dataclass
class AgentMessage:
    sender: AgentRole | str
    receiver: AgentRole | str
    content: str
    message_type: MessageType
    timestamp: float = field(default_factory=time.time)


class BaseAgent:
    def __init__(self, role: AgentRole):
        self.role = role

    async def execute(self, context: dict, client: Any) -> Any:
        raise NotImplementedError


class AgentCoordinator:
    def __init__(self):
        self.traces: list[AgentTraceRecord] = []
        self.messages: list[AgentMessage] = []

    def record_message(self, sender: AgentRole | str, receiver: AgentRole | str, content: str, message_type: MessageType):
        msg = AgentMessage(sender, receiver, content, message_type)
        self.messages.append(msg)
        
    def record_trace(
        self,
        agent_role: str,
        stage: StageName,
        input_summary: str,
        output_summary: str,
        duration_ms: int,
        tokens_used: int,
        model_used: str,
    ):
        trace = AgentTraceRecord(
            agent_role=agent_role,
            stage=stage,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            tokens_used=tokens_used,
            model_used=model_used,
            messages=[
                {"sender": m.sender, "receiver": m.receiver, "content": m.content, "type": m.message_type, "timestamp": m.timestamp}
                for m in self.messages
                if m.sender == agent_role or m.receiver == agent_role
            ]
        )
        self.traces.append(trace)

    async def run_stage_with_agent(
        self,
        role: AgentRole,
        stage: StageName,
        action: callable,
        input_summary: str,
        model_name: str = "unknown"
    ) -> Any:
        start_time = time.time()
        self.record_message("coordinator", role, f"Begin stage: {stage.value}", MessageType.REQUEST)
        
        output_summary = "Aborted or crashed"
        try:
            result = await action()
            output_summary = "Completed successfully"
            self.record_message(role, "coordinator", output_summary, MessageType.RESPONSE)
            return result
        except BaseException as e:
            output_summary = f"Failed: {str(e) or type(e).__name__}"
            self.record_message(role, "coordinator", output_summary, MessageType.RESPONSE)
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            self.record_trace(
                agent_role=role.value,
                stage=stage,
                input_summary=input_summary,
                output_summary=output_summary,
                duration_ms=duration_ms,
                tokens_used=0,  # This will be updated by telemetry if needed
                model_used=model_name
            )

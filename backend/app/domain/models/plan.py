from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
import uuid

class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class Step(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    success: bool = False
    attachments: List[str] = []
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def is_done(self) -> bool:
        return self.status == ExecutionStatus.COMPLETED or self.status == ExecutionStatus.FAILED

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at is None or self.finished_at is None:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)

class Plan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    goal: str = ""
    language: Optional[str] = "en"
    steps: List[Step] = []
    message: Optional[str] = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def is_done(self) -> bool:
        return self.status == ExecutionStatus.COMPLETED or self.status == ExecutionStatus.FAILED
    
    def get_next_step(self) -> Optional[Step]:
        for step in self.steps:
            if not step.is_done():
                return step
        return None
    
    def dump_json(self) -> str:
        # Timestamps are UI/event concerns; excluding them keeps the planner
        # prompt free of noise that could otherwise shift LLM behaviour.
        return self.model_dump_json(
            include={"goal", "language", "steps"},
            exclude={"steps": {"__all__": {"started_at", "finished_at"}}},
        )

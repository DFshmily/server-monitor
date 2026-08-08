"""Pydantic models for metrics data."""
from pydantic import BaseModel, Field
from typing import Any


class AgentPayload(BaseModel):
    """Payload sent by the monitoring agent."""
    server_name: str
    metrics: dict[str, Any]


class MetricsRecord(BaseModel):
    """Stored metrics record returned by API."""
    id: int
    server_name: str
    timestamp: int
    data: dict

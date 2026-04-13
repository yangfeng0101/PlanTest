# Parallel Task Database Model (SQLAlchemy)
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, DateTime, Integer, JSON, Enum as SQLEnum, Index
from sqlalchemy.orm import DeclarativeBase
from enum import Enum
import uuid

from app.models.database import Base


class DeviceSelectionStrategy(str, Enum):
    """Strategy for selecting devices"""
    ALL = "all"
    RANDOM = "random"
    SPECIFIC = "specific"


class ParallelTaskStatus(str, Enum):
    """Status of parallel execution task"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ParallelTaskDB(Base):
    """Parallel task database model"""
    __tablename__ = "parallel_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    script_id = Column(String(36), nullable=False, index=True)
    status = Column(
        SQLEnum(ParallelTaskStatus),
        default=ParallelTaskStatus.PENDING,
        nullable=False,
        index=True
    )
    selection_strategy = Column(
        SQLEnum(DeviceSelectionStrategy),
        default=DeviceSelectionStrategy.ALL,
        nullable=False
    )
    max_concurrency = Column(Integer, default=5, nullable=False)
    parameters = Column(JSON, default=dict)
    device_capabilities = Column(JSON, default=dict)
    sub_tasks = Column(JSON, default=list)  # List of sub-task info dicts
    total_devices = Column(Integer, default=0, nullable=False)
    completed_devices = Column(Integer, default=0, nullable=False)
    failed_devices = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_parallel_tasks_script_status', 'script_id', 'status'),
    )

    def __repr__(self):
        return f"<ParallelTask(id={self.id}, status={self.status})>"

# Aggregated Result Database Model (SQLAlchemy)
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, DateTime, Integer, Float, JSON, Enum as SQLEnum, Index
from enum import Enum
import uuid

from app.models.database import Base


class AggregationStatus(str, Enum):
    """Status of result aggregation"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AggregatedResultDB(Base):
    """Aggregated result database model for parallel execution"""
    __tablename__ = "aggregated_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parallel_task_id = Column(String(36), nullable=False, index=True)
    script_id = Column(String(36), nullable=False, index=True)
    status = Column(
        SQLEnum(AggregationStatus),
        default=AggregationStatus.PENDING,
        nullable=False,
        index=True
    )
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    # Summary metrics
    total_devices = Column(Integer, default=0, nullable=False)
    completed_devices = Column(Integer, default=0, nullable=False)
    failed_devices = Column(Integer, default=0, nullable=False)
    success_rate = Column(Float, default=0.0, nullable=False)
    total_duration = Column(Float, default=0.0, nullable=False)

    # Test metrics (aggregated across all devices)
    total_tests = Column(Integer, default=0, nullable=False)
    passed_tests = Column(Integer, default=0, nullable=False)
    failed_tests = Column(Integer, default=0, nullable=False)
    skipped_tests = Column(Integer, default=0, nullable=False)
    test_success_rate = Column(Float, default=0.0, nullable=False)

    # Device-level results stored as JSON
    device_results = Column(JSON, default=list)
    failed_device_ids = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index('ix_aggregated_results_task_status', 'parallel_task_id', 'status'),
    )

    def __repr__(self):
        return f"<AggregatedResult(id={self.id}, parallel_task_id={self.parallel_task_id})>"

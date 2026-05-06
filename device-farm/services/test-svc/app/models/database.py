# Database Models for Test Service (SQLAlchemy)
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, DateTime, Integer, Float, JSON, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase
from enum import Enum
import uuid


class Base(DeclarativeBase):
    pass


class ScriptType(str, Enum):
    PYTHON = "python"


class ScriptStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DevicePlatform(str, Enum):
    ANDROID = "android"
    IOS = "ios"


def _enum_values(enum_cls):
    return [member.value for member in enum_cls]


def _value_enum(enum_cls):
    return SQLEnum(enum_cls, values_callable=_enum_values, native_enum=False)


class ScriptDB(Base):
    """Script database model"""
    __tablename__ = "scripts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    script_type = Column(_value_enum(ScriptType), default=ScriptType.PYTHON, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(_value_enum(ScriptStatus), default=ScriptStatus.DRAFT, nullable=False)
    tags = Column(JSON, default=list)
    file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tasks = relationship("TaskDB", back_populates="script")

    def __repr__(self):
        return f"<Script(id={self.id}, name={self.name})>"


class TaskDB(Base):
    """Task database model"""
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    script_id = Column(String(36), ForeignKey("scripts.id"), nullable=False, index=True)
    device_id = Column(String(100), nullable=True, index=True)
    device_platform = Column(_value_enum(DevicePlatform), default=DevicePlatform.ANDROID, nullable=False)
    device_capabilities = Column(JSON, default=dict)
    parameters = Column(JSON, default=dict)
    status = Column(_value_enum(TaskStatus), default=TaskStatus.PENDING, nullable=False, index=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    log_file = Column(String(500), nullable=True)
    report_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    # Relationships
    script = relationship("ScriptDB", back_populates="tasks")
    logs = relationship("TaskLogDB", back_populates="task", cascade="all, delete-orphan")
    screenshots = relationship("ScreenshotDB", back_populates="task", cascade="all, delete-orphan")
    videos = relationship("VideoDB", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Task(id={self.id}, status={self.status})>"


class TaskLogDB(Base):
    """Task log database model"""
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    level = Column(String(10), default="INFO", nullable=False)
    message = Column(Text, nullable=False)
    event_type = Column(String(50), nullable=True)
    line_number = Column(Integer, nullable=True)

    # Relationships
    task = relationship("TaskDB", back_populates="logs")

    def __repr__(self):
        return f"<TaskLog(task_id={self.task_id}, level={self.level})>"


class ScreenshotDB(Base):
    """Screenshot database model"""
    __tablename__ = "screenshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    index = Column(Integer, nullable=False)  # Order in task execution
    object_name = Column(String(500), nullable=False)  # MinIO object name
    url = Column(String(1000), nullable=True)  # Presigned URL
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    task = relationship("TaskDB", back_populates="screenshots")

    def __repr__(self):
        return f"<Screenshot(id={self.id}, task_id={self.task_id})>"


class VideoDB(Base):
    """Video database model"""
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    object_name = Column(String(500), nullable=False)  # MinIO object name
    url = Column(String(1000), nullable=True)  # Presigned URL
    duration = Column(Float, nullable=True)  # Duration in seconds
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    task = relationship("TaskDB", back_populates="videos")

    def __repr__(self):
        return f"<Video(id={self.id}, task_id={self.task_id})>"

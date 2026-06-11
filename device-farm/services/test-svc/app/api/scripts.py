import os
import json
import ast
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_db_session
from app.models.models import (
    Script,
    ScriptCreate,
    ScriptUpdate,
    ScriptListResponse,
    ScriptStatus,
    ScriptType,
)
from app.models.database import ScriptDB, ScriptStatus as ScriptStatusDB, ScriptType as ScriptTypeDB
from app.config import settings
from app.auth import verify_api_key
from app.tasks.script_sandbox import ALLOWED_SCRIPT_IMPORTS

router = APIRouter()


class ScriptValidationRequest(BaseModel):
    content: str = Field(..., min_length=1)


class ScriptValidationResponse(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


LEGACY_GLOBAL_CALLS = {
    "log": "建议使用 app.log()",
    "wait": "建议使用 app.wait()",
    "screenshot": "建议使用 app.screenshot()",
    "take_screenshot": "建议使用 app.screenshot()",
    "tap": "建议使用 app.tap()",
    "swipe": "建议使用 app.swipe()",
    "input_text": "建议使用 app.input_text()",
    "press_key": "建议使用 app.press_key()",
    "assert_text": "建议使用 app.assert_text()",
}
RESULT_CALLS = {"test_pass", "test_fail", "test_skip"}


def _validate_script_content(content: str) -> ScriptValidationResponse:
    errors: List[str] = []
    warnings: List[str] = []

    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        line = exc.lineno or 0
        column = exc.offset or 0
        errors.append(f"Python 语法错误：第 {line} 行第 {column} 列，{exc.msg}")
        return ScriptValidationResponse(valid=False, errors=errors, warnings=warnings)

    result_call_found = False
    activate_call_found = False
    legacy_warnings = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".", 1)[0]
                if root_name not in ALLOWED_SCRIPT_IMPORTS:
                    errors.append(f"不允许导入模块：{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                errors.append("不支持相对导入")
            root_name = (node.module or "").split(".", 1)[0]
            if root_name not in ALLOWED_SCRIPT_IMPORTS:
                errors.append(f"不允许导入模块：{node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in RESULT_CALLS:
                    result_call_found = True
                if func.id in LEGACY_GLOBAL_CALLS:
                    legacy_warnings.add(f"{func.id}() 是兼容旧脚本的写法，{LEGACY_GLOBAL_CALLS[func.id]}")
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "app" and func.attr in {"activate_app", "launch_app", "restart_app"}:
                    activate_call_found = True

    warnings.extend(sorted(legacy_warnings))
    if not result_call_found:
        warnings.append("脚本中未发现 test_pass()/test_fail()/test_skip()，建议显式标记测试结果")
    if not activate_call_found:
        warnings.append("脚本中未发现 app.activate_app()/app.launch_app()/app.restart_app()，请确认 App 启动逻辑由外部完成或不需要启动 App")

    return ScriptValidationResponse(valid=len(errors) == 0, errors=errors, warnings=warnings)


def _to_pydantic_script_type(db_type: ScriptTypeDB) -> ScriptType:
    return ScriptType(db_type.value if hasattr(db_type, "value") else db_type)


def _to_db_script_type(script_type: ScriptType) -> ScriptTypeDB:
    return ScriptTypeDB(script_type.value if hasattr(script_type, "value") else script_type)


def _to_pydantic_script_status(db_status: ScriptStatusDB) -> ScriptStatus:
    return ScriptStatus(db_status.value if hasattr(db_status, "value") else db_status)


def _to_db_script_status(script_status: ScriptStatus) -> ScriptStatusDB:
    return ScriptStatusDB(script_status.value if hasattr(script_status, "value") else script_status)


def _script_db_to_pydantic(script_db: ScriptDB) -> Script:
    return Script(
        id=script_db.id,
        name=script_db.name,
        description=script_db.description,
        script_type=_to_pydantic_script_type(script_db.script_type),
        content=script_db.content,
        status=_to_pydantic_script_status(script_db.status),
        tags=script_db.tags or [],
        file_path=script_db.file_path,
        created_at=script_db.created_at,
        updated_at=script_db.updated_at,
    )


def _save_script_to_file(script: Script) -> str:
    """Save script content to file system"""
    os.makedirs(settings.SCRIPT_STORAGE_PATH, exist_ok=True)

    file_extension = ".py"
    file_name = f"{script.id}{file_extension}"
    file_path = os.path.join(settings.SCRIPT_STORAGE_PATH, file_name)

    with open(file_path, "w") as f:
        f.write(script.content)

    # Save metadata
    meta_path = os.path.join(settings.SCRIPT_STORAGE_PATH, f"{script.id}.json")
    with open(meta_path, "w") as f:
        json.dump(script.model_dump(), f, default=str)

    return file_path


def _load_script_from_file(script_id: str) -> Optional[Script]:
    """Load script from file system"""
    meta_path = os.path.join(settings.SCRIPT_STORAGE_PATH, f"{script_id}.json")

    if not os.path.exists(meta_path):
        return None

    with open(meta_path, "r") as f:
        data = json.load(f)

    # Parse datetime strings
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    data["updated_at"] = datetime.fromisoformat(data["updated_at"])

    return Script(**data)


def _delete_script_files(script_id: str):
    """Delete script files from file system"""
    meta_path = os.path.join(settings.SCRIPT_STORAGE_PATH, f"{script_id}.json")
    py_path = os.path.join(settings.SCRIPT_STORAGE_PATH, f"{script_id}.py")
    js_path = os.path.join(settings.SCRIPT_STORAGE_PATH, f"{script_id}.js")

    for path in [meta_path, py_path, js_path]:
        if os.path.exists(path):
            os.remove(path)


@router.get("", response_model=ScriptListResponse)
async def list_scripts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[ScriptStatus] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """List all scripts with pagination."""
    conditions = []
    if status:
        conditions.append(ScriptDB.status == _to_db_script_status(status))

    if search:
        pattern = f"%{search}%"
        conditions.append(
            (ScriptDB.name.ilike(pattern)) | (ScriptDB.description.ilike(pattern))
        )

    query = select(ScriptDB)
    count_query = select(func.count()).select_from(ScriptDB)
    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = (
        query.order_by(ScriptDB.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = [_script_db_to_pydantic(script_db) for script_db in result.scalars().all()]

    return ScriptListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 1
    )


@router.post("/validate", response_model=ScriptValidationResponse)
async def validate_script(
    request: ScriptValidationRequest,
    _: str = Depends(verify_api_key),
):
    """Validate Python script syntax and platform usage."""
    return _validate_script_content(request.content)


@router.post("", response_model=Script, status_code=status.HTTP_201_CREATED)
async def create_script(
    script: ScriptCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Create a new script."""
    new_script = Script(**script.model_dump())
    new_script.file_path = _save_script_to_file(new_script)

    script_db = ScriptDB(
        id=new_script.id,
        name=new_script.name,
        description=new_script.description,
        script_type=_to_db_script_type(new_script.script_type),
        content=new_script.content,
        status=_to_db_script_status(new_script.status),
        tags=new_script.tags,
        file_path=new_script.file_path,
        created_at=new_script.created_at,
        updated_at=new_script.updated_at,
    )
    db.add(script_db)
    await db.flush()
    await db.refresh(script_db)

    return _script_db_to_pydantic(script_db)


@router.get("/{script_id}", response_model=Script)
async def get_script(
    script_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Get script by ID."""
    query = select(ScriptDB).where(ScriptDB.id == script_id)
    result = await db.execute(query)
    script_db = result.scalar_one_or_none()
    if script_db:
        return _script_db_to_pydantic(script_db)

    # Keep a read fallback for scripts created before DB-backed storage existed.
    script = _load_script_from_file(script_id)
    if script:
        return script

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Script {script_id} not found",
    )


async def _get_script_db_async(script_id: str) -> Optional[Script]:
    async with get_db_session() as db:
        query = select(ScriptDB).where(ScriptDB.id == script_id)
        result = await db.execute(query)
        script_db = result.scalar_one_or_none()
        if script_db:
            return _script_db_to_pydantic(script_db)

    return _load_script_from_file(script_id)


def _get_script_db(script_id: str) -> Optional[Script]:
    """Sync script loader used by Celery workers."""
    from app.api import tasks as tasks_api
    return tasks_api._run_async(_get_script_db_async(script_id))


@router.put("/{script_id}", response_model=Script)
async def update_script(
    script_id: str,
    script_update: ScriptUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Update an existing script."""
    query = select(ScriptDB).where(ScriptDB.id == script_id)
    result = await db.execute(query)
    script_db = result.scalar_one_or_none()

    if not script_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script {script_id} not found",
        )

    update_data = script_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "script_type" and value is not None:
            value = _to_db_script_type(value)
        elif field == "status" and value is not None:
            value = _to_db_script_status(value)
        setattr(script_db, field, value)

    script_db.updated_at = datetime.utcnow()
    script = _script_db_to_pydantic(script_db)
    script.file_path = _save_script_to_file(script)
    script_db.file_path = script.file_path

    await db.flush()
    await db.refresh(script_db)

    return _script_db_to_pydantic(script_db)


@router.delete("/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(
    script_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Delete a script."""
    query = select(ScriptDB).where(ScriptDB.id == script_id)
    result = await db.execute(query)
    script_db = result.scalar_one_or_none()

    if not script_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script {script_id} not found",
        )

    await db.delete(script_db)
    _delete_script_files(script_id)

    return None

# Scripts API Router
import os
import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status, Depends
from fastapi.responses import JSONResponse

from app.models.models import (
    Script,
    ScriptCreate,
    ScriptUpdate,
    ScriptListResponse,
    ScriptStatus,
)
from app.config import settings
from app.auth import verify_api_key

router = APIRouter()

# In-memory storage (replace with database in production)
_scripts_db: dict = {}


def _save_script_to_file(script: Script) -> str:
    """Save script content to file system"""
    os.makedirs(settings.SCRIPT_STORAGE_PATH, exist_ok=True)

    file_extension = ".py" if script.script_type.value == "python" else ".js"
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
    _: str = Depends(verify_api_key),
):
    """List all scripts with pagination"""
    scripts = list(_scripts_db.values())

    # Apply filters
    if status:
        scripts = [s for s in scripts if s.status == status]

    if search:
        search_lower = search.lower()
        scripts = [
            s for s in scripts
            if search_lower in s.name.lower()
            or (s.description and search_lower in s.description.lower())
        ]

    # Sort by created_at descending
    scripts.sort(key=lambda x: x.created_at, reverse=True)

    # Paginate
    total = len(scripts)
    start = (page - 1) * page_size
    end = start + page_size
    items = scripts[start:end]

    return ScriptListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 1
    )


@router.post("", response_model=Script, status_code=status.HTTP_201_CREATED)
async def create_script(
    script: ScriptCreate,
    _: str = Depends(verify_api_key),
):
    """Create a new script"""
    new_script = Script(**script.model_dump())

    # Save to file system
    file_path = _save_script_to_file(new_script)
    new_script.file_path = file_path

    # Store in memory
    _scripts_db[new_script.id] = new_script

    return new_script


@router.get("/{script_id}", response_model=Script)
async def get_script(
    script_id: str,
    _: str = Depends(verify_api_key),
):
    """Get script by ID"""
    if script_id not in _scripts_db:
        # Try to load from file
        script = _load_script_from_file(script_id)
        if script:
            _scripts_db[script_id] = script
            return script
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script {script_id} not found"
        )

    return _scripts_db[script_id]


@router.put("/{script_id}", response_model=Script)
async def update_script(
    script_id: str,
    script_update: ScriptUpdate,
    _: str = Depends(verify_api_key),
):
    """Update an existing script"""
    if script_id not in _scripts_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script {script_id} not found"
        )

    existing_script = _scripts_db[script_id]
    update_data = script_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(existing_script, field, value)

    existing_script.updated_at = datetime.utcnow()

    # Save updated script
    _save_script_to_file(existing_script)
    _scripts_db[script_id] = existing_script

    return existing_script


@router.delete("/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(
    script_id: str,
    _: str = Depends(verify_api_key),
):
    """Delete a script"""
    if script_id not in _scripts_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script {script_id} not found"
        )

    del _scripts_db[script_id]
    _delete_script_files(script_id)

    return None

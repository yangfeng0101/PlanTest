from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UIBounds(BaseModel):
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


class UIPoint(BaseModel):
    x: int = 0
    y: int = 0


class UIScreen(BaseModel):
    width: int = 0
    height: int = 0


class SelectorSuggestion(BaseModel):
    type: str
    value: str


class UIElement(BaseModel):
    uid: str
    parent_uid: Optional[str] = None
    depth: int = 0
    index: int = 0
    class_name: str = ""
    resource_id: str = ""
    text: str = ""
    content_desc: str = ""
    package: str = ""
    bounds: UIBounds = Field(default_factory=UIBounds)
    center: UIPoint = Field(default_factory=UIPoint)
    clickable: bool = False
    enabled: bool = False
    selected: bool = False
    focused: bool = False
    scrollable: bool = False
    xpath: str = ""
    selector_suggestions: List[SelectorSuggestion] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class UIHierarchyResponse(BaseModel):
    device_id: str
    platform: str = "android"
    captured_at: datetime
    screen: UIScreen
    elements: List[UIElement]
    tree: Dict[str, Any]

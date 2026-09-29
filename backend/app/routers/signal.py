"""信号机接口：维护信号机，覆盖灯位配置、登记断丝、安排维修、办理停用等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.signal import SignalService

router = APIRouter(prefix="/api/signal", tags=["信号机"])

service = SignalService()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按信号机编号检索"),
    status: str | None = Query(default=None, description="正常、主灯丝断、维修中、已停用"),
    maintainable: bool = Query(default=False, description="只返回可维修范围，已停用的信号机会被排除"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按信号机编号与状态过滤信号机列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, maintainable=maintainable, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条信号机，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="信号机已登记", entry=entry)


@router.put("/{entry_id}/config", response_model=ActionResult)
def update_config(entry_id: int, payload: EntryPayload) -> ActionResult:
    """改动灯位配置；显示距离等可选项缺失时保留原有数据，并在信息里说明。"""
    entry, message = service.update_config(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条信号机执行登记断丝、安排维修、办理停用；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出信号机清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "signal", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条信号机明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"信号机 {entry_id} 不存在或已归档")
    return entry

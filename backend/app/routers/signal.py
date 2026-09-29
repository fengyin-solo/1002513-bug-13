"""信号机接口：维护信号机，覆盖登记断丝、安排维修、办理停用等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.signal import STATUS_ORDER, SignalService

router = APIRouter(prefix="/api/signal", tags=["信号机"])

service = SignalService()

LIST_FIELDS = ["信号机编号", "所属车站", "信号机类型", "灯位配置", "显示距离", "灯泡寿命", "点灯单元", "信号机状态"]
STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按信号机编号检索"),
    status: str | None = Query(default=None, description="正常、主灯丝断、维修中、已停用"),
    scope: str | None = Query(default=None, description="repairable：仅看可维修范围（已停用除外）"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按信号机编号与状态过滤信号机列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, scope=scope, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats/summary")
def stats_summary() -> dict[str, int]:
    """信号机状态统计：正常、主灯丝断、维修中、已停用与可维修数量。"""
    return service.statistics()


@router.get("/repairable", response_model=PageResult[dict])
def list_repairable(
    keyword: str | None = Query(default=None, description="按信号机编号检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """维修入口：仅返回可维修信号机，已停用的不会出现。"""
    items, total = service.list_entries(keyword=keyword, scope="repairable", page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


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


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条信号机，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="信号机已登记", entry=entry)


@router.put("/{entry_id}/config", response_model=ActionResult)
def update_config(entry_id: int, payload: EntryPayload) -> ActionResult:
    """改动灯位配置、显示距离、点灯单元；显示距离缺失时保留原有数据并给出说明。"""
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

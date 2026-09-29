"""信号机业务规则：状态流转、灯位配置、断丝登记、寿命核算与可维修口径统一收口在这里。

所有对外展示都走 ``_project`` 派生一份视图，列表、详情与维修入口共用同一口径，
避免同一台信号机在不同入口显示不一致。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.store import store

MODULE = "signal"
REQUIRED_FIELDS = ["信号机编号", "所属车站", "信号机类型"]
EDITABLE_FIELDS = ["灯位配置", "显示距离", "点灯单元"]

STATUS_NORMAL = "正常"
STATUS_BROKEN = "主灯丝断"
STATUS_REPAIR = "维修中"
STATUS_DISABLED = "已停用"
STATUS_ORDER = [STATUS_NORMAL, STATUS_BROKEN, STATUS_REPAIR, STATUS_DISABLED]
ACTION_RULES = {"登记断丝": STATUS_BROKEN, "安排维修": STATUS_REPAIR, "办理停用": STATUS_DISABLED}
ABNORMAL_STATUSES = {STATUS_BROKEN, STATUS_REPAIR}

MISSING_DISTANCE = "未登记"


def _parse_day(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _life_expiry(entry: dict[str, Any]) -> date | None:
    """寿命到期日优先取登记值，否则按安装日期加寿命天数推算。"""
    expiry = _parse_day(entry.get("寿命到期日"))
    if expiry is not None:
        return expiry
    installed = _parse_day(entry.get("安装日期"))
    if installed is None:
        return None
    try:
        life_days = int(str(entry.get("寿命天数")).strip())
    except (TypeError, ValueError):
        return None
    return installed + timedelta(days=life_days)


class SignalService:
    # ---- 读：统一派生口径 -------------------------------------------------
    def _project(self, entry: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        view = dict(entry)
        raw_status = entry.get("status")
        status = raw_status if raw_status in STATUS_ORDER else STATUS_NORMAL
        view["status"] = status
        view["信号机状态"] = status

        expiry = _life_expiry(entry)
        if expiry is None:
            view["寿命剩余天数"] = None
            view["灯泡寿命"] = "寿命信息未登记"
        else:
            # 到期日与今天相差 0 天即到期当天，按到期处理，不再提前一天。
            remaining = (expiry - today).days
            view["寿命到期日"] = expiry.isoformat()
            view["寿命剩余天数"] = remaining
            view["灯泡寿命"] = "已到期" if remaining <= 0 else f"剩余{remaining}天"

        distance = str(entry.get("显示距离") or "").strip()
        if distance:
            view["显示距离"] = distance
        else:
            view["显示距离"] = MISSING_DISTANCE
            view.setdefault("显示距离说明", "显示距离缺失，沿用原有数据，待现场补录")

        view["可维修"] = status != STATUS_DISABLED
        return view

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        scope: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._project(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("信号机编号", ""))]
        if status:
            rows = [row for row in rows if row["信号机状态"] == status]
        # 维修入口口径：已停用信号机不再纳入可维修范围。
        if scope == "repairable":
            rows = [row for row in rows if row["可维修"]]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._project(entry)

    def statistics(self) -> dict[str, int]:
        counts = {status: 0 for status in STATUS_ORDER}
        for row in store.rows(MODULE):
            counts[self._project(row)["信号机状态"]] += 1
        counts["可维修"] = sum(count for status, count in counts.items() if status != STATUS_DISABLED)
        return counts

    # ---- 写 ---------------------------------------------------------------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field) or "").strip() for field in REQUIRED_FIELDS})
        for field in ["灯位配置", "显示距离", "点灯单元", "安装日期", "寿命到期日"]:
            entry[field] = str(values.get(field) or "").strip()
        entry["寿命天数"] = values.get("寿命天数")
        entry["断丝登记"] = []
        entry["status"] = STATUS_NORMAL
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._project(entry), []

    def update_config(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """改动灯位配置等字段；显示距离缺失（未提交或为空）时保留原有数据并给出说明。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"信号机 {entry_id} 不存在或已归档"
        for field in EDITABLE_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = str(value).strip()

        distance = str(values.get("显示距离") or "").strip()
        if distance:
            entry.pop("显示距离说明", None)
        else:
            old = str(entry.get("显示距离") or "").strip()
            suffix = f"（原值：{old}）" if old else "（原值缺失，待现场补录）"
            entry["显示距离说明"] = f"本次改动灯位配置未提供显示距离，已保留原有数据{suffix}"
        return self._project(entry), "信号机灯位配置已更新"

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"信号机 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于信号机可执行范围"

        status = entry.get("status") if entry.get("status") in STATUS_ORDER else STATUS_NORMAL
        if status == STATUS_DISABLED:
            return None, "信号机已停用，不在可维修范围内，不能再登记断丝或安排维修"

        if action == "登记断丝":
            lamp_message = self._register_broken_filament(entry, values)
            if lamp_message is None:
                return None, "请填写断丝灯位，例如：红灯位"
            message = lamp_message
        else:
            message = f"信号机已{action}"

        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_DISABLED
        entry["abnormal"] = target in ABNORMAL_STATUSES
        return self._project(entry), message

    def _register_broken_filament(self, entry: dict[str, Any], values: dict[str, Any]) -> str | None:
        lamp = str(values.get("灯位") or "").strip()
        if not lamp:
            return None
        unit = str(values.get("点灯单元") or "").strip()
        stamp = datetime.now().isoformat(timespec="seconds")
        records: list[dict[str, Any]] = entry.setdefault("断丝登记", [])
        # 同一灯位只保留一条：重复登记时刷新原记录，而不是再追加一条。
        existing = next(
            (record for record in records if str(record.get("灯位") or "").strip() == lamp),
            None,
        )
        if existing is not None:
            if unit:
                existing["点灯单元"] = unit
            existing["登记时间"] = stamp
            return f"{lamp}此前已登记过断丝，已更新原记录，未重复新增"
        records.append({"灯位": lamp, "点灯单元": unit, "登记时间": stamp})
        return f"{lamp}断丝已登记"

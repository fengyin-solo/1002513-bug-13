"""信号机业务规则：状态流转、字段校验、灯位/断丝登记与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "signal"
REQUIRED_FIELDS = ["信号机编号", "所属车站", "信号机类型"]
# 灯位配置相关字段：登记时可一并带入，改配置时只覆盖这些字段
CONFIG_FIELDS = ["灯位配置", "显示距离", "灯泡寿命", "点灯单元"]
STATUS_ORDER = ["正常", "主灯丝断", "维修中", "已停用"]
ACTION_RULES = {"登记断丝": "主灯丝断", "安排维修": "维修中", "办理停用": "已停用"}
# 已停用是终态：停用后既不能登记断丝、也不能安排维修
TERMINAL_STATUS = STATUS_ORDER[-1]


def _today() -> date:
    """单独包一层，方便寿命规则以“今天”为基准计算。"""
    return date.today()


def _parse_due_date(raw: Any) -> date | None:
    """识别“灯泡寿命”里记录的到期日期；不是日期（如纯文字说明）时返回 None，不报错。"""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _life_status(due: date | None) -> str:
    """剩余天数口径：到期当天即按到期处理，不提前一天。

    今天与到期日同一天时剩余 0 天；逾期天数用负数表示，由页面提示更换。
    """
    if due is None:
        return ""
    return str((due - _today()).days)


def _present(entry: dict[str, Any]) -> dict[str, Any]:
    """列表、详情、动作结果统一从这里取展示数据，保证各处口径一致。"""
    data = dict(entry)
    due = _parse_due_date(entry.get("灯泡寿命"))
    data["寿命到期日"] = due.isoformat() if due else ""
    data["剩余天数"] = _life_status(due)
    # “信号机状态”以内部 status 为唯一事实来源，避免列表和详情各说各话
    data["信号机状态"] = entry.get("status")
    return data


class SignalService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        maintainable: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("信号机编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if maintainable:
            # 可维修范围：已停用的信号机不再纳入
            rows = [row for row in rows if row.get("status") != TERMINAL_STATUS]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in CONFIG_FIELDS:
            text = str(values.get(field) or "").strip()
            if text:
                entry[field] = text
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["断丝记录"] = []
        rows.append(entry)
        return _present(entry), []

    def update_config(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """改动灯位配置：显示距离等可选项留空时保留原有数据，并在返回信息里说明。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"信号机 {entry_id} 不存在或已归档"
        lamp = str(values.get("灯位配置") or "").strip()
        if not lamp:
            return None, "灯位配置为必填项，请填写后再提交"
        due_text = str(values.get("灯泡寿命") or "").strip()
        if due_text and _parse_due_date(due_text) is None:
            return None, "灯泡寿命需为到期日期（YYYY-MM-DD），无法识别当前填写内容"
        entry["灯位配置"] = lamp
        kept: list[str] = []
        for field in ("显示距离", "点灯单元"):
            text = str(values.get(field) or "").strip()
            if text:
                entry[field] = text
            elif entry.get(field):
                kept.append(field)
        if due_text:
            entry["灯泡寿命"] = due_text
        elif entry.get("灯泡寿命"):
            kept.append("灯泡寿命")
        message = "灯位配置已更新"
        if kept:
            message += f"；{'、'.join(kept)}未填写，保留原有数据"
        return _present(entry), message

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"信号机 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于信号机可执行范围"
        if entry.get("status") == TERMINAL_STATUS:
            return None, "信号机已停用，不在可维修范围内，不能再办理相关作业"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        records: list[dict[str, Any]] = entry.setdefault("断丝记录", [])
        if action == "登记断丝":
            values = values or {}
            lamp = str(values.get("灯位") or "主灯丝").strip() or "主灯丝"
            # 同一灯位重复登记只保留一条：已有记录时直接返回，不再追加
            if any(str(record.get("灯位")) == lamp for record in records):
                return _present(entry), f"灯位「{lamp}」已登记过断丝，无需重复登记"
            records.append({"灯位": lamp, "点灯单元": str(values.get("点灯单元") or "").strip()})
            entry["status"] = target
            entry["abnormal"] = True
            entry["pending"] = True
            return _present(entry), f"信号机已{action}"

        entry["status"] = target
        if action == "安排维修":
            entry["pending"] = False
        return _present(entry), f"信号机已{action}"

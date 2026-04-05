
import copy
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


# =========================
# Data model
# =========================

@dataclass
class HierarchyItem:
    uid: int
    id_number: int
    name: str
    level: str   # large / middle / small
    parent_uid: Optional[int] = None


@dataclass
class ActionDefinition:
    uid: int
    small_item_uid: int
    action_no: int
    name: str
    action_type: str  # onoff / points
    points: List[str] = field(default_factory=list)


@dataclass
class OperationInstance:
    uid: int
    action_uid: int
    name: str
    duration_ms: int
    start_trigger: str = "manual"  # manual / after_finish / after_start
    trigger_operation_uid: Optional[int] = None
    from_value: str = ""
    to_value: str = ""


class AppModel:
    def __init__(self):
        self.hierarchy_items: List[HierarchyItem] = []
        self.action_definitions: List[ActionDefinition] = []
        self.operations: List[OperationInstance] = []

    # ---------- internal unique IDs ----------
    def next_hierarchy_uid(self) -> int:
        return max([x.uid for x in self.hierarchy_items], default=0) + 1

    def next_action_uid(self) -> int:
        return max([x.uid for x in self.action_definitions], default=0) + 1

    def next_operation_uid(self) -> int:
        return max([x.uid for x in self.operations], default=0) + 1

    # ---------- local display IDs ----------
    def next_local_id(self, level: str, parent_uid: Optional[int]) -> int:
        nums = [
            x.id_number for x in self.hierarchy_items
            if x.level == level and x.parent_uid == parent_uid
        ]
        return max(nums, default=0) + 1

    def next_action_no(self, small_item_uid: int) -> int:
        nums = [x.action_no for x in self.action_definitions if x.small_item_uid == small_item_uid]
        return max(nums, default=0) + 1

    # ---------- lookups ----------
    def get_hierarchy(self, uid: int) -> Optional[HierarchyItem]:
        return next((x for x in self.hierarchy_items if x.uid == uid), None)

    def get_action_def(self, uid: int) -> Optional[ActionDefinition]:
        return next((x for x in self.action_definitions if x.uid == uid), None)

    def get_operation(self, uid: int) -> Optional[OperationInstance]:
        return next((x for x in self.operations if x.uid == uid), None)

    def small_items(self) -> List[HierarchyItem]:
        return [x for x in self.hierarchy_items if x.level == "small"]

    def children_of(self, parent_uid: Optional[int], level: Optional[str] = None) -> List[HierarchyItem]:
        result = [x for x in self.hierarchy_items if x.parent_uid == parent_uid]
        if level:
            result = [x for x in result if x.level == level]
        return result

    def hierarchy_path(self, item_uid: int) -> str:
        names = []
        cur = self.get_hierarchy(item_uid)
        while cur:
            names.append(cur.name)
            cur = self.get_hierarchy(cur.parent_uid) if cur.parent_uid is not None else None
        return " / ".join(reversed(names))

    def get_large_for_small(self, small_uid: int) -> Optional[HierarchyItem]:
        small = self.get_hierarchy(small_uid)
        if not small:
            return None
        middle = self.get_hierarchy(small.parent_uid) if small.parent_uid is not None else None
        if not middle:
            return None
        return self.get_hierarchy(middle.parent_uid) if middle.parent_uid is not None else None

    def get_middle_for_small(self, small_uid: int) -> Optional[HierarchyItem]:
        small = self.get_hierarchy(small_uid)
        return self.get_hierarchy(small.parent_uid) if small and small.parent_uid is not None else None

    def action_label(self, action_uid: int) -> str:
        a = self.get_action_def(action_uid)
        if not a:
            return f"(missing:{action_uid})"
        small = self.get_hierarchy(a.small_item_uid)
        middle = self.get_middle_for_small(a.small_item_uid)
        large = self.get_large_for_small(a.small_item_uid)
        large_part = f"{large.id_number}:{large.name}" if large else "-"
        middle_part = f"{middle.id_number}:{middle.name}" if middle else "-"
        small_part = f"{small.id_number}:{small.name}" if small else "-"
        return f"{large_part} / {middle_part} / {small_part} / 動作{a.action_no}:{a.name}"

    # ---------- persistence ----------
    def to_dict(self) -> Dict:
        return {
            "hierarchy_items": [asdict(x) for x in self.hierarchy_items],
            "action_definitions": [asdict(x) for x in self.action_definitions],
            "operations": [asdict(x) for x in self.operations],
            "schema_version": 2,
        }

    def from_dict(self, data: Dict):
        # schema v2
        if data.get("schema_version") == 2 or (data.get("hierarchy_items") and "uid" in data["hierarchy_items"][0]):
            self.hierarchy_items = [HierarchyItem(**x) for x in data.get("hierarchy_items", [])]
            self.action_definitions = [ActionDefinition(**x) for x in data.get("action_definitions", [])]
            self.operations = [OperationInstance(**x) for x in data.get("operations", [])]
            return

        # backward compatibility for old schema
        old_hierarchy = data.get("hierarchy_items", [])
        old_actions = data.get("action_definitions", [])
        old_ops = data.get("operations", [])

        hierarchy_id_map: Dict[int, int] = {}
        by_old_id = {x["id"]: x for x in old_hierarchy}

        # recreate large
        for old in [x for x in old_hierarchy if x["level"] == "large"]:
            uid = self.next_hierarchy_uid()
            hierarchy_id_map[old["id"]] = uid
            self.hierarchy_items.append(HierarchyItem(
                uid=uid,
                id_number=self.next_local_id("large", None),
                name=old["name"],
                level="large",
                parent_uid=None,
            ))

        # recreate middle
        for old in [x for x in old_hierarchy if x["level"] == "middle"]:
            old_parent = old.get("parent_id")
            parent_uid = hierarchy_id_map.get(old_parent)
            uid = self.next_hierarchy_uid()
            hierarchy_id_map[old["id"]] = uid
            self.hierarchy_items.append(HierarchyItem(
                uid=uid,
                id_number=self.next_local_id("middle", parent_uid),
                name=old["name"],
                level="middle",
                parent_uid=parent_uid,
            ))

        # recreate small
        for old in [x for x in old_hierarchy if x["level"] == "small"]:
            old_parent = old.get("parent_id")
            parent_uid = hierarchy_id_map.get(old_parent)
            uid = self.next_hierarchy_uid()
            hierarchy_id_map[old["id"]] = uid
            self.hierarchy_items.append(HierarchyItem(
                uid=uid,
                id_number=self.next_local_id("small", parent_uid),
                name=old["name"],
                level="small",
                parent_uid=parent_uid,
            ))

        action_id_map: Dict[int, int] = {}
        for old in old_actions:
            uid = self.next_action_uid()
            action_id_map[old["id"]] = uid
            small_uid = hierarchy_id_map.get(old["small_item_id"])
            self.action_definitions.append(ActionDefinition(
                uid=uid,
                small_item_uid=small_uid,
                action_no=self.next_action_no(small_uid),
                name=old["name"],
                action_type=old["action_type"],
                points=old.get("points", []),
            ))

        for old in old_ops:
            uid = self.next_operation_uid()
            self.operations.append(OperationInstance(
                uid=uid,
                action_uid=action_id_map.get(old["action_def_id"]),
                name=old["name"],
                duration_ms=old["duration_ms"],
                start_trigger=old.get("start_trigger", "manual"),
                trigger_operation_uid=None,  # set later
                from_value=old.get("from_value", ""),
                to_value=old.get("to_value", ""),
            ))

        old_to_new_op: Dict[int, int] = {}
        for old, new in zip(old_ops, self.operations):
            old_to_new_op[old["id"]] = new.uid
        for old, new in zip(old_ops, self.operations):
            trig = old.get("trigger_operation_id")
            new.trigger_operation_uid = old_to_new_op.get(trig) if trig is not None else None

    def clone_data(self) -> Dict:
        return copy.deepcopy(self.to_dict())


# =========================
# Dialogs
# =========================

class DeviceActionRowDialog(QDialog):
    def __init__(self, model: AppModel, action_def: Optional[ActionDefinition] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("機器一覧項目")
        self.model = model
        self.action_def = action_def

        self.large_combo = QComboBox()
        self.middle_combo = QComboBox()
        self.small_combo = QComboBox()

        self.large_id_edit = QLineEdit()
        self.large_name_edit = QLineEdit()
        self.middle_id_edit = QLineEdit()
        self.middle_name_edit = QLineEdit()
        self.small_id_edit = QLineEdit()
        self.small_name_edit = QLineEdit()

        self.action_type_combo = QComboBox()
        self.action_type_combo.addItems(["onoff", "points"])
        self.action_no_edit = QLineEdit()
        self.action_name_edit = QLineEdit()
        self.points_edit = QLineEdit()
        self.points_hint = QLabel("points の場合のみ。例: 原点, 待機, 加工")

        for large in sorted(self.model.children_of(None, "large"), key=lambda x: (x.id_number, x.uid)):
            self.large_combo.addItem(f"{large.id_number}: {large.name}", large.uid)
        self.large_combo.addItem("(新規作成)", "new")

        self._reload_middle_combo()
        self._reload_small_combo()

        form = QFormLayout(self)
        form.addRow("既存大項目", self.large_combo)
        form.addRow("大項目ID", self.large_id_edit)
        form.addRow("大項目", self.large_name_edit)
        form.addRow("既存中項目", self.middle_combo)
        form.addRow("中項目ID", self.middle_id_edit)
        form.addRow("中項目", self.middle_name_edit)
        form.addRow("既存小項目", self.small_combo)
        form.addRow("小項目ID", self.small_id_edit)
        form.addRow("小項目", self.small_name_edit)
        form.addRow("動作種別", self.action_type_combo)
        form.addRow("動作番号", self.action_no_edit)
        form.addRow("動作", self.action_name_edit)
        form.addRow("ポイント一覧", self.points_edit)
        form.addRow("", self.points_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.large_combo.currentIndexChanged.connect(self._on_large_changed)
        self.middle_combo.currentIndexChanged.connect(self._on_middle_changed)
        self.small_combo.currentIndexChanged.connect(self._on_small_changed)
        self.action_type_combo.currentTextChanged.connect(self._refresh_points_enabled)
        self._refresh_points_enabled()

        if action_def:
            self._load_existing_action(action_def)
        else:
            self._prefill_new_ids()

    def _refresh_points_enabled(self):
        enabled = self.action_type_combo.currentText() == "points"
        self.points_edit.setEnabled(enabled)
        self.points_hint.setEnabled(enabled)

    def _reload_middle_combo(self):
        self.middle_combo.clear()
        large_uid = self.large_combo.currentData()
        if isinstance(large_uid, int):
            for middle in sorted(self.model.children_of(large_uid, "middle"), key=lambda x: (x.id_number, x.uid)):
                self.middle_combo.addItem(f"{middle.id_number}: {middle.name}", middle.uid)
        self.middle_combo.addItem("(新規作成)", "new")

    def _reload_small_combo(self):
        self.small_combo.clear()
        middle_uid = self.middle_combo.currentData()
        if isinstance(middle_uid, int):
            for small in sorted(self.model.children_of(middle_uid, "small"), key=lambda x: (x.id_number, x.uid)):
                self.small_combo.addItem(f"{small.id_number}: {small.name}", small.uid)
        self.small_combo.addItem("(新規作成)", "new")

    def _on_large_changed(self):
        self._reload_middle_combo()
        self._reload_small_combo()
        self._prefill_new_ids()

    def _on_middle_changed(self):
        self._reload_small_combo()
        self._prefill_new_ids()

    def _on_small_changed(self):
        self._prefill_new_ids()

    def _prefill_new_ids(self):
        large_val = self.large_combo.currentData()
        if large_val == "new" or self.large_combo.count() == 1:
            self.large_id_edit.setText(str(self.model.next_local_id("large", None)))
        elif isinstance(large_val, int):
            large = self.model.get_hierarchy(large_val)
            if large:
                self.large_id_edit.setText(str(large.id_number))
                self.large_name_edit.setText(large.name)

        middle_val = self.middle_combo.currentData()
        parent_large_uid = self.large_combo.currentData() if isinstance(self.large_combo.currentData(), int) else None
        if middle_val == "new":
            self.middle_id_edit.setText(str(self.model.next_local_id("middle", parent_large_uid)))
        elif isinstance(middle_val, int):
            middle = self.model.get_hierarchy(middle_val)
            if middle:
                self.middle_id_edit.setText(str(middle.id_number))
                self.middle_name_edit.setText(middle.name)

        small_val = self.small_combo.currentData()
        parent_middle_uid = self.middle_combo.currentData() if isinstance(self.middle_combo.currentData(), int) else None
        if small_val == "new":
            self.small_id_edit.setText(str(self.model.next_local_id("small", parent_middle_uid)))
        elif isinstance(small_val, int):
            small = self.model.get_hierarchy(small_val)
            if small:
                self.small_id_edit.setText(str(small.id_number))
                self.small_name_edit.setText(small.name)
                self.action_no_edit.setText(str(self.model.next_action_no(small.uid)))

    def _load_existing_action(self, action_def: ActionDefinition):
        small = self.model.get_hierarchy(action_def.small_item_uid)
        middle = self.model.get_middle_for_small(action_def.small_item_uid)
        large = self.model.get_large_for_small(action_def.small_item_uid)

        if large:
            idx = self.large_combo.findData(large.uid)
            if idx >= 0:
                self.large_combo.setCurrentIndex(idx)
        self._reload_middle_combo()
        if middle:
            idx = self.middle_combo.findData(middle.uid)
            if idx >= 0:
                self.middle_combo.setCurrentIndex(idx)
        self._reload_small_combo()
        if small:
            idx = self.small_combo.findData(small.uid)
            if idx >= 0:
                self.small_combo.setCurrentIndex(idx)

        self.large_id_edit.setText(str(large.id_number if large else 1))
        self.large_name_edit.setText(large.name if large else "")
        self.middle_id_edit.setText(str(middle.id_number if middle else 1))
        self.middle_name_edit.setText(middle.name if middle else "")
        self.small_id_edit.setText(str(small.id_number if small else 1))
        self.small_name_edit.setText(small.name if small else "")
        self.action_type_combo.setCurrentText(action_def.action_type)
        self.action_no_edit.setText(str(action_def.action_no))
        self.action_name_edit.setText(action_def.name)
        self.points_edit.setText(", ".join(action_def.points))
        self._refresh_points_enabled()

    def get_value(self) -> Dict:
        action_type = self.action_type_combo.currentText()
        points = [x.strip() for x in self.points_edit.text().split(",") if x.strip()] if action_type == "points" else ["OFF", "ON"]
        return {
            "large_existing": self.large_combo.currentData(),
            "large_id": int(self.large_id_edit.text().strip()),
            "large_name": self.large_name_edit.text().strip(),
            "middle_existing": self.middle_combo.currentData(),
            "middle_id": int(self.middle_id_edit.text().strip()),
            "middle_name": self.middle_name_edit.text().strip(),
            "small_existing": self.small_combo.currentData(),
            "small_id": int(self.small_id_edit.text().strip()),
            "small_name": self.small_name_edit.text().strip(),
            "action_type": action_type,
            "action_no": int(self.action_no_edit.text().strip()),
            "action_name": self.action_name_edit.text().strip(),
            "points": points,
        }


class OperationDialog(QDialog):
    def __init__(self, model: AppModel, operation: Optional[OperationInstance] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("動作設定")
        self.model = model
        self.operation = operation

        self.action_combo = QComboBox()
        for a in sorted(self.model.action_definitions, key=lambda x: (self.model.hierarchy_path(x.small_item_uid), x.action_no, x.uid)):
            self.action_combo.addItem(self.model.action_label(a.uid), a.uid)

        self.name_edit = QLineEdit()
        self.duration_edit = QLineEdit("1000")

        self.trigger_combo = QComboBox()
        self.trigger_combo.addItems(["manual", "after_finish", "after_start"])

        self.dep_combo = QComboBox()
        self.dep_combo.addItem("-", "")
        for op in sorted(self.model.operations, key=lambda x: x.uid):
            if operation and op.uid == operation.uid:
                continue
            self.dep_combo.addItem(f"{op.uid}: {op.name}", str(op.uid))

        self.from_combo = QComboBox()
        self.to_combo = QComboBox()

        form = QFormLayout(self)
        form.addRow("対象動作定義", self.action_combo)
        form.addRow("設定名", self.name_edit)
        form.addRow("時間(ms)", self.duration_edit)
        form.addRow("開始トリガ", self.trigger_combo)
        form.addRow("依存先動作", self.dep_combo)
        form.addRow("開始値 / 開始ポイント", self.from_combo)
        form.addRow("終了値 / 終了ポイント", self.to_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.action_combo.currentIndexChanged.connect(self._reload_values)
        self.trigger_combo.currentTextChanged.connect(self._refresh_dep_enabled)
        self._reload_values()
        self._refresh_dep_enabled()

        if operation:
            idx = self.action_combo.findData(operation.action_uid)
            if idx >= 0:
                self.action_combo.setCurrentIndex(idx)
            self.name_edit.setText(operation.name)
            self.duration_edit.setText(str(operation.duration_ms))
            self.trigger_combo.setCurrentText(operation.start_trigger)
            dep_val = "" if operation.trigger_operation_uid is None else str(operation.trigger_operation_uid)
            didx = self.dep_combo.findData(dep_val)
            if didx >= 0:
                self.dep_combo.setCurrentIndex(didx)
            self._reload_values()
            fidx = self.from_combo.findText(operation.from_value)
            if fidx >= 0:
                self.from_combo.setCurrentIndex(fidx)
            tidx = self.to_combo.findText(operation.to_value)
            if tidx >= 0:
                self.to_combo.setCurrentIndex(tidx)

    def _refresh_dep_enabled(self):
        enabled = self.trigger_combo.currentText() != "manual"
        self.dep_combo.setEnabled(enabled)

    def _reload_values(self):
        self.from_combo.clear()
        self.to_combo.clear()
        action_def = self.model.get_action_def(int(self.action_combo.currentData()))
        values = []
        if action_def:
            values = ["OFF", "ON"] if action_def.action_type == "onoff" else (action_def.points or ["P1", "P2"])
        self.from_combo.addItems(values)
        self.to_combo.addItems(values)
        if len(values) >= 2:
            self.from_combo.setCurrentIndex(0)
            self.to_combo.setCurrentIndex(min(1, len(values) - 1))

    def get_value(self):
        action_uid = int(self.action_combo.currentData())
        name = self.name_edit.text().strip()
        duration_ms = max(0, int(self.duration_edit.text().strip() or "0"))
        start_trigger = self.trigger_combo.currentText()
        raw_dep = self.dep_combo.currentData()
        dep_uid = int(raw_dep) if start_trigger != "manual" and raw_dep not in ("", None) else None
        from_value = self.from_combo.currentText()
        to_value = self.to_combo.currentText()
        return action_uid, name, duration_ms, start_trigger, dep_uid, from_value, to_value


# =========================
# Schedule calculation
# =========================

def calculate_schedule(model: AppModel) -> Tuple[Dict[int, Tuple[int, int]], List[str]]:
    ops = {op.uid: op for op in model.operations}
    errors = []
    visiting = set()
    visited = set()

    def dfs(op_uid: int):
        if op_uid in visiting:
            raise ValueError(f"循環依存があります: 動作UID {op_uid}")
        if op_uid in visited:
            return
        visiting.add(op_uid)
        op = ops[op_uid]
        if op.trigger_operation_uid is not None and op.trigger_operation_uid in ops:
            dfs(op.trigger_operation_uid)
        visiting.remove(op_uid)
        visited.add(op_uid)

    try:
        for op_uid in ops:
            dfs(op_uid)
    except ValueError as e:
        return {}, [str(e)]

    memo: Dict[int, Tuple[int, int]] = {}

    def calc(op_uid: int) -> Tuple[int, int]:
        if op_uid in memo:
            return memo[op_uid]
        op = ops[op_uid]
        if op.start_trigger == "manual" or op.trigger_operation_uid is None:
            start = 0
        else:
            pred = ops.get(op.trigger_operation_uid)
            if pred is None:
                errors.append(f"動作UID {op.uid}: 依存先 {op.trigger_operation_uid} が見つかりません")
                start = 0
            else:
                p_start, p_end = calc(pred.uid)
                start = p_end if op.start_trigger == "after_finish" else p_start
        end = start + max(0, op.duration_ms)
        memo[op_uid] = (start, end)
        return memo[op_uid]

    for op_uid in ops:
        calc(op_uid)

    return memo, errors


# =========================
# Chart view
# =========================

class SelectableOpRect(QGraphicsRectItem):
    def __init__(self, rect: QRectF, operation_uid: int, callback):
        super().__init__(rect)
        self.operation_uid = operation_uid
        self.callback = callback
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.callback:
            self.callback(self.operation_uid)


class TimingChartView(QGraphicsView):
    dependency_created = Signal(int, int)  # source_uid, target_uid

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setScene(QGraphicsScene(self))
        self.link_mode = False
        self._pending_source_uid: Optional[int] = None

    def set_link_mode(self, enabled: bool):
        self.link_mode = enabled
        self._pending_source_uid = None

    def _on_operation_clicked(self, operation_uid: int):
        if not self.link_mode:
            return
        if self._pending_source_uid is None:
            self._pending_source_uid = operation_uid
        else:
            if self._pending_source_uid != operation_uid:
                self.dependency_created.emit(self._pending_source_uid, operation_uid)
            self._pending_source_uid = None

    def render_chart(self, model: AppModel):
        scene = self.scene()
        scene.clear()

        schedule, errors = calculate_schedule(model)
        if errors:
            y = 20
            scene.setSceneRect(0, 0, 1000, 300)
            title = scene.addSimpleText("ERROR")
            title.setPos(20, y)
            y += 30
            for e in errors:
                txt = scene.addSimpleText(f"- {e}")
                txt.setPos(20, y)
                y += 22
            hint = scene.addSimpleText("Ctrl+Z で元に戻す / Ctrl+Y でやり直し")
            hint.setPos(20, y + 10)
            return

        row_h = 80
        left_w = 320
        header_h = 50
        time_scale = 0.12
        max_time = max([end for _, end in schedule.values()], default=3000)
        total_w = left_w + max_time * time_scale + 300
        total_h = header_h + max(1, len(model.small_items())) * row_h + 80
        scene.setSceneRect(0, 0, total_w, total_h)

        smalls = sorted(
            model.small_items(),
            key=lambda x: (
                (model.get_large_for_small(x.uid).id_number if model.get_large_for_small(x.uid) else 0),
                (model.get_middle_for_small(x.uid).id_number if model.get_middle_for_small(x.uid) else 0),
                x.id_number,
                x.uid,
            ),
        )
        row_map = {s.uid: i for i, s in enumerate(smalls)}

        scene.addRect(0, 0, total_w, header_h)
        scene.addLine(left_w, 0, left_w, total_h)

        step = 500
        t = 0
        while t <= max_time + 1000:
            x = left_w + t * time_scale
            pen = QPen(QColor(180, 180, 180))
            pen.setStyle(Qt.DashLine)
            scene.addLine(x, header_h, x, total_h - 20, pen)
            txt = scene.addSimpleText(f"{t} ms")
            txt.setPos(x + 4, 8)
            t += step

        for s in smalls:
            row = row_map[s.uid]
            top = header_h + row * row_h
            bg = QGraphicsRectItem(0, top, total_w, row_h)
            bg.setBrush(QBrush(QColor(248, 249, 251) if row % 2 == 0 else QColor(238, 241, 244)))
            bg.setPen(QPen(QColor(220, 225, 230)))
            scene.addItem(bg)
            large = model.get_large_for_small(s.uid)
            middle = model.get_middle_for_small(s.uid)
            label_text = f"{large.id_number if large else '-'}-{middle.id_number if middle else '-'}-{s.id_number}  {model.hierarchy_path(s.uid)}"
            label = scene.addSimpleText(label_text)
            label.setPos(10, top + 8)

        op_anchor: Dict[int, Dict[str, QPointF]] = {}

        for op in sorted(model.operations, key=lambda x: x.uid):
            action_def = model.get_action_def(op.action_uid)
            if not action_def:
                continue
            small_uid = action_def.small_item_uid
            row = row_map.get(small_uid)
            if row is None:
                continue

            start, end = schedule.get(op.uid, (0, 0))
            top = header_h + row * row_h
            x1 = left_w + start * time_scale
            x2 = left_w + end * time_scale

            if action_def.action_type == "onoff":
                y_off = top + row_h * 0.68
                y_on = top + row_h * 0.28
                y1 = y_on if op.from_value == "ON" else y_off
                y2 = y_on if op.to_value == "ON" else y_off
                pen = QPen(QColor(28, 124, 84), 3)
                scene.addLine(x1, y1, x2, y2, pen)
                if y1 != y2:
                    scene.addLine(x1, y1, x1, y2, pen)
                hit_rect = QRectF(min(x1, x2), min(y1, y2) - 10, max(20, abs(x2 - x1)), abs(y2 - y1) + 20)
            else:
                points = action_def.points or ["P1", "P2"]
                index_map = {p: i for i, p in enumerate(points)}
                n = max(1, len(points) - 1)
                f_idx = index_map.get(op.from_value, 0)
                t_idx = index_map.get(op.to_value, f_idx)
                y1 = top + 14 + (row_h - 28) * (f_idx / max(1, n))
                y2 = top + 14 + (row_h - 28) * (t_idx / max(1, n))
                pen = QPen(QColor(45, 92, 191), 3)
                scene.addLine(x1, y1, x2, y2, pen)
                hit_rect = QRectF(min(x1, x2) - 6, min(y1, y2) - 10, max(20, abs(x2 - x1) + 12), abs(y2 - y1) + 20)
                for p, i in index_map.items():
                    py = top + 14 + (row_h - 28) * (i / max(1, n))
                    scene.addLine(left_w - 6, py, left_w, py, QPen(QColor(140, 140, 140)))
                    if i < 6:
                        label = scene.addSimpleText(p)
                        label.setPos(left_w - 70, py - 8)

            hit = SelectableOpRect(hit_rect, op.uid, self._on_operation_clicked)
            hit.setBrush(QBrush(QColor(0, 0, 0, 1)))
            hit.setPen(QPen(QColor(0, 0, 0, 0)))
            scene.addItem(hit)

            caption = scene.addSimpleText(f"OP{op.uid}: {op.name}")
            caption.setPos(x1 + 6, top + 6)
            op_anchor[op.uid] = {"start": QPointF(x1, y1), "end": QPointF(x2, y2)}

        for op in model.operations:
            if op.trigger_operation_uid is None:
                continue
            if op.trigger_operation_uid not in op_anchor or op.uid not in op_anchor:
                continue

            src_key = "end" if op.start_trigger == "after_finish" else "start"
            p1 = op_anchor[op.trigger_operation_uid][src_key]
            p2 = op_anchor[op.uid]["start"]

            line = scene.addLine(p1.x(), p1.y(), p2.x(), p2.y(), QPen(QColor(180, 70, 50), 2))

            angle = line.line().angle()
            arrow_size = 10
            p = p2
            import math
            rad1 = math.radians(angle + 150)
            rad2 = math.radians(angle - 150)
            arrow = QPolygonF([
                p,
                QPointF(p.x() + arrow_size * math.cos(rad1), p.y() - arrow_size * math.sin(rad1)),
                QPointF(p.x() + arrow_size * math.cos(rad2), p.y() - arrow_size * math.sin(rad2)),
            ])
            arrow_item = QGraphicsPolygonItem(arrow)
            arrow_item.setBrush(QBrush(QColor(180, 70, 50)))
            arrow_item.setPen(QPen(QColor(180, 70, 50)))
            scene.addItem(arrow_item)


# =========================
# Tabs
# =========================



class DeviceTab(QWidget):
    model_about_to_change = Signal(str)
    model_changed = Signal()

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self.model = model

        layout = QVBoxLayout(self)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["項目", "動作種別", "動作番号 / 動作"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

        note = QLabel("※ 大項目 → 中項目 → 小項目 → 動作 の階層で表示します。クリックで展開 / 折りたたみできます。")
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("動作追加")
        self.edit_btn = QPushButton("動作編集")
        self.del_btn = QPushButton("動作削除")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.edit_btn)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.add_btn.clicked.connect(self.add_row)
        self.edit_btn.clicked.connect(self.edit_row)
        self.del_btn.clicked.connect(self.delete_row)

        self.refresh()

    def refresh(self):
        self.tree.clear()

        large_items = sorted(
            self.model.children_of(None, "large"),
            key=lambda x: (x.id_number, x.uid)
        )

        for large in large_items:
            large_item = QTreeWidgetItem([f"{large.id_number} {large.name}", "", ""])
            large_item.setData(0, Qt.UserRole, ("hierarchy", large.uid))
            self.tree.addTopLevelItem(large_item)

            middle_items = sorted(
                self.model.children_of(large.uid, "middle"),
                key=lambda x: (x.id_number, x.uid)
            )
            for middle in middle_items:
                middle_item = QTreeWidgetItem([f"{middle.id_number} {middle.name}", "", ""])
                middle_item.setData(0, Qt.UserRole, ("hierarchy", middle.uid))
                large_item.addChild(middle_item)

                small_items = sorted(
                    self.model.children_of(middle.uid, "small"),
                    key=lambda x: (x.id_number, x.uid)
                )
                for small in small_items:
                    small_item = QTreeWidgetItem([f"{small.id_number} {small.name}", "", ""])
                    small_item.setData(0, Qt.UserRole, ("hierarchy", small.uid))
                    middle_item.addChild(small_item)

                    actions = sorted(
                        [a for a in self.model.action_definitions if a.small_item_uid == small.uid],
                        key=lambda x: (x.action_no, x.uid)
                    )
                    for action in actions:
                        action_item = QTreeWidgetItem([
                            f"{action.action_no} {action.name}",
                            action.action_type,
                            f"{action.action_no} / {action.name}",
                        ])
                        action_item.setData(0, Qt.UserRole, ("action", action.uid))
                        small_item.addChild(action_item)

        self.tree.expandToDepth(2)

    def _selected_action_uid(self) -> Optional[int]:
        item = self.tree.currentItem()
        if not item:
            return None
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "action":
            return None
        return data[1]

    def add_row(self):
        dlg = DeviceActionRowDialog(self.model, parent=self)
        if dlg.exec():
            try:
                value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "ID・動作番号は数値で入力してください。")
                return

            if not value["large_name"] or not value["middle_name"] or not value["small_name"] or not value["action_name"]:
                QMessageBox.warning(self, "入力不足", "大項目 / 中項目 / 小項目 / 動作 を入力してください。")
                return

            self.model_about_to_change.emit("機器一覧追加")
            large_uid = self._resolve_or_create_hierarchy("large", value["large_existing"], None, value["large_id"], value["large_name"])
            middle_uid = self._resolve_or_create_hierarchy("middle", value["middle_existing"], large_uid, value["middle_id"], value["middle_name"])
            small_uid = self._resolve_or_create_hierarchy("small", value["small_existing"], middle_uid, value["small_id"], value["small_name"])

            self.model.action_definitions.append(ActionDefinition(
                uid=self.model.next_action_uid(),
                small_item_uid=small_uid,
                action_no=value["action_no"],
                name=value["action_name"],
                action_type=value["action_type"],
                points=value["points"],
            ))
            self.refresh()
            self.model_changed.emit()

    def edit_row(self):
        action_uid = self._selected_action_uid()
        if action_uid is None:
            QMessageBox.information(self, "選択", "編集する動作を選択してください。")
            return
        action = self.model.get_action_def(action_uid)
        if not action:
            return

        dlg = DeviceActionRowDialog(self.model, action_def=action, parent=self)
        if dlg.exec():
            try:
                value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "ID・動作番号は数値で入力してください。")
                return

            if not value["large_name"] or not value["middle_name"] or not value["small_name"] or not value["action_name"]:
                QMessageBox.warning(self, "入力不足", "大項目 / 中項目 / 小項目 / 動作 を入力してください。")
                return

            self.model_about_to_change.emit("機器一覧編集")
            large_uid = self._resolve_or_create_hierarchy("large", value["large_existing"], None, value["large_id"], value["large_name"])
            middle_uid = self._resolve_or_create_hierarchy("middle", value["middle_existing"], large_uid, value["middle_id"], value["middle_name"])
            small_uid = self._resolve_or_create_hierarchy("small", value["small_existing"], middle_uid, value["small_id"], value["small_name"])

            action.small_item_uid = small_uid
            action.action_no = value["action_no"]
            action.name = value["action_name"]
            action.action_type = value["action_type"]
            action.points = value["points"]

            self._cleanup_orphans()
            self.refresh()
            self.model_changed.emit()

    def delete_row(self):
        action_uid = self._selected_action_uid()
        if action_uid is None:
            QMessageBox.information(self, "選択", "削除する動作を選択してください。")
            return
        self.model_about_to_change.emit("機器一覧削除")
        self.model.operations = [op for op in self.model.operations if op.action_uid != action_uid]
        self.model.action_definitions = [a for a in self.model.action_definitions if a.uid != action_uid]
        self._cleanup_orphans()
        self.refresh()
        self.model_changed.emit()

    def _resolve_or_create_hierarchy(self, level: str, existing_value, parent_uid: Optional[int], id_number: int, name: str) -> int:
        if isinstance(existing_value, int):
            item = self.model.get_hierarchy(existing_value)
            if item:
                item.id_number = id_number
                item.name = name
                item.parent_uid = parent_uid
                item.level = level
                return item.uid

        uid = self.model.next_hierarchy_uid()
        self.model.hierarchy_items.append(HierarchyItem(
            uid=uid,
            id_number=id_number,
            name=name,
            level=level,
            parent_uid=parent_uid,
        ))
        return uid

    def _cleanup_orphans(self):
        used_small = {a.small_item_uid for a in self.model.action_definitions}
        self.model.hierarchy_items = [
            x for x in self.model.hierarchy_items
            if x.level != "small" or x.uid in used_small
        ]
        used_middle = {x.parent_uid for x in self.model.hierarchy_items if x.level == "small" and x.parent_uid is not None}
        self.model.hierarchy_items = [
            x for x in self.model.hierarchy_items
            if x.level != "middle" or x.uid in used_middle
        ]
        used_large = {x.parent_uid for x in self.model.hierarchy_items if x.level == "middle" and x.parent_uid is not None}
        self.model.hierarchy_items = [
            x for x in self.model.hierarchy_items
            if x.level != "large" or x.uid in used_large
        ]


class OperationsTab(QWidget):
    model_about_to_change = Signal(str)
    model_changed = Signal()

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self.model = model

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "動作UID", "対象", "設定名", "時間(ms)", "開始トリガ", "依存先動作UID", "開始値", "終了値"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("動作追加")
        self.edit_btn = QPushButton("動作編集")
        self.del_btn = QPushButton("動作削除")
        self.refresh_btn = QPushButton("再表示")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.edit_btn)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.refresh_btn)
        layout.addLayout(btn_row)

        help_box = QGroupBox("設定ルール")
        help_layout = QVBoxLayout(help_box)
        help_layout.addWidget(QLabel(
            "manual: 時刻0から開始\n"
            "after_finish: 指定した動作の完了後に開始\n"
            "after_start: 指定した動作の開始と同時に開始"
        ))
        layout.addWidget(help_box)

        self.add_btn.clicked.connect(self.add_operation)
        self.edit_btn.clicked.connect(self.edit_operation)
        self.del_btn.clicked.connect(self.delete_operation)
        self.refresh_btn.clicked.connect(self.refresh)

        self.refresh()

    def refresh(self):
        ops = sorted(self.model.operations, key=lambda x: x.uid)
        self.table.setRowCount(len(ops))
        for r, op in enumerate(ops):
            dep = "-" if op.trigger_operation_uid is None else str(op.trigger_operation_uid)
            vals = [
                str(op.uid),
                self.model.action_label(op.action_uid),
                op.name,
                str(op.duration_ms),
                op.start_trigger,
                dep,
                op.from_value,
                op.to_value,
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setData(Qt.UserRole, op.uid)
                self.table.setItem(r, c, item)

    def _selected_operation_uid(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def add_operation(self):
        if not self.model.action_definitions:
            QMessageBox.warning(self, "項目不足", "先に機器一覧で動作を作成してください。")
            return
        dlg = OperationDialog(self.model, parent=self)
        if dlg.exec():
            try:
                action_uid, name, duration_ms, start_trigger, dep_uid, from_value, to_value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "時間(ms)は数値で入力してください。")
                return
            if not name:
                QMessageBox.warning(self, "入力不足", "設定名を入力してください。")
                return
            self.model_about_to_change.emit("動作追加")
            self.model.operations.append(OperationInstance(
                uid=self.model.next_operation_uid(),
                action_uid=action_uid,
                name=name,
                duration_ms=duration_ms,
                start_trigger=start_trigger,
                trigger_operation_uid=dep_uid,
                from_value=from_value,
                to_value=to_value,
            ))
            self.refresh()
            self.model_changed.emit()

    def edit_operation(self):
        op_uid = self._selected_operation_uid()
        if op_uid is None:
            return
        op = self.model.get_operation(op_uid)
        if not op:
            return
        dlg = OperationDialog(self.model, operation=op, parent=self)
        if dlg.exec():
            try:
                action_uid, name, duration_ms, start_trigger, dep_uid, from_value, to_value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "時間(ms)は数値で入力してください。")
                return
            self.model_about_to_change.emit("動作編集")
            op.action_uid = action_uid
            op.name = name
            op.duration_ms = duration_ms
            op.start_trigger = start_trigger
            op.trigger_operation_uid = dep_uid
            op.from_value = from_value
            op.to_value = to_value
            self.refresh()
            self.model_changed.emit()

    def delete_operation(self):
        op_uid = self._selected_operation_uid()
        if op_uid is None:
            return
        self.model_about_to_change.emit("動作削除")
        for op in self.model.operations:
            if op.trigger_operation_uid == op_uid:
                op.trigger_operation_uid = None
                op.start_trigger = "manual"
        self.model.operations = [op for op in self.model.operations if op.uid != op_uid]
        self.refresh()
        self.model_changed.emit()


class ChartTab(QWidget):
    model_about_to_change = Signal(str)
    model_changed = Signal()

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self.model = model

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.link_toggle = QPushButton("依存関係リンクモード: OFF")
        self.link_toggle.setCheckable(True)
        self.redraw_btn = QPushButton("チャート再描画")
        self.info_label = QLabel("リンクモードON時: 先に元の動作、次に先の動作をクリック")
        top_row.addWidget(self.link_toggle)
        top_row.addWidget(self.redraw_btn)
        top_row.addWidget(self.info_label)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.chart = TimingChartView()
        layout.addWidget(self.chart)

        self.link_toggle.toggled.connect(self.on_link_mode_toggled)
        self.redraw_btn.clicked.connect(self.refresh)
        self.chart.dependency_created.connect(self.create_dependency_from_chart)

        self.refresh()

    def on_link_mode_toggled(self, checked: bool):
        self.chart.set_link_mode(checked)
        self.link_toggle.setText(f"依存関係リンクモード: {'ON' if checked else 'OFF'}")

    def create_dependency_from_chart(self, source_uid: int, target_uid: int):
        target = self.model.get_operation(target_uid)
        if not target:
            return
        answer = QMessageBox.question(
            self,
            "依存設定",
            f"動作UID {source_uid} → 動作UID {target_uid} の依存を設定しますか？\n"
            "はい: 完了後に開始\n"
            "いいえ: 開始と同時に開始",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )
        if answer == QMessageBox.Cancel:
            return

        self.model_about_to_change.emit("依存関係設定")
        target.trigger_operation_uid = source_uid
        target.start_trigger = "after_finish" if answer == QMessageBox.Yes else "after_start"
        self.refresh()
        self.model_changed.emit()

    def refresh(self):
        self.chart.render_chart(self.model)


# =========================
# Main window
# =========================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("タイミングチャートアプリ MVP")
        self.resize(1550, 920)

        self.model = AppModel()
        self._undo_stack: List[Tuple[str, Dict]] = []
        self._redo_stack: List[Tuple[str, Dict]] = []
        self._history_limit = 100

        self._load_sample_data()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.chart_tab = ChartTab(self.model)
        self.device_tab = DeviceTab(self.model)
        self.ops_tab = OperationsTab(self.model)

        self.tabs.addTab(self.chart_tab, "グラフ")
        self.tabs.addTab(self.device_tab, "機器一覧")
        self.tabs.addTab(self.ops_tab, "動作設定")

        self._wire_model_signals()
        self._build_toolbar()
        self.refresh_all()
        self._reset_history("初期状態")

    def _wire_model_signals(self):
        for tab in (self.device_tab, self.ops_tab, self.chart_tab):
            tab.model_about_to_change.connect(self.push_undo_snapshot)
            tab.model_changed.connect(self.refresh_all)

    def _apply_model_to_tabs(self):
        self.chart_tab.model = self.model
        self.device_tab.model = self.model
        self.ops_tab.model = self.model

    def _build_toolbar(self):
        tb = QToolBar("Main")
        self.addToolBar(tb)

        self.new_action = QAction("新規", self)
        self.save_action = QAction("保存", self)
        self.load_action = QAction("読込", self)
        self.undo_action = QAction("戻る", self)
        self.redo_action = QAction("進む", self)

        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action.setShortcut(QKeySequence.Redo)

        self.new_action.triggered.connect(self.new_project)
        self.save_action.triggered.connect(self.save_project)
        self.load_action.triggered.connect(self.load_project)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action.triggered.connect(self.redo)

        tb.addAction(self.new_action)
        tb.addAction(self.save_action)
        tb.addAction(self.load_action)
        tb.addSeparator()
        tb.addAction(self.undo_action)
        tb.addAction(self.redo_action)

        self.addAction(self.undo_action)
        self.addAction(self.redo_action)
        self._update_history_actions()

    def push_undo_snapshot(self, label: str):
        self._undo_stack.append((label, self.model.clone_data()))
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._update_history_actions()

    def _restore_snapshot(self, snapshot: Dict):
        self.model.from_dict(copy.deepcopy(snapshot))
        self._apply_model_to_tabs()
        self.refresh_all()

    def _reset_history(self, label: str = "初期状態"):
        self._undo_stack = [(label, self.model.clone_data())]
        self._redo_stack = []
        self._update_history_actions()

    def _update_history_actions(self):
        can_undo = len(self._undo_stack) > 1
        can_redo = len(self._redo_stack) > 0
        self.undo_action.setEnabled(can_undo)
        self.redo_action.setEnabled(can_redo)
        self.undo_action.setText(f"戻る ({self._undo_stack[-1][0]})" if can_undo else "戻る")
        self.redo_action.setText(f"進む ({self._redo_stack[-1][0]})" if can_redo else "進む")

    def undo(self):
        if len(self._undo_stack) <= 1:
            return
        current = self._undo_stack.pop()
        self._redo_stack.append(current)
        _, snapshot = self._undo_stack[-1]
        self._restore_snapshot(snapshot)
        self._update_history_actions()

    def redo(self):
        if not self._redo_stack:
            return
        label, snapshot = self._redo_stack.pop()
        self._undo_stack.append((label, copy.deepcopy(snapshot)))
        self._restore_snapshot(snapshot)
        self._update_history_actions()

    def refresh_all(self):
        self._apply_model_to_tabs()
        self.chart_tab.refresh()
        self.device_tab.refresh()
        self.ops_tab.refresh()
        self._update_history_actions()

    def new_project(self):
        self.model = AppModel()
        self._apply_model_to_tabs()
        self.refresh_all()
        self._reset_history("新規プロジェクト")

    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存", "", "JSON (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model.to_dict(), f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "保存", "保存しました。")

    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "読込", "", "JSON (*.json)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.model = AppModel()
        self.model.from_dict(data)
        self._apply_model_to_tabs()
        self.refresh_all()
        self._reset_history("読込後")
        QMessageBox.information(self, "読込", "読み込みました。")

    def _load_sample_data(self):
        large1 = HierarchyItem(uid=1, id_number=1, name="設備A", level="large", parent_uid=None)
        middle1 = HierarchyItem(uid=2, id_number=1, name="搬送ユニット", level="middle", parent_uid=1)
        small1 = HierarchyItem(uid=3, id_number=1, name="Z軸", level="small", parent_uid=2)
        small2 = HierarchyItem(uid=4, id_number=2, name="吸着センサ", level="small", parent_uid=2)
        large2 = HierarchyItem(uid=5, id_number=2, name="設備B", level="large", parent_uid=None)
        middle2 = HierarchyItem(uid=6, id_number=1, name="検査ユニット", level="middle", parent_uid=5)
        small3 = HierarchyItem(uid=7, id_number=1, name="検査シリンダ", level="small", parent_uid=6)

        self.model.hierarchy_items = [large1, middle1, small1, small2, large2, middle2, small3]
        self.model.action_definitions = [
            ActionDefinition(uid=1, small_item_uid=3, action_no=1, name="位置移動", action_type="points", points=["ポイント1", "ポイント2", "ポイント3"]),
            ActionDefinition(uid=2, small_item_uid=4, action_no=1, name="検出", action_type="onoff", points=["OFF", "ON"]),
            ActionDefinition(uid=3, small_item_uid=7, action_no=1, name="前進後退", action_type="points", points=["後退", "中間", "前進"]),
        ]
        self.model.operations = [
            OperationInstance(uid=1, action_uid=1, name="Z軸 上昇", duration_ms=1200, start_trigger="manual", trigger_operation_uid=None, from_value="ポイント1", to_value="ポイント3"),
            OperationInstance(uid=2, action_uid=2, name="吸着ON", duration_ms=300, start_trigger="after_finish", trigger_operation_uid=1, from_value="OFF", to_value="ON"),
            OperationInstance(uid=3, action_uid=3, name="検査前進", duration_ms=900, start_trigger="after_start", trigger_operation_uid=2, from_value="後退", to_value="前進"),
            OperationInstance(uid=4, action_uid=2, name="吸着OFF", duration_ms=300, start_trigger="after_finish", trigger_operation_uid=3, from_value="ON", to_value="OFF"),
        ]


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

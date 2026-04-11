
import copy
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QInputDialog

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QEvent
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
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QStyledItemDelegate,
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
    action_type: str = ""


@dataclass
class ActionDefinition:
    uid: int
    small_item_uid: int
    action_no: int
    name: str
    points: List[str] = field(default_factory=list)


@dataclass
class OperationInstance:
    uid: int
    action_uid: int
    name: str = ""
    duration_ms: int = 0
    operation_mode: str = "ポイント移動"
    time_mode: str = "直値指定"
    start_trigger: str = "時刻0"
    start_operation_uid: Optional[int] = None
    end_mode: str = "直値指定"
    end_trigger: str = "終了"
    end_operation_uid: Optional[int] = None
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
        small_type = small.action_type if small else ""
        return f"{large_part} / {middle_part} / {small_part} / {small_type} / 動作{a.action_no}:{a.name}"

    def point_options_for_small(self, small_uid: int) -> List[str]:
        small = self.get_hierarchy(small_uid)
        if not small:
            return []
        if small.action_type == "onoff":
            return ["ON", "OFF"]
        values = []
        for a in sorted([x for x in self.action_definitions if x.small_item_uid == small_uid], key=lambda x: (x.action_no, x.uid)):
            for p in a.points:
                if p not in values:
                    values.append(p)
        return values


    def normalize_onoff_points(self):
        for small in self.small_items():
            if small.action_type != "onoff":
                continue
            actions = sorted(
                [a for a in self.action_definitions if a.small_item_uid == small.uid],
                key=lambda x: (x.action_no, x.uid)
            )
            if not actions:
                self.action_definitions.append(ActionDefinition(
                    uid=self.next_action_uid(),
                    small_item_uid=small.uid,
                    action_no=1,
                    name="ON",
                    points=["ON", "OFF"],
                ))
                self.action_definitions.append(ActionDefinition(
                    uid=self.next_action_uid(),
                    small_item_uid=small.uid,
                    action_no=2,
                    name="OFF",
                    points=["ON", "OFF"],
                ))
                continue
            first = actions[0]
            first.action_no = 1
            first.name = "ON"
            first.points = ["ON", "OFF"]
            for idx, a in enumerate(actions[1:], start=2):
                a.action_no = idx
                if idx == 2:
                    a.name = "OFF"
                elif a.name in ("ON", "OFF"):
                    a.name = f"追加{idx-2}"
                a.points = ["ON", "OFF"]


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
            self.normalize_onoff_points()
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
            small_item = self.get_hierarchy(small_uid)
            if small_item and not small_item.action_type:
                small_item.action_type = old.get("action_type", "onoff")
            self.action_definitions.append(ActionDefinition(
                uid=uid,
                small_item_uid=small_uid,
                action_no=self.next_action_no(small_uid),
                name=old["name"],
                points=old.get("points", []),
            ))

        for old in old_ops:
            uid = self.next_operation_uid()
            start_trigger = old.get("start_trigger", "manual")
            if start_trigger == "manual":
                start_trigger_new = "時刻0"
            elif start_trigger == "after_start":
                start_trigger_new = "開始"
            else:
                start_trigger_new = "終了"
            self.operations.append(OperationInstance(
                uid=uid,
                action_uid=action_id_map.get(old["action_def_id"]),
                name=old.get("name", ""),
                duration_ms=old.get("duration_ms", 0),
                operation_mode="ポイント移動",
                time_mode="直値指定",
                start_trigger=start_trigger_new,
                start_operation_uid=None,  # set later
                end_mode="直値指定",
                end_trigger="終了",
                end_operation_uid=None,
                from_value=old.get("from_value", ""),
                to_value=old.get("to_value", ""),
            ))

        old_to_new_op: Dict[int, int] = {}
        for old, new in zip(old_ops, self.operations):
            old_to_new_op[old["id"]] = new.uid
        for old, new in zip(old_ops, self.operations):
            trig = old.get("trigger_operation_id")
            new.start_operation_uid = old_to_new_op.get(trig) if trig is not None else None

        self.normalize_onoff_points()

    def clone_data(self) -> Dict:
        return copy.deepcopy(self.to_dict())


# =========================
# Dialogs
# =========================


class HierarchyItemDialog(QDialog):
    def __init__(self, model: AppModel, item: Optional[HierarchyItem] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("機器項目")
        self.model = model
        self.item = item

        self.level_combo = QComboBox()
        self.level_combo.addItems(["large", "middle", "small"])
        self.parent_combo = QComboBox()
        self.id_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.action_type_combo = QComboBox()
        self.action_type_combo.addItems(["", "onoff", "points"])

        form = QFormLayout(self)
        form.addRow("レベル", self.level_combo)
        form.addRow("親項目", self.parent_combo)
        form.addRow("ID", self.id_edit)
        form.addRow("名称", self.name_edit)
        form.addRow("動作種別(小項目のみ)", self.action_type_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.level_combo.currentTextChanged.connect(self._reload_parents)
        self.level_combo.currentTextChanged.connect(self._on_level_changed)

        self._reload_parents()
        self._on_level_changed()

        if item:
            self.level_combo.setCurrentText(item.level)
            self._reload_parents()
            parent_val = "" if item.parent_uid is None else str(item.parent_uid)
            idx = self.parent_combo.findData(parent_val)
            if idx >= 0:
                self.parent_combo.setCurrentIndex(idx)
            self.id_edit.setText(str(item.id_number))
            self.name_edit.setText(item.name)
            self.action_type_combo.setCurrentText(item.action_type or "")
            self._on_level_changed()
        else:
            self.id_edit.setText("1")

    def _reload_parents(self):
        level = self.level_combo.currentText()
        self.parent_combo.clear()
        self.parent_combo.addItem("-", "")
        if level == "large":
            return
        parent_level = "large" if level == "middle" else "middle"
        for x in sorted([h for h in self.model.hierarchy_items if h.level == parent_level], key=lambda x: (x.id_number, x.uid)):
            self.parent_combo.addItem(f"{x.id_number} {x.name}", str(x.uid))

    def _on_level_changed(self):
        is_small = self.level_combo.currentText() == "small"
        self.action_type_combo.setEnabled(is_small)
        if not is_small:
            self.action_type_combo.setCurrentText("")

    def get_value(self):
        raw_parent = self.parent_combo.currentData()
        parent_uid = int(raw_parent) if raw_parent not in ("", None) else None
        return {
            "level": self.level_combo.currentText(),
            "parent_uid": parent_uid,
            "id_number": int(self.id_edit.text().strip()),
            "name": self.name_edit.text().strip(),
            "action_type": self.action_type_combo.currentText().strip(),
        }


class ActionDefinitionDialog(QDialog):
    def __init__(self, model: AppModel, action_def: Optional[ActionDefinition] = None, fixed_small_uid: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ポイント")
        self.model = model
        self.action_def = action_def

        self.small_combo = QComboBox()
        small_items = sorted(
            [x for x in self.model.small_items()],
            key=lambda x: (
                (self.model.get_large_for_small(x.uid).id_number if self.model.get_large_for_small(x.uid) else 0),
                (self.model.get_middle_for_small(x.uid).id_number if self.model.get_middle_for_small(x.uid) else 0),
                x.id_number, x.uid
            )
        )
        for s in small_items:
            self.small_combo.addItem(self.model.hierarchy_path(s.uid), s.uid)

        self.action_no_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.points_edit = QLineEdit()
        self.points_hint = QLabel("points の場合のみ。例: 原点, 待機, 加工")

        form = QFormLayout(self)
        form.addRow("対象小項目", self.small_combo)
        form.addRow("ポイント番号", self.action_no_edit)
        form.addRow("ポイント", self.name_edit)
        form.addRow("ポイント一覧", self.points_edit)
        form.addRow("", self.points_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.small_combo.currentIndexChanged.connect(self._reload_points_hint)

        if fixed_small_uid is not None:
            idx = self.small_combo.findData(fixed_small_uid)
            if idx >= 0:
                self.small_combo.setCurrentIndex(idx)

        if action_def:
            idx = self.small_combo.findData(action_def.small_item_uid)
            if idx >= 0:
                self.small_combo.setCurrentIndex(idx)
            self.action_no_edit.setText(str(action_def.action_no))
            self.name_edit.setText(action_def.name)
            self.points_edit.setText(", ".join(action_def.points))
        else:
            small_uid = self.small_combo.currentData()
            self.action_no_edit.setText(str(self.model.next_action_no(int(small_uid)) if small_uid is not None else 1))

        self._reload_points_hint()

    def _reload_points_hint(self):
        small_uid = self.small_combo.currentData()
        small = self.model.get_hierarchy(int(small_uid)) if small_uid is not None else None
        is_points = bool(small and small.action_type == "points")
        self.points_edit.setEnabled(True)
        self.points_hint.setEnabled(True)
        if small and small.action_type == "onoff":
            self.points_edit.setText("ON, OFF")
            self.points_hint.setText("onoff の場合は 1:ON, 2:OFF に固定です。")
        else:
            self.points_hint.setText("points の場合のみ。例: 原点, 待機, 加工")

    def get_value(self):
        small_uid = int(self.small_combo.currentData())
        small = self.model.get_hierarchy(small_uid)
        raw_points = [x.strip() for x in self.points_edit.text().split(",") if x.strip()]
        if small and small.action_type == "onoff":
            points = ["ON", "OFF"]
        else:
            points = raw_points
        return {
            "small_item_uid": small_uid,
            "action_no": int(self.action_no_edit.text().strip()),
            "name": self.name_edit.text().strip(),
            "points": points,
        }




class OperationDialog(QDialog):
    def __init__(self, model: AppModel, operation: Optional[OperationInstance] = None, parent=None, default_uid: Optional[int] = None):
        super().__init__(parent)
        self.setWindowTitle("動作設定")
        self.model = model
        self.operation = operation

        self.uid_edit = QLineEdit(str(operation.uid if operation else (default_uid if default_uid is not None else self.model.next_operation_uid())))
        self.large_combo = QComboBox()
        self.middle_combo = QComboBox()
        self.small_combo = QComboBox()
        self.from_combo = QComboBox()
        self.to_combo = QComboBox()

        self.start_trigger_combo = QComboBox()
        self.start_trigger_combo.addItems(["時刻0", "開始", "終了"])
        self.start_dep_combo = QComboBox()
        self.start_dep_combo.setEditable(True)

        self.end_mode_combo = QComboBox()
        self.end_mode_combo.addItems(["直値指定", "トリガ指定"])
        self.end_trigger_combo = QComboBox()
        self.end_trigger_combo.addItems(["時刻0", "開始", "終了"])
        self.end_dep_combo = QComboBox()
        self.end_dep_combo.setEditable(True)

        self.duration_edit = QLineEdit(str(operation.duration_ms if operation else 1000))

        self._load_large()
        self._load_operation_refs()

        form = QFormLayout(self)
        form.addRow("動作UID", self.uid_edit)
        form.addRow("大項目", self.large_combo)
        form.addRow("中項目", self.middle_combo)
        form.addRow("小項目", self.small_combo)
        form.addRow("開始ポイント", self.from_combo)
        form.addRow("終了ポイント", self.to_combo)
        form.addRow("開始トリガ", self.start_trigger_combo)
        form.addRow("開始依存元動作UID", self.start_dep_combo)
        form.addRow("終了設定", self.end_mode_combo)
        form.addRow("終了トリガ", self.end_trigger_combo)
        form.addRow("終了依存元動作UID", self.end_dep_combo)
        form.addRow("時間(ms)", self.duration_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.large_combo.currentIndexChanged.connect(self._load_middle)
        self.middle_combo.currentIndexChanged.connect(self._load_small)
        self.small_combo.currentIndexChanged.connect(self._reload_points)
        self.start_trigger_combo.currentTextChanged.connect(self._refresh_dep_enabled)
        self.end_mode_combo.currentTextChanged.connect(self._refresh_dep_enabled)
        self.end_trigger_combo.currentTextChanged.connect(self._refresh_dep_enabled)

        self._load_middle()
        self._load_small()
        self._reload_points()
        self._refresh_dep_enabled()

        if operation:
            action = self.model.get_action_def(operation.action_uid)
            if action:
                small = self.model.get_hierarchy(action.small_item_uid)
                middle = self.model.get_middle_for_small(action.small_item_uid)
                large = self.model.get_large_for_small(action.small_item_uid)
                if large:
                    idx = self.large_combo.findData(large.uid)
                    if idx >= 0:
                        self.large_combo.setCurrentIndex(idx)
                self._load_middle()
                if middle:
                    idx = self.middle_combo.findData(middle.uid)
                    if idx >= 0:
                        self.middle_combo.setCurrentIndex(idx)
                self._load_small()
                if small:
                    idx = self.small_combo.findData(small.uid)
                    if idx >= 0:
                        self.small_combo.setCurrentIndex(idx)
            self.duration_edit.setText(str(operation.duration_ms))
            self.start_trigger_combo.setCurrentText(operation.start_trigger or "時刻0")
            self.start_dep_combo.setEditText("" if operation.start_operation_uid is None else str(operation.start_operation_uid))
            self.end_mode_combo.setCurrentText(operation.end_mode or "直値指定")
            self.end_trigger_combo.setCurrentText(operation.end_trigger or "終了")
            self.end_dep_combo.setEditText("" if operation.end_operation_uid is None else str(operation.end_operation_uid))
            self._reload_points()
            fidx = self.from_combo.findData(operation.from_value)
            if fidx >= 0:
                self.from_combo.setCurrentIndex(fidx)
            tidx = self.to_combo.findData(operation.to_value)
            if tidx >= 0:
                self.to_combo.setCurrentIndex(tidx)

    def _load_large(self):
        self.large_combo.clear()
        for x in sorted(self.model.children_of(None, "large"), key=lambda x: (x.id_number, x.uid)):
            self.large_combo.addItem(f"{x.id_number} {x.name}", x.uid)

    def _load_middle(self):
        self.middle_combo.clear()
        large_uid = self.large_combo.currentData()
        for x in sorted(self.model.children_of(large_uid, "middle"), key=lambda x: (x.id_number, x.uid)):
            self.middle_combo.addItem(f"{x.id_number} {x.name}", x.uid)

    def _load_small(self):
        self.small_combo.clear()
        middle_uid = self.middle_combo.currentData()
        for x in sorted(self.model.children_of(middle_uid, "small"), key=lambda x: (x.id_number, x.uid)):
            self.small_combo.addItem(f"{x.id_number} {x.name}", x.uid)
        self._reload_points()

    def _load_operation_refs(self):
        self.start_dep_combo.clear()
        self.end_dep_combo.clear()
        self.start_dep_combo.addItem("", "")
        self.end_dep_combo.addItem("", "")
        for op in sorted(self.model.operations, key=lambda x: x.uid):
            if self.operation and op.uid == self.operation.uid:
                continue
            label = f"{op.uid}"
            self.start_dep_combo.addItem(label, str(op.uid))
            self.end_dep_combo.addItem(label, str(op.uid))

    def _reload_points(self):
        self.from_combo.clear()
        self.to_combo.clear()
        small_uid = self.small_combo.currentData()
        if small_uid is None:
            return
        vals = self.model.point_options_for_small(int(small_uid))
        for i, val in enumerate(vals, start=1):
            label = f"{i}:{val}"
            self.from_combo.addItem(label, val)
            self.to_combo.addItem(label, val)
        if vals:
            self.from_combo.setCurrentIndex(0)
            self.to_combo.setCurrentIndex(min(1, len(vals) - 1))

    def _refresh_dep_enabled(self):
        self.start_dep_combo.setEnabled(self.start_trigger_combo.currentText() != "時刻0")
        trig_end = self.end_mode_combo.currentText() == "トリガ指定"
        self.end_trigger_combo.setEnabled(trig_end)
        self.end_dep_combo.setEnabled(trig_end and self.end_trigger_combo.currentText() != "時刻0")
        self.duration_edit.setEnabled(not trig_end)

    def _parse_uid_text(self, text: str) -> Optional[int]:
        text = (text or "").strip()
        if text == "":
            return None
        return int(text)

    def get_value(self):
        small_uid = int(self.small_combo.currentData())
        actions = sorted([a for a in self.model.action_definitions if a.small_item_uid == small_uid], key=lambda x: (x.action_no, x.uid))
        action_uid = actions[0].uid if actions else None
        small = self.model.get_hierarchy(small_uid)
        operation_mode = "ON-OFF" if (small and small.action_type == "onoff") else "ポイント移動"
        return {
            "uid": int(self.uid_edit.text().strip()),
            "action_uid": action_uid,
            "operation_mode": operation_mode,
            "time_mode": "直値指定",
            "duration_ms": int(self.duration_edit.text().strip() or "0"),
            "start_trigger": self.start_trigger_combo.currentText(),
            "start_operation_uid": self._parse_uid_text(self.start_dep_combo.currentText()),
            "end_mode": self.end_mode_combo.currentText(),
            "end_trigger": self.end_trigger_combo.currentText(),
            "end_operation_uid": self._parse_uid_text(self.end_dep_combo.currentText()),
            "from_value": self.from_combo.currentData(),
            "to_value": self.to_combo.currentData(),
        }


# =========================
# Schedule calculation
# =========================


def calculate_schedule(model: AppModel) -> Tuple[Dict[int, Tuple[int, int]], List[str]]:
    ops = {op.uid: op for op in model.operations}
    errors = []
    visiting = set()
    visited = set()

    def deps_of(op):
        deps = []
        if op.start_trigger != "時刻0" and op.start_operation_uid in ops:
            deps.append(op.start_operation_uid)
        if op.end_mode == "トリガ指定" and op.end_trigger != "時刻0" and op.end_operation_uid in ops:
            deps.append(op.end_operation_uid)
        return deps

    def dfs(op_uid: int):
        if op_uid in visiting:
            raise ValueError(f"循環依存があります: 動作UID {op_uid}")
        if op_uid in visited:
            return
        visiting.add(op_uid)
        op = ops[op_uid]
        for dep in deps_of(op):
            dfs(dep)
        visiting.remove(op_uid)
        visited.add(op_uid)

    try:
        for op_uid in ops:
            dfs(op_uid)
    except ValueError as e:
        return {}, [str(e)]

    memo: Dict[int, Tuple[int, int]] = {}

    def anchor_time(ref_uid: Optional[int], trig: str) -> Optional[int]:
        if trig == "時刻0":
            return 0
        if ref_uid is None:
            return None
        ref = ops.get(ref_uid)
        if ref is None:
            return None
        s, e = calc(ref.uid)
        return s if trig == "開始" else e

    def calc(op_uid: int) -> Tuple[int, int]:
        if op_uid in memo:
            return memo[op_uid]
        op = ops[op_uid]
        start = anchor_time(op.start_operation_uid, op.start_trigger)
        if start is None:
            errors.append(f"動作UID {op.uid}: 開始依存元 {op.start_operation_uid} が見つかりません")
            start = 0

        if op.end_mode == "トリガ指定":
            end = anchor_time(op.end_operation_uid, op.end_trigger)
            if end is None:
                errors.append(f"動作UID {op.uid}: 終了依存元 {op.end_operation_uid} が見つかりません")
                end = start + max(0, op.duration_ms)
        else:
            end = start + max(0, op.duration_ms)

        if end < start:
            end = start

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

        self.setMinimumSize(1500, 820)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

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
            y = 24
            scene.setSceneRect(0, 0, 1800, 900)
            scene.addRect(0, 0, 1800, 900, QPen(QColor(210, 215, 220)), QBrush(QColor(250, 251, 252)))
            title = scene.addSimpleText("ERROR")
            title.setPos(20, y)
            y += 34
            for e in errors:
                txt = scene.addSimpleText(f"- {e}")
                txt.setPos(20, y)
                y += 24
            hint = scene.addSimpleText("Ctrl+Z で元に戻す / Ctrl+Y でやり直し")
            hint.setPos(20, y + 12)
            return

        row_h = 108
        header_h = 76

        col_large = 90
        col_middle = 120
        col_small = 200
        col_points = 150
        left_w = col_large + col_middle + col_small + col_points

        time_scale = 0.16
        max_time = max([end for _, end in schedule.values()], default=3000)
        graph_w = max(1800, int(max_time * time_scale) + 500)
        total_w = left_w + graph_w
        total_h = max(920, header_h + max(1, len(model.small_items())) * row_h + 120)
        scene.setSceneRect(0, 0, total_w, total_h)

        # Region backgrounds
        scene.addRect(0, 0, left_w, total_h, QPen(QColor(205, 210, 216)), QBrush(QColor(245, 247, 249)))
        scene.addRect(left_w, 0, graph_w, total_h, QPen(QColor(210, 214, 220)), QBrush(QColor(255, 255, 255)))
        scene.addRect(0, 0, total_w, header_h, QPen(QColor(200, 205, 212)), QBrush(QColor(236, 240, 244)))

        x_large = col_large
        x_middle = col_large + col_middle
        x_small = col_large + col_middle + col_small
        scene.addLine(x_large, 0, x_large, total_h, QPen(QColor(210, 214, 220), 1))
        scene.addLine(x_middle, 0, x_middle, total_h, QPen(QColor(210, 214, 220), 1))
        scene.addLine(x_small, 0, x_small, total_h, QPen(QColor(210, 214, 220), 1))
        scene.addLine(left_w, 0, left_w, total_h, QPen(QColor(110, 120, 135), 2))

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

        # Header labels
        scene.addSimpleText("大項目").setPos(12, 18)
        scene.addSimpleText("中項目").setPos(col_large + 12, 18)
        scene.addSimpleText("小項目").setPos(col_large + col_middle + 12, 18)
        scene.addSimpleText("ポイント").setPos(col_large + col_middle + col_small + 12, 18)

        # Left rows / labels
        for s in smalls:
            row = row_map[s.uid]
            top = header_h + row * row_h
            left_bg = QColor(250, 251, 252) if row % 2 == 0 else QColor(243, 246, 248)
            graph_bg = QColor(252, 253, 254) if row % 2 == 0 else QColor(248, 250, 252)
            scene.addRect(0, top, left_w, row_h, QPen(QColor(220, 225, 230)), QBrush(left_bg))
            scene.addRect(left_w, top, graph_w, row_h, QPen(QColor(232, 236, 240)), QBrush(graph_bg))
            scene.addLine(0, top + row_h, total_w, top + row_h, QPen(QColor(224, 228, 233), 1))

            large = model.get_large_for_small(s.uid)
            middle = model.get_middle_for_small(s.uid)

            scene.addSimpleText(f"{large.id_number} {large.name}" if large else "").setPos(10, top + 14)
            scene.addSimpleText(f"{middle.id_number} {middle.name}" if middle else "").setPos(col_large + 10, top + 14)
            scene.addSimpleText(f"{s.id_number} {s.name}").setPos(col_large + col_middle + 10, top + 14)

            point_values = model.point_options_for_small(s.uid)
            n = max(1, len(point_values) - 1)
            for i, p in enumerate(point_values):
                py = top + 18 + (row_h - 36) * (i / max(1, n))
                scene.addSimpleText(f"{i+1}:{p}").setPos(col_large + col_middle + col_small + 10, py - 8)

        # Time ruler and grid
        minor_step = 100
        major_step = 500
        t = 0
        while t <= max_time + 1500:
            x = left_w + t * time_scale
            if t % major_step == 0:
                pen = QPen(QColor(186, 191, 198), 1)
                scene.addLine(x, header_h, x, total_h - 28, pen)
                txt = scene.addSimpleText(f"{t} ms")
                txt.setPos(x + 4, 8)
                tick_h = 18
            else:
                pen = QPen(QColor(222, 226, 231), 1)
                pen.setStyle(Qt.DotLine)
                scene.addLine(x, header_h, x, total_h - 28, pen)
                tick_h = 10
            scene.addLine(x, header_h - tick_h, x, header_h, QPen(QColor(150, 156, 165), 1))
            t += minor_step

        op_anchor: Dict[int, Dict[str, QPointF]] = {}

        for op in sorted(model.operations, key=lambda x: x.uid):
            action_def = model.get_action_def(op.action_uid)
            if not action_def:
                continue
            small_uid = action_def.small_item_uid
            row = row_map.get(small_uid)
            if row is None:
                continue

            start_time, end_time = schedule.get(op.uid, (0, 0))
            top = header_h + row * row_h
            x1 = left_w + start_time * time_scale
            x2 = left_w + end_time * time_scale

            point_values = model.point_options_for_small(small_uid)
            index_map = {p: i for i, p in enumerate(point_values)} if point_values else {}
            n = max(1, len(point_values) - 1)

            small_item = model.get_hierarchy(action_def.small_item_uid)
            if small_item and small_item.action_type == "onoff":
                y1 = top + 18 + (row_h - 36) * (0 if op.from_value == "ON" else 1)
                y2 = top + 18 + (row_h - 36) * (0 if op.to_value == "ON" else 1)
                pen = QPen(QColor(28, 124, 84), 3)
                scene.addLine(x1, y1, x2, y2, pen)
                if y1 != y2:
                    scene.addLine(x1, y1, x1, y2, pen)
                hit_rect = QRectF(min(x1, x2), min(y1, y2) - 12, max(24, abs(x2 - x1)), abs(y2 - y1) + 24)
            else:
                f_idx = index_map.get(op.from_value, 0)
                t_idx = index_map.get(op.to_value, f_idx)
                y1 = top + 18 + (row_h - 36) * (f_idx / max(1, n))
                y2 = top + 18 + (row_h - 36) * (t_idx / max(1, n))
                pen = QPen(QColor(45, 92, 191), 3)
                scene.addLine(x1, y1, x2, y2, pen)
                hit_rect = QRectF(min(x1, x2) - 8, min(y1, y2) - 12, max(24, abs(x2 - x1) + 16), abs(y2 - y1) + 24)

                for p, i in index_map.items():
                    py = top + 18 + (row_h - 36) * (i / max(1, n))
                    scene.addLine(left_w - 8, py, left_w, py, QPen(QColor(140, 140, 140)))

            hit = SelectableOpRect(hit_rect, op.uid, self._on_operation_clicked)
            hit.setBrush(QBrush(QColor(0, 0, 0, 1)))
            hit.setPen(QPen(QColor(0, 0, 0, 0)))
            scene.addItem(hit)

            caption = scene.addSimpleText(f"OP{op.uid}")
            caption.setPos(x1 + 6, top + 8)
            op_anchor[op.uid] = {"start": QPointF(x1, y1), "end": QPointF(x2, y2)}

        for op in model.operations:
            if op.start_operation_uid is None:
                continue
            if op.start_operation_uid not in op_anchor or op.uid not in op_anchor:
                continue

            src_key = "end" if op.start_trigger == "終了" else "start"
            p1 = op_anchor[op.start_operation_uid][src_key]
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


class ClearSelectionTreeWidget(QTreeWidget):
    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        current = self.currentItem()
        if item is None or item == current:
            self.clearSelection()
            self.setCurrentItem(None)
            event.accept()
            return
        super().mousePressEvent(event)


class DeviceTab(QWidget):
    model_about_to_change = Signal(str)
    model_changed = Signal()

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self.model = model

        layout = QVBoxLayout(self)

        self.tree = ClearSelectionTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["項目", "動作種別", "ポイント"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Interactive)
        self.tree.setColumnWidth(0, 420)
        self.tree.setColumnWidth(1, 120)
        self.tree.setColumnWidth(2, 360)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

        note = QLabel("※ 大項目 → 中項目 → 小項目の階層で表示します。ポイントは小項目に紐づいて右側に表示します。")
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        self.add_device_btn = QPushButton("機器追加")
        self.edit_device_btn = QPushButton("機器編集")
        self.del_device_btn = QPushButton("機器削除")
        self.add_action_btn = QPushButton("ポイント追加")
        self.edit_action_btn = QPushButton("ポイント編集")
        self.del_action_btn = QPushButton("ポイント削除")
        btn_row.addWidget(self.add_device_btn)
        btn_row.addWidget(self.edit_device_btn)
        btn_row.addWidget(self.del_device_btn)
        btn_row.addSpacing(16)
        btn_row.addWidget(self.add_action_btn)
        btn_row.addWidget(self.edit_action_btn)
        btn_row.addWidget(self.del_action_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.add_device_btn.clicked.connect(self.add_device)
        self.edit_device_btn.clicked.connect(self.edit_device)
        self.del_device_btn.clicked.connect(self.delete_device)
        self.add_action_btn.clicked.connect(self.add_action)
        self.edit_action_btn.clicked.connect(self.edit_action)
        self.del_action_btn.clicked.connect(self.delete_action)

        self.refresh()

    def refresh(self):
        self.tree.clear()
        large_items = sorted(self.model.children_of(None, "large"), key=lambda x: (x.id_number, x.uid))
        for large in large_items:
            large_item = QTreeWidgetItem([f"{large.id_number} {large.name}", "", ""])
            large_item.setData(0, Qt.UserRole, ("hierarchy", large.uid))
            self.tree.addTopLevelItem(large_item)

            middle_items = sorted(self.model.children_of(large.uid, "middle"), key=lambda x: (x.id_number, x.uid))
            for middle in middle_items:
                middle_item = QTreeWidgetItem([f"{middle.id_number} {middle.name}", "", ""])
                middle_item.setData(0, Qt.UserRole, ("hierarchy", middle.uid))
                large_item.addChild(middle_item)

                small_items = sorted(self.model.children_of(middle.uid, "small"), key=lambda x: (x.id_number, x.uid))
                for small in small_items:
                    actions = sorted([a for a in self.model.action_definitions if a.small_item_uid == small.uid], key=lambda x: (x.action_no, x.uid))
                    action_text = "\n".join([f"{a.action_no} / {a.name}" for a in actions])
                    small_item = QTreeWidgetItem([f"{small.id_number} {small.name}", small.action_type or "", action_text])
                    small_item.setData(0, Qt.UserRole, ("hierarchy", small.uid))
                    middle_item.addChild(small_item)

        self.tree.expandToDepth(2)

    def _current_item_data(self):
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def _selected_hierarchy_uid(self) -> Optional[int]:
        data = self._current_item_data()
        if not data or data[0] != "hierarchy":
            return None
        return data[1]

    def _selected_small_uid(self) -> Optional[int]:
        uid = self._selected_hierarchy_uid()
        if uid is None:
            return None
        item = self.model.get_hierarchy(uid)
        return uid if item and item.level == "small" else None

    def _choose_action_for_small(self, small_uid: int) -> Optional[int]:
        actions = sorted([a for a in self.model.action_definitions if a.small_item_uid == small_uid], key=lambda x: (x.action_no, x.uid))
        if not actions:
            QMessageBox.information(self, "ポイントなし", "この小項目にはポイントがありません。")
            return None
        if len(actions) == 1:
            return actions[0].uid
        labels = [f"{a.action_no} / {a.name}" for a in actions]
        selected, ok = QInputDialog.getItem(self, "ポイント選択", "対象ポイントを選択してください", labels, 0, False)
        if not ok:
            return None
        return actions[labels.index(selected)].uid

    def add_device(self):
        dlg = HierarchyItemDialog(self.model, parent=self)
        if dlg.exec():
            try:
                value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "IDは数値で入力してください。")
                return
            if not value["name"]:
                QMessageBox.warning(self, "入力不足", "名称を入力してください。")
                return
            if value["level"] != "large" and value["parent_uid"] is None:
                QMessageBox.warning(self, "入力不足", "親項目を選択してください。")
                return
            if value["level"] == "small" and not value["action_type"]:
                QMessageBox.warning(self, "入力不足", "小項目には動作種別を設定してください。")
                return

            self.model_about_to_change.emit("機器追加")
            new_uid = self.model.next_hierarchy_uid()
            self.model.hierarchy_items.append(HierarchyItem(
                uid=new_uid,
                id_number=value["id_number"],
                name=value["name"],
                level=value["level"],
                parent_uid=value["parent_uid"],
                action_type=value["action_type"],
            ))
            if value["level"] == "small" and value["action_type"] == "onoff":
                self._initialize_onoff_points(new_uid)
            self.refresh()
            self.model_changed.emit()

    def edit_device(self):
        uid = self._selected_hierarchy_uid()
        if uid is None:
            QMessageBox.information(self, "選択", "編集する機器項目を選択してください。")
            return
        item = self.model.get_hierarchy(uid)
        if not item:
            return
        dlg = HierarchyItemDialog(self.model, item=item, parent=self)
        if dlg.exec():
            try:
                value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "IDは数値で入力してください。")
                return
            if not value["name"]:
                QMessageBox.warning(self, "入力不足", "名称を入力してください。")
                return
            if value["level"] != "large" and value["parent_uid"] is None:
                QMessageBox.warning(self, "入力不足", "親項目を選択してください。")
                return
            if value["level"] == "small" and not value["action_type"]:
                QMessageBox.warning(self, "入力不足", "小項目には動作種別を設定してください。")
                return

            self.model_about_to_change.emit("機器編集")
            item.id_number = value["id_number"]
            item.name = value["name"]
            item.level = value["level"]
            item.parent_uid = value["parent_uid"]
            item.action_type = value["action_type"]
            if item.level == "small" and item.action_type == "onoff":
                self._initialize_onoff_points(item.uid)
            self.refresh()
            self.model_changed.emit()

    def delete_device(self):
        uid = self._selected_hierarchy_uid()
        if uid is None:
            QMessageBox.information(self, "選択", "削除する機器項目を選択してください。")
            return

        descendants = set()
        stack = [uid]
        while stack:
            cur = stack.pop()
            descendants.add(cur)
            stack.extend([x.uid for x in self.model.children_of(cur)])

        related_action_uids = [a.uid for a in self.model.action_definitions if a.small_item_uid in descendants]
        self.model_about_to_change.emit("機器削除")
        self.model.operations = [op for op in self.model.operations if op.action_uid not in related_action_uids]
        self.model.action_definitions = [a for a in self.model.action_definitions if a.small_item_uid not in descendants]
        self.model.hierarchy_items = [h for h in self.model.hierarchy_items if h.uid not in descendants]
        self.refresh()
        self.model_changed.emit()


    def _initialize_onoff_points(self, small_uid: int):
        actions = sorted(
            [a for a in self.model.action_definitions if a.small_item_uid == small_uid],
            key=lambda x: (x.action_no, x.uid)
        )
        if not actions:
            self.model.action_definitions.append(ActionDefinition(
                uid=self.model.next_action_uid(),
                small_item_uid=small_uid,
                action_no=1,
                name="ON",
                points=["ON", "OFF"],
            ))
            self.model.action_definitions.append(ActionDefinition(
                uid=self.model.next_action_uid(),
                small_item_uid=small_uid,
                action_no=2,
                name="OFF",
                points=["ON", "OFF"],
            ))
            return
        first = actions[0]
        first.action_no = 1
        first.name = "ON"
        first.points = ["ON", "OFF"]
        for idx, a in enumerate(actions[1:], start=2):
            a.action_no = idx
            if idx == 2:
                a.name = "OFF"
            elif a.name in ("ON", "OFF"):
                a.name = f"追加{idx-2}"
            a.points = ["ON", "OFF"]

    def add_action(self):
        small_uid = self._selected_small_uid()
        if small_uid is None:
            QMessageBox.information(self, "選択", "ポイント追加は小項目を選択して実行してください。")
            return
        dlg = ActionDefinitionDialog(self.model, fixed_small_uid=small_uid, parent=self)
        if dlg.exec():
            try:
                value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "ポイント番号は数値で入力してください。")
                return
            if not value["name"]:
                QMessageBox.warning(self, "入力不足", "ポイント名を入力してください。")
                return
            self.model_about_to_change.emit("ポイント追加")
            self.model.action_definitions.append(ActionDefinition(
                uid=self.model.next_action_uid(),
                small_item_uid=value["small_item_uid"],
                action_no=value["action_no"],
                name=value["name"],
                points=value["points"],
            ))
            self.model.normalize_onoff_points()
            self.refresh()
            self.model_changed.emit()

    def edit_action(self):
        small_uid = self._selected_small_uid()
        if small_uid is None:
            QMessageBox.information(self, "選択", "ポイント編集は小項目を選択して実行してください。")
            return
        action_uid = self._choose_action_for_small(small_uid)
        if action_uid is None:
            return
        action = self.model.get_action_def(action_uid)
        if not action:
            return
        dlg = ActionDefinitionDialog(self.model, action_def=action, fixed_small_uid=small_uid, parent=self)
        if dlg.exec():
            try:
                value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "ポイント番号は数値で入力してください。")
                return
            if not value["name"]:
                QMessageBox.warning(self, "入力不足", "ポイント名を入力してください。")
                return
            self.model_about_to_change.emit("ポイント編集")
            action.small_item_uid = value["small_item_uid"]
            action.action_no = value["action_no"]
            action.name = value["name"]
            action.points = value["points"]
            self.model.normalize_onoff_points()
            self.refresh()
            self.model_changed.emit()

    def delete_action(self):
        small_uid = self._selected_small_uid()
        if small_uid is None:
            QMessageBox.information(self, "選択", "ポイント削除は小項目を選択して実行してください。")
            return
        action_uid = self._choose_action_for_small(small_uid)
        if action_uid is None:
            return
        self.model_about_to_change.emit("ポイント削除")
        self.model.operations = [op for op in self.model.operations if op.action_uid != action_uid]
        self.model.action_definitions = [a for a in self.model.action_definitions if a.uid != action_uid]
        self.refresh()
        self.model_changed.emit()




class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            return int(self.text()) < int(other.text())
        except Exception:
            return super().__lt__(other)


class OperationsTab(QWidget):
    model_about_to_change = Signal(str)
    model_changed = Signal()

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self.model = model

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels([
            "No", "動作UID", "大項目", "中項目", "小項目", "開始ポイント", "終了ポイント",
            "開始トリガ", "開始依存元動作UID", "終了設定", "終了トリガ", "終了依存元動作UID", "時間(ms)"
        ])
        for i in range(13):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Interactive)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
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

        self.add_btn.clicked.connect(self.add_operation)
        self.edit_btn.clicked.connect(self.edit_operation)
        self.del_btn.clicked.connect(self.delete_operation)
        self.refresh_btn.clicked.connect(self.refresh)
        self.table.itemDoubleClicked.connect(lambda _: self.edit_operation())
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self._renumber_no_column())

        self.refresh()

    def refresh(self):
        current_uid = self._selected_operation_uid()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.model.operations))
        for r, op in enumerate(self.model.operations):
            action = self.model.get_action_def(op.action_uid)
            small = self.model.get_hierarchy(action.small_item_uid) if action else None
            middle = self.model.get_middle_for_small(action.small_item_uid) if action else None
            large = self.model.get_large_for_small(action.small_item_uid) if action else None
            point_options = self.model.point_options_for_small(action.small_item_uid) if action else []

            def point_label(value: str) -> str:
                if not value:
                    return ""
                try:
                    idx = point_options.index(value) + 1
                    return f"{idx}:{value}"
                except ValueError:
                    return value

            vals = [
                str(r + 1),
                str(op.uid),
                f"{large.id_number} {large.name}" if large else "",
                f"{middle.id_number} {middle.name}" if middle else "",
                f"{small.id_number} {small.name}" if small else "",
                point_label(op.from_value),
                point_label(op.to_value),
                op.start_trigger,
                "-" if op.start_operation_uid is None else str(op.start_operation_uid),
                op.end_mode,
                op.end_trigger if op.end_mode == "トリガ指定" else "-",
                "-" if op.end_operation_uid is None else str(op.end_operation_uid),
                str(op.duration_ms),
            ]
            for c, v in enumerate(vals):
                numeric_cols = {0, 1, 8, 11, 12}
                item = NumericTableWidgetItem(v) if c in numeric_cols and v not in ("", "-") else QTableWidgetItem(v)
                item.setData(Qt.UserRole, op.uid)
                self.table.setItem(r, c, item)

        self.table.setSortingEnabled(True)
        self.table.sortItems(1, Qt.AscendingOrder)
        self._renumber_no_column()
        if current_uid is not None:
            self._select_operation_uid(current_uid)

    def _renumber_no_column(self):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is None:
                item = NumericTableWidgetItem(str(r + 1))
                self.table.setItem(r, 0, item)
            else:
                item.setText(str(r + 1))

    def _select_operation_uid(self, op_uid: int):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            if item and item.data(Qt.UserRole) == op_uid:
                self.table.selectRow(r)
                break

    def _selected_operation_uid(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1)
        return item.data(Qt.UserRole) if item else None

    def _uid_exists(self, uid: int, exclude_uid: Optional[int] = None) -> bool:
        return any(op.uid == uid and op.uid != exclude_uid for op in self.model.operations)

    def _unused_operation_uid(self) -> int:
        used = {op.uid for op in self.model.operations}
        uid = 1
        while uid in used:
            uid += 1
        return uid

    def add_operation(self):
        if not self.model.small_items():
            QMessageBox.warning(self, "項目不足", "先に機器一覧で小項目とポイントを設定してください。")
            return

        selected_uid = self._selected_operation_uid()
        dlg = OperationDialog(self.model, parent=self, default_uid=self._unused_operation_uid())
        if dlg.exec():
            try:
                value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "動作UID / 依存元UID / 時間(ms) は数値で入力してください。")
                return
            if value["action_uid"] is None:
                QMessageBox.warning(self, "入力不足", "対象小項目にポイントが必要です。")
                return
            if self._uid_exists(value["uid"]):
                QMessageBox.warning(self, "UID重複", f"動作UID {value['uid']} はすでに存在します。")
                return

            self.model_about_to_change.emit("動作追加")
            new_op = OperationInstance(
                uid=value["uid"],
                action_uid=value["action_uid"],
                operation_mode=value["operation_mode"],
                time_mode=value["time_mode"],
                duration_ms=value["duration_ms"],
                start_trigger=value["start_trigger"],
                start_operation_uid=value["start_operation_uid"],
                end_mode=value["end_mode"],
                end_trigger=value["end_trigger"],
                end_operation_uid=value["end_operation_uid"],
                from_value=value["from_value"],
                to_value=value["to_value"],
            )

            if selected_uid is None:
                self.model.operations.append(new_op)
            else:
                insert_idx = next((i for i, op in enumerate(self.model.operations) if op.uid == selected_uid), len(self.model.operations))
                self.model.operations.insert(insert_idx + 1, new_op)

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
                value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "動作UID / 依存元UID / 時間(ms) は数値で入力してください。")
                return
            if self._uid_exists(value["uid"], exclude_uid=op.uid):
                QMessageBox.warning(self, "UID重複", f"動作UID {value['uid']} はすでに存在します。")
                return

            self.model_about_to_change.emit("動作編集")
            old_uid = op.uid
            op.uid = value["uid"]
            op.action_uid = value["action_uid"]
            op.operation_mode = value["operation_mode"]
            op.time_mode = value["time_mode"]
            op.duration_ms = value["duration_ms"]
            op.start_trigger = value["start_trigger"]
            op.start_operation_uid = value["start_operation_uid"]
            op.end_mode = value["end_mode"]
            op.end_trigger = value["end_trigger"]
            op.end_operation_uid = value["end_operation_uid"]
            op.from_value = value["from_value"]
            op.to_value = value["to_value"]

            for other in self.model.operations:
                if other is op:
                    continue
                if other.start_operation_uid == old_uid:
                    other.start_operation_uid = op.uid
                if other.end_operation_uid == old_uid:
                    other.end_operation_uid = op.uid

            self.refresh()
            self.model_changed.emit()

    def delete_operation(self):
        op_uid = self._selected_operation_uid()
        if op_uid is None:
            return
        self.model_about_to_change.emit("動作削除")
        for op in self.model.operations:
            if op.start_operation_uid == op_uid:
                op.start_operation_uid = None
                op.start_trigger = "時刻0"
            if op.end_operation_uid == op_uid:
                op.end_operation_uid = None
                op.end_mode = "直値指定"
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
        self.chart.setMinimumHeight(820)
        layout.addWidget(self.chart, 1)

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
            f"動作UID {source_uid} → 動作UID {target_uid} の開始依存を設定しますか？\n"
            "はい: 元動作の終了で開始\n"
            "いいえ: 元動作の開始で開始",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )
        if answer == QMessageBox.Cancel:
            return

        self.model_about_to_change.emit("依存関係設定")
        target.start_operation_uid = source_uid
        target.start_trigger = "終了" if answer == QMessageBox.Yes else "開始"
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
        small1 = HierarchyItem(uid=3, id_number=1, name="Z軸", level="small", parent_uid=2, action_type="points")
        small2 = HierarchyItem(uid=4, id_number=2, name="吸着センサ", level="small", parent_uid=2, action_type="onoff")
        small3 = HierarchyItem(uid=8, id_number=3, name="クランプ", level="small", parent_uid=2, action_type="onoff")

        middle2 = HierarchyItem(uid=5, id_number=2, name="供給ユニット", level="middle", parent_uid=1)
        small4 = HierarchyItem(uid=6, id_number=1, name="供給X軸", level="small", parent_uid=5, action_type="points")
        small5 = HierarchyItem(uid=7, id_number=2, name="ワーク検知", level="small", parent_uid=5, action_type="onoff")

        large2 = HierarchyItem(uid=9, id_number=2, name="設備B", level="large", parent_uid=None)
        middle3 = HierarchyItem(uid=10, id_number=1, name="検査ユニット", level="middle", parent_uid=9)
        small6 = HierarchyItem(uid=11, id_number=1, name="検査シリンダ", level="small", parent_uid=10, action_type="points")
        small7 = HierarchyItem(uid=12, id_number=2, name="OK判定", level="small", parent_uid=10, action_type="onoff")

        self.model.hierarchy_items = [
            large1, middle1, small1, small2, small3,
            middle2, small4, small5,
            large2, middle3, small6, small7,
        ]

        self.model.action_definitions = [
            ActionDefinition(uid=1, small_item_uid=3, action_no=1, name="上昇", points=["原点", "待機", "上限"]),
            ActionDefinition(uid=2, small_item_uid=3, action_no=2, name="下降", points=["原点", "待機", "上限"]),
            ActionDefinition(uid=3, small_item_uid=4, action_no=1, name="ON", points=["ON", "OFF"]),
            ActionDefinition(uid=3, small_item_uid=4, action_no=2, name="OFF", points=["ON", "OFF"]),
            ActionDefinition(uid=4, small_item_uid=8, action_no=1, name="ON", points=["ON", "OFF"]),
            ActionDefinition(uid=4, small_item_uid=8, action_no=2, name="OFF", points=["ON", "OFF"]),
            ActionDefinition(uid=5, small_item_uid=6, action_no=1, name="供給移動", points=["受取", "待機", "供給"]),
            ActionDefinition(uid=6, small_item_uid=7, action_no=1, name="ON", points=["ON", "OFF"]),
            ActionDefinition(uid=6, small_item_uid=7, action_no=2, name="OFF", points=["ON", "OFF"]),
            ActionDefinition(uid=7, small_item_uid=11, action_no=1, name="前進後退", points=["後退", "中間", "前進"]),
            ActionDefinition(uid=8, small_item_uid=12, action_no=1, name="ON", points=["ON", "OFF"]),
            ActionDefinition(uid=8, small_item_uid=12, action_no=2, name="OFF", points=["ON", "OFF"]),
        ]

        self.model.operations = [
            OperationInstance(
                uid=1, action_uid=1, duration_ms=1200,
                operation_mode="ポイント移動", time_mode="直値指定",
                start_trigger="時刻0", start_operation_uid=None,
                end_mode="直値指定", end_trigger="終了", end_operation_uid=None,
                from_value="原点", to_value="上限",
            ),
            OperationInstance(
                uid=2, action_uid=3, duration_ms=300,
                operation_mode="ON-OFF", time_mode="直値指定",
                start_trigger="終了", start_operation_uid=1,
                end_mode="直値指定", end_trigger="終了", end_operation_uid=None,
                from_value="OFF", to_value="ON",
            ),
            OperationInstance(
                uid=3, action_uid=4, duration_ms=200,
                operation_mode="ON-OFF", time_mode="直値指定",
                start_trigger="終了", start_operation_uid=2,
                end_mode="直値指定", end_trigger="終了", end_operation_uid=None,
                from_value="OFF", to_value="ON",
            ),
            OperationInstance(
                uid=4, action_uid=5, duration_ms=900,
                operation_mode="ポイント移動", time_mode="直値指定",
                start_trigger="開始", start_operation_uid=3,
                end_mode="直値指定", end_trigger="終了", end_operation_uid=None,
                from_value="待機", to_value="供給",
            ),
            OperationInstance(
                uid=5, action_uid=6, duration_ms=150,
                operation_mode="ON-OFF", time_mode="直値指定",
                start_trigger="終了", start_operation_uid=4,
                end_mode="直値指定", end_trigger="終了", end_operation_uid=None,
                from_value="OFF", to_value="ON",
            ),
            OperationInstance(
                uid=6, action_uid=7, duration_ms=800,
                operation_mode="ポイント移動", time_mode="直値指定",
                start_trigger="終了", start_operation_uid=5,
                end_mode="直値指定", end_trigger="終了", end_operation_uid=None,
                from_value="後退", to_value="前進",
            ),
            OperationInstance(
                uid=7, action_uid=8, duration_ms=250,
                operation_mode="ON-OFF", time_mode="直値指定",
                start_trigger="終了", start_operation_uid=6,
                end_mode="直値指定", end_trigger="終了", end_operation_uid=None,
                from_value="OFF", to_value="ON",
            ),
            OperationInstance(
                uid=8, action_uid=3, duration_ms=300,
                operation_mode="ON-OFF", time_mode="直値指定",
                start_trigger="終了", start_operation_uid=7,
                end_mode="直値指定", end_trigger="終了", end_operation_uid=None,
                from_value="ON", to_value="OFF",
            ),
        ]
        self.model.normalize_onoff_points()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

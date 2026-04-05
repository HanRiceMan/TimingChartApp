
import json
import math
import sys
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSplitter,
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
    id: int
    name: str
    level: str   # large / middle / small
    parent_id: Optional[int] = None


@dataclass
class ActionDefinition:
    id: int
    small_item_id: int
    name: str
    action_type: str  # onoff / points
    points: List[str] = field(default_factory=list)


@dataclass
class OperationInstance:
    id: int
    action_def_id: int
    name: str
    duration_ms: int
    start_trigger: str = "manual"  # manual / after_finish / after_start
    trigger_operation_id: Optional[int] = None
    from_value: str = ""
    to_value: str = ""


class AppModel:
    def __init__(self):
        self.hierarchy_items: List[HierarchyItem] = []
        self.action_definitions: List[ActionDefinition] = []
        self.operations: List[OperationInstance] = []

    # ---------- ID utilities ----------
    def next_hierarchy_id(self) -> int:
        return max([x.id for x in self.hierarchy_items], default=0) + 1

    def next_action_def_id(self) -> int:
        return max([x.id for x in self.action_definitions], default=0) + 1

    def next_operation_id(self) -> int:
        return max([x.id for x in self.operations], default=0) + 1

    # ---------- lookups ----------
    def get_hierarchy(self, item_id: int) -> Optional[HierarchyItem]:
        return next((x for x in self.hierarchy_items if x.id == item_id), None)

    def get_action_def(self, action_def_id: int) -> Optional[ActionDefinition]:
        return next((x for x in self.action_definitions if x.id == action_def_id), None)

    def get_operation(self, operation_id: int) -> Optional[OperationInstance]:
        return next((x for x in self.operations if x.id == operation_id), None)

    def small_items(self) -> List[HierarchyItem]:
        return [x for x in self.hierarchy_items if x.level == "small"]

    def children_of(self, parent_id: Optional[int]) -> List[HierarchyItem]:
        return [x for x in self.hierarchy_items if x.parent_id == parent_id]

    def hierarchy_path(self, item_id: int) -> str:
        names = []
        cur = self.get_hierarchy(item_id)
        while cur:
            names.append(cur.name)
            cur = self.get_hierarchy(cur.parent_id) if cur.parent_id is not None else None
        return " / ".join(reversed(names))

    def action_label(self, action_def_id: int) -> str:
        a = self.get_action_def(action_def_id)
        if not a:
            return f"(missing:{action_def_id})"
        return f"{a.id}: {self.hierarchy_path(a.small_item_id)} / {a.name}"

    # ---------- persistence ----------
    def to_dict(self) -> Dict:
        return {
            "hierarchy_items": [asdict(x) for x in self.hierarchy_items],
            "action_definitions": [asdict(x) for x in self.action_definitions],
            "operations": [asdict(x) for x in self.operations],
        }

    def from_dict(self, data: Dict):
        self.hierarchy_items = [HierarchyItem(**x) for x in data.get("hierarchy_items", [])]
        self.action_definitions = [ActionDefinition(**x) for x in data.get("action_definitions", [])]
        self.operations = [OperationInstance(**x) for x in data.get("operations", [])]


# =========================
# Dialogs
# =========================

class HierarchyItemDialog(QDialog):
    def __init__(self, model: AppModel, item: Optional[HierarchyItem] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("階層項目")
        self.model = model
        self.item = item

        self.name_edit = QLineEdit()
        self.level_combo = QComboBox()
        self.level_combo.addItems(["large", "middle", "small"])

        self.parent_combo = QComboBox()
        self._load_parents()

        form = QFormLayout(self)
        form.addRow("名称", self.name_edit)
        form.addRow("レベル", self.level_combo)
        form.addRow("親項目", self.parent_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.level_combo.currentTextChanged.connect(self._load_parents)

        if item:
            self.name_edit.setText(item.name)
            self.level_combo.setCurrentText(item.level)
            self._load_parents()
            parent_val = "" if item.parent_id is None else str(item.parent_id)
            idx = self.parent_combo.findData(parent_val)
            if idx >= 0:
                self.parent_combo.setCurrentIndex(idx)

    def _load_parents(self):
        current_parent = self.parent_combo.currentData()
        level = self.level_combo.currentText()
        self.parent_combo.clear()
        self.parent_combo.addItem("-", "")

        if level == "large":
            return

        allowed_parent_level = "large" if level == "middle" else "middle"
        for x in self.model.hierarchy_items:
            if x.level == allowed_parent_level:
                self.parent_combo.addItem(f"{x.id}: {x.name}", str(x.id))

        if current_parent is not None:
            idx = self.parent_combo.findData(current_parent)
            if idx >= 0:
                self.parent_combo.setCurrentIndex(idx)

    def get_value(self) -> Tuple[str, str, Optional[int]]:
        name = self.name_edit.text().strip()
        level = self.level_combo.currentText()
        raw = self.parent_combo.currentData()
        parent_id = int(raw) if raw not in ("", None) else None
        return name, level, parent_id


class ActionDefinitionDialog(QDialog):
    def __init__(self, model: AppModel, action_def: Optional[ActionDefinition] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("動作定義")
        self.model = model
        self.action_def = action_def

        self.small_combo = QComboBox()
        for s in self.model.small_items():
            self.small_combo.addItem(f"{s.id}: {self.model.hierarchy_path(s.id)}", s.id)

        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["onoff", "points"])
        self.points_edit = QLineEdit()
        self.points_hint = QLabel("ポイント名をカンマ区切りで入力（例: 原点, 受取, 加工, 待機）")

        form = QFormLayout(self)
        form.addRow("対象小項目", self.small_combo)
        form.addRow("動作名称", self.name_edit)
        form.addRow("動作種別", self.type_combo)
        form.addRow("ポイント一覧", self.points_edit)
        form.addRow("", self.points_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.type_combo.currentTextChanged.connect(self._refresh_points_enabled)
        self._refresh_points_enabled()

        if action_def:
            idx = self.small_combo.findData(action_def.small_item_id)
            if idx >= 0:
                self.small_combo.setCurrentIndex(idx)
            self.name_edit.setText(action_def.name)
            self.type_combo.setCurrentText(action_def.action_type)
            self.points_edit.setText(", ".join(action_def.points))
            self._refresh_points_enabled()

    def _refresh_points_enabled(self):
        enabled = self.type_combo.currentText() == "points"
        self.points_edit.setEnabled(enabled)
        self.points_hint.setEnabled(enabled)

    def get_value(self):
        small_item_id = int(self.small_combo.currentData())
        name = self.name_edit.text().strip()
        action_type = self.type_combo.currentText()
        points = [x.strip() for x in self.points_edit.text().split(",") if x.strip()] if action_type == "points" else ["OFF", "ON"]
        return small_item_id, name, action_type, points


class OperationDialog(QDialog):
    def __init__(self, model: AppModel, operation: Optional[OperationInstance] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("動作設定")
        self.model = model
        self.operation = operation

        self.action_combo = QComboBox()
        for a in self.model.action_definitions:
            self.action_combo.addItem(self.model.action_label(a.id), a.id)

        self.name_edit = QLineEdit()
        self.duration_edit = QLineEdit("1000")

        self.trigger_combo = QComboBox()
        self.trigger_combo.addItems(["manual", "after_finish", "after_start"])

        self.dep_combo = QComboBox()
        self.dep_combo.addItem("-", "")
        for op in self.model.operations:
            self.dep_combo.addItem(f"{op.id}: {op.name}", str(op.id))

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
            idx = self.action_combo.findData(operation.action_def_id)
            if idx >= 0:
                self.action_combo.setCurrentIndex(idx)
            self.name_edit.setText(operation.name)
            self.duration_edit.setText(str(operation.duration_ms))
            self.trigger_combo.setCurrentText(operation.start_trigger)
            dep_val = "" if operation.trigger_operation_id is None else str(operation.trigger_operation_id)
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
            if action_def.action_type == "onoff":
                values = ["OFF", "ON"]
            else:
                values = action_def.points or ["P1", "P2"]
        self.from_combo.addItems(values)
        self.to_combo.addItems(values)
        if len(values) >= 2:
            self.from_combo.setCurrentIndex(0)
            self.to_combo.setCurrentIndex(min(1, len(values) - 1))

    def get_value(self):
        action_def_id = int(self.action_combo.currentData())
        name = self.name_edit.text().strip()
        duration_ms = max(0, int(self.duration_edit.text().strip() or "0"))
        start_trigger = self.trigger_combo.currentText()
        raw_dep = self.dep_combo.currentData()
        dep_id = int(raw_dep) if start_trigger != "manual" and raw_dep not in ("", None) else None
        from_value = self.from_combo.currentText()
        to_value = self.to_combo.currentText()
        return action_def_id, name, duration_ms, start_trigger, dep_id, from_value, to_value


# =========================
# Schedule calculation
# =========================

def calculate_schedule(model: AppModel) -> Tuple[Dict[int, Tuple[int, int]], List[str]]:
    ops = {op.id: op for op in model.operations}
    errors = []

    # cycle detection
    visiting = set()
    visited = set()

    def dfs(op_id: int):
        if op_id in visiting:
            raise ValueError(f"循環依存があります: 動作ID {op_id}")
        if op_id in visited:
            return
        visiting.add(op_id)
        op = ops[op_id]
        if op.trigger_operation_id is not None and op.trigger_operation_id in ops:
            dfs(op.trigger_operation_id)
        visiting.remove(op_id)
        visited.add(op_id)

    try:
        for op_id in ops:
            dfs(op_id)
    except ValueError as e:
        return {}, [str(e)]

    memo: Dict[int, Tuple[int, int]] = {}

    def calc(op_id: int) -> Tuple[int, int]:
        if op_id in memo:
            return memo[op_id]
        op = ops[op_id]
        if op.start_trigger == "manual" or op.trigger_operation_id is None:
            start = 0
        else:
            pred = ops.get(op.trigger_operation_id)
            if pred is None:
                errors.append(f"動作ID {op.id}: 依存先 {op.trigger_operation_id} が見つかりません")
                start = 0
            else:
                p_start, p_end = calc(pred.id)
                start = p_end if op.start_trigger == "after_finish" else p_start
        end = start + max(0, op.duration_ms)
        memo[op_id] = (start, end)
        return memo[op_id]

    for op_id in ops:
        calc(op_id)

    return memo, errors


# =========================
# Chart view
# =========================

class SelectableOpRect(QGraphicsRectItem):
    def __init__(self, rect: QRectF, operation_id: int, callback):
        super().__init__(rect)
        self.operation_id = operation_id
        self.callback = callback
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.callback:
            self.callback(self.operation_id)


class TimingChartView(QGraphicsView):
    dependency_created = Signal(int, int)  # source_op_id, target_op_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setScene(QGraphicsScene(self))
        self.link_mode = False
        self._pending_source_op_id: Optional[int] = None
        self.selection_label = None

    def set_link_mode(self, enabled: bool):
        self.link_mode = enabled
        self._pending_source_op_id = None

    def _on_operation_clicked(self, operation_id: int):
        if not self.link_mode:
            return
        if self._pending_source_op_id is None:
            self._pending_source_op_id = operation_id
        else:
            if self._pending_source_op_id != operation_id:
                self.dependency_created.emit(self._pending_source_op_id, operation_id)
            self._pending_source_op_id = None

    def render_chart(self, model: AppModel):
        scene = self.scene()
        scene.clear()

        schedule, errors = calculate_schedule(model)
        if errors:
            y = 20
            for e in errors:
                txt = scene.addSimpleText(f"ERROR: {e}")
                txt.setPos(20, y)
                y += 20
            return

        row_h = 80
        left_w = 280
        header_h = 50
        time_scale = 0.12  # px per ms
        max_time = max([end for _, end in schedule.values()], default=3000)
        total_w = left_w + max_time * time_scale + 200
        total_h = header_h + max(1, len(model.small_items())) * row_h + 80
        scene.setSceneRect(0, 0, total_w, total_h)

        # small item row allocation
        smalls = sorted(model.small_items(), key=lambda x: x.id)
        row_map = {s.id: i for i, s in enumerate(smalls)}

        # header background
        scene.addRect(0, 0, total_w, header_h)
        scene.addLine(left_w, 0, left_w, total_h)

        # time grid
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

        # row backgrounds / labels
        for s in smalls:
            row = row_map[s.id]
            top = header_h + row * row_h
            bg = QGraphicsRectItem(0, top, total_w, row_h)
            bg.setBrush(QBrush(QColor(248, 249, 251) if row % 2 == 0 else QColor(238, 241, 244)))
            bg.setPen(QPen(QColor(220, 225, 230)))
            scene.addItem(bg)
            label = scene.addSimpleText(f"{s.id}: {model.hierarchy_path(s.id)}")
            label.setPos(10, top + 8)

        op_anchor: Dict[int, Dict[str, QPointF]] = {}

        for op in sorted(model.operations, key=lambda x: x.id):
            action_def = model.get_action_def(op.action_def_id)
            if not action_def:
                continue
            small_id = action_def.small_item_id
            row = row_map.get(small_id)
            if row is None:
                continue
            start, end = schedule.get(op.id, (0, 0))
            top = header_h + row * row_h
            x1 = left_w + start * time_scale
            x2 = left_w + end * time_scale

            mid_y = top + row_h / 2

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

                # point labels
                for p, i in index_map.items():
                    py = top + 14 + (row_h - 28) * (i / max(1, n))
                    scene.addLine(left_w - 6, py, left_w, py, QPen(QColor(140, 140, 140)))
                    if i < 5:
                        label = scene.addSimpleText(p)
                        label.setPos(left_w - 60, py - 8)

            hit = SelectableOpRect(hit_rect, op.id, self._on_operation_clicked)
            hit.setBrush(QBrush(QColor(0, 0, 0, 1)))
            hit.setPen(QPen(QColor(0, 0, 0, 0)))
            scene.addItem(hit)

            caption = scene.addSimpleText(f"OP{op.id}: {op.name}")
            caption.setPos(x1 + 6, top + 6)

            op_anchor[op.id] = {
                "start": QPointF(x1, y1),
                "end": QPointF(x2, y2),
            }

        # dependency arrows
        for op in model.operations:
            if op.trigger_operation_id is None:
                continue
            if op.trigger_operation_id not in op_anchor or op.id not in op_anchor:
                continue

            src_key = "end" if op.start_trigger == "after_finish" else "start"
            p1 = op_anchor[op.trigger_operation_id][src_key]
            p2 = op_anchor[op.id]["start"]
            elbow_x = (p1.x() + p2.x()) / 2

            pen = QPen(QColor(180, 70, 50), 2)
            scene.addLine(p1.x(), p1.y(), elbow_x, p1.y(), pen)
            scene.addLine(elbow_x, p1.y(), elbow_x, p2.y(), pen)
            scene.addLine(elbow_x, p2.y(), p2.x(), p2.y(), pen)

            arrow = QPolygonF([
                QPointF(p2.x(), p2.y()),
                QPointF(p2.x() - 8, p2.y() - 4),
                QPointF(p2.x() - 8, p2.y() + 4),
            ])
            arrow_item = QGraphicsPolygonItem(arrow)
            arrow_item.setBrush(QBrush(QColor(180, 70, 50)))
            arrow_item.setPen(QPen(QColor(180, 70, 50)))
            scene.addItem(arrow_item)


# =========================
# Tabs
# =========================

class DeviceTab(QWidget):
    model_changed = Signal()

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self.model = model

        layout = QHBoxLayout(self)

        left_box = QVBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["階層 / ID", "名称", "レベル"])
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        left_box.addWidget(self.tree)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("階層追加")
        self.edit_btn = QPushButton("階層編集")
        self.del_btn = QPushButton("階層削除")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.edit_btn)
        btn_row.addWidget(self.del_btn)
        left_box.addLayout(btn_row)

        right_box = QVBoxLayout()
        self.actions_table = QTableWidget(0, 5)
        self.actions_table.setHorizontalHeaderLabels(["ID", "小項目ID", "小項目", "動作名称", "種別"])
        self.actions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_box.addWidget(QLabel("動作定義一覧"))
        right_box.addWidget(self.actions_table)

        a_btn_row = QHBoxLayout()
        self.add_action_btn = QPushButton("動作定義追加")
        self.edit_action_btn = QPushButton("動作定義編集")
        self.del_action_btn = QPushButton("動作定義削除")
        a_btn_row.addWidget(self.add_action_btn)
        a_btn_row.addWidget(self.edit_action_btn)
        a_btn_row.addWidget(self.del_action_btn)
        right_box.addLayout(a_btn_row)

        layout.addLayout(left_box, 3)
        layout.addLayout(right_box, 4)

        self.add_btn.clicked.connect(self.add_hierarchy)
        self.edit_btn.clicked.connect(self.edit_hierarchy)
        self.del_btn.clicked.connect(self.delete_hierarchy)
        self.add_action_btn.clicked.connect(self.add_action)
        self.edit_action_btn.clicked.connect(self.edit_action)
        self.del_action_btn.clicked.connect(self.delete_action)

        self.refresh()

    def refresh(self):
        self.tree.clear()
        large_items = [x for x in self.model.hierarchy_items if x.level == "large"]
        for large in sorted(large_items, key=lambda x: x.id):
            root = QTreeWidgetItem([str(large.id), large.name, large.level])
            root.setData(0, Qt.UserRole, large.id)
            self.tree.addTopLevelItem(root)
            for mid in sorted(self.model.children_of(large.id), key=lambda x: x.id):
                mid_item = QTreeWidgetItem([str(mid.id), mid.name, mid.level])
                mid_item.setData(0, Qt.UserRole, mid.id)
                root.addChild(mid_item)
                for small in sorted(self.model.children_of(mid.id), key=lambda x: x.id):
                    s_item = QTreeWidgetItem([str(small.id), small.name, small.level])
                    s_item.setData(0, Qt.UserRole, small.id)
                    mid_item.addChild(s_item)
        self.tree.expandAll()

        self.actions_table.setRowCount(len(self.model.action_definitions))
        for r, a in enumerate(sorted(self.model.action_definitions, key=lambda x: x.id)):
            small = self.model.get_hierarchy(a.small_item_id)
            values = [
                str(a.id),
                str(a.small_item_id),
                self.model.hierarchy_path(a.small_item_id) if small else "",
                a.name,
                a.action_type,
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setData(Qt.UserRole, a.id)
                self.actions_table.setItem(r, c, item)

    def _selected_hierarchy_id(self) -> Optional[int]:
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def _selected_action_def_id(self) -> Optional[int]:
        row = self.actions_table.currentRow()
        if row < 0:
            return None
        item = self.actions_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def add_hierarchy(self):
        dlg = HierarchyItemDialog(self.model, parent=self)
        if dlg.exec():
            name, level, parent_id = dlg.get_value()
            if not name:
                QMessageBox.warning(self, "入力不足", "名称を入力してください。")
                return
            if level != "large" and parent_id is None:
                QMessageBox.warning(self, "入力不足", f"{level} は親項目が必要です。")
                return
            self.model.hierarchy_items.append(HierarchyItem(
                id=self.model.next_hierarchy_id(),
                name=name,
                level=level,
                parent_id=parent_id,
            ))
            self.refresh()
            self.model_changed.emit()

    def edit_hierarchy(self):
        item_id = self._selected_hierarchy_id()
        if item_id is None:
            return
        item = self.model.get_hierarchy(item_id)
        if not item:
            return
        dlg = HierarchyItemDialog(self.model, item=item, parent=self)
        if dlg.exec():
            name, level, parent_id = dlg.get_value()
            if not name:
                QMessageBox.warning(self, "入力不足", "名称を入力してください。")
                return
            item.name = name
            item.level = level
            item.parent_id = parent_id
            self.refresh()
            self.model_changed.emit()

    def delete_hierarchy(self):
        item_id = self._selected_hierarchy_id()
        if item_id is None:
            return

        descendants = set()
        stack = [item_id]
        while stack:
            cur = stack.pop()
            descendants.add(cur)
            stack.extend([x.id for x in self.model.children_of(cur)])

        # remove dependent action defs and operations
        related_action_ids = [a.id for a in self.model.action_definitions if a.small_item_id in descendants]
        self.model.operations = [op for op in self.model.operations if op.action_def_id not in related_action_ids]
        self.model.action_definitions = [a for a in self.model.action_definitions if a.small_item_id not in descendants]
        self.model.hierarchy_items = [h for h in self.model.hierarchy_items if h.id not in descendants]

        self.refresh()
        self.model_changed.emit()

    def add_action(self):
        if not self.model.small_items():
            QMessageBox.warning(self, "項目不足", "先に小項目を作成してください。")
            return
        dlg = ActionDefinitionDialog(self.model, parent=self)
        if dlg.exec():
            small_item_id, name, action_type, points = dlg.get_value()
            if not name:
                QMessageBox.warning(self, "入力不足", "動作名称を入力してください。")
                return
            self.model.action_definitions.append(ActionDefinition(
                id=self.model.next_action_def_id(),
                small_item_id=small_item_id,
                name=name,
                action_type=action_type,
                points=points,
            ))
            self.refresh()
            self.model_changed.emit()

    def edit_action(self):
        action_id = self._selected_action_def_id()
        if action_id is None:
            return
        action_def = self.model.get_action_def(action_id)
        if not action_def:
            return
        dlg = ActionDefinitionDialog(self.model, action_def=action_def, parent=self)
        if dlg.exec():
            small_item_id, name, action_type, points = dlg.get_value()
            action_def.small_item_id = small_item_id
            action_def.name = name
            action_def.action_type = action_type
            action_def.points = points
            self.refresh()
            self.model_changed.emit()

    def delete_action(self):
        action_id = self._selected_action_def_id()
        if action_id is None:
            return
        self.model.operations = [op for op in self.model.operations if op.action_def_id != action_id]
        self.model.action_definitions = [a for a in self.model.action_definitions if a.id != action_id]
        self.refresh()
        self.model_changed.emit()


class OperationsTab(QWidget):
    model_changed = Signal()

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self.model = model

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "動作ID", "動作定義", "設定名", "時間(ms)", "開始トリガ",
            "依存先動作", "開始値", "終了値"
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
        ops = sorted(self.model.operations, key=lambda x: x.id)
        self.table.setRowCount(len(ops))
        for r, op in enumerate(ops):
            dep = "-" if op.trigger_operation_id is None else str(op.trigger_operation_id)
            vals = [
                str(op.id),
                self.model.action_label(op.action_def_id),
                op.name,
                str(op.duration_ms),
                op.start_trigger,
                dep,
                op.from_value,
                op.to_value,
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setData(Qt.UserRole, op.id)
                self.table.setItem(r, c, item)

    def _selected_operation_id(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def add_operation(self):
        if not self.model.action_definitions:
            QMessageBox.warning(self, "項目不足", "先に動作定義を作成してください。")
            return
        dlg = OperationDialog(self.model, parent=self)
        if dlg.exec():
            try:
                action_def_id, name, duration_ms, start_trigger, dep_id, from_value, to_value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "時間(ms)は数値で入力してください。")
                return
            if not name:
                QMessageBox.warning(self, "入力不足", "設定名を入力してください。")
                return
            self.model.operations.append(OperationInstance(
                id=self.model.next_operation_id(),
                action_def_id=action_def_id,
                name=name,
                duration_ms=duration_ms,
                start_trigger=start_trigger,
                trigger_operation_id=dep_id,
                from_value=from_value,
                to_value=to_value,
            ))
            self.refresh()
            self.model_changed.emit()

    def edit_operation(self):
        op_id = self._selected_operation_id()
        if op_id is None:
            return
        op = self.model.get_operation(op_id)
        if not op:
            return
        dlg = OperationDialog(self.model, operation=op, parent=self)
        if dlg.exec():
            try:
                action_def_id, name, duration_ms, start_trigger, dep_id, from_value, to_value = dlg.get_value()
            except ValueError:
                QMessageBox.warning(self, "入力エラー", "時間(ms)は数値で入力してください。")
                return
            op.action_def_id = action_def_id
            op.name = name
            op.duration_ms = duration_ms
            op.start_trigger = start_trigger
            op.trigger_operation_id = dep_id
            op.from_value = from_value
            op.to_value = to_value
            self.refresh()
            self.model_changed.emit()

    def delete_operation(self):
        op_id = self._selected_operation_id()
        if op_id is None:
            return
        for op in self.model.operations:
            if op.trigger_operation_id == op_id:
                op.trigger_operation_id = None
                op.start_trigger = "manual"
        self.model.operations = [op for op in self.model.operations if op.id != op_id]
        self.refresh()
        self.model_changed.emit()


class ChartTab(QWidget):
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

    def create_dependency_from_chart(self, source_id: int, target_id: int):
        target = self.model.get_operation(target_id)
        if not target:
            return
        answer = QMessageBox.question(
            self,
            "依存設定",
            f"動作ID {source_id} → 動作ID {target_id} の依存を設定しますか？\n"
            "はい: 完了後に開始\n"
            "いいえ: 開始と同時に開始",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )
        if answer == QMessageBox.Cancel:
            return
        target.trigger_operation_id = source_id
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
        self.resize(1500, 900)

        self.model = AppModel()
        self._load_sample_data()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.device_tab = DeviceTab(self.model)
        self.ops_tab = OperationsTab(self.model)
        self.chart_tab = ChartTab(self.model)

        self.tabs.addTab(self.chart_tab, "グラフ")
        self.tabs.addTab(self.device_tab, "機器一覧")
        self.tabs.addTab(self.ops_tab, "動作設定")

        self.device_tab.model_changed.connect(self.refresh_all)
        self.ops_tab.model_changed.connect(self.refresh_all)
        self.chart_tab.model_changed.connect(self.refresh_all)

        self._build_toolbar()
        self.refresh_all()

    def _build_toolbar(self):
        tb = QToolBar("Main")
        self.addToolBar(tb)

        save_action = QAction("保存", self)
        load_action = QAction("読込", self)
        new_action = QAction("新規", self)

        save_action.triggered.connect(self.save_project)
        load_action.triggered.connect(self.load_project)
        new_action.triggered.connect(self.new_project)

        tb.addAction(new_action)
        tb.addAction(save_action)
        tb.addAction(load_action)

    def refresh_all(self):
        self.device_tab.refresh()
        self.ops_tab.refresh()
        self.chart_tab.refresh()

    def new_project(self):
        self.model = AppModel()
        self.device_tab.model = self.model
        self.ops_tab.model = self.model
        self.chart_tab.model = self.model
        self.refresh_all()

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
        self.model.from_dict(data)
        self.refresh_all()
        QMessageBox.information(self, "読込", "読み込みました。")

    def _load_sample_data(self):
        # Sample hierarchy
        self.model.hierarchy_items = [
            HierarchyItem(1, "設備A", "large", None),
            HierarchyItem(2, "搬送ユニット", "middle", 1),
            HierarchyItem(3, "Z軸", "small", 2),
            HierarchyItem(4, "吸着センサ", "small", 2),
            HierarchyItem(5, "設備B", "large", None),
            HierarchyItem(6, "検査ユニット", "middle", 5),
            HierarchyItem(7, "検査シリンダ", "small", 6),
        ]
        self.model.action_definitions = [
            ActionDefinition(1, 3, "位置移動", "points", ["ポイント1", "ポイント2", "ポイント3"]),
            ActionDefinition(2, 4, "検出", "onoff", ["OFF", "ON"]),
            ActionDefinition(3, 7, "前進後退", "points", ["後退", "中間", "前進"]),
        ]
        self.model.operations = [
            OperationInstance(1, 1, "Z軸 上昇", 1200, "manual", None, "ポイント1", "ポイント3"),
            OperationInstance(2, 2, "吸着ON", 300, "after_finish", 1, "OFF", "ON"),
            OperationInstance(3, 3, "検査前進", 900, "after_start", 2, "後退", "前進"),
            OperationInstance(4, 2, "吸着OFF", 300, "after_finish", 3, "ON", "OFF"),
        ]


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

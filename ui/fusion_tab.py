"""
视图融合页面 —— 多视角点云融合（Open3D 显示）。
"""

import os
import logging

import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QCheckBox, QDoubleSpinBox,
    QSpinBox, QListWidget, QListWidgetItem, QFileDialog,
    QHBoxLayout, QVBoxLayout, QGridLayout, QGroupBox,
    QMessageBox, QAbstractItemView,
)
from PyQt5.QtCore import Qt

from utils.fusion_utils import scan_capture_dirs, fuse_captures, save_point_cloud_ply
import config

logger = logging.getLogger(__name__)


class FusionTab(QWidget):
    """视图融合页面。"""

    def __init__(self, log_func):
        super().__init__()
        self._log = log_func
        self._captures = []   # list[dict], 从 disk 加载的采集数据
        self._pcd = None      # open3d.geometry.PointCloud | None

        self._init_ui()

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        # --- 加载 ---
        root.addWidget(self._create_load_panel())

        # --- 选择 + 参数 ---
        mid = QHBoxLayout()
        mid.addWidget(self._create_select_panel(), stretch=1)
        mid.addWidget(self._create_params_panel())
        root.addLayout(mid)

        # --- 操作按钮 ---
        root.addWidget(self._create_action_panel())

    def _create_load_panel(self):
        group = QGroupBox("加载标定数据")
        layout = QHBoxLayout(group)

        self.label_dir = QLabel("未选择目录...")
        self.label_dir.setFrameStyle(QLabel.Sunken)
        self.label_dir.setStyleSheet("padding: 2px 6px;")
        layout.addWidget(self.label_dir, stretch=1)

        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._on_browse)
        layout.addWidget(btn_browse)

        self.btn_load = QPushButton("加载")
        self.btn_load.clicked.connect(self._on_load)
        layout.addWidget(self.btn_load)

        return group

    def _create_select_panel(self):
        group = QGroupBox("选择采集 (仅成功)")
        layout = QVBoxLayout(group)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_widget.setMaximumHeight(200)
        layout.addWidget(self.list_widget)

        bar = QHBoxLayout()
        btn_sel_all = QPushButton("全选")
        btn_sel_all.clicked.connect(self._on_select_all)
        bar.addWidget(btn_sel_all)

        btn_desel_all = QPushButton("取消全选")
        btn_desel_all.clicked.connect(self._on_deselect_all)
        bar.addWidget(btn_desel_all)

        self.label_sel_count = QLabel("已选: 0")
        bar.addWidget(self.label_sel_count)
        bar.addStretch()
        layout.addLayout(bar)

        return group

    def _create_params_panel(self):
        group = QGroupBox("点云参数")
        layout = QGridLayout(group)
        layout.setSpacing(4)

        # 体素大小
        layout.addWidget(QLabel("体素下采样 (m):"), 0, 0)
        self.spin_voxel = QDoubleSpinBox()
        self.spin_voxel.setRange(0.0, 0.1)
        self.spin_voxel.setDecimals(4)
        self.spin_voxel.setSingleStep(0.001)
        self.spin_voxel.setValue(config.DEFAULT_FUSION_VOXEL_SIZE)
        layout.addWidget(self.spin_voxel, 0, 1)

        # 距离过滤
        layout.addWidget(QLabel("最远距离 (m):"), 1, 0)
        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.1, 10.0)
        self.spin_dist.setDecimals(2)
        self.spin_dist.setSingleStep(0.1)
        self.spin_dist.setValue(config.DEFAULT_FUSION_DISTANCE_MAX)
        layout.addWidget(self.spin_dist, 1, 1)

        # 像素跳采
        layout.addWidget(QLabel("像素跳采:"), 2, 0)
        self.spin_skip = QSpinBox()
        self.spin_skip.setRange(1, 16)
        self.spin_skip.setValue(config.DEFAULT_FUSION_POINT_SKIP)
        layout.addWidget(self.spin_skip, 2, 1)

        # Mask 开关
        self.chk_mask = QCheckBox("启用 Mask 高亮")
        self.chk_mask.setToolTip(
            "开启后自动查找各采集目录下的 *_mask.png / *_mask.jpg，"
            "将 mask 区域用高亮颜色显示"
        )
        layout.addWidget(self.chk_mask, 3, 0, 1, 2)

        return group

    def _create_action_panel(self):
        group = QGroupBox("操作")
        layout = QHBoxLayout(group)

        self.btn_fuse = QPushButton("🔬 融合并显示")
        self.btn_fuse.clicked.connect(self._on_fuse)
        self.btn_fuse.setEnabled(False)
        layout.addWidget(self.btn_fuse)

        self.btn_save_ply = QPushButton("💾 保存 PLY")
        self.btn_save_ply.clicked.connect(self._on_save_ply)
        self.btn_save_ply.setEnabled(False)
        layout.addWidget(self.btn_save_ply)

        self.btn_clear = QPushButton("清除")
        self.btn_clear.clicked.connect(self._on_clear)
        layout.addWidget(self.btn_clear)

        layout.addStretch()
        return group

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def _on_browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择标定数据保存目录")
        if d:
            self.label_dir.setText(d)

    def _on_load(self):
        root_dir = self.label_dir.text()
        if not root_dir or not os.path.isdir(root_dir):
            QMessageBox.warning(self, "警告", "请先选择有效的标定数据目录。")
            return

        self._captures = scan_capture_dirs(root_dir)
        self._pcd = None
        self.btn_save_ply.setEnabled(False)

        self._refresh_list()
        self.btn_fuse.setEnabled(len(self._captures) > 0)
        self._log(f"从 {root_dir} 加载了 {len(self._captures)} 个有效采集")

    def _refresh_list(self):
        self.list_widget.clear()
        for cap in self._captures:
            text = (
                f"{cap['name']}  "
                f"角点:{cap.get('num_corners', '?')}  "
                f"重投影:{cap.get('reproj_error', 0):.4f}px"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, cap)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.list_widget.addItem(item)

        self._update_sel_count()

    def _update_sel_count(self):
        n = sum(
            1 for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        )
        self.label_sel_count.setText(f"已选: {n}")

    def _on_select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Checked)
        self._update_sel_count()

    def _on_deselect_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Unchecked)
        self._update_sel_count()

    # ------------------------------------------------------------------
    # 融合
    # ------------------------------------------------------------------

    def _get_selected_captures(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return selected

    def _on_fuse(self):
        selected = self._get_selected_captures()
        if len(selected) < 1:
            QMessageBox.warning(self, "警告", "请至少选择一个采集。")
            return

        voxel = self.spin_voxel.value()
        skip = self.spin_skip.value()
        dist = self.spin_dist.value()
        mask_on = self.chk_mask.isChecked()

        mask_info = ""
        if mask_on:
            mask_names = set()
            for cap in selected:
                for mname in cap.get("masks", {}):
                    mask_names.add(mname)
            if mask_names:
                mask_info = f", mask={{{', '.join(sorted(mask_names))}}}"
            else:
                mask_info = ", mask=无(未找到mask图像)"

        self._log(
            f"开始融合 {len(selected)} 个视角: "
            f"voxel={voxel}m, skip={skip}, dist_max={dist}m{mask_info}"
        )

        try:
            self._pcd = fuse_captures(
                selected, voxel, skip, dist,
                mask_enabled=mask_on,
                mask_colors=config.MASK_HIGHLIGHT_COLORS,
            )
        except Exception as e:
            self._log(f"[ERROR] 融合失败: {e}")
            QMessageBox.critical(self, "融合失败", str(e))
            return

        if self._pcd is None or len(self._pcd.points) == 0:
            QMessageBox.warning(self, "警告", "融合后点云为空。请检查数据和参数。")
            return

        self.btn_save_ply.setEnabled(True)
        self._log(
            f"融合完成: {len(self._pcd.points)} 个点。"
            f"正在打开 Open3D 窗口..."
        )

        # Open3D 可视化（独立窗口）
        try:
            import open3d as o3d
            # 添加坐标系辅助
            coord = o3d.geometry.TriangleMesh.create_coordinate_frame(
                size=0.1, origin=[0, 0, 0]
            )
            o3d.visualization.draw_geometries(
                [self._pcd, coord],
                window_name="融合点云 — 标定板坐标系",
                width=1280, height=720,
            )
        except Exception as e:
            self._log(f"[ERROR] Open3D 显示失败: {e}")
            QMessageBox.critical(self, "显示失败", str(e))

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------

    def _on_save_ply(self):
        if self._pcd is None:
            QMessageBox.warning(self, "警告", "请先执行融合。")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "保存融合点云", "fused.ply",
            "PLY Files (*.ply);;All Files (*)"
        )
        if not path:
            return

        save_point_cloud_ply(self._pcd, path)
        self._log(f"点云已保存: {path}")

    # ------------------------------------------------------------------
    # 清除
    # ------------------------------------------------------------------

    def _on_clear(self):
        self._captures = []
        self._pcd = None
        self.list_widget.clear()
        self.btn_fuse.setEnabled(False)
        self.btn_save_ply.setEnabled(False)
        self.label_sel_count.setText("已选: 0")

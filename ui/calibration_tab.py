"""
标定页面 —— Charuco 板检测与位姿估计。
"""

import os
import json
import logging
from datetime import datetime

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QComboBox, QCheckBox,
    QDoubleSpinBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QHBoxLayout, QVBoxLayout,
    QGridLayout, QGroupBox, QMessageBox, QAbstractItemView,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap

from utils.image_utils import cv_image_to_qpixmap, resize_for_display
from utils.calibration_utils import (
    create_charuco_board, detect_charuco_pose, draw_detection_overlay,
)
import config

logger = logging.getLogger(__name__)

# 采集列表中各列的序号
COL_INDEX = 0
COL_TIME = 1
COL_STATUS = 2
COL_CORNERS = 3
COL_REPROJ = 4


class CalibrationTab(QWidget):
    """Charuco 标定页面，包含相机预览、拍摄、位姿估计和采集管理。"""

    def __init__(self, get_camera, get_camera_running,
                 start_camera_cb, stop_camera_cb,
                 get_frames, get_intrinsics, log_func):
        super().__init__()

        self._get_camera = get_camera
        self._get_camera_running = get_camera_running
        self._start_camera_cb = start_camera_cb
        self._stop_camera_cb = stop_camera_cb
        self._get_frames = get_frames
        self._get_intrinsics = get_intrinsics
        self._log = log_func

        # 采集列表
        self._captures = []           # list[dict]
        self._selected_capture_idx = -1

        # 预览定时器
        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._on_preview_tick)

        self._init_ui()

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        # --- Charuco 参数 ---
        root.addWidget(self._create_board_params_panel())

        # --- 相机控制条 ---
        root.addWidget(self._create_camera_bar())

        # --- 预览 + 位姿 ---
        root.addWidget(self._create_preview_panel(), stretch=1)

        # --- 采集列表 ---
        root.addWidget(self._create_capture_list_panel())

    def _create_board_params_panel(self):
        group = QGroupBox("Charuco 标定板参数")
        layout = QGridLayout(group)
        layout.setSpacing(6)

        # 棋盘格列数
        layout.addWidget(QLabel("棋盘格列数:"), 0, 0)
        self.spin_squares_x = QSpinBox()
        self.spin_squares_x.setRange(2, 20)
        self.spin_squares_x.setValue(config.DEFAULT_CHARUCO_SQUARES_X)
        layout.addWidget(self.spin_squares_x, 0, 1)

        # 棋盘格行数
        layout.addWidget(QLabel("棋盘格行数:"), 0, 2)
        self.spin_squares_y = QSpinBox()
        self.spin_squares_y.setRange(2, 20)
        self.spin_squares_y.setValue(config.DEFAULT_CHARUCO_SQUARES_Y)
        layout.addWidget(self.spin_squares_y, 0, 3)

        # 方格边长 (m)
        layout.addWidget(QLabel("方格边长 (m):"), 1, 0)
        self.spin_square_len = QDoubleSpinBox()
        self.spin_square_len.setRange(0.001, 1.0)
        self.spin_square_len.setDecimals(4)
        self.spin_square_len.setSingleStep(0.005)
        self.spin_square_len.setValue(config.DEFAULT_CHARUCO_SQUARE_LENGTH)
        layout.addWidget(self.spin_square_len, 1, 1)

        # 标记边长 (m)
        layout.addWidget(QLabel("标记边长 (m):"), 1, 2)
        self.spin_marker_len = QDoubleSpinBox()
        self.spin_marker_len.setRange(0.001, 1.0)
        self.spin_marker_len.setDecimals(4)
        self.spin_marker_len.setSingleStep(0.005)
        self.spin_marker_len.setValue(config.DEFAULT_CHARUCO_MARKER_LENGTH)
        layout.addWidget(self.spin_marker_len, 1, 3)

        # 字典
        layout.addWidget(QLabel("ArUco 字典:"), 2, 0)
        self.combo_dict = QComboBox()
        for name in config.CHARUCO_DICT_OPTIONS:
            self.combo_dict.addItem(name)
        self.combo_dict.setCurrentText(config.DEFAULT_CHARUCO_DICT_NAME)
        layout.addWidget(self.combo_dict, 2, 1, 1, 3)

        return group

    def _create_camera_bar(self):
        group = QGroupBox("相机控制")
        layout = QHBoxLayout(group)

        self.btn_start = QPushButton("启动相机")
        self.btn_start.clicked.connect(self._on_start)
        layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("停止相机")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        layout.addWidget(self.btn_stop)

        self.label_cam_status = QLabel("● 未连接")
        self.label_cam_status.setStyleSheet("color: #888;")
        layout.addWidget(self.label_cam_status)

        layout.addStretch()

        self.btn_capture = QPushButton("📷 拍摄当前帧")
        self.btn_capture.clicked.connect(self._on_capture)
        self.btn_capture.setEnabled(False)
        layout.addWidget(self.btn_capture)

        return group

    def _create_preview_panel(self):
        group = QGroupBox("标定预览")
        layout = QHBoxLayout(group)

        # RGB + 检测叠加
        rgb_box = QVBoxLayout()
        rgb_box.addWidget(QLabel("RGB 图像 (检测叠加)", alignment=Qt.AlignCenter))
        self.label_rgb = QLabel("等待相机...", alignment=Qt.AlignCenter)
        self.label_rgb.setMinimumSize(320, 240)
        self.label_rgb.setStyleSheet("background-color: #1a1a1a; color: #888;")
        self.label_rgb.setScaledContents(False)
        rgb_box.addWidget(self.label_rgb)
        layout.addLayout(rgb_box)

        # Aligned Depth
        dep_box = QVBoxLayout()
        dep_box.addWidget(QLabel("Aligned Depth", alignment=Qt.AlignCenter))
        self.label_depth = QLabel("等待相机...", alignment=Qt.AlignCenter)
        self.label_depth.setMinimumSize(320, 240)
        self.label_depth.setStyleSheet("background-color: #1a1a1a; color: #888;")
        self.label_depth.setScaledContents(False)
        dep_box.addWidget(self.label_depth)
        layout.addLayout(dep_box)

        # 位姿文本
        pose_box = QVBoxLayout()
        pose_box.addWidget(QLabel("位姿估计", alignment=Qt.AlignCenter))
        self.label_pose = QLabel("等待拍摄...", alignment=Qt.AlignLeft)
        self.label_pose.setMinimumWidth(280)
        self.label_pose.setStyleSheet(
            "background-color: #1a1a1a; color: #0f0; "
            "font-family: Consolas; font-size: 12px; padding: 8px;"
        )
        self.label_pose.setTextFormat(Qt.PlainText)
        pose_box.addWidget(self.label_pose)
        layout.addLayout(pose_box)

        return group

    def _create_capture_list_panel(self):
        group = QGroupBox("采集列表")
        layout = QVBoxLayout(group)

        # 工具栏
        bar = QHBoxLayout()
        bar.addWidget(QLabel("已采集:"))
        self.label_count = QLabel("0 张")
        bar.addWidget(self.label_count)
        bar.addStretch()

        self.btn_view = QPushButton("查看选中")
        self.btn_view.clicked.connect(self._on_view_selected)
        bar.addWidget(self.btn_view)

        self.btn_delete = QPushButton("删除选中")
        self.btn_delete.clicked.connect(self._on_delete_selected)
        bar.addWidget(self.btn_delete)

        self.btn_save_all = QPushButton("💾 保存全部")
        self.btn_save_all.clicked.connect(self._on_save_all)
        bar.addWidget(self.btn_save_all)

        layout.addLayout(bar)

        # 表格
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "#", "时间", "状态", "角点数", "重投影误差(px)"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(200)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        layout.addWidget(self.table)

        return group

    # ------------------------------------------------------------------
    # 相机控制
    # ------------------------------------------------------------------

    def _on_start(self):
        self._start_camera_cb()
        if self._get_camera_running():
            self._preview_timer.start(33)
            self._update_cam_ui()

    def _on_stop(self):
        self._stop_camera_cb()
        self._preview_timer.stop()
        self._clear_preview()
        self._update_cam_ui()

    def _update_cam_ui(self):
        running = self._get_camera_running()
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_capture.setEnabled(running)
        if running:
            self.label_cam_status.setText("● 运行中")
            self.label_cam_status.setStyleSheet("color: #0f0;")
        else:
            self.label_cam_status.setText("● 未连接")
            self.label_cam_status.setStyleSheet("color: #888;")

    def _clear_preview(self):
        text = "无画面"
        for lbl in [self.label_rgb, self.label_depth]:
            lbl.setText(text)
            lbl.setStyleSheet("background-color: #1a1a1a; color: #888;")

    # ------------------------------------------------------------------
    # 预览刷新
    # ------------------------------------------------------------------

    def _on_preview_tick(self):
        if not self._get_camera_running():
            return
        frames = self._get_frames()
        if frames is None:
            return

        # 如果有选中的采集帧，显示采集帧；否则显示实时画面
        if self._selected_capture_idx >= 0:
            return  # 保持显示选中帧

        # RGB
        rgb = frames["color_image"]
        rgb_disp = resize_for_display(
            rgb, config.DISPLAY_MAX_WIDTH, config.DISPLAY_MAX_HEIGHT
        )
        self.label_rgb.setPixmap(cv_image_to_qpixmap(rgb_disp))

        # Aligned Depth
        dal = frames["depth_colormap_aligned"]
        dal_disp = resize_for_display(
            dal, config.DISPLAY_MAX_WIDTH, config.DISPLAY_MAX_HEIGHT
        )
        self.label_depth.setPixmap(cv_image_to_qpixmap(dal_disp))

    # ------------------------------------------------------------------
    # 拍摄 + 位姿估计
    # ------------------------------------------------------------------

    def _on_capture(self):
        frames = self._get_frames()
        if frames is None:
            QMessageBox.warning(self, "警告", "当前没有可用的帧数据。")
            return

        # 获取内参
        camera = self._get_camera()
        if camera is None:
            QMessageBox.warning(self, "警告", "相机未初始化。")
            return

        depth_scale = camera.get_depth_scale() if camera else 0.001

        intrinsics = self._get_intrinsics()
        if intrinsics is None:
            QMessageBox.warning(self, "警告", "无法获取相机内参。")
            return

        color_intr = intrinsics["color"]
        camera_matrix = np.array([
            [color_intr["fx"], 0, color_intr["ppx"]],
            [0, color_intr["fy"], color_intr["ppy"]],
            [0, 0, 1],
        ], dtype=np.float32)

        # 获取 Charuco 板参数
        board_params = self._get_board_params()
        board, aruco_dict = create_charuco_board(**board_params)

        # 位姿估计
        color_image = frames["color_image"]
        pose_result = detect_charuco_pose(
            color_image, board, aruco_dict, camera_matrix
        )

        # 保存采集
        capture = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ts_file": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "color_image": color_image.copy(),
            "depth_raw": frames["depth_raw"].copy(),
            "depth_aligned": frames["depth_aligned"].copy(),
            "depth_colormap_raw": frames["depth_colormap_raw"].copy(),
            "depth_colormap_aligned": frames["depth_colormap_aligned"].copy(),
            "pose_result": pose_result,
            "board_params": board_params,
            "depth_scale": depth_scale,
            "intrinsics": {
                k: v for k, v in color_intr.items()
                if k in ("fx", "fy", "ppx", "ppy", "width", "height")
            },
        }
        self._captures.append(capture)

        # 更新列表
        self._refresh_table()

        # 显示结果
        self._log(
            f"标定拍摄 #{len(self._captures)}: "
            f"{'成功' if pose_result['success'] else '失败'} "
            f"(角点={pose_result.get('num_corners', 0)})"
        )

        # 在位姿文本区显示最新拍摄结果（不影响实时预览）
        self._show_pose_text(len(self._captures) - 1)

    def _get_board_params(self):
        return {
            "squares_x": self.spin_squares_x.value(),
            "squares_y": self.spin_squares_y.value(),
            "square_length": self.spin_square_len.value(),
            "marker_length": self.spin_marker_len.value(),
            "dict_name": self.combo_dict.currentText(),
        }

    # ------------------------------------------------------------------
    # 采集列表管理
    # ------------------------------------------------------------------

    def _refresh_table(self):
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._captures))
        for i, cap in enumerate(self._captures):
            pr = cap["pose_result"]
            status = "✓ 成功" if pr["success"] else "✗ 失败"
            corners = str(pr.get("num_corners", 0))
            err = f"{pr.get('reproj_error', 0):.4f}" if pr["success"] else "-"

            self.table.setItem(i, COL_INDEX, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, COL_TIME, QTableWidgetItem(cap["timestamp"]))
            self.table.setItem(i, COL_STATUS, QTableWidgetItem(status))
            self.table.setItem(i, COL_CORNERS, QTableWidgetItem(corners))
            self.table.setItem(i, COL_REPROJ, QTableWidgetItem(err))

        self.label_count.setText(f"{len(self._captures)} 张")

    def _on_table_selection(self):
        rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not rows:
            self._selected_capture_idx = -1
            return
        self._selected_capture_idx = rows.pop()
        self._show_capture(self._selected_capture_idx)

    def _on_view_selected(self):
        rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not rows:
            QMessageBox.information(self, "提示", "请先在列表中选中一条采集记录。")
            return
        self._selected_capture_idx = rows.pop()
        self._show_capture(self._selected_capture_idx)

    def _on_delete_selected(self):
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()),
                      reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先在列表中选中要删除的记录。")
            return
        for r in rows:
            del self._captures[r]
        self._selected_capture_idx = -1
        self._refresh_table()
        self._log(f"已删除 {len(rows)} 条采集记录")

    def _show_pose_text(self, idx):
        """仅更新位姿文本区，不改变图像显示，不冻结实时预览。"""
        if idx < 0 or idx >= len(self._captures):
            return
        cap = self._captures[idx]
        pr = cap["pose_result"]
        if pr["success"]:
            rv = pr["rvec"].flatten()
            tv = pr["tvec"].flatten()
            text = (
                f"# {idx + 1}  {cap['timestamp']}\n"
                f"{'─' * 30}\n"
                f"状态: 成功 ✓\n"
                f"角点数: {pr['num_corners']}\n"
                f"重投影误差: {pr['reproj_error']:.4f} px\n\n"
                f"旋转向量 (Rodrigues):\n"
                f"  rx = {rv[0]:.6f}\n"
                f"  ry = {rv[1]:.6f}\n"
                f"  rz = {rv[2]:.6f}\n\n"
                f"平移向量 (m):\n"
                f"  tx = {tv[0]:.6f}\n"
                f"  ty = {tv[1]:.6f}\n"
                f"  tz = {tv[2]:.6f}\n"
            )
        else:
            text = (
                f"# {idx + 1}  {cap['timestamp']}\n"
                f"{'─' * 30}\n"
                f"状态: 失败 ✗\n"
                f"角点数: {pr.get('num_corners', 0)}\n"
            )
        self.label_pose.setText(text)

    def _show_capture(self, idx):
        """在预览区显示指定采集帧的图像和位姿（会冻结实时预览）。"""
        if idx < 0 or idx >= len(self._captures):
            return
        cap = self._captures[idx]
        pr = cap["pose_result"]

        # 获取内参用于绘制
        color_intr = cap["intrinsics"]
        camera_matrix = np.array([
            [color_intr["fx"], 0, color_intr["ppx"]],
            [0, color_intr["fy"], color_intr["ppy"]],
            [0, 0, 1],
        ], dtype=np.float32)

        # RGB + 检测叠加
        vis_rgb = draw_detection_overlay(cap["color_image"], pr, camera_matrix)
        vis_rgb_disp = resize_for_display(
            vis_rgb, config.DISPLAY_MAX_WIDTH, config.DISPLAY_MAX_HEIGHT
        )
        self.label_rgb.setPixmap(cv_image_to_qpixmap(vis_rgb_disp))

        # Depth
        dal_disp = resize_for_display(
            cap["depth_colormap_aligned"],
            config.DISPLAY_MAX_WIDTH, config.DISPLAY_MAX_HEIGHT
        )
        self.label_depth.setPixmap(cv_image_to_qpixmap(dal_disp))

        # 位姿文本
        self._show_pose_text(idx)

    # ------------------------------------------------------------------
    # 保存全部
    # ------------------------------------------------------------------

    def _on_save_all(self):
        if not self._captures:
            QMessageBox.information(self, "提示", "没有可保存的采集数据。")
            return

        save_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not save_dir:
            return

        saved = 0
        for i, cap in enumerate(self._captures):
            if self._save_single_capture(cap, save_dir, i + 1):
                saved += 1

        self._log(f"已保存 {saved}/{len(self._captures)} 条采集到: {save_dir}")
        QMessageBox.information(
            self, "保存完成",
            f"成功保存 {saved}/{len(self._captures)} 条采集记录。"
        )

    def _save_single_capture(self, cap: dict, save_dir: str, index: int) -> bool:
        """保存单条采集到 save_dir/<ts_file>/ 子目录。"""
        ts = cap["ts_file"]
        cap_dir = os.path.join(save_dir, f"calib_{index:03d}_{ts}")
        try:
            os.makedirs(cap_dir, exist_ok=True)

            # RGB 图像
            cv2.imwrite(
                os.path.join(cap_dir, "rgb.png"), cap["color_image"]
            )

            # 深度图 (colormap)
            cv2.imwrite(
                os.path.join(cap_dir, "depth_aligned.png"),
                cap["depth_colormap_aligned"],
            )

            # 深度 NPY
            np.save(
                os.path.join(cap_dir, "depth_aligned.npy"),
                cap["depth_aligned"],
            )

            # 位姿 JSON
            pr = cap["pose_result"]
            pose_data = {
                "timestamp": cap["timestamp"],
                "board_params": cap["board_params"],
                "intrinsics": cap["intrinsics"],
                "depth_scale": cap.get("depth_scale", 0.001),
                "success": bool(pr["success"]),
                "num_corners": pr.get("num_corners", 0),
            }
            if pr["success"]:
                pose_data["rvec"] = pr["rvec"].flatten().tolist()
                pose_data["tvec"] = pr["tvec"].flatten().tolist()
                pose_data["reproj_error_px"] = float(pr["reproj_error"])
            else:
                pose_data["rvec"] = None
                pose_data["tvec"] = None

            with open(os.path.join(cap_dir, "pose.json"), "w",
                      encoding="utf-8") as f:
                json.dump(pose_data, f, indent=2, ensure_ascii=False)

            # 带检测叠加的可视化图像
            if pr["success"]:
                color_intr = cap["intrinsics"]
                camera_matrix = np.array([
                    [color_intr["fx"], 0, color_intr["ppx"]],
                    [0, color_intr["fy"], color_intr["ppy"]],
                    [0, 0, 1],
                ], dtype=np.float32)
                vis = draw_detection_overlay(
                    cap["color_image"], pr, camera_matrix
                )
                cv2.imwrite(os.path.join(cap_dir, "rgb_detection.png"), vis)

            return True
        except Exception as e:
            logger.error(f"保存采集 {index} 失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 外部接口
    # ------------------------------------------------------------------

    def notify_camera_started(self):
        """外部通知相机已启动（如从采集页启动时调用）。"""
        self._preview_timer.start(33)
        self._update_cam_ui()

    def notify_camera_stopped(self):
        """外部通知相机已停止。"""
        self._preview_timer.stop()
        self._clear_preview()
        self._update_cam_ui()

    def get_capture_count(self):
        return len(self._captures)

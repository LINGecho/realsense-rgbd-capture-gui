"""
主窗口 UI。

使用 PyQt5 构建，包含参数控制区、图像显示区、日志输出区。
通过 QTimer 定时刷新图像，不阻塞 UI 线程。
"""

import os
import logging
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QComboBox, QCheckBox,
    QLineEdit, QTextEdit, QFileDialog, QHBoxLayout, QVBoxLayout,
    QGridLayout, QGroupBox, QSplitter, QMessageBox, QTabWidget,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap, QFont

from camera import RealSenseCamera, RealSenseCameraError
from utils.image_utils import cv_image_to_qpixmap, resize_for_display
from utils.save_utils import save_frame_data
from ui.calibration_tab import CalibrationTab
from ui.fusion_tab import FusionTab
import config

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """RealSense RGB-D 采集主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RealSense RGB-D 采集工具")
        self.setMinimumSize(1200, 800)

        # 状态
        self.camera = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_timer_tick)
        self._current_frames = None

        # 构建 UI
        self._init_ui()

        # 内部状态
        self._try_init_camera()

        # 日志
        self._log("程序已启动。请点击「启动相机」开始采集。")

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)

        # --- 标签页 ---
        self.tabs = QTabWidget()

        # 采集页
        self.capture_tab = QWidget()
        cap_layout = QVBoxLayout(self.capture_tab)
        cap_layout.setContentsMargins(4, 4, 4, 4)
        cap_layout.addWidget(self._create_control_panel())
        cap_layout.addWidget(self._create_image_panel(), stretch=1)

        self.tabs.addTab(self.capture_tab, "采集")

        # 标定页
        self.calib_tab = CalibrationTab(
            get_camera=lambda: self.camera,
            get_camera_running=lambda: (
                self.camera is not None and self.camera.is_running()
            ),
            start_camera_cb=self._on_start,
            stop_camera_cb=self._on_stop,
            get_frames=lambda: self._current_frames,
            get_intrinsics=lambda: (
                self.camera.get_intrinsics() if self.camera else None
            ),
            log_func=self._log,
        )

        self.tabs.addTab(self.calib_tab, "标定")

        # 融合页
        self.fusion_tab = FusionTab(log_func=self._log)
        self.tabs.addTab(self.fusion_tab, "融合")

        root_layout.addWidget(self.tabs)

        # --- 日志区 ---
        root_layout.addWidget(self._create_log_panel())

    def _create_control_panel(self):
        group = QGroupBox("参数控制")
        layout = QGridLayout(group)
        layout.setSpacing(6)

        # RGB 分辨率
        layout.addWidget(QLabel("RGB 分辨率:"), 0, 0)
        self.combo_color_res = QComboBox()
        for w, h in config.RESOLUTION_OPTIONS:
            self.combo_color_res.addItem(f"{w}x{h}", (w, h))
        self.combo_color_res.setCurrentText(
            f"{config.DEFAULT_COLOR_WIDTH}x{config.DEFAULT_COLOR_HEIGHT}"
        )
        layout.addWidget(self.combo_color_res, 0, 1)

        # Depth 分辨率
        layout.addWidget(QLabel("Depth 分辨率:"), 0, 2)
        self.combo_depth_res = QComboBox()
        for w, h in config.RESOLUTION_OPTIONS:
            self.combo_depth_res.addItem(f"{w}x{h}", (w, h))
        self.combo_depth_res.setCurrentText(
            f"{config.DEFAULT_DEPTH_WIDTH}x{config.DEFAULT_DEPTH_HEIGHT}"
        )
        layout.addWidget(self.combo_depth_res, 0, 3)

        # FPS
        layout.addWidget(QLabel("FPS:"), 0, 4)
        self.combo_fps = QComboBox()
        for fps in config.FPS_OPTIONS:
            self.combo_fps.addItem(str(fps), fps)
        self.combo_fps.setCurrentText(str(config.DEFAULT_FPS))
        layout.addWidget(self.combo_fps, 0, 5)

        # 启动 / 停止
        self.btn_start = QPushButton("启动相机")
        self.btn_start.clicked.connect(self._on_start)
        layout.addWidget(self.btn_start, 1, 0, 1, 2)

        self.btn_stop = QPushButton("停止相机")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        layout.addWidget(self.btn_stop, 1, 2, 1, 2)

        # 保存目录
        self.btn_dir = QPushButton("选择保存目录")
        self.btn_dir.clicked.connect(self._on_select_dir)
        layout.addWidget(self.btn_dir, 2, 0, 1, 2)

        self.label_dir = QLabel(os.path.abspath(config.DEFAULT_SAVE_DIR))
        self.label_dir.setFrameStyle(QLabel.Sunken)
        self.label_dir.setStyleSheet("padding: 2px 4px;")
        layout.addWidget(self.label_dir, 2, 2, 1, 4)

        # 文件名前缀
        layout.addWidget(QLabel("文件名前缀:"), 3, 0)
        self.edit_prefix = QLineEdit()
        self.edit_prefix.setPlaceholderText("留空自动使用时间戳")
        layout.addWidget(self.edit_prefix, 3, 1, 1, 3)

        # 保存按钮
        self.btn_save = QPushButton("保存当前帧")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setEnabled(False)
        layout.addWidget(self.btn_save, 3, 4, 1, 2)

        # 保存项复选框
        layout.addWidget(QLabel("保存内容:"), 4, 0)

        self._save_checkboxes = {}
        save_row = QHBoxLayout()
        for key in config.SAVE_ITEM_LABELS:
            cb = QCheckBox(config.SAVE_ITEM_LABELS[key])
            cb.setChecked(config.DEFAULT_SAVE_OPTIONS.get(key, True))
            self._save_checkboxes[key] = cb
            save_row.addWidget(cb)
        layout.addLayout(save_row, 4, 1, 1, 5)

        # 全选 / 取消全选
        select_row = QHBoxLayout()
        btn_select_all = QPushButton("全选")
        btn_select_all.clicked.connect(self._on_select_all_save)
        select_row.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("取消全选")
        btn_deselect_all.clicked.connect(self._on_deselect_all_save)
        select_row.addWidget(btn_deselect_all)

        select_row.addStretch()
        layout.addLayout(select_row, 5, 1, 1, 5)

        return group

    def _create_image_panel(self):
        group = QGroupBox("实时画面")
        layout = QHBoxLayout(group)

        # RGB
        rgb_box = QVBoxLayout()
        rgb_box.addWidget(QLabel("RGB 图像", alignment=Qt.AlignCenter))
        self.label_rgb = QLabel("等待相机...", alignment=Qt.AlignCenter)
        self.label_rgb.setMinimumSize(320, 240)
        self.label_rgb.setStyleSheet("background-color: #1a1a1a; color: #888;")
        self.label_rgb.setScaledContents(False)
        rgb_box.addWidget(self.label_rgb)
        layout.addLayout(rgb_box)

        # Raw Depth
        raw_box = QVBoxLayout()
        raw_box.addWidget(QLabel("Raw Depth", alignment=Qt.AlignCenter))
        self.label_depth_raw = QLabel("等待相机...", alignment=Qt.AlignCenter)
        self.label_depth_raw.setMinimumSize(320, 240)
        self.label_depth_raw.setStyleSheet("background-color: #1a1a1a; color: #888;")
        self.label_depth_raw.setScaledContents(False)
        raw_box.addWidget(self.label_depth_raw)
        layout.addLayout(raw_box)

        # Aligned Depth
        aligned_box = QVBoxLayout()
        aligned_box.addWidget(QLabel("Aligned Depth", alignment=Qt.AlignCenter))
        self.label_depth_aligned = QLabel("等待相机...", alignment=Qt.AlignCenter)
        self.label_depth_aligned.setMinimumSize(320, 240)
        self.label_depth_aligned.setStyleSheet("background-color: #1a1a1a; color: #888;")
        self.label_depth_aligned.setScaledContents(False)
        aligned_box.addWidget(self.label_depth_aligned)
        layout.addLayout(aligned_box)

        return group

    def _create_log_panel(self):
        group = QGroupBox("日志")
        layout = QHBoxLayout(group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        return group

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {msg}")
        # 限制行数
        if self.log_text.document().blockCount() > config.LOG_MAX_LINES:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.movePosition(cursor.Down, cursor.KeepAnchor, 100)
            cursor.removeSelectedText()

    # ------------------------------------------------------------------
    # 相机操作
    # ------------------------------------------------------------------

    def _try_init_camera(self):
        """尝试创建 RealSenseCamera 实例（不启动 pipeline）。"""
        try:
            self.camera = RealSenseCamera()
        except RealSenseCameraError as e:
            self.camera = None
            self._log(f"[ERROR] {e}")

    def _on_start(self):
        if self.camera is None:
            self._try_init_camera()
        if self.camera is None:
            QMessageBox.critical(
                self, "错误",
                "无法创建 RealSense 相机实例。\n"
                "请检查：\n"
                "1. pyrealsense2 是否已安装\n"
                "2. RealSense SDK 是否已安装\n"
                "3. 相机是否正确连接"
            )
            return

        color_w, color_h = self.combo_color_res.currentData()
        depth_w, depth_h = self.combo_depth_res.currentData()
        fps = self.combo_fps.currentData()

        try:
            self.camera.start(color_w, color_h, depth_w, depth_h, fps)
            self._log(
                f"相机已启动: RGB={color_w}x{color_h}, "
                f"Depth={depth_w}x{depth_h}, FPS={fps}"
            )
            self.timer.start(33)  # ~30 fps 刷新
            self._update_ui_state(running=True)
            self.calib_tab.notify_camera_started()
        except RealSenseCameraError as e:
            self._log(f"[ERROR] 相机启动失败: {e}")
            QMessageBox.warning(
                self, "启动失败",
                f"相机启动失败:\n{e}\n\n"
                "请尝试其他分辨率或检查 RealSense Viewer 中支持的 profile。"
            )

    def _on_stop(self):
        self.timer.stop()
        if self.camera:
            self.camera.stop()
        self._log("相机已停止。")
        self._current_frames = None
        self._clear_images()
        self._update_ui_state(running=False)
        self.calib_tab.notify_camera_stopped()

    def _update_ui_state(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_save.setEnabled(running)
        self.combo_color_res.setEnabled(not running)
        self.combo_depth_res.setEnabled(not running)
        self.combo_fps.setEnabled(not running)

    def _clear_images(self):
        text = "无画面"
        for label in [self.label_rgb, self.label_depth_raw, self.label_depth_aligned]:
            label.setText(text)
            label.setStyleSheet("background-color: #1a1a1a; color: #888;")

    # ------------------------------------------------------------------
    # 定时刷新图像
    # ------------------------------------------------------------------

    def _on_timer_tick(self):
        if self.camera is None or not self.camera.is_running():
            return
        frames = self.camera.get_frames()
        if frames is None:
            return
        self._current_frames = frames

        # RGB
        rgb = frames["color_image"]
        rgb_disp = resize_for_display(
            rgb, config.DISPLAY_MAX_WIDTH, config.DISPLAY_MAX_HEIGHT
        )
        self.label_rgb.setPixmap(cv_image_to_qpixmap(rgb_disp))

        # Raw Depth
        draw = frames["depth_colormap_raw"]
        draw_disp = resize_for_display(
            draw, config.DISPLAY_MAX_WIDTH, config.DISPLAY_MAX_HEIGHT
        )
        self.label_depth_raw.setPixmap(cv_image_to_qpixmap(draw_disp))

        # Aligned Depth
        dal = frames["depth_colormap_aligned"]
        dal_disp = resize_for_display(
            dal, config.DISPLAY_MAX_WIDTH, config.DISPLAY_MAX_HEIGHT
        )
        self.label_depth_aligned.setPixmap(cv_image_to_qpixmap(dal_disp))

    # ------------------------------------------------------------------
    # 选择保存目录
    # ------------------------------------------------------------------

    def _on_select_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if d:
            self.label_dir.setText(d)

    # ------------------------------------------------------------------
    # 保存当前帧
    # ------------------------------------------------------------------

    def _on_save(self):
        if self._current_frames is None:
            QMessageBox.information(self, "提示", "当前没有可用的帧数据，请先启动相机。")
            return

        save_dir = self.label_dir.text()
        if not save_dir:
            QMessageBox.warning(self, "警告", "请先选择保存目录。")
            return

        prefix = self.edit_prefix.text().strip()

        # 读取用户选择的保存项
        save_options = self._get_save_options()
        if not any(save_options.values()):
            QMessageBox.warning(self, "警告", "请至少选择一项保存内容。")
            return

        # 构建 metadata
        color_w, color_h = self.combo_color_res.currentData()
        depth_w, depth_h = self.combo_depth_res.currentData()
        fps = self.combo_fps.currentData()

        metadata = {
            "rgb_resolution": [color_w, color_h],
            "depth_resolution": [depth_w, depth_h],
            "fps": fps,
            "depth_scale": self.camera.get_depth_scale() if self.camera else 0.001,
        }

        intrinsics = self.camera.get_intrinsics() if self.camera else None
        if intrinsics:
            metadata.update({
                "color_intrinsics": intrinsics.get("color"),
                "depth_intrinsics": intrinsics.get("depth"),
                "aligned_depth_intrinsics": intrinsics.get("aligned_depth"),
            })
        else:
            metadata.update({
                "color_intrinsics": None,
                "depth_intrinsics": None,
                "aligned_depth_intrinsics": None,
            })
            self._log("[WARN] 未能获取相机内参，元数据中将写入 null")

        result = save_frame_data(save_dir, prefix, self._current_frames,
                                 metadata, save_options)
        if result:
            self._log(f"已保存 {len(result)} 项: {os.path.basename(save_dir)}")
        else:
            self._log("[ERROR] 保存失败")

    # ------------------------------------------------------------------
    # 保存项选择
    # ------------------------------------------------------------------

    def _get_save_options(self):
        """从复选框状态构建保存项选择字典。"""
        return {
            key: cb.isChecked()
            for key, cb in self._save_checkboxes.items()
        }

    def _on_select_all_save(self):
        for cb in self._save_checkboxes.values():
            cb.setChecked(True)

    def _on_deselect_all_save(self):
        for cb in self._save_checkboxes.values():
            cb.setChecked(False)

    # ------------------------------------------------------------------
    # 关闭窗口
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self.timer.stop()
        if self.camera and self.camera.is_running():
            self.camera.stop()
        self.calib_tab.notify_camera_stopped()
        self._log("程序退出。")
        event.accept()

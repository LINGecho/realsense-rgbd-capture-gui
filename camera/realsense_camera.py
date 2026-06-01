"""
RealSense 相机封装类。

负责相机的启动、停止、帧获取、内参获取。
所有帧数据以 numpy 数组形式返回。
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    import pyrealsense2 as rs
    HAS_REALSENSE = True
except ImportError:
    HAS_REALSENSE = False
    rs = None


class RealSenseCameraError(Exception):
    """RealSense 相机相关异常的基类。"""
    pass


class RealSenseCamera:
    """Intel RealSense 相机封装。

    管理 pipeline、align、profile 的生命周期，
    并对外提供统一的帧获取接口。
    """

    def __init__(self):
        if not HAS_REALSENSE:
            raise RealSenseCameraError(
                "pyrealsense2 未安装，请先安装: pip install pyrealsense2"
            )
        self.pipeline = None
        self.profile = None
        self.align = None
        self._running = False
        self._depth_scale = 0.001

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self, color_width, color_height, depth_width, depth_height, fps):
        """启动相机 pipeline 并配置流。

        Args:
            color_width, color_height: RGB 分辨率
            depth_width, depth_height: Depth 分辨率
            fps: 帧率

        Raises:
            RealSenseCameraError: 配置不支持或设备不可用
        """
        try:
            self.pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(
                rs.stream.color,
                color_width, color_height,
                rs.format.bgr8, fps,
            )
            config.enable_stream(
                rs.stream.depth,
                depth_width, depth_height,
                rs.format.z16, fps,
            )

            self.profile = self.pipeline.start(config)
            self.align = rs.align(rs.stream.color)
            self._running = True

            # 获取深度 scale
            depth_sensor = self.profile.get_device().first_depth_sensor()
            if depth_sensor is not None:
                self._depth_scale = depth_sensor.get_depth_scale()
            else:
                self._depth_scale = 0.001

            logger.info(
                "相机已启动 "
                f"RGB=({color_width},{color_height}) "
                f"Depth=({depth_width},{depth_height}) "
                f"FPS={fps} depth_scale={self._depth_scale:.6f}"
            )
        except RuntimeError as e:
            raise RealSenseCameraError(f"相机启动失败: {e}") from e

    def stop(self):
        """停止相机并释放 pipeline。"""
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
                logger.info("相机已停止")
            except Exception:
                pass
            self.pipeline = None
        self.profile = None
        self.align = None
        self._running = False

    def is_running(self):
        return self._running and self.pipeline is not None

    # ------------------------------------------------------------------
    # 帧获取
    # ------------------------------------------------------------------

    def get_frames(self):
        """等待并获取一帧对齐后的数据。

        Returns:
            dict or None:
                {
                    "color_image": np.ndarray (H,W,3) BGR,
                    "depth_raw": np.ndarray (H,W) uint16,
                    "depth_aligned": np.ndarray (H,W) uint16,
                    "depth_colormap_raw": np.ndarray (H,W,3) BGR colormap,
                    "depth_colormap_aligned": np.ndarray (H,W,3) BGR colormap,
                    "timestamp": float (ms),
                }
            失败时返回 None。
        """
        if not self.is_running():
            return None
        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=5000)
            aligned_frames = self.align.process(frames)

            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()
            aligned_depth_frame = aligned_frames.get_depth_frame()

            if not all([color_frame, depth_frame, aligned_depth_frame]):
                return None

            color_image = np.asanyarray(color_frame.get_data())           # BGR
            depth_raw = np.asanyarray(depth_frame.get_data())              # uint16
            depth_aligned = np.asanyarray(aligned_depth_frame.get_data())  # uint16

            # 伪彩色可视化图
            depth_colormap_raw = self._depth_to_colormap(depth_raw)
            depth_colormap_aligned = self._depth_to_colormap(depth_aligned)

            timestamp = frames.get_timestamp()

            return {
                "color_image": color_image,
                "depth_raw": depth_raw,
                "depth_aligned": depth_aligned,
                "depth_colormap_raw": depth_colormap_raw,
                "depth_colormap_aligned": depth_colormap_aligned,
                "timestamp": timestamp,
            }
        except RuntimeError:
            return None

    # ------------------------------------------------------------------
    # 内参 & 深度 scale
    # ------------------------------------------------------------------

    def get_intrinsics(self):
        """获取颜色和深度内参。

        Returns:
            dict or None: 包含 color/depth/aligned_depth 三个 intrinsics 字典
        """
        if not self.is_running() or self.profile is None:
            return None
        try:
            color_stream = self.profile.get_stream(
                rs.stream.color
            ).as_video_stream_profile()
            depth_stream = self.profile.get_stream(
                rs.stream.depth
            ).as_video_stream_profile()
            # 对齐后的深度流内参与颜色流一致（像素空间对齐）
            aligned_depth_stream = color_stream

            return {
                "color": self._intrinsics_to_dict(color_stream.get_intrinsics()),
                "depth": self._intrinsics_to_dict(depth_stream.get_intrinsics()),
                "aligned_depth": self._intrinsics_to_dict(
                    aligned_depth_stream.get_intrinsics()
                ),
            }
        except Exception as e:
            logger.warning(f"获取内参失败: {e}")
            return None

    def get_depth_scale(self):
        return self._depth_scale

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _depth_to_colormap(depth_image):
        """将 uint16 深度图转换为 BGR 伪彩色图。"""
        import cv2
        if depth_image is None:
            return None
        # 归一化到 0-255 并应用 colormap
        d = depth_image.astype(np.float32)
        d_max = np.max(d)
        if d_max > 0:
            d = d / d_max * 255.0
        d = np.clip(d, 0, 255).astype(np.uint8)
        colormap = cv2.applyColorMap(d, cv2.COLORMAP_JET)
        return colormap

    @staticmethod
    def _intrinsics_to_dict(intrinsics):
        """将 pyrealsense2.intrinsics 转为普通 dict。"""
        return {
            "width": intrinsics.width,
            "height": intrinsics.height,
            "fx": intrinsics.fx,
            "fy": intrinsics.fy,
            "ppx": intrinsics.ppx,
            "ppy": intrinsics.ppy,
            "model": str(intrinsics.model),
            "coeffs": list(intrinsics.coeffs),
        }

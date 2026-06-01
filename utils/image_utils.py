"""
图像处理工具函数。
"""

import cv2
import numpy as np
from PyQt5.QtGui import QPixmap, QImage


def depth_to_colormap(depth_image: np.ndarray) -> np.ndarray:
    """将 uint16 深度图转换为 BGR 伪彩色图。

    Args:
        depth_image: uint16 深度图，shape (H, W)

    Returns:
        BGR 格式的 colormap 图，shape (H, W, 3), dtype uint8
    """
    if depth_image is None:
        return np.zeros((480, 640, 3), dtype=np.uint8)
    d = depth_image.astype(np.float32)
    d_max = np.max(d)
    if d_max > 0:
        d = d / d_max * 255.0
    d = np.clip(d, 0, 255).astype(np.uint8)
    colormap = cv2.applyColorMap(d, cv2.COLORMAP_JET)
    return colormap


def cv_image_to_qpixmap(image: np.ndarray) -> QPixmap:
    """将 OpenCV BGR 图像转换为 Qt QPixmap。

    Args:
        image: numpy 数组，BGR 格式

    Returns:
        QPixmap
    """
    if image is None:
        return QPixmap()
    h, w = image.shape[:2]
    if len(image.shape) == 2:
        # 灰度图
        qimg = QImage(image.data, w, h, w, QImage.Format_Grayscale8)
    else:
        # BGR -> RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, rgb.shape[1] * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


def resize_for_display(image: np.ndarray, target_width: int, target_height: int) -> np.ndarray:
    """将图像等比缩放到目标尺寸以内。

    Args:
        image: numpy 数组
        target_width, target_height: 最大显示宽高

    Returns:
        缩放后的 numpy 数组
    """
    if image is None:
        return None
    h, w = image.shape[:2]
    scale = min(target_width / w, target_height / h, 1.0)
    if scale < 1.0:
        new_w = int(w * scale)
        new_h = int(h * scale)
        return cv2.resize(image, (new_w, new_h))
    return image

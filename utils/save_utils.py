"""
保存帧数据到磁盘。
"""

import os
import json
import time
import logging
from datetime import datetime

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class NumpyJSONEncoder(json.JSONEncoder):
    """支持 numpy 数值类型的 JSON 编码器。"""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _unique_path(save_dir: str, prefix: str, suffix: str) -> str:
    """生成不冲突的文件路径，冲突时追加时间戳。"""
    base = os.path.join(save_dir, f"{prefix}{suffix}")
    if not os.path.exists(base):
        return base
    # 冲突时追加时间戳
    ts = datetime.now().strftime("%H%M%S")
    alt = os.path.join(save_dir, f"{prefix}_{ts}{suffix}")
    return alt


def save_frame_data(save_dir: str, filename_prefix: str,
                    frame_dict: dict, metadata: dict) -> dict:
    """保存当前帧的全部数据。

    Args:
        save_dir: 保存目录
        filename_prefix: 文件名前缀（为空时自动使用时间戳）
        frame_dict: get_frames() 返回的帧数据字典
        metadata: 额外的元数据（内参、depth_scale 等）

    Returns:
        dict: 所有保存的文件路径，失败返回 None
    """
    if not frame_dict:
        logger.warning("帧数据为空，跳过保存")
        return None

    # 前缀为空时使用时间戳
    if not filename_prefix or not filename_prefix.strip():
        filename_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 确保保存目录存在
    os.makedirs(save_dir, exist_ok=True)

    try:
        file_paths = {}

        # RGB PNG
        rgb_path = _unique_path(save_dir, filename_prefix, "_rgb.png")
        cv2.imwrite(rgb_path, frame_dict["color_image"])
        file_paths["rgb_png"] = rgb_path

        # Raw Depth PNG (colormap)
        raw_png_path = _unique_path(save_dir, filename_prefix, "_depth_raw.png")
        cv2.imwrite(raw_png_path, frame_dict["depth_colormap_raw"])
        file_paths["depth_raw_png"] = raw_png_path

        # Aligned Depth PNG (colormap)
        aligned_png_path = _unique_path(save_dir, filename_prefix, "_depth_aligned.png")
        cv2.imwrite(aligned_png_path, frame_dict["depth_colormap_aligned"])
        file_paths["depth_aligned_png"] = aligned_png_path

        # Raw Depth NPY (uint16)
        raw_npy_path = _unique_path(save_dir, filename_prefix, "_depth_raw.npy")
        np.save(raw_npy_path, frame_dict["depth_raw"])
        file_paths["depth_raw_npy"] = raw_npy_path

        # Aligned Depth NPY (uint16)
        aligned_npy_path = _unique_path(save_dir, filename_prefix, "_depth_aligned.npy")
        np.save(aligned_npy_path, frame_dict["depth_aligned"])
        file_paths["depth_aligned_npy"] = aligned_npy_path

        # Meta JSON
        meta_path = _unique_path(save_dir, filename_prefix, "_meta.json")
        meta_json_path = os.path.join(save_dir, os.path.basename(meta_path))

        meta_content = {
            "save_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filename_prefix": filename_prefix,
            **metadata,
            "file_paths": {k: os.path.basename(v) for k, v in file_paths.items()},
        }
        file_paths["meta_json"] = meta_json_path

        with open(meta_json_path, "w", encoding="utf-8") as f:
            json.dump(meta_content, f, indent=2, ensure_ascii=False,
                      cls=NumpyJSONEncoder)

        logger.info(f"数据已保存: {filename_prefix} -> {save_dir}")
        return file_paths

    except Exception as e:
        logger.error(f"保存数据失败: {e}")
        return None

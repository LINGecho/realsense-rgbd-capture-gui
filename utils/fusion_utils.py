"""
多视角点云融合工具。

将多张标定图像（RGB + 对齐深度 + 位姿）映射到同一标定板坐标系，
合并为单个彩色点云。
"""

import os
import json
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _scan_masks(cap_dir: str) -> dict[str, str]:
    """扫描目录下的 mask 图像文件。

    匹配格式: <name>_mask.png 或 <name>_mask.jpg，
    例如 cup_mask.png → {"cup": "/path/to/cup_mask.png"}

    Returns:
        dict[mask_name, mask_path]
    """
    masks = {}
    if not os.path.isdir(cap_dir):
        return masks
    for fname in sorted(os.listdir(cap_dir)):
        base, ext = os.path.splitext(fname.lower())
        if ext not in (".png", ".jpg", ".jpeg"):
            continue
        if not base.endswith("_mask"):
            continue
        name = base[:-5]  # 去掉 "_mask" 后缀
        if name:
            masks[name] = os.path.join(cap_dir, fname)
    return masks


def load_capture_from_dir(cap_dir: str) -> dict | None:
    """从标定采集目录加载数据。

    Returns:
        dict 或 None:
            timestamp, board_params, intrinsics, success,
            rvec, tvec, depth_scale, rgb_path, depth_npy_path, masks
    """
    pose_file = os.path.join(cap_dir, "pose.json")
    rgb_file = os.path.join(cap_dir, "rgb.png")
    depth_file = os.path.join(cap_dir, "depth_aligned.npy")

    if not os.path.isfile(pose_file):
        logger.warning(f"跳过 {os.path.basename(cap_dir)}: 缺少 pose.json")
        return None
    if not os.path.isfile(rgb_file):
        logger.warning(f"跳过 {os.path.basename(cap_dir)}: 缺少 rgb.png")
        return None
    if not os.path.isfile(depth_file):
        logger.warning(f"跳过 {os.path.basename(cap_dir)}: 缺少 depth_aligned.npy")
        return None

    with open(pose_file, "r", encoding="utf-8") as f:
        pose_data = json.load(f)

    if not pose_data.get("success"):
        logger.warning(f"跳过 {os.path.basename(cap_dir)}: 位姿估计未成功")
        return None

    rvec = np.array(pose_data["rvec"], dtype=np.float32).reshape(3, 1)
    tvec = np.array(pose_data["tvec"], dtype=np.float32).reshape(3, 1)
    depth_scale = pose_data.get("depth_scale", 0.001)

    masks = _scan_masks(cap_dir)

    return {
        "name": os.path.basename(cap_dir),
        "timestamp": pose_data.get("timestamp", ""),
        "intrinsics": pose_data["intrinsics"],
        "rvec": rvec,
        "tvec": tvec,
        "depth_scale": depth_scale,
        "rgb_path": rgb_file,
        "depth_path": depth_file,
        "num_corners": pose_data.get("num_corners", 0),
        "reproj_error": pose_data.get("reproj_error_px", None),
        "masks": masks,
    }


def scan_capture_dirs(root_dir: str) -> list[dict]:
    """扫描目录下所有 calib_* 子目录并加载有效采集。

    Returns:
        list[dict]: 按名称排序的有效采集列表
    """
    captures = []
    if not os.path.isdir(root_dir):
        return captures

    for entry in sorted(os.listdir(root_dir)):
        sub = os.path.join(root_dir, entry)
        if not os.path.isdir(sub) or not entry.startswith("calib_"):
            continue
        cap = load_capture_from_dir(sub)
        if cap:
            captures.append(cap)

    logger.info(f"从 {root_dir} 加载了 {len(captures)} 个有效采集")
    return captures


def depth_to_point_cloud(depth_map: np.ndarray,
                         color_image: np.ndarray,
                         intrinsics: dict,
                         depth_scale: float,
                         point_skip: int = 4,
                         distance_max: float = 2.0,
                         masks: dict[str, np.ndarray] | None = None
                         ) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """将深度图反投影为相机坐标系下的 3D 点云。

    Args:
        depth_map: uint16 深度图 (H, W)
        color_image: BGR 彩色图 (H, W, 3)
        intrinsics: {"fx", "fy", "ppx", "ppy", "width", "height"}
        depth_scale: 深度单位 (RealSense 默认 0.001)
        point_skip: 每隔 N 个像素取一个点
        distance_max: 最远距离 (m)，超过的不取
        masks: 可选，{name: binary_mask_uint8(H,W)} 255=物体

    Returns:
        (points_cam, colors, mask_ids):
            points_cam (N,3), colors (N,3) BGR,
            mask_ids (N,) int32 或 None: -1=无mask, 0/1/2...=mask索引
    """
    fx = intrinsics["fx"]
    fy = intrinsics["fy"]
    cx = intrinsics["ppx"]
    cy = intrinsics["ppy"]

    h, w = depth_map.shape[:2]

    # 创建像素网格（跳采样）
    u = np.arange(0, w, point_skip)
    v = np.arange(0, h, point_skip)
    uu, vv = np.meshgrid(u, v)
    uu = uu.ravel()
    vv = vv.ravel()

    # 读取深度值并转换为米
    z_raw = depth_map[vv, uu].astype(np.float32)
    z_m = z_raw * depth_scale

    n_total = len(z_raw)
    n_invalid = int((z_raw == 0).sum())
    n_too_far = int((z_m >= distance_max).sum())

    # 过滤无效深度（0 或太远）
    valid = (z_raw > 0) & (z_m < distance_max)
    uu = uu[valid]
    vv = vv[valid]
    z_m = z_m[valid]

    n_valid = len(z_m)
    if n_valid == 0:
        logger.warning(
            f"深度反投影无有效点: 总={n_total}, 无效={n_invalid}, "
            f"超出距离={n_too_far}, 非零深度范围=[{z_raw[z_raw>0].min():.3f},{z_raw[z_raw>0].max():.3f}]m"
        )
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.float32), None

    logger.debug(
        f"深度反投影: 总={n_total}, 有效={n_valid}, "
        f"无效(0)={n_invalid}, 超距={n_too_far}, "
        f"Z范围=[{z_m.min():.3f},{z_m.max():.3f}]m"
    )

    # 反投影
    x = (uu - cx) * z_m / fx
    y = (vv - cy) * z_m / fy

    points_cam = np.stack([x, y, z_m], axis=-1)  # (N, 3)

    # 取对应颜色 (BGR)
    colors = color_image[vv, uu].astype(np.float32) / 255.0  # (N, 3)

    # 计算 mask 归属
    mask_ids = None
    if masks:
        mask_ids = np.full(n_valid, -1, dtype=np.int32)
        for i, (mask_name, mask_img) in enumerate(masks.items()):
            if mask_img.shape[:2] != (h, w):
                logger.warning(
                    f"Mask '{mask_name}' 尺寸 {mask_img.shape[:2]} "
                    f"与图像 ({h},{w}) 不匹配，跳过"
                )
                continue
            # 取采样像素处的 mask 值 (>127 视为前景)
            mask_vals = mask_img[vv, uu]
            hit = mask_vals > 127
            # 仅对尚未分配 mask 的点赋值（先匹配的优先）
            mask_ids[(mask_ids < 0) & hit] = i

    return points_cam, colors, mask_ids


def transform_to_board(points_cam: np.ndarray, rvec: np.ndarray,
                       tvec: np.ndarray) -> np.ndarray:
    """将相机坐标系点云变换到标定板坐标系。

    solvePnP 返回的 rvec/tvec 满足: P_cam = R @ P_board + t
    因此: P_board = R^T @ (P_cam - t)

    Args:
        points_cam: (N, 3) 相机坐标系点
        rvec: (3, 1) 罗德里格斯旋转向量
        tvec: (3, 1) 平移向量

    Returns:
        (N, 3) 标定板坐标系点
    """
    R, _ = cv2.Rodrigues(rvec)
    R_T = R.T  # (3, 3)
    t = tvec.reshape(3)

    # P_board = R^T @ (P_cam - t) = R^T @ P_cam - R^T @ t
    points_board = (R_T @ (points_cam - t).T).T

    return points_board


def fuse_captures(captures: list[dict],
                  voxel_size: float = 0.003,
                  point_skip: int = 4,
                  distance_max: float = 2.0,
                  mask_enabled: bool = False,
                  mask_colors: list[tuple[float, float, float]] | None = None
                  ) -> "open3d.geometry.PointCloud | None":
    """将多个采集融合为单个体素下采样点云。

    Args:
        mask_enabled: 是否启用 mask 高亮
        mask_colors: mask 高亮颜色列表 (RGB 0-1)，按分配顺序使用

    Returns:
        open3d.geometry.PointCloud 或 None
    """
    try:
        import open3d as o3d
    except ImportError:
        logger.error("open3d 未安装，请执行: pip install open3d")
        return None

    # 第一遍：发现所有 mask 名称，建立全局索引
    mask_name_to_idx: dict[str, int] = {}
    mask_names_all: list[str] = []
    if mask_enabled:
        for cap in captures:
            for mname in sorted(cap.get("masks", {}).keys()):
                if mname not in mask_name_to_idx:
                    mask_name_to_idx[mname] = len(mask_name_to_idx)
                    mask_names_all.append(mname)

    all_points = []
    all_colors = []

    for cap in captures:
        # 读取图像
        depth = np.load(cap["depth_path"])
        color = cv2.imread(cap["rgb_path"])
        if color is None:
            logger.warning(f"无法读取 {cap['rgb_path']}，跳过")
            continue

        # 准备 masks（按全局名称顺序加载，缺失的跳过）
        masks_loaded = None
        if mask_enabled and cap.get("masks") and mask_names_all:
            masks_loaded = {}
            for mname in mask_names_all:  # 按全局顺序
                mpath = cap["masks"].get(mname)
                if mpath is None:
                    continue
                mask_img = cv2.imread(mpath, cv2.IMREAD_GRAYSCALE)
                if mask_img is None:
                    logger.warning(f"无法读取 mask: {mpath}")
                    continue
                masks_loaded[mname] = mask_img

        # 反投影到相机坐标系
        pts_cam, cols, mask_ids = depth_to_point_cloud(
            depth, color, cap["intrinsics"],
            cap["depth_scale"], point_skip, distance_max,
            masks=masks_loaded if mask_enabled else None,
        )

        if len(pts_cam) == 0:
            logger.warning(f"{cap['name']}: 无有效深度点，跳过")
            continue

        # 应用 mask 高亮颜色
        if mask_ids is not None and len(mask_names_all) > 0:
            # 重映射本地索引 → 全局索引
            local_names = list(masks_loaded.keys())
            local_to_global = np.array(
                [mask_name_to_idx.get(n, -1) for n in local_names],
                dtype=np.int32,
            )
            remapped = np.full_like(mask_ids, -1)
            for li, gi in enumerate(local_to_global):
                if gi >= 0:
                    remapped[mask_ids == li] = gi
            mask_ids = remapped

            # 上色
            default_colors = mask_colors or [
                (1.0, 0.15, 0.15),  # 默认亮红
            ]
            for gi, mname in enumerate(mask_names_all):
                color_idx = gi % len(default_colors)
                hl = default_colors[color_idx]
                hl_bgr = (hl[2], hl[1], hl[0])  # RGB → BGR
                hit = mask_ids == gi
                cols[hit] = np.array(hl_bgr, dtype=np.float32)

        # 变换到标定板坐标系
        pts_board = transform_to_board(pts_cam, cap["rvec"], cap["tvec"])

        all_points.append(pts_board)
        all_colors.append(cols)

        mask_info = ""
        if mask_ids is not None:
            mask_counts = ", ".join(
                f"{mask_names_all[gi]}={(mask_ids == gi).sum()}"
                for gi in range(len(mask_names_all))
                if (mask_ids == gi).any()
            )
            mask_info = f", mask点: [{mask_counts}]"
        logger.info(
            f"  {cap['name']}: {len(pts_board)} 个点, "
            f"板坐标范围 [{pts_board[:,0].min():.2f},{pts_board[:,0].max():.2f}] "
            f"[{pts_board[:,1].min():.2f},{pts_board[:,1].max():.2f}] "
            f"[{pts_board[:,2].min():.2f},{pts_board[:,2].max():.2f}]"
            f"{mask_info}"
        )

    if not all_points:
        logger.error("没有有效点云可融合")
        return None

    # 合并
    merged_pts = np.vstack(all_points)
    merged_cols = np.vstack(all_colors)

    logger.info(
        f"融合点云: {merged_pts.shape[0]} 个点 (来自 {len(all_points)} 个视角)"
    )
    if mask_enabled and mask_names_all:
        logger.info(f"Mask 对象: {', '.join(mask_names_all)}")

    # 构建 Open3D 点云
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(merged_pts)
    pcd.colors = o3d.utility.Vector3dVector(merged_cols[:, ::-1])  # BGR -> RGB

    # 体素下采样
    if voxel_size > 0:
        n_before = len(pcd.points)
        pcd = pcd.voxel_down_sample(voxel_size)
        logger.info(
            f"体素下采样 ({voxel_size}m): {n_before} -> {len(pcd.points)} 个点"
        )

    return pcd


def save_point_cloud_ply(pcd, filepath: str):
    """保存点云为 PLY 文件。"""
    try:
        import open3d as o3d
        o3d.io.write_point_cloud(filepath, pcd)
        logger.info(f"点云已保存: {filepath}")
    except ImportError:
        logger.error("open3d 未安装")
    except Exception as e:
        logger.error(f"保存 PLY 失败: {e}")

"""
Charuco 标定板检测与位姿估计 (兼容 OpenCV 4.7+ / 5.x)。
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def create_charuco_board(squares_x: int, squares_y: int,
                         square_length: float, marker_length: float,
                         dict_name: str):
    """创建 Charuco 板对象和对应的 ArUco 字典。

    Returns:
        (board, aruco_dict)
    """
    # 显式类型转换，避免 QSpinBox/QDoubleSpinBox 类型问题
    squares_x = int(squares_x)
    squares_y = int(squares_y)
    square_length = float(square_length)
    marker_length = float(marker_length)
    dict_name = str(dict_name)

    # 参数合法性检查
    if squares_x <= 1 or squares_y <= 1:
        raise ValueError(f"棋盘格行列数必须 > 1, 当前: {squares_x}x{squares_y}")
    if marker_length <= 0:
        raise ValueError(f"标记边长必须 > 0, 当前: {marker_length}")
    if square_length <= marker_length:
        raise ValueError(
            f"方格边长({square_length})必须大于标记边长({marker_length})"
        )

    aruco_dict = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, dict_name)
    )
    # 某些 OpenCV 4.x Python 绑定中 squareLength/markerLength 参数顺序可能颠倒
    try:
        board = cv2.aruco.CharucoBoard(
            (squares_x, squares_y), square_length, marker_length, aruco_dict
        )
    except cv2.error:
        logger.debug("CharucoBoard 标准参数顺序失败，尝试交换 square/marker length")
        board = cv2.aruco.CharucoBoard(
            (squares_x, squares_y), marker_length, square_length, aruco_dict
        )
    # 兼容 4.6.0 之前的 Charuco 板生成模式
    # 8x8 为偶数行，若板子是旧版工具生成的，必须开启 legacy pattern
    board.setLegacyPattern(True)
    return board, aruco_dict


def detect_charuco_pose(image: np.ndarray, board, aruco_dict,
                        camera_matrix: np.ndarray,
                        dist_coeffs: np.ndarray | None = None
                        ) -> dict | None:
    """在图像中检测 Charuco 板并估计位姿。

    自动适配 OpenCV 4.7+/5.x API (CharucoDetector)。

    Args:
        image: BGR 图像
        board: cv2.aruco.CharucoBoard
        aruco_dict: cv2.aruco.Dictionary (未使用，保留兼容性)
        camera_matrix: 3x3 相机内参矩阵
        dist_coeffs: 畸变系数，默认零畸变

    Returns:
        dict:
            success: bool
            rvec: (3,1) 旋转向量 (Rodrigues)
            tvec: (3,1) 平移向量
            charuco_corners: (N,1,2) 插值后的角点
            charuco_ids: (N,1) 角点 ID
            marker_corners: 检测到的 marker 角点
            marker_ids: 检测到的 marker ID
            reproj_error: float 重投影误差 (像素)
            num_corners: int 检测到的角点数
    """
    if dist_coeffs is None:
        dist_coeffs = np.zeros((5, 1), dtype=np.float32)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # --- OpenCV 4.7+ / 5.x: CharucoDetector ---
    detector = cv2.aruco.CharucoDetector(board)

    charuco_params = cv2.aruco.CharucoParameters()
    charuco_params.cameraMatrix = camera_matrix
    charuco_params.distCoeffs = dist_coeffs
    detector.setCharucoParameters(charuco_params)

    charuco_corners, charuco_ids, marker_corners, marker_ids = \
        detector.detectBoard(gray)

    n_markers = len(marker_ids) if marker_ids is not None else 0
    n_corners = len(charuco_ids) if charuco_ids is not None else 0
    logger.info(
        f"detectBoard: 检测到 {n_markers} 个标记, "
        f"{n_corners} 个 Charuco 角点"
    )

    if n_markers == 0:
        logger.warning("未检测到任何 ArUco 标记")
        return {"success": False, "num_corners": 0, "num_markers": 0}

    if n_corners < 4:
        logger.warning(
            f"Charuco 角点不足: {n_corners} (需要 >= 4)，"
            f" 标记数={n_markers}。请调整拍摄角度或检查光照。"
        )
        return {
            "success": False,
            "num_corners": n_corners,
            "num_markers": n_markers,
            "marker_corners": marker_corners,
            "marker_ids": marker_ids,
        }

    # --- solvePnP 估计位姿 ---
    ids_flat = np.asarray(charuco_ids, dtype=np.intp).ravel()
    board_corners_3d = np.asarray(board.getChessboardCorners(), dtype=np.float32)
    logger.info(
        f"棋盘格总角点数: {len(board_corners_3d)}, "
        f"检测到的角点 ID 范围: [{ids_flat.min()}, {ids_flat.max()}]"
    )

    obj_points = board_corners_3d[ids_flat]
    img_points = np.asarray(charuco_corners, dtype=np.float32).reshape(-1, 2)

    success, rvec, tvec = cv2.solvePnP(
        obj_points, img_points, camera_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )

    if not success:
        logger.warning(
            f"solvePnP 位姿估计失败: "
            f"obj_points={obj_points.shape}, img_points={img_points.shape}, "
            f"camera_matrix=\n{camera_matrix}"
        )
        return {
            "success": False,
            "num_corners": n_corners,
            "num_markers": n_markers,
            "charuco_corners": charuco_corners,
            "charuco_ids": charuco_ids,
            "marker_corners": marker_corners,
            "marker_ids": marker_ids,
        }

    # 重投影误差
    img_points_proj, _ = cv2.projectPoints(
        obj_points, rvec, tvec, camera_matrix, dist_coeffs
    )
    reproj_error = float(
        np.linalg.norm(
            img_points - img_points_proj.reshape(-1, 2), axis=1
        ).mean()
    )

    logger.info(
        f"Charuco 位姿估计成功: 角点={len(charuco_ids)}, "
        f"重投影误差={reproj_error:.4f} px"
    )

    return {
        "success": True,
        "rvec": rvec,
        "tvec": tvec,
        "charuco_corners": charuco_corners,
        "charuco_ids": charuco_ids,
        "marker_corners": marker_corners,
        "marker_ids": marker_ids,
        "reproj_error": reproj_error,
        "num_corners": len(charuco_ids),
    }


def draw_detection_overlay(image: np.ndarray, result: dict,
                           camera_matrix: np.ndarray,
                           dist_coeffs: np.ndarray | None = None) -> np.ndarray:
    """在图像上绘制 Charuco 检测结果和坐标轴。

    Returns:
        BGR 图像（副本）
    """
    if dist_coeffs is None:
        dist_coeffs = np.zeros((5, 1), dtype=np.float32)

    vis = image.copy()

    if not result.get("success"):
        mc = result.get("marker_corners")
        mi = result.get("marker_ids")
        if mc and mi is not None:
            cv2.aruco.drawDetectedMarkers(vis, mc, mi)
        cv2.putText(vis, "Detection Failed", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        return vis

    # 角点
    cc = result.get("charuco_corners")
    ci = result.get("charuco_ids")
    if cc is not None and ci is not None:
        cv2.aruco.drawDetectedCornersCharuco(vis, cc, ci, (0, 255, 0))

    # markers
    mc = result.get("marker_corners")
    mi = result.get("marker_ids")
    if mc and mi is not None:
        cv2.aruco.drawDetectedMarkers(vis, mc, mi)

    # 坐标轴
    rvec = result["rvec"]
    tvec = result["tvec"]
    cv2.drawFrameAxes(vis, camera_matrix, dist_coeffs, rvec, tvec, 0.05, 3)

    # 位姿文本
    rx, ry, rz = rvec.flatten()
    tx, ty, tz = tvec.flatten()
    cv2.putText(vis, f"R: [{rx:.3f}, {ry:.3f}, {rz:.3f}]", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.putText(vis, f"t: [{tx:.3f}, {ty:.3f}, {tz:.3f}]", (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    err = result.get("reproj_error", 0)
    cv2.putText(vis, f"Reproj: {err:.4f}px", (10, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    return vis

"""
默认配置常量。
"""

# 默认相机参数
DEFAULT_COLOR_WIDTH = 1280
DEFAULT_COLOR_HEIGHT = 720
DEFAULT_DEPTH_WIDTH = 848
DEFAULT_DEPTH_HEIGHT = 480
DEFAULT_FPS = 30

# 可选分辨率列表 (width, height)
RESOLUTION_OPTIONS = [
    (640, 480),
    (848, 480),
    (1280, 720),
]

# 可选帧率列表
FPS_OPTIONS = [6, 15, 30, 60]

# 默认保存目录（相对于项目根目录）
DEFAULT_SAVE_DIR = "data"

# 图像显示区域最大宽度（超出后等比缩放）
DISPLAY_MAX_WIDTH = 480
DISPLAY_MAX_HEIGHT = 360

# 日志最大行数
LOG_MAX_LINES = 500

# 默认保存项选择：全部开启
DEFAULT_SAVE_OPTIONS = {
    "rgb_png": True,
    "depth_raw_png": True,
    "depth_aligned_png": True,
    "depth_raw_npy": True,
    "depth_aligned_npy": True,
    "meta_json": True,
}

# 保存项的中文标签（key -> 显示名）
SAVE_ITEM_LABELS = {
    "rgb_png": "RGB 图",
    "depth_raw_png": "Raw深度图",
    "depth_aligned_png": "对齐深度图",
    "depth_raw_npy": "Raw深度(NPY)",
    "depth_aligned_npy": "对齐深度(NPY)",
    "meta_json": "元数据",
}

# Charuco 标定板默认参数
DEFAULT_CHARUCO_SQUARES_X = 8
DEFAULT_CHARUCO_SQUARES_Y = 8
DEFAULT_CHARUCO_SQUARE_LENGTH = 0.012   # 米 (12mm)
DEFAULT_CHARUCO_MARKER_LENGTH = 0.009   # 米 (9mm)
DEFAULT_CHARUCO_DICT_NAME = "DICT_4X4_50"

# ArUco 字典选项（OpenCV 标准预定义字典全集）
CHARUCO_DICT_OPTIONS = [
    "DICT_4X4_50", "DICT_4X4_100", "DICT_4X4_250", "DICT_4X4_1000",
    "DICT_5X5_50", "DICT_5X5_100", "DICT_5X5_250", "DICT_5X5_1000",
    "DICT_6X6_50", "DICT_6X6_100", "DICT_6X6_250", "DICT_6X6_1000",
    "DICT_7X7_50", "DICT_7X7_100", "DICT_7X7_250", "DICT_7X7_1000",
]

# 点云融合默认参数
DEFAULT_DEPTH_SCALE = 0.001           # RealSense D4xx 默认深度单位 (m)
DEFAULT_FUSION_VOXEL_SIZE = 0.003     # 体素下采样大小 (m)
DEFAULT_FUSION_DISTANCE_MAX = 2.0     # 最远距离过滤 (m)
DEFAULT_FUSION_POINT_SKIP = 4         # 每隔 N 个像素取一个点（加速）

# Mask 高亮颜色调色板（RGB 0-1 范围，用于 Open3D 点云显示）
# 每个 mask 按发现顺序依次分配颜色
MASK_HIGHLIGHT_COLORS = [
    (1.0, 0.15, 0.15),     # 亮红
    (0.15, 1.0, 0.15),     # 亮绿
    (1.0, 1.0, 0.15),      # 亮黄
    (0.15, 1.0, 1.0),      # 亮青
    (1.0, 0.15, 1.0),      # 亮品红
    (0.15, 0.50, 1.0),     # 亮蓝
    (1.0, 0.55, 0.15),     # 亮橙
    (0.55, 0.15, 1.0),     # 亮紫
]

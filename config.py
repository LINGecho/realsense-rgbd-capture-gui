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

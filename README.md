# RealSense RGB-D 采集工具

基于 PyQt5 的 Intel RealSense 相机 RGB-D 数据采集 GUI 工具，支持实时预览、参数调节和本地保存。

## 功能

- 实时显示 RGB / Raw Depth / Aligned Depth 三路画面
- 支持分辨率和帧率调节（通过下拉框选择）
- 一键保存当前帧：RGB PNG + Depth colormap PNG + Depth uint16 NPY + Meta JSON
- 自动对齐深度图到彩色图（`rs.align`）
- 文件名前缀自定义，冲突自动追加时间戳
- 完整的相机内参记录（color / depth / aligned_depth intrinsics）
- 日志区显示启动状态、配置、保存路径和错误信息

## 环境要求

本工具使用 **conda 环境** `py_envs`，不需要额外创建虚拟环境。

## 安装与运行

```bash
# 1. 切换到项目目录
cd realsense_ui

# 2. 激活 conda 环境
conda activate py_envs

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行
python main.py
```

## 依赖

| 包 | 用途 |
|---|---|
| `pyrealsense2` | Intel RealSense SDK 的 Python 绑定 |
| `opencv-python` | 图像处理、colormap、保存 PNG |
| `numpy` | 深度数据存储（.npy） |
| `PyQt5` | GUI 界面 |

## UI 操作流程

1. 启动程序：`python main.py`
2. 在顶部控制区选择 RGB 分辨率、Depth 分辨率和 FPS
3. 点击「启动相机」——三路画面开始实时刷新
4. 点击「选择保存目录」指定数据存储位置（默认为 `./data/`）
5. 在「文件名前缀」输入框中输入命名（如 `object_001`），留空则自动使用时间戳
6. 点击「保存当前帧」保存当前画面
7. 点击「停止相机」释放设备
8. 关闭窗口时自动停止相机

## 保存的数据格式

每次保存生成以下文件（以 `object_001` 为例）：

| 文件 | 格式 | 说明 |
|---|---|---|
| `object_001_rgb.png` | PNG | 彩色图像（BGR 格式保存） |
| `object_001_depth_raw.png` | PNG | 原始深度 colormap 可视化图 |
| `object_001_depth_aligned.png` | PNG | 对齐后深度 colormap 可视化图 |
| `object_001_depth_raw.npy` | NPY | 原始深度 uint16 数据 |
| `object_001_depth_aligned.npy` | NPY | 对齐后深度 uint16 数据 |
| `object_001_meta.json` | JSON | 相机内参、depth_scale、分辨率、保存时间等 |

**注意**：深度值单位 = uint16 像素值 × `depth_scale`（通常约 0.001m = 1mm），`depth_scale` 记录在 meta.json 中。

### meta.json 示例

```json
{
  "save_time": "2025-01-15 14:30:00",
  "filename_prefix": "object_001",
  "rgb_resolution": [1280, 720],
  "depth_resolution": [848, 480],
  "fps": 30,
  "depth_scale": 0.0010000000474974513,
  "color_intrinsics": {
    "width": 1280, "height": 720,
    "fx": 918.1, "fy": 917.8,
    "ppx": 640.0, "ppy": 360.0,
    "model": "distortion.inverse_brown_conrady",
    "coeffs": [0.0, 0.0, 0.0, 0.0, 0.0]
  },
  "depth_intrinsics": { ... },
  "aligned_depth_intrinsics": { ... },
  "file_paths": { ... }
}
```

## 项目结构

```
realsense_ui/
├── README.md
├── requirements.txt
├── main.py                  # 程序入口
├── config.py                # 默认配置常量
├── camera/
│   ├── __init__.py
│   └── realsense_camera.py  # RealSense 相机封装类
├── ui/
│   ├── __init__.py
│   └── main_window.py       # PyQt5 主窗口 UI
├── utils/
│   ├── __init__.py
│   ├── image_utils.py       # 图像转换工具
│   └── save_utils.py        # 数据保存工具
└── data/                    # 默认保存目录
    └── .gitkeep
```

## 常见问题

### 1. 找不到 RealSense 相机

- 检查 USB 线缆是否连接正常
- 确认相机没有被 RealSense Viewer 占用（关闭 Viewer 后再试）
- 在 RealSense Viewer 中确认相机能正常出图
- 如果 RealSense Viewer 都打不开，Python 程序也大概率打不开，请先排查硬件/驱动问题

### 2. pyrealsense2 安装失败

**Windows**：
- 需要先安装 [Intel RealSense SDK 2.0](https://github.com/IntelRealSense/librealsense/releases)
- 安装完成后重启电脑
- 确认 Python 版本与 SDK 兼容（推荐 Python 3.8 - 3.11）
- 确认 pip 为最新版: `pip install --upgrade pip`

**Linux**：
- 需要安装 librealsense2: `sudo apt install librealsense2-dev`
- 或从源码编译 librealsense2
- 确认内核模块已加载: `modprobe uvcvideo`

**macOS**：
- pyrealsense2 在 macOS 上支持有限，建议使用 Windows/Linux

### 3. 图像不刷新或卡顿

- 确认相机已点击「启动相机」
- 查看日志区是否有异常信息
- 尝试降低分辨率或帧率（如 640x480@15）
- 检查 USB 带宽是否充足（避免使用 USB Hub，直接插主板 USB 3.0 口）

### 4. Depth 图像全黑或太暗

- Depth 原始数据是 uint16，值域可能到几千，不能直接当普通图像显示
- 本工具已使用 `cv2.COLORMAP_JET` 做 colormap 可视化
- 如果仍偏暗，可能被测物体超出了相机有效范围（D415: ~0.3m-10m, D435: ~0.3m-3m）
- 检查 RealSense Viewer 中 Depth 是否正常显示

### 5. 分辨率不支持导致启动失败

- 换成 640x480@30 再试（这是大多数 RealSense 型号都支持的配置）
- 在 RealSense Viewer 中查看当前相机支持的 stream profile
- 日志区会显示具体错误信息

### 6. 启动时报 "pyrealsense2 未安装"

- 确认当前在 `py_envs` conda 环境下
- 运行 `pip show pyrealsense2` 检查是否已安装
- 如果在 Windows 上 pip 无法安装，请先安装 Intel RealSense SDK（见问题 2）

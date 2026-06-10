# RealSense RGB-D 采集工具

基于 PyQt5 的 Intel RealSense 相机 RGB-D 数据采集 GUI 工具，支持实时预览、参数调节、标定拍摄和点云融合。

## 功能

### 采集页
- 实时显示 RGB / Raw Depth / Aligned Depth 三路画面
- 支持分辨率和帧率调节（通过下拉框选择）
- 保存内容可勾选：RGB PNG、深度图 PNG、深度 NPY、元数据 JSON
- 一键保存当前帧，文件名前缀自定义，冲突自动追加时间戳
- 自动对齐深度图到彩色图（`rs.align`）
- 完整的相机内参记录（color / depth / aligned_depth intrinsics）

### 标定页
- Charuco 标定板参数可配置（棋盘格行列数、方格/标记边长、ArUco 字典）
- 实时 RGB + Aligned Depth 预览
- 拍摄当前帧并自动进行 Charuco 角点检测与位姿估计（PnP）
- 采集列表管理：查看检测叠加、删除、批量保存
- 保存内容：RGB 图、深度图、深度 NPY、位姿 JSON、检测可视化图

### 融合页
- 多视角点云融合（标定板坐标系对齐）
- 体素下采样、距离过滤、跳像素采样等参数可调
- 支持 Mask 高亮：加载 `*_mask.png` 二值图像，mask 区域用高亮颜色显示
- 支持多个 mask 对象，不同对象自动分配不同颜色
- 融合结果可导出 PLY 文件

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
| `opencv-python` | 图像处理、ArUco 检测、colormap、保存 PNG |
| `numpy` | 深度数据存储（.npy） |
| `PyQt5` | GUI 界面 |
| `open3d` | 点云处理与 TSDF 融合（融合页需要） |

## UI 操作流程

### 采集
1. 启动程序：`python main.py`
2. 在「采集」页顶部控制区选择 RGB 分辨率、Depth 分辨率和 FPS
3. 勾选需要保存的内容项
4. 点击「启动相机」——三路画面开始实时刷新
5. 点击「选择保存目录」指定数据存储位置（默认为 `./data/`）
6. 点击「保存当前帧」保存当前画面
7. 点击「停止相机」释放设备

### 标定
1. 切换到「标定」页，配置 Charuco 板参数
2. 点击「启动相机」，确认 RGB 和 Depth 预览正常
3. 将标定板置于相机视野中，点击「拍摄当前帧」
4. 系统自动检测角点并估计位姿，结果显示在右侧位姿面板
5. 从多个角度重复拍摄（建议 15-30 张）
6. 在采集列表中可选中记录查看检测叠加图
7. 点击「保存全部」将采集数据批量导出

### 融合
1. 切换到「融合」页
2. 点击「浏览...」选择包含 `calib_*` 子目录的标定数据根目录，点击「加载」
3. 在列表中勾选要参与融合的帧（默认全选）
4. 调整体素大小、距离阈值、像素跳采等参数
5. 如需高亮特定物体，勾选「启用 Mask 高亮」——系统自动查找 `*_mask.png`
6. 点击「融合并显示」在 Open3D 窗口中查看结果
7. 点击「保存 PLY」导出点云

## 保存的数据格式

### 采集页保存

每次保存生成以下文件（以 `object_001` 为例，按勾选内容生成）：

| 文件 | 格式 | 说明 |
|---|---|---|
| `object_001_rgb.png` | PNG | 彩色图像（BGR 格式保存） |
| `object_001_depth_raw.png` | PNG | 原始深度 colormap 可视化图 |
| `object_001_depth_aligned.png` | PNG | 对齐后深度 colormap 可视化图 |
| `object_001_depth_raw.npy` | NPY | 原始深度 uint16 数据 |
| `object_001_depth_aligned.npy` | NPY | 对齐后深度 uint16 数据 |
| `object_001_meta.json` | JSON | 相机内参、depth_scale、分辨率、保存时间等 |

### 标定页保存

每次标定拍摄保存到 `calib_XXX_<timestamp>/` 子目录：

| 文件 | 格式 | 说明 |
|---|---|---|
| `rgb.png` | PNG | 彩色图像 |
| `depth_aligned.png` | PNG | 对齐后深度 colormap 图 |
| `depth_aligned.npy` | NPY | 对齐后深度 uint16 数据 |
| `pose.json` | JSON | 位姿估计结果（rvec/tvec/重投影误差） |
| `rgb_detection.png` | PNG | 带角点检测叠加的可视化图（仅成功时） |

### 融合页 Mask 图像格式

放置在 `calib_*` 子目录中，命名规则 `<对象名>_mask.png`（或 `.jpg`）：

| 项目 | 要求 |
|---|---|
| 命名 | `对象名_mask.png`，如 `cup_mask.png` |
| 分辨率 | 与同目录 `rgb.png` 一致 |
| 格式 | PNG 或 JPG，灰度图 |
| 像素 | 白色(>127) = 目标物体，黑色(≤127) = 背景 |
| 数量 | 每个目录可放多个，不同对象分配不同高亮色 |

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
├── main.py                      # 程序入口
├── config.py                    # 默认配置常量
├── camera/
│   ├── __init__.py
│   └── realsense_camera.py      # RealSense 相机封装类
├── ui/
│   ├── __init__.py
│   ├── main_window.py           # PyQt5 主窗口（采集页 + 标签页容器）
│   ├── calibration_tab.py       # 标定页（Charuco 检测 + 位姿估计）
│   └── fusion_tab.py            # 融合页（TSDF 点云融合）
├── utils/
│   ├── __init__.py
│   ├── image_utils.py           # 图像转换工具
│   ├── save_utils.py            # 数据保存工具
│   ├── calibration_utils.py     # Charuco 检测与位姿估计
│   └── fusion_utils.py          # TSDF 融合算法
└── data/                        # 默认保存目录
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

### 7. 标定拍摄后预览卡住

- 拍摄完成后实时预览应继续运行
- 位姿结果显示在右侧文本区，不会影响画面刷新
- 如需查看某条采集的检测叠加图，在列表中点击对应行即可

### 8. Mask 高亮不生效

- 确认融合页已勾选「启用 Mask 高亮」
- 确认 mask 文件命名格式为 `<对象名>_mask.png`（下划线不可省略）
- 确认 mask 分辨率与同目录 `rgb.png` 完全一致
- 确认 mask 是灰度图且有白色区域（像素值 > 127）
- 查看日志区是否有 mask 加载/尺寸不匹配的警告

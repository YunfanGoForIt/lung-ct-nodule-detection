# 肺部 CT 结节检测与可视化系统

本工程按 `肺部CT结节检测大作业设计文档-2.md` 的 Stage0-5 Pipeline 实现：

- Stage0：解析 `.mhd` 头文件，读取 `.raw` 原始体数据，保留 HU 浮点体数据，并做肺窗窗宽窗位输出。
- Stage1：阈值、形态学开闭、连通域、空洞填充生成肺实质掩膜。
- Stage2：二维 FFT + 高斯差频域带通滤波增强中尺度结节结构。
- Stage3：在肺 ROI 内做候选亮斑检测、连通域提取与面积范围筛选。
- Stage4：计算几何、灰度统计、GLCM 纹理特征，并用圆形度/直径/HU 规则削减假阳性。
- Stage5：输出带标注 2D 切片、肺掩膜、带通增强图、伪彩色 MIP 与 `features.csv`。

本机已安装 OpenCV 与 CMake。核心 Pipeline 仍采用轻量 C++17 实现，保证端到端测试不依赖真实 LUNA16 数据；交互浏览界面使用 OpenCV HighGUI，图像输出使用标准 PGM/PPM，可被 OpenCV 直接读取。

## 构建

```bash
make
```

会生成：

- `build/lung_pipeline`：命令行检测程序。
- `build/lung_viewer`：OpenCV 切片浏览界面。

## 端到端测试

```bash
make test
```

测试会自动生成一个 64x64x16 的合成 `.mhd/.raw` CT 体数据，包含两叶肺和一个模拟结节，然后完整运行 Stage0-5。通过后会在 `build/e2e_output/` 下生成：

- `meta.txt`：体数据尺寸、spacing、窗宽窗位与带通参数。
- `features.csv`：候选结节中心、直径、圆形度、HU 统计和 GLCM 特征。
- `mip.ppm`：伪彩色最大密度投影。
- `slice_XXX_window.pgm`：窗宽窗位切片。
- `slice_XXX_mask.pgm`：肺实质掩膜。
- `slice_XXX_bandpass.pgm`：频域带通增强图。
- `slice_XXX_overlay.ppm`：绿色肺轮廓 + 红色结节标注叠加图。

## 运行真实数据

```bash
./build/lung_pipeline path/to/case.mhd output/case_result
```

可选参数：

```bash
--wl -600 --ww 1500 --sigma-low 30 --sigma-high 5 --min-diameter 3 --max-diameter 30
```

小尺寸合成数据可使用更小的带通尺度：

```bash
./build/lung_pipeline build/synthetic_case/synthetic.mhd build/cli_run_tuned --sigma-low 12 --sigma-high 2.5 --max-diameter 14
```

## 打开图形界面

先确认已经有输出目录，例如端到端测试生成的 `build/e2e_output/`，然后运行：

```bash
./build/lung_viewer build/e2e_output
```

界面包含：

- `control`：滑条控制切片编号。
- `viewer`：2x2 面板，依次显示窗宽窗位图、肺掩膜、频域带通增强图、检测叠加图。
- `mip`：伪彩色最大密度投影。

快捷键：

- `a` / 左方向键：上一张切片。
- `d` / 右方向键：下一张切片。
- `q` 或 `Esc`：退出。

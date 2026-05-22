# 肺部 CT 结节检测与可视化系统

本工程按 `肺部CT结节检测大作业设计文档-2.md` 的 Stage0-5 Pipeline 实现：

- Stage0：解析 `.mhd` 头文件，读取 `.raw` 原始体数据，保留 HU 浮点体数据，并做肺窗窗宽窗位输出。
- Stage1：阈值、形态学开闭、连通域、空洞填充生成肺实质掩膜。
- Stage2：二维 FFT + 高斯差频域带通滤波增强中尺度结节结构。
- Stage3：在肺 ROI 内做候选亮斑检测、连通域提取与面积范围筛选。
- Stage4：计算几何、灰度统计、GLCM 纹理特征，并用圆形度/直径/HU 规则削减假阳性。
- Stage5：输出带标注 2D 切片、肺掩膜、带通增强图、伪彩色 MIP 与 `features.csv`。

本机已安装 OpenCV 与 CMake。核心 Pipeline 仍采用轻量 C++17 实现，保证端到端测试不依赖真实 LUNA16 数据；交互浏览界面使用 OpenCV HighGUI，图像输出使用标准 PGM/PPM，可被 OpenCV 直接读取。

## 数据获取与下载避坑

本仓库不会提交真实 CT 数据，`data/` 已被 `.gitignore` 忽略。真实数据需要单独下载到本机。

### 最小验证数据

如果只是复现实验和课堂演示，不需要下载完整 LUNA16。当前项目使用的最小真实数据组合是：

- `annotations.csv`：官方结节参考标注，约 134 KB。
- `subset8.zip`：LUNA16 第 8 子集，88 例 CT，约 5.7 GB 压缩包，解压后约 10.6 GB。

期望本地路径：

```text
data/luna16_zenodo/csv/annotations.csv
data/luna16_zenodo/subset8.zip
data/luna16_subset8_download/subset8/*.mhd
data/luna16_subset8_download/subset8/*.raw
```

### 方式一：官方 Zenodo

LUNA16 官网下载页：

```text
https://luna16.grand-challenge.org/Download/
```

官方 Zenodo 分两部分：

```text
Part 1/2: https://zenodo.org/records/3723295
Part 2/2: https://zenodo.org/records/4121926
```

本项目需要：

- `annotations.csv`：在 Part 1/2。
- `subset8.zip`：在 Part 2/2。

可尝试命令行下载：

```bash
mkdir -p data/luna16_zenodo/csv

curl -L --fail --retry 5 --retry-delay 3 \
  -o data/luna16_zenodo/csv/annotations.csv \
  "https://zenodo.org/records/3723295/files/annotations.csv?download=1"

curl -L --fail --retry 5 --retry-delay 3 \
  -o data/luna16_zenodo/subset8.zip \
  "https://zenodo.org/records/4121926/files/subset8.zip?download=1"
```

解压：

```bash
mkdir -p data/luna16_subset8_download
unzip data/luna16_zenodo/subset8.zip -d data/luna16_subset8_download
```

### 方式二：镜像源

如果官方 Zenodo 访问失败，可以使用镜像。我们实际成功用过的镜像是：

```text
https://huggingface.co/datasets/Angelou0516/LUNA16
```

注意：这是镜像，不是官方源。报告和 README 中应优先引用 LUNA16 官网与 Zenodo 官方记录；镜像只作为下载可达性备选。

### 下载后必须校验

不要只看文件名存在就认为下载成功。我们之前踩过一次坑：网络中断后得到的 `subset8.zip` 能看到部分文件名，但里面有一批 `.raw` 实际字节数不完整，跑程序会读失败或结果异常。

至少做两层检查：

```bash
unzip -t data/luna16_zenodo/subset8.zip
```

确认压缩包无错误后，再检查 `.mhd` 和 `.raw` 是否成对：

```bash
find data/luna16_subset8_download/subset8 -name "*.mhd" | wc -l
find data/luna16_subset8_download/subset8 -name "*.raw" | wc -l
```

subset8 正常应有 88 个 `.mhd` 和 88 个 `.raw`。如果数量不一致，或者某个 `.raw` 明显过小，说明下载/解压不完整。

### 已知坑

- **Zenodo 是官方源，不是镜像。** 但在部分网络环境下，命令行直连可能返回 `403 Forbidden`，浏览器或换网络有时可行。
- **代理不一定解决 Zenodo 403。** 我们曾切换过代理节点，Zenodo 仍然 403；不要把 403 简单当成代码问题。
- **大文件下载可能静默中断。** 特别是 `.raw` 文件，必须做压缩包测试和 `.mhd/.raw` 成对校验。
- **不要只下载单个 `.mhd`。** `.mhd` 只是文本头文件，真正 CT 体素在对应 `.raw` 里；没有 `.raw` 程序无法读取真实 CT。
- **批量实验建议不要输出所有切片图。** 对 88 例全量跑时使用 `--no-debug-images`，否则会产生大量 `.pgm/.ppm` 调试图，占用很多磁盘。

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

## 使用 LUNA16 标注验证

官方 `annotations.csv` 下载后可放在 `data/luna16_zenodo/csv/annotations.csv`。运行 Pipeline 后，用下列工具将程序输出的体素坐标转换为 `.mhd` 世界坐标，并与官方结节中心坐标按毫米距离匹配：

```bash
./tools/validate_luna_annotations.py \
  --mhd path/to/case.mhd \
  --features output/case_result/features.csv \
  --annotations data/luna16_zenodo/csv/annotations.csv \
  --out output/case_result/annotation_validation.csv
```

验证结果会同时生成 `annotation_validation.csv` 和 `annotation_validation_summary.txt`，其中 `strict_hit_distance_le_radius` 表示候选点到标注中心的距离是否落在该标注结节半径内。

对整个 subset 批量运行并汇总：

```bash
./tools/run_subset_batch_validation.py \
  --subset-dir data/luna16_subset8_download/subset8 \
  --annotations data/luna16_zenodo/csv/annotations.csv \
  --output-root data/subset8_batch_validation \
  --pipeline ./build/lung_pipeline
```

批量脚本默认使用 `--no-debug-images`，避免为每例 CT 写出完整切片序列；输出根目录中会生成 `subset8_validation_summary.csv` 和 `subset8_validation_report.txt`。

当前 subset8 训练集调参后采用的最终过滤参数如下；它保持测试集严格召回不变，同时显著减少候选数量：

```bash
./tools/run_subset_batch_validation.py \
  --subset-dir data/luna16_subset8_download/subset8 \
  --annotations data/luna16_zenodo/csv/annotations.csv \
  --output-root data/subset8_batch_validation_tuned \
  --pipeline ./build/lung_pipeline \
  --pipeline-arg=--min-circularity --pipeline-arg=0.46 \
  --pipeline-arg=--final-min-mean-hu --pipeline-arg=-410 \
  --pipeline-arg=--final-max-mean-hu --pipeline-arg=60 \
  --pipeline-arg=--final-min-std-hu --pipeline-arg=25 \
  --pipeline-arg=--final-max-std-hu --pipeline-arg=210 \
  --pipeline-arg=--final-max-glcm-contrast --pipeline-arg=3.3 \
  --pipeline-arg=--final-min-glcm-homogeneity --pipeline-arg=0.45 \
  --pipeline-arg=--final-max-slice-count --pipeline-arg=18 \
  --pipeline-arg=--max-final-candidates --pipeline-arg=180
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

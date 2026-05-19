# 肺部CT结节检测与可视化系统（传统图像处理版）
## 大作业设计文档

---

## 一、项目概述

### 1.1 背景与动机
肺癌是全球癌症死亡率之首，早期发现肺结节是提高生存率的关键。近年来深度学习在肺结节检测中表现优异，但其"黑箱"特性难以体现数字图像处理课程的核心知识体系。本项目**完全基于传统图像处理方法**，以C++与OpenCV为工具，构建一套从原始CT体数据到候选结节检测、特征提取、3D可视化的完整Pipeline，系统展示课程第1~8章的全部核心知识点。

### 1.2 项目目标
- **输入**：LUNA16公开数据集中的肺部CT体数据（.mhd/.raw格式）
- **处理**：C++读取.mhd/.raw → 保留原始HU数据 → 窗宽窗位调整 → 肺实质分割 → 频域带通滤波增强 → 候选结节检测 → 多特征假阳性削减
- **输出**：原始HU切片、带标注的2D切片序列、结节特征统计表、3D最大密度投影（MIP）视图
- **约束**：不使用任何深度学习或预训练模型，所有检测逻辑由传统图像处理算法实现；原始体数据在内存中始终保留为16-bit/float，BMP仅作为展示输出，不作为唯一中间数据

### 1.3 核心创新点
- **纯C++医学影像数据链路**：自主解析.mhd文本头与.raw二进制裸数据，保留原始HU体数据，并生成窗宽窗位展示序列，体现对医学影像底层格式的掌握。
- **频域带通滤波器设计**：针对肺结节物理尺寸（3 mm ~ 30 mm），在傅里叶频域构造高斯差带通滤波器，滤除低频背景与高频噪声，保留结节对应的中频能量带。直接对应课程第3章频域增强。
- **全流程可视化**：从HU值映射、频谱图、肺掩膜到3D MIP，每一步均可视化，便于现场演示。

### 1.4 分阶段完成边界
考虑到作业时间和实现风险，项目按“先可演示、再增强、最后加分”的方式推进：

| 阶段 | 完成标准 | 是否必须 |
|---|---|---|
| **最低完成线** | 能读取CT体数据，完成窗宽窗位、肺分割、单张候选检测和标注叠加展示 | 必须 |
| **标准完成线** | 加入频域带通增强、圆形度/GLCM筛选、病例级结果统计 | 必须 |
| **展示强化线** | MIP、伪彩色、消融对比、演示用 GUI | 建议 |
| **可选加分线** | 多尺度 LoG、跨切片 3D 连接、更多病例对比 | 可选 |

这样做的原则是：每完成一层，就已经是一份能交的作品；后面的 Stage 只是在同一条主线上不断增强，而不是前面不做完就无法收尾。

---

## 二、数据集确认与获取

### 2.1 数据集：LUNA16
LUNA16（LUng Nodule Analysis 2016）是从LIDC-IDRI（1018例）中筛选出的权威数据集，排除层厚>2.5 mm的扫描，保留**888例**低剂量肺部CT，是肺结节传统算法研究的标准基准。

| 属性 | 详情 |
|---|---|
| **规模** | 888例CT扫描 |
| **格式** | .mhd（元数据头文件，纯文本） + .raw（原始体数据，二进制裸数据） |
| **分辨率** | 512 × 512像素/切片，每例约200~400张切片 |
| **体素间距** | 约 0.7 × 0.7 × 1.0 mm（各向异性） |
| **标注** | `annotations.csv`：结节世界坐标(X,Y,Z)与直径(mm)；`candidates_V2.csv`：候选点坐标 |
| **协议** | Creative Commons Attribution 4.0，学术使用完全免费 |

### 2.2 下载方式
1. **官方Zenodo（推荐）**：
   - Part 1/2: https://doi.org/10.5281/zenodo.2595812
   - Part 2/2: https://doi.org/10.5281/zenodo.2596478
   - 总容量约50~60 GB，建议仅下载 `subset0`（约10 GB，80例）用于作业详细分析。
2. **Kaggle镜像**：搜索 "LUNA16" 或 "LUNA Lung Cancer Dataset"，国内访问更友好。

### 2.3 数据格式说明（C++读取关键）
LUNA16的 `.mhd` 文件是**纯文本头文件**，包含：
```
ObjectType = Image
NDims = 3
DimSize = 512 512 402          // 每例切片数不同
ElementType = MET_SHORT        // 16位有符号整数
ElementSpacing = 0.74 0.74 1.0 // 体素间距(mm)
ElementByteOrderMSB = False     // 一般为小端
ElementDataFile = xxx.raw      // 对应原始二进制数据文件
BinaryData = True
TransformMatrix = 1 0 0 0 1 0 0 0 1
Offset = 0 0 0
```
`.raw` 文件是**无头二进制裸数据**，按 `DimSize` 指定的维度顺序连续存储像素值。

**本项目策略**：用**纯C++**解析.mhd头文件获取参数，直接`fread`读取.raw二进制数据到内存。程序内部保留原始HU矩阵，必要时再做窗宽窗位映射生成 8-bit 展示图，并用 OpenCV `cv::imwrite` 保存为 `.bmp`/`.png` 序列。这样既便于演示，也不会把后续算法锁死在 8-bit 数据上。

---

## 三、完整技术Pipeline

### Stage 0：数据IO与预处理（对应课程第1章：采样与量化）
这一阶段的目标不是“先做完所有视觉效果”，而是先把数据链路跑通，确保原始 HU、显示图、元数据三者都能稳定对应。

#### 3.1 C++ MHD头文件解析器
`.mhd` 为文本文件，逐行读取键值对即可解析：

```cpp
struct MHDHeader {
    int ndims = 3;
    std::vector<int> dimSize;           // 如 [512, 512, 402]
    std::string elementType;            // MET_SHORT / MET_FLOAT / MET_UCHAR
    std::vector<float> elementSpacing;  // 体素间距
    std::string elementDataFile;        // 对应的.raw文件名
    bool binaryData = true;
};

MHDHeader parseMHD(const std::string& mhdPath) {
    MHDHeader header;
    std::ifstream file(mhdPath);
    std::string line;
    while (std::getline(file, line)) {
        std::istringstream iss(line);
        std::string key, eq;
        iss >> key >> eq;
        if (key == "NDims") iss >> header.ndims;
        else if (key == "DimSize") { int v; while (iss >> v) header.dimSize.push_back(v); }
        else if (key == "ElementType") iss >> header.elementType;
        else if (key == "ElementSpacing") { float v; while (iss >> v) header.elementSpacing.push_back(v); }
        else if (key == "ElementDataFile") iss >> header.elementDataFile;
        else if (key == "BinaryData") { std::string v; iss >> v; header.binaryData = (v == "True" || v == "true"); }
    }
    return header;
}
```

#### 3.2 C++ 读取.raw二进制裸数据
根据 `ElementType` 确定每个体素的字节数（`MET_SHORT` = 2字节，`MET_FLOAT` = 4字节），按 `DimSize` 计算总数据量，一次性或分块读入：

```cpp
std::string rawPath = /* mhd同目录下的.raw文件 */;
std::ifstream rawFile(rawPath, std::ios::binary);
long long totalVoxels = 1LL * width * height * slices;
std::vector<char> buffer(totalVoxels * bytesPerVoxel);
rawFile.read(buffer.data(), buffer.size());
```

**字节序**：LUNA16默认小端（Little Endian），与x86/x64 CPU一致，直接`memcpy`即可。

#### 3.3 窗宽窗位调整 + 展示输出
CT原始动态范围约 [-1000, +3000] HU，远超显示器256级灰度。通过**窗宽(WW)**与**窗位(WL)**进行灰度映射：

- **肺窗参数**：`WL = -600`, `WW = 1500`（医学影像标准肺窗）
- **映射公式**：
  ```
  G_out = clip( (HU - (WL - WW/2)) / WW × 255, 0, 255 )
  ```

逐切片映射后，使用 `cv::imwrite("slice_xxx.bmp", slice_8bit)` 或 `.png` 保存为展示序列。同时输出 `meta.txt` 保留体素间距、方向矩阵、窗宽窗位参数，供后续3D重建和坐标映射使用。注意：**算法流程继续使用原始 HU 数据，不以 8-bit 图代替原始体数据**。

```cpp
cv::Mat windowing(const cv::Mat& src, float wl, float ww) {
    float min = wl - ww / 2.0f;
    cv::Mat dst;
    src.convertTo(dst, CV_32F);
    dst = (dst - min) / ww * 255.0f;
    cv::threshold(dst, dst, 255, 255, cv::THRESH_TRUNC);
    cv::threshold(dst, dst, 0, 0, cv::THRESH_TOZERO);
    dst.convertTo(dst, CV_8U);
    return dst;
}
```

**课程对应**：采样与量化（CT的HU量化）、灰度变换（第2章）、文件格式与数据表示。

---

### Stage 1：肺实质分割（对应课程第6、7章：形态学 + 图像分割）
目的：去除CT扫描中的扫描床、体外空气、胸壁肌肉，仅保留左右两叶肺区域，将后续结节搜索空间缩减90%以上。

**算法流程**：
1. **阈值分割**：对肺窗图像设定阈值（如灰度值<20的暗区对应肺内空气与肺实质），生成二值图。
2. **形态学开运算**（`cv::MORPH_OPEN`）：使用5×5椭圆结构元，去除细小气管与噪声。对应课程**形态学图像处理**中的腐蚀+膨胀。
3. **连通域分析**（`cv::connectedComponentsWithStats`）：保留面积最大的两个连通域（左肺与右肺），剔除扫描床等外部区域。
4. **空洞填充（形态学闭运算/重建）**：肺内血管与结节表现为高密度点，在肺掩膜中形成"洞"。使用**闭运算**（`cv::MORPH_CLOSE`）或**灰度形态学重建**填充，防止结节区域被误切除。
5. **掩膜提取**：最终获得纯肺实质的二值掩膜，与原图做 `cv::bitwise_and` 得到ROI。

**课程对应**：阈值分割、形态学（腐蚀/膨胀/开闭）、连通域标记、区域生长思想。

---

### Stage 2：频域带通滤波增强（核心创新，对应课程第3章：傅里叶域增强）
这是本项目区别于普通结节检测作业的理论核心。

#### 2.1 为什么需要带通滤波？
肺结节在CT上有明确的物理尺寸范围：**直径 3 mm ~ 30 mm**。在频域中，图像结构尺寸与空间频率成反比：
- **超大尺度结构**（肺叶轮廓、整体亮度梯度）→ **超低频**
- **微小结构**（噪声、血管纹理、CT扫描伪影）→ **超高频**
- **中等尺度结构**（结节）→ **中频**

因此，设计一个**频域带通滤波器（Band-pass Filter）**，保留中频带、滤除低频背景与高频噪声，可显著增强结节对比度。

#### 2.2 滤波器设计：高斯差带通（Difference of Gaussians in Frequency Domain）
为避免理想带通的振铃效应（Ringing Artifact），采用两个高斯低通的差值构造平滑带通：

```
H(u,v) = exp(-D²(u,v) / (2·σ_low²)) - exp(-D²(u,v) / (2·σ_high²))
```

其中 `D(u,v)` 为频谱点到中心的欧氏距离，`σ_low > σ_high`。
- 第一项：宽高斯 → 允许低频+中频通过
- 第二项：窄高斯 → 允许更高频率通过
- 差值：仅保留中频带，形成平滑带通特性

#### 2.3 C++实现流程
```cpp
void fftShift(cv::Mat& complexI) {
    cv::Mat tmp;
    int cx = complexI.cols / 2;
    int cy = complexI.rows / 2;
    cv::Mat q0(complexI, cv::Rect(0, 0, cx, cy));
    cv::Mat q1(complexI, cv::Rect(cx, 0, complexI.cols - cx, cy));
    cv::Mat q2(complexI, cv::Rect(0, cy, cx, complexI.rows - cy));
    cv::Mat q3(complexI, cv::Rect(cx, cy, complexI.cols - cx, complexI.rows - cy));
    q0.copyTo(tmp);  q3.copyTo(q0);  tmp.copyTo(q3);
    q1.copyTo(tmp);  q2.copyTo(q1);  tmp.copyTo(q2);
}

cv::Mat bandPassEnhance(cv::Mat src) {
    // 1. 扩展尺寸至最优DFT尺寸
    cv::Mat padded;
    int m = cv::getOptimalDFTSize(src.rows);
    int n = cv::getOptimalDFTSize(src.cols);
    cv::copyMakeBorder(src, padded, 0, m - src.rows, 0, n - src.cols, cv::BORDER_CONSTANT, cv::Scalar::all(0));

    // 2. 构造双通道Mat（实部+虚部）并做DFT
    cv::Mat planes[] = {cv::Mat_<float>(padded), cv::Mat::zeros(padded.size(), CV_32F)};
    cv::Mat complexI;
    cv::merge(planes, 2, complexI);
    cv::dft(complexI, complexI);
    fftShift(complexI);  // 将低频移动到中心，确保滤波器中心与频谱中心一致

    // 3. 构造高斯差带通滤波器
    cv::Mat filter(padded.size(), CV_32F);
    cv::Point center(n/2, m/2);
    float sigmaLow = 30.0f;   // 对应大结节低频截止
    float sigmaHigh = 5.0f;   // 对应小结节高频截止
    for(int i=0; i<m; i++) {
        for(int j=0; j<n; j++) {
            float D = cv::norm(cv::Point(j,i) - center);
            filter.at<float>(i,j) = std::exp(-D*D/(2*sigmaLow*sigmaLow)) 
                                  - std::exp(-D*D/(2*sigmaHigh*sigmaHigh));
        }
    }

    // 4. 频域滤波：逐通道相乘
    cv::split(complexI, planes);
    planes[0] = planes[0].mul(filter);
    planes[1] = planes[1].mul(filter);
    cv::merge(planes, 2, complexI);
    fftShift(complexI);  // 逆DFT前移回OpenCV默认频谱布局

    // 5. 逆DFT并取实部
    cv::Mat result;
    cv::idft(complexI, result, cv::DFT_REAL_OUTPUT | cv::DFT_SCALE);
    result = result(cv::Rect(0, 0, src.cols, src.rows));
    cv::normalize(result, result, 0, 255, cv::NORM_MINMAX);
    result.convertTo(result, CV_8U);
    return result;
}
```

如果实现时想进一步简化，也可以不做中心化，但滤波器必须按 OpenCV 默认的左上角直流点来构造。报告和代码应保持一致，避免出现“报告写中心频域、程序却按未中心化频谱滤波”的错位问题。

#### 2.4 可视化与论证
- **频谱图展示**：在报告中展示CT切片的中心化幅度谱，标注低频、中频、高频区域。
- **对比实验**：同一结节区域，分别展示（a）原始图、（b）空间域高斯平滑、（c）频域带通滤波结果。论证频域方法在保留结节边缘的同时抑制背景的能力。

**课程对应**：离散傅里叶变换（DFT）、频域滤波器设计、频域平滑与锐化、振铃效应与滤波器选择。

---

### Stage 3：候选结节检测（对应课程第2、7章：空间域滤波 + 图像分割）
经过带通增强后，结节表现为圆形/类圆形亮斑。采用**多尺度拉普拉斯高斯（LoG）Blob检测**与**形态学重建**相结合。

**算法流程**：
1. **高斯平滑**（`cv::GaussianBlur`）：进一步抑制残余噪声，对应空间域线性滤波。
2. **拉普拉斯锐化**（`cv::Laplacian`）：增强斑点状结构，对应空间域锐化。
3. **多尺度检测**：对一系列σ（1.0, 2.0, 3.0, 4.0 mm）分别计算LoG响应，在尺度空间寻找极值点。
4. **自适应阈值分割**：在LoG响应图上使用Otsu或局部阈值，提取亮斑区域。
5. **形态学重建**：以亮斑中心为种子点，在原始肺ROI上做灰度形态学重建，精确提取结节边界。

**简化版（适合作业时间）**：
若 LoG 多尺度实现复杂，可改用**阈值 + 连通域 + 霍夫圆检测（`cv::HoughCircles`）**的组合：在带通增强图上做自适应阈值 → 找轮廓 → 用圆形度（Circularity = 4πA/P²）和面积范围筛选。这一版足够支撑课堂演示，也更容易稳住结果。

**课程对应**：高斯滤波、拉普拉斯锐化、阈值分割、边缘检测、形态学重建。

---

### Stage 4：特征提取与假阳性削减（对应课程第8章：图像描述）
检测出的候选区域包含大量假阳性（血管截面、钙化灶）。需提取多维度特征进行筛选。

#### 4.1 特征体系

| 特征类别 | 具体指标 | 计算方法 | 课程对应 |
|---|---|---|---|
| **几何特征** | 面积、周长、圆形度、矩形度、离心率 | `cv::contourArea`, `cv::arcLength` | 图像描述：形状特征 |
| **灰度统计** | 均值、标准差、偏度 | `cv::meanStdDev` | 图像描述：统计矩 |
| **纹理特征** | GLCM对比度、相关性、能量、同质性 | 自实现灰度共生矩阵 | 图像描述：纹理分析 |
| **3D形态** | 体积、3D球形度、跨切片连通性 | 3D连通域追踪 | 图像描述：拓扑特征 |

#### 4.2 GLCM实现要点（C++）
灰度共生矩阵（Gray-Level Co-occurrence Matrix）是课程第8章纹理描述的核心。实现步骤：
1. 将结节ROI量化为16或32级灰度（降低计算量）。
2. 统计方向θ（0°, 45°, 90°, 135°）、距离d=1的像素对灰度联合概率 `P(i,j)`。
3. 计算二次统计特征：
   - **对比度（Contrast）**：Σ(i-j)²·P(i,j)
   - **能量（Energy）**：ΣP(i,j)²
   - **同质性（Homogeneity）**：ΣP(i,j) / (1+|i-j|)
   - **相关性（Correlation）**：衡量线性灰度依赖

#### 4.3 筛选规则示例
```
IF (圆形度 > 0.70) 
   AND (等效直径 3~30 mm) 
   AND (GLCM对比度 ∈ [下限, 上限]) 
   AND (平均灰度 > 肺实质均值 + 2σ)
THEN 保留为结节
ELSE 假阳性剔除
```

**课程对应**：图像描述、统计特征、纹理特征、特征选择。

#### 4.4 消融实验设计
为了让报告更完整，也更好回答老师“这个结果是怎么一步步变好的”，建议做一个简单但清晰的消融对比：

| 版本 | 处理链 | 目的 |
|---|---|---|
| **A** | 原始切片 + 阈值/轮廓 | 基线，观察最初假阳性情况 |
| **B** | A + 肺实质分割 | 证明 ROI 缩小带来的收益 |
| **C** | B + 频域带通增强 | 证明第 3 章内容的实际效果 |
| **D** | C + 圆形度/GLCM 筛选 | 证明特征筛选能进一步削减假阳性 |

对比时只需要选 1 到 2 个典型病例，把“候选数变化”“漏检/误检变化”“视觉效果变化”展示出来即可，不必追求大规模统计。

---

### Stage 5：3D可视化与切片浏览（对应课程第4、5、8章：几何变换 + 彩色处理 + 图像显示）
#### 5.1 2D切片交互浏览
使用OpenCV `cv::imshow` + `createTrackbar` 构建轻量GUI：
- 滑条控制当前切片序号 `z`。
- 左窗：原始CT切片；右窗：检测结果（肺掩膜绿色轮廓 + 结节红色圆圈 + 特征标签）。

#### 5.2 伪彩色映射（对应课程第5章：彩色图像处理）
CT本质为灰度图像，但可用**伪彩色（Pseudo-color）映射**增强可视化：
- 空气（<-900 HU）→ 深蓝色
- 肺实质（-900 ~ -500 HU）→ 青色/绿色
- 软组织/结节（-500 ~ +50 HU）→ 黄色/橙色
- 骨骼（>+100 HU）→ 红色
通过 `cv::applyColorMap` 或自定义LUT实现，将灰度CT值映射到彩色空间，直观区分组织类型。

#### 5.3 3D最大密度投影（MIP）（对应课程第4章：图像几何变换）
最大密度投影（Maximum Intensity Projection）是医学影像3D可视化的经典方法：
- 沿Z轴（或任意视角）对体数据取最大值投影到2D平面。
- 数学本质：对3D矩阵 `V(x,y,z)`，生成 `MIP(x,y) = max_z V(x,y,z)`。
- 可进一步实现**多视角旋转**：绕X/Y轴做几何变换（旋转矩阵 + 三线性插值），生成不同角度的MIP视图。

**C++实现**：
```cpp
cv::Mat computeMIP(const std::vector<cv::Mat>& slices) {
    cv::Mat mip = slices[0].clone();
    for(size_t z=1; z<slices.size(); z++) {
        cv::max(mip, slices[z], mip);
    }
    // 伪彩色映射
    cv::Mat colorMIP;
    cv::applyColorMap(mip, colorMIP, cv::COLORMAP_JET);
    return colorMIP;
}
```

**课程对应**：几何变换（旋转/投影）、插值方法、彩色映射、图像显示与描述。

---

## 四、课程知识点全覆盖对照表

| 课程章节 | 知识点 | 本项目对应环节 | 证据形式 |
|---|---|---|---|
| **1. Introduction** | 采样、量化、CT成像、文件格式 | Stage 0：C++解析.mhd头文件、读取.raw裸数据、HU保留、展示序列输出 | 报告理论章节 + 代码 |
| **2. Spatial Enhancement** | 灰度变换、直方图、空间滤波 | Stage 0窗宽窗位；Stage 3高斯/拉普拉斯滤波 | 公式+效果图 |
| **3. Fourier Enhancement** | DFT、频域平滑/锐化 | Stage 2：高斯差带通滤波器设计 | **核心章节：频谱图、滤波器掩膜、对比实验** |
| **4. Geometry Transform** | 旋转、缩放、插值 | Stage 0重采样；Stage 5.3 MIP多视角旋转 | 代码+3D视图 |
| **5. Color Processing** | 伪彩色、彩色空间 | Stage 5.2：HU值→伪彩色映射；检测标注彩色叠加 | 彩色可视化图 |
| **6. Morphology** | 腐蚀、膨胀、开闭、重建 | Stage 1肺分割；Stage 3形态学重建去噪 | 各步骤二值图 |
| **7. Segmentation** | 阈值、区域生长、边缘检测 | Stage 1阈值分割；Stage 3 LoG/区域生长/边缘检测 | 分割结果对比 |
| **8. Presentation & Description** | 几何特征、纹理、GLCM、统计矩 | Stage 4：圆形度、GLCM、灰度统计、3D描述 | 特征表格+公式 |

---

## 五、C++工程实现框架

### 5.1 项目目录结构
```
LungNoduleDetection/
├── CMakeLists.txt
├── main.cpp                  // GUI主循环与演示逻辑
├── io/
│   ├── mhd_reader.cpp/h      // .mhd头文件解析 + .raw二进制读取
│   └── volume_loader.cpp     // 加载bmp切片序列，管理3D体数据
├── preprocessing/
│   ├── windowing.cpp         // 窗宽窗位映射（HU -> 8-bit展示图）
│   └── resample.cpp          // 3D重采样与插值
├── frequency/
│   ├── dft_utils.cpp         // DFT/IDFT封装、频谱中心化
│   └── bandpass_filter.cpp   // 高斯差带通滤波器生成
├── segmentation/
│   ├── lung_mask.cpp         // 肺实质分割（阈值+形态学+连通域）
│   └── nodule_candidate.cpp  // 候选结节检测（LoG/阈值/霍夫圆）
├── features/
│   ├── geometric.cpp         // 面积、周长、圆形度
│   └── glcm.cpp              // 灰度共生矩阵与二次特征
├── visualization/
│   ├── mip_renderer.cpp      // MIP投影与伪彩色
│   └── overlay.cpp           // 检测标注叠加
└── data/
    ├── subset0/              // 原始 .mhd + .raw
    └── preprocessed/         // 输出的 .bmp 序列 + meta.txt
```

### 5.2 核心类设计
```cpp
class CTVolume {
public:
    std::vector<cv::Mat> huSlices;    // 原始HU切片，CV_16S或CV_32F，用于算法
    std::vector<cv::Mat> displaySlices; // 8-bit窗宽窗位图，仅用于显示/保存
    float spacing[3];                 // 体素间距 (mm)

    bool loadFromRawMHD(const std::string& mhdPath, float wl, float ww);
    bool loadDisplayFolder(const std::string& folder);
    cv::Mat getHUSlice(int z) const;
    cv::Mat getDisplaySlice(int z) const;
    cv::Mat getMIP() const;           // 最大密度投影
    cv::Mat getBandPassEnhancedSlice(int z, float sLow, float sHigh) const;
};

struct Nodule {
    cv::Point3i center;               // 体素坐标 (x,y,z)
    float diameter_mm;              // 等效直径
    float circularity;              // 圆形度
    float contrast;                 // GLCM对比度
    float energy;                   // GLCM能量
    float meanIntensity;            // 平均灰度
};
```

### 5.3 关键代码片段

**A. C++ MHD解析 + RAW读取 + HU保留 + 展示输出（示意版）**
```cpp
#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>
#include <opencv2/opencv.hpp>

struct MHDHeader {
    int ndims = 3;
    std::vector<int> dimSize;
    std::string elementType;
    std::vector<float> elementSpacing;
    std::string elementDataFile;
    bool binaryData = true;
};

MHDHeader parseMHD(const std::string& mhdPath) {
    MHDHeader header;
    std::ifstream file(mhdPath);
    std::string line;
    while (std::getline(file, line)) {
        std::istringstream iss(line);
        std::string key, eq;
        iss >> key >> eq;
        if (key == "NDims") iss >> header.ndims;
        else if (key == "DimSize") { int v; while (iss >> v) header.dimSize.push_back(v); }
        else if (key == "ElementType") iss >> header.elementType;
        else if (key == "ElementSpacing") { float v; while (iss >> v) header.elementSpacing.push_back(v); }
        else if (key == "ElementDataFile") iss >> header.elementDataFile;
        else if (key == "BinaryData") { std::string v; iss >> v; header.binaryData = (v == "True" || v == "true"); }
    }
    return header;
}

cv::Mat windowing(const cv::Mat& src, float wl, float ww) {
    float min = wl - ww / 2.0f;
    cv::Mat dst;
    src.convertTo(dst, CV_32F);
    dst = (dst - min) / ww * 255.0f;
    cv::threshold(dst, dst, 255, 255, cv::THRESH_TRUNC);
    cv::threshold(dst, dst, 0, 0, cv::THRESH_TOZERO);
    dst.convertTo(dst, CV_8U);
    return dst;
}

bool convertMHDToBMP(const std::string& mhdPath, const std::string& outFolder, 
                       float wl = -600.0f, float ww = 1500.0f) {
    MHDHeader h = parseMHD(mhdPath);
    if (h.dimSize.size() != 3) { std::cerr << "Only 3D supported!
"; return false; }

    int width = h.dimSize[0], height = h.dimSize[1], slices = h.dimSize[2];
    long long totalVoxels = 1LL * width * height * slices;

    int bytesPerVoxel = 2, cvType = CV_16S;
    if (h.elementType == "MET_FLOAT") { bytesPerVoxel = 4; cvType = CV_32F; }
    else if (h.elementType == "MET_UCHAR") { bytesPerVoxel = 1; cvType = CV_8U; }

    std::string rawPath = mhdPath.substr(0, mhdPath.find_last_of("/\") + 1) + h.elementDataFile;
    std::ifstream rawFile(rawPath, std::ios::binary);
    if (!rawFile) { std::cerr << "Cannot open raw!
"; return false; }

    std::vector<char> buffer(totalVoxels * bytesPerVoxel);
    rawFile.read(buffer.data(), buffer.size());

    cv::Mat huSlice(height, width, cvType);
    for (int z = 0; z < slices; z++) {
        long long offset = 1LL * z * width * height * bytesPerVoxel;
        std::memcpy(huSlice.data, buffer.data() + offset, width * height * bytesPerVoxel);
        // 正式工程中将 huSlice.clone() 存入 huSlices，供分割、滤波和特征计算使用。
        cv::Mat slice8bit = windowing(huSlice, wl, ww);
        char fname[256];
        snprintf(fname, sizeof(fname), "%s/slice_%03d.bmp", outFolder.c_str(), z);
        cv::imwrite(fname, slice8bit);
    }

    // 保存元数据
    std::ofstream meta(outFolder + "/meta.txt");
    meta << "width " << width << "
height " << height << "
slices " << slices << "
";
    meta << "spacing_x " << h.elementSpacing[0] << "
spacing_y " << h.elementSpacing[1] << "
spacing_z " << h.elementSpacing[2] << "
";
    meta << "wl " << wl << "
ww " << ww << "
";
    return true;
}
```

**B. 频域带通滤波（完整版）**
```cpp
// 复用前文 dft_utils 中的 fftShift，确保滤波器中心和频谱中心一致。
cv::Mat frequencyBandPass(const cv::Mat& src, float sigmaLow, float sigmaHigh) {
    int m = cv::getOptimalDFTSize(src.rows);
    int n = cv::getOptimalDFTSize(src.cols);
    cv::Mat padded;
    cv::copyMakeBorder(src, padded, 0, m-src.rows, 0, n-src.cols, cv::BORDER_CONSTANT, cv::Scalar::all(0));

    cv::Mat planes[] = {cv::Mat_<float>(padded), cv::Mat::zeros(padded.size(), CV_32F)};
    cv::Mat complexI;
    cv::merge(planes, 2, complexI);
    cv::dft(complexI, complexI);
    fftShift(complexI);

    cv::Mat filter(padded.size(), CV_32F);
    cv::Point center(n/2, m/2);
    for(int i=0; i<m; ++i) {
        for(int j=0; j<n; ++j) {
            float D = cv::norm(cv::Point2f(j,i) - cv::Point2f(center));
            float g1 = std::exp(-(D*D)/(2.0f*sigmaLow*sigmaLow));
            float g2 = std::exp(-(D*D)/(2.0f*sigmaHigh*sigmaHigh));
            filter.at<float>(i,j) = g1 - g2;
        }
    }

    cv::split(complexI, planes);
    planes[0] = planes[0].mul(filter);
    planes[1] = planes[1].mul(filter);
    cv::merge(planes, 2, complexI);
    fftShift(complexI);

    cv::Mat result;
    cv::idft(complexI, result, cv::DFT_REAL_OUTPUT | cv::DFT_SCALE);
    result = result(cv::Rect(0, 0, src.cols, src.rows));
    cv::normalize(result, result, 0, 255, cv::NORM_MINMAX);
    result.convertTo(result, CV_8U);
    return result;
}
```

**C. GLCM特征提取**
```cpp
void computeGLCM(const cv::Mat& roi, double& contrast, double& energy, double& homogeneity) {
    cv::Mat quantized;
    roi.convertTo(quantized, CV_32F);
    quantized = quantized / 16.0f;
    quantized.convertTo(quantized, CV_8U);

    int levels = 16;
    cv::Mat glcm = cv::Mat::zeros(levels, levels, CV_32F);

    for(int i=0; i<quantized.rows; i++) {
        for(int j=0; j<quantized.cols-1; j++) {
            int p = quantized.at<uchar>(i,j);
            int q = quantized.at<uchar>(i,j+1);
            glcm.at<float>(p,q) += 1.0f;
        }
    }
    double total = cv::sum(glcm)[0];
    if (total <= 0.0) return;
    glcm /= total;

    contrast = 0; energy = 0; homogeneity = 0;
    for(int i=0; i<levels; i++) {
        for(int j=0; j<levels; j++) {
            float p = glcm.at<float>(i,j);
            contrast += (i-j)*(i-j) * p;
            energy += p * p;
            homogeneity += p / (1.0 + std::abs(i-j));
        }
    }
}
```

---

## 六、评分标准应对策略

对照作业要求中的5项评分标准，逐条制定应对策略：

| 评分项 | 分值 | 应对策略 |
|---|---|---|
| **1. 与课程内容符合** | 3分 | 通过"课程知识点全覆盖对照表"确保8个章节全部涉及；报告中每章设独立小节，明确引用教材公式与页码。 |
| **2. 完整性** | 2分 | 提供从数据加载→预处理→检测→特征提取→可视化的**完整可执行代码**；PDF报告含摘要、原理、实验、结论、附录代码。 |
| **3. 工作量** | 3分 | 2人分工明确；实现6个Stage共10+个算法模块；处理真实LUNA16数据；输出定量统计（检测数、假阳性率、特征表）。 |
| **4. 现场表现** | 1分 | 设计4分钟精确演示脚本（见第七节）；GUI交互流畅，有滑条、有标注、有3D视图；提前录制备用视频。 |
| **5. 难度** | 1分 | **纯C++医学影像IO**体现底层能力；**频域带通滤波器**是理论亮点；3D MIP与跨切片分析体现工程复杂度；GLCM自实现体现理论深度。 |

---

## 七、报告结构与演示脚本

### 7.1 PDF报告建议结构（15~20页）

1. **摘要**（1页）：背景、方法概述、主要结果、创新点一句话总结。
2. **第一章 绪论**（2页）：肺癌筛查意义、传统方法vs深度学习、课程知识点映射。
3. **第二章 数据集与C++数据IO**（3页）：
   - 2.1 LUNA16介绍与下载
   - 2.2 .mhd/.raw格式解析：文本头字段、二进制裸数据读取、字节序处理
   - 2.3 C++窗宽窗位映射与展示序列输出
   - 2.4 元数据保留策略（meta.txt）
4. **第三章 空间域增强与肺分割**（3页）：
   - 3.1 窗宽窗位映射（公式+肺窗/纵隔窗对比图）
   - 3.2 肺实质分割流程（阈值→开运算→连通域→闭运算填充）
   - 每步附效果图（原图、二值图、掩膜叠加图）
5. **第四章 频域带通滤波增强**（4页，**核心章节**）：
   - 4.1 频域分析理论基础：结节尺寸与频率的对应关系
   - 4.2 高斯差带通滤波器设计：公式、参数物理意义、滤波器掩膜可视化
   - 4.3 DFT/IDFT实现细节：最优尺寸、中心化、振铃效应规避
   - 4.4 实验对比：原图 vs 空间域高斯 vs 频域带通（同一ROI并排展示）
   - 4.5 频谱图分析：展示幅度谱，标注通带范围
6. **第五章 结节检测与分割**（2页）：LoG多尺度/自适应阈值、形态学重建、霍夫圆备选方案。
7. **第六章 特征提取与假阳性削减**（2页）：几何特征公式、GLCM定义与实现、筛选规则表、削减前后对比。
8. **第七章 3D可视化系统**（2页）：伪彩色映射原理、MIP投影公式、GUI交互设计、多视角旋转效果。
9. **第八章 实验结果与消融分析**（2页）：选取2例典型LUNA16数据，展示完整Pipeline结果；与官方标注做定性对比；用消融表展示各阶段对结果的贡献。
10. **第九章 总结与展望**（1页）：传统方法优势与局限、课程学习收获。
11. **参考文献**：引用LUNA16论文、冈萨雷斯教材、OpenCV文档。
12. **附录A**：核心C++代码（MHD读取、带通滤波、GLCM、肺分割）。
13. **附录B**：编译与运行说明（CMake、依赖库、数据路径）。

### 7.2 4分钟现场演示脚本（精确到秒）

| 时间 | 讲解词 | 屏幕操作 |
|---|---|---|
| 0:00-0:20 | "大家好，我们做的是基于传统图像处理的肺结节检测系统，数据集用LUNA16，全部代码纯C++实现。" | 展示项目标题页 |
| 0:20-0:50 | "首先看数据IO：我们自主解析.mhd文本头，直接fread读取.raw二进制裸数据，算法保留原始HU，同时生成肺窗展示序列。" | 展示代码片段或meta.txt，说明C++底层读取 |
| 0:50-1:20 | "接下来是肺实质分割：用阈值+形态学开闭+连通域分析，去掉扫描床和胸壁。" | 点击'分割'按钮，左图原图，右图绿色肺轮廓 |
| 1:20-2:00 | **（核心亮点）** "本项目的关键创新是频域带通滤波。结节尺寸3-30mm对应中频，我们在傅里叶域设计高斯差带通，滤除低频背景和高频噪声。" | 展示频谱图 → 展示滤波器掩膜 → 展示增强后结节对比度 |
| 2:00-2:30 | "增强后做候选检测：用空间域拉普拉斯锐化+自适应阈值，提取亮斑，再用圆形度和GLCM纹理筛选假阳性。" | 点击'检测'，红圈自动标注结节；右侧弹出特征表格 |
| 2:30-3:00 | "这是3D最大密度投影，用伪彩色映射展示结节在肺中的空间位置，支持多视角旋转。" | 展示MIP伪彩图，点击不同角度 |
| 3:00-3:30 | "最后看完整统计：这例CT共检测到X个候选，其中Y个通过特征筛选，与官方标注对比可见..." | 展示结果汇总表 |
| 3:30-4:00 | "总结：本项目从数据IO到算法实现全程纯C++，覆盖课程全部8章内容，特别是频域带通滤波的设计，体现了传统图像处理在医学场景中的价值。谢谢！" | 展示课程知识点对照表 |

**老师提问1分钟预案**：
- Q: "为什么不用Python做预处理？" → A: "本项目要求纯C++实现以展示对底层文件格式和内存操作的掌握；.mhd是纯文本头，.raw是裸二进制，C++解析非常直接。"
- Q: "BMP会不会丢失信息？" → A: "BMP/PNG只用于展示，算法内部仍保留原始16-bit HU体数据；窗宽窗位映射只是把医学影像压缩到显示器可看的灰度范围。"
- Q: "带通滤波器参数怎么确定？" → A: "基于结节先验尺寸3-30mm，通过空间频率反比关系估算中频范围，最终通过实验在验证集上调优。"
- Q: "检测精度如何？" → A: "传统方法以高灵敏度为目标，假阳性率较高，但本项目重点在于完整Pipeline与知识点覆盖，而非与SOTA比较。"

---

## 八、2人分工建议

| 成员 | 负责模块 | 对应课程章节 | 交付物 |
|---|---|---|---|
| **同学A** | 1. C++数据IO（.mhd解析/.raw读取/HU保留/窗宽窗位展示输出/meta.txt）<br>2. 肺实质分割（阈值+形态学+连通域）<br>3. 候选结节检测（LoG/阈值/轮廓提取）<br>4. GUI框架与现场演示程序整合 | 第1、2、6、7章 | `mhd_reader.cpp`, `windowing.cpp`, `lung_mask.cpp`, `nodule_candidate.cpp`, `main.cpp` |
| **同学B** | 1. 频域带通滤波器设计与实现（DFT/滤波器/IDFT）<br>2. 特征提取（几何特征+GLCM自实现）<br>3. 假阳性削减规则引擎<br>4. 3D可视化（MIP投影+伪彩色+多视角）<br>5. 报告撰写与PPT制作 | 第3、4、5、8章 | `bandpass_filter.cpp`, `glcm.cpp`, `mip_renderer.cpp`, 报告全文 |

**协作接口**：
- 同学A输出 `std::vector<cv::Rect> candidates`（2D候选框序列）给同学B。
- 同学B基于候选框提取ROI，计算特征，返回 `std::vector<Nodule> confirmedNodules`。
- 两人在第14周前完成模块联调，预留2周做集成测试与演示排练。

---

## 九、风险识别与应对

| 风险 | 影响 | 应对策略 |
|---|---|---|
| **LUNA16数据下载慢/过大** | 无法及时开始实验 | 仅下载`subset0`（~10GB）；用Kaggle镜像；或用C++程序只处理1-2例做深度开发 |
| **.raw文件读取错误** | 图像花屏或崩溃 | 严格按.mhd中`ElementType`和`DimSize`分配buffer；小端字节序与x86一致无需交换；先用1例验证像素范围 |
| **频域带通效果不明显** | 核心亮点失败 | 准备Plan B：若带通效果不佳，改用**频域低通去噪对比实验**（同样覆盖第3章，实现更简单） |
| **3D MIP性能不足** | 演示卡顿 | 预先计算MIP序列存为图片，演示时直接播放，而非实时计算 |
| **结节检测假阳性过高** | 演示观感差 | 现场演示时选择**标注清晰、结节明显**的典型案例；报告里诚实分析假阳性来源 |
| **提交日前时间不足** | 无法完成 | 按第十节时间表倒推，先锁定最低完成线，再把频域增强和消融对比作为优先加分项 |

---

## 十、下一步行动清单（建议时间表）

假设当前为第12周（距离展示日约3-4周）：

- [ ] **本周（Week 12）**：下载 LUNA16 subset0；用 C++ 跑通 `.mhd` 解析 + `.raw` 读取 + 窗宽窗位 + BMP/PNG 展示输出；验证 1 例数据能正常显示。
- [ ] **下周（Week 13）**：完成肺分割；完成 DFT 带通滤波骨架 + 伪彩色映射。联调 Stage 0~2。
- [ ] **第14周**：完成结节候选检测；完成 GLCM + 几何特征 + 假阳性筛选。联调 Stage 3~4，确定 1~2 例演示用例。
- [ ] **第15周**：整合 GUI 与 MIP 可视化；优化参数；开始撰写报告（两人合写）。
- [ ] **第16周初**：报告定稿、代码打包、PPT 制作、演示彩排（精确到秒）。
- [ ] **提交日**：提交 PDF + 代码 + PPT，现场展示。

---

## 附录：关键公式速查

**窗宽窗位映射**：
$$G_{out} = \text{clip}\left( \frac{HU - (WL - WW/2)}{WW} \times 255, \ 0, \ 255 \right)$$

**高斯差频域带通滤波器**：
$$H(u,v) = \exp\left(-\frac{D^2(u,v)}{2\sigma_{low}^2}\right) - \exp\left(-\frac{D^2(u,v)}{2\sigma_{high}^2}\right)$$
其中 $D(u,v) = \sqrt{(u-M/2)^2 + (v-N/2)^2}$

**圆形度（Circularity）**：
$$C = \frac{4\pi A}{P^2}$$
$C=1$ 为理想圆，结节通常 $C > 0.7$。

**GLCM对比度**：
$$\text{Contrast} = \sum_{i,j} (i-j)^2 \cdot P(i,j)$$

**最大密度投影（MIP）**：
$$\text{MIP}(x,y) = \max_{z} V(x,y,z)$$

---

*本文档基于冈萨雷斯《数字图像处理》课程大纲与LUNA16公开数据集编写，数据IO与预处理全程采用纯C++实现，供大作业选题与技术路线参考。*

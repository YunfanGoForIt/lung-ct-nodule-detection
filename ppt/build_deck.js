const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Yunfan";
pptx.company = "Medical Image Processing Coursework";
pptx.subject = "Lung CT nodule detection with classical image processing";
pptx.title = "肺部 CT 结节检测与可视化系统";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};
pptx.defineLayout({ name: "LAYOUT_WIDE", width: 13.333, height: 7.5 });

const outDir = path.join(__dirname, "output");
fs.mkdirSync(outDir, { recursive: true });

const C = {
  bg: "F7F6F2",
  ink: "171717",
  muted: "606060",
  line: "D8D6D0",
  red: "D71920",
  blue: "1F4E79",
  green: "2E7D32",
  pale: "ECEAE4",
  white: "FFFFFF",
};

const A = {
  window: path.join(__dirname, "assets", "slice_034_window.png"),
  mask: path.join(__dirname, "assets", "slice_034_mask.png"),
  bandpass: path.join(__dirname, "assets", "slice_034_bandpass.png"),
  overlay: path.join(__dirname, "assets", "slice_034_overlay.png"),
  mip: path.join(__dirname, "..", "data", "real_run_check_300136985030081433029390459071", "mip.png"),
};

const W = 13.333;
const H = 7.5;
const font = "Microsoft YaHei";
const mono = "Arial";

function slideBase(slide, no) {
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.line, { x: 0.6, y: 0.42, w: 12.1, h: 0, line: { color: C.ink, width: 0.6 } });
  slide.addText("肺部 CT 结节检测 / Classical DIP Pipeline", {
    x: 0.6, y: 0.18, w: 7.4, h: 0.22, fontFace: mono, fontSize: 7.5, color: C.muted, bold: true,
    margin: 0,
  });
  slide.addText(String(no).padStart(2, "0"), {
    x: 12.15, y: 6.88, w: 0.58, h: 0.25, fontFace: mono, fontSize: 9,
    color: C.muted, align: "right", margin: 0,
  });
}

function title(slide, text, no, sub) {
  slideBase(slide, no);
  slide.addText(text, {
    x: 0.72, y: 0.7, w: 8.8, h: 0.55, fontFace: font, fontSize: 24, bold: true,
    color: C.ink, margin: 0,
  });
  slide.addShape(pptx.ShapeType.rect, { x: 0.72, y: 1.34, w: 0.62, h: 0.045, fill: { color: C.red }, line: { color: C.red } });
  if (sub) {
    slide.addText(sub, {
      x: 1.45, y: 1.24, w: 8.2, h: 0.25, fontFace: mono, fontSize: 8.5, color: C.muted, margin: 0,
    });
  }
}

function label(slide, text, x, y, w, color = C.red) {
  slide.addText(text, {
    x, y, w, h: 0.22, fontFace: mono, fontSize: 7.2, bold: true, color, margin: 0,
    breakLine: false,
  });
}

function body(slide, text, x, y, w, h, size = 13, color = C.ink) {
  slide.addText(text, { x, y, w, h, fontFace: font, fontSize: size, color, fit: "shrink", breakLine: false, margin: 0.03 });
}

function metric(slide, value, labelText, x, y, w, accent = C.red) {
  slide.addText(value, { x, y, w, h: 0.48, fontFace: mono, fontSize: 24, bold: true, color: accent, margin: 0 });
  slide.addShape(pptx.ShapeType.line, { x, y: y + 0.56, w, h: 0, line: { color: C.line, width: 0.7 } });
  slide.addText(labelText, { x, y: y + 0.68, w, h: 0.28, fontFace: font, fontSize: 9.5, color: C.muted, margin: 0 });
}

function imageCard(slide, img, caption, x, y, w, h) {
  slide.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: { color: C.white }, line: { color: C.line, width: 0.6 } });
  slide.addImage({ path: img, x: x + 0.08, y: y + 0.08, w: w - 0.16, h: h - 0.46, sizingCrop: true });
  slide.addText(caption, { x: x + 0.1, y: y + h - 0.3, w: w - 0.2, h: 0.18, fontFace: font, fontSize: 8.5, color: C.muted, margin: 0 });
}

function pipelineNode(slide, id, titleText, desc, x, y, w, h, accent = C.ink) {
  slide.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: { color: C.white }, line: { color: C.line, width: 0.7 } });
  slide.addText(id, { x: x + 0.14, y: y + 0.12, w: 0.5, h: 0.2, fontFace: mono, fontSize: 8, bold: true, color: accent, margin: 0 });
  slide.addText(titleText, { x: x + 0.14, y: y + 0.38, w: w - 0.28, h: 0.26, fontFace: font, fontSize: 12, bold: true, color: C.ink, margin: 0 });
  slide.addText(desc, { x: x + 0.14, y: y + 0.78, w: w - 0.28, h: h - 0.9, fontFace: font, fontSize: 8.5, color: C.muted, fit: "shrink", margin: 0 });
}

function arrow(slide, x1, y1, x2, y2) {
  slide.addShape(pptx.ShapeType.line, {
    x: x1, y: y1, w: x2 - x1, h: y2 - y1,
    line: { color: C.red, width: 1.1, beginArrowType: "none", endArrowType: "triangle" },
  });
}

function barChart(slide, data, x, y, w, h, maxVal, unit) {
  const barW = w / data.length * 0.42;
  const gap = w / data.length * 0.58;
  data.forEach((d, i) => {
    const bx = x + i * (barW + gap) + gap * 0.34;
    const bh = h * d.value / maxVal;
    slide.addShape(pptx.ShapeType.rect, {
      x: bx, y: y + h - bh, w: barW, h: bh,
      fill: { color: d.color }, line: { color: d.color },
    });
    slide.addText(String(d.value), { x: bx - 0.12, y: y + h - bh - 0.3, w: barW + 0.24, h: 0.2, fontFace: mono, fontSize: 8.4, color: C.ink, align: "center", margin: 0 });
    slide.addText(d.label, { x: bx - 0.25, y: y + h + 0.1, w: barW + 0.5, h: 0.35, fontFace: font, fontSize: 8.2, color: C.muted, align: "center", fit: "shrink", margin: 0 });
  });
  slide.addShape(pptx.ShapeType.line, { x, y: y + h, w, h: 0, line: { color: C.ink, width: 0.7 } });
  slide.addText(unit, { x, y: y - 0.3, w: 2.4, h: 0.2, fontFace: mono, fontSize: 7.5, color: C.muted, margin: 0 });
}

function twoColumnText(slide, left, right, x, y, w) {
  const colW = (w - 0.35) / 2;
  slide.addShape(pptx.ShapeType.rect, { x, y, w: colW, h: 3.0, fill: { color: C.white }, line: { color: C.line, width: 0.6 } });
  slide.addShape(pptx.ShapeType.rect, { x: x + colW + 0.35, y, w: colW, h: 3.0, fill: { color: C.white }, line: { color: C.line, width: 0.6 } });
  body(slide, left, x + 0.25, y + 0.25, colW - 0.5, 2.4, 11.5);
  body(slide, right, x + colW + 0.6, y + 0.25, colW - 0.5, 2.4, 11.5);
}

function slide01() {
  const slide = pptx.addSlide();
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 0.22, h: H, fill: { color: C.red }, line: { color: C.red } });
  slide.addText("肺部 CT 结节检测与可视化系统", {
    x: 0.72, y: 1.15, w: 8.6, h: 0.7, fontFace: font, fontSize: 31, bold: true, color: C.ink, margin: 0,
  });
  slide.addText("传统图像处理版 · C++17 / OpenCV · LUNA16", {
    x: 0.76, y: 2.02, w: 7.2, h: 0.28, fontFace: mono, fontSize: 11, bold: true, color: C.red, margin: 0,
  });
  slide.addText("Stage0-5 pipeline: MHD/RAW 读取、肺实质分割、频域增强、候选检测、特征筛选、GUI 可视化", {
    x: 0.76, y: 5.82, w: 9.3, h: 0.35, fontFace: font, fontSize: 12, color: C.muted, margin: 0,
  });
  slide.addImage({ path: A.overlay, x: 9.25, y: 0.95, w: 3.25, h: 3.25 });
  slide.addImage({ path: A.mip, x: 9.25, y: 4.35, w: 3.25, h: 1.85 });
  slide.addShape(pptx.ShapeType.line, { x: 0.76, y: 2.55, w: 7.25, h: 0, line: { color: C.ink, width: 0.9 } });
  slide.addText("医学图像处理大作业 / 课堂汇报", { x: 0.76, y: 6.75, w: 5, h: 0.25, fontFace: mono, fontSize: 8.5, color: C.muted, margin: 0 });
}

function slide02() {
  const slide = pptx.addSlide();
  title(slide, "选题动机与课程契合", 2, "why this problem is suitable for classical DIP");
  metric(slide, "3–30 mm", "LUNA16 结节尺寸范围：适合用尺度、频域和形态特征建模", 0.82, 1.82, 2.45);
  metric(slide, "No DL", "不使用深度学习；完整展示课程 1-8 章知识点", 3.95, 1.82, 2.5, C.blue);
  metric(slide, "4 min", "课堂演示要求：短时间内讲清楚流程、结果与可视化", 7.05, 1.82, 2.55, C.green);
  twoColumnText(
    slide,
    "任务目标\n从三维肺部 CT 数据中自动检测可疑结节位置，并输出可解释的图像、表格与 GUI 展示。\n\n课程关联\n采样与量化、灰度变换、傅里叶增强、形态学、分割、区域描述与纹理特征。",
    "设计约束\n使用 C++ 与 OpenCV；保留原始 HU 数据；BMP/PGM/PPM 仅作为展示输出，不替代算法中的体数据。\n\n汇报重点\n不是追求深度学习 SOTA，而是证明传统图像处理 pipeline 能端到端运行、验证和调参。",
    0.82, 3.82, 8.8
  );
}

function slide03() {
  const slide = pptx.addSlide();
  title(slide, "数据集与 Ground Truth", 3, "LUNA16 subset8 + official annotations.csv");
  pipelineNode(slide, "DATA", "LUNA16 subset8", "88 例胸部 CT\n.mhd 记录体数据元信息\n.raw 保存原始 HU 体素", 0.8, 1.75, 2.55, 2.0, C.red);
  pipelineNode(slide, "GT", "annotations.csv", "60 例有结节标注\n118 个标准结节\n每行给出 3D 中心坐标与直径", 3.75, 1.75, 2.65, 2.0, C.blue);
  pipelineNode(slide, "MATCH", "坐标匹配", "程序输出体素坐标\n由 Offset / Spacing 转为世界坐标\n距离 <= 标注半径即命中", 6.82, 1.75, 3.0, 2.0, C.green);
  arrow(slide, 3.35, 2.75, 3.72, 2.75);
  arrow(slide, 6.4, 2.75, 6.78, 2.75);
  imageCard(slide, A.window, "肺窗切片：二维观察基础", 10.15, 1.45, 2.35, 2.35);
  label(slide, "Ground Truth 不是逐层 mask", 0.82, 4.35, 3.2);
  body(slide, "专家标注以 3D 结节中心 + 直径的方式给出；一个结节可能跨多层 CT，但 CSV 中只对应一行。程序验证时使用三维距离匹配，而不是肉眼逐张判断红圈。", 0.82, 4.75, 9.2, 0.95, 14);
  metric(slide, "88", "subset8 CT cases", 10.35, 4.62, 0.92, C.red);
  metric(slide, "118", "annotated nodules", 11.42, 4.62, 1.05, C.blue);
}

function slide04() {
  const slide = pptx.addSlide();
  title(slide, "系统 Pipeline：Stage0–5", 4, "from raw volume to visualized candidates");
  const nodes = [
    ["0", "IO / 肺窗", ".mhd/.raw 解析\nHU 保留 + 窗宽窗位"],
    ["1", "肺分割", "阈值 + 形态学\n连通域 + 空洞填充"],
    ["2", "频域增强", "2D FFT\n高斯差带通滤波"],
    ["3", "候选检测", "肺 ROI 内亮斑\n连通域生成 2D 候选"],
    ["4", "特征筛选", "直径 / 圆形度 / HU\nGLCM 纹理 / 跨层信息"],
    ["5", "可视化", "overlay / MIP\nfeatures.csv / GUI"],
  ];
  nodes.forEach((n, i) => {
    const x = 0.75 + (i % 3) * 4.05;
    const y = 1.72 + Math.floor(i / 3) * 2.25;
    pipelineNode(slide, `STAGE ${n[0]}`, n[1], n[2], x, y, 3.38, 1.52, i === 0 ? C.red : C.ink);
  });
  arrow(slide, 4.08, 2.48, 4.42, 2.48);
  arrow(slide, 8.12, 2.48, 8.48, 2.48);
  arrow(slide, 2.45, 3.25, 2.45, 3.92);
  arrow(slide, 4.08, 4.72, 4.42, 4.72);
  arrow(slide, 8.12, 4.72, 8.48, 4.72);
  label(slide, "设计原则", 0.75, 6.05, 1.2);
  body(slide, "前端尽量不漏：生成较充分的候选；后端逐步削减假阳性：用可解释特征和训练集调参控制输出。", 1.65, 5.98, 9.6, 0.38, 13);
}

function slide05() {
  const slide = pptx.addSlide();
  title(slide, "Stage0–1：从 HU 切片到肺掩膜", 5, "windowing and lung parenchyma segmentation");
  imageCard(slide, A.window, "肺窗窗口图：适合观察肺实质", 0.78, 1.65, 3.0, 3.05);
  imageCard(slide, A.mask, "肺掩膜：白色区域进入后续搜索", 4.02, 1.65, 3.0, 3.05);
  imageCard(slide, A.overlay, "绿色轮廓：分割边界叠加验证", 7.26, 1.65, 3.0, 3.05);
  label(slide, "算法要点", 0.82, 5.25, 1.2);
  body(slide, "HU < -320 初步提取低密度肺区域；删除边界连通空气；开运算去噪；保留最大两连通域；闭运算与空洞填充修复肺内结构。", 0.82, 5.62, 10.8, 0.5, 13);
}

function slide06() {
  const slide = pptx.addSlide();
  title(slide, "Stage2–3：频域增强与二维候选生成", 6, "band-pass response creates candidate seeds");
  imageCard(slide, A.bandpass, "频域带通增强图：突出中等尺度结构", 0.82, 1.65, 3.25, 3.25);
  imageCard(slide, A.overlay, "检测叠加图：红圈为程序预测候选", 4.35, 1.65, 3.25, 3.25);
  pipelineNode(slide, "FFT", "高斯差带通", "sigmaLow = 30\nsigmaHigh = 5\n压低背景与高频噪声", 8.02, 1.72, 2.18, 1.6, C.red);
  pipelineNode(slide, "SEED", "亮斑种子", "增强响应位于前 15%\n且 -500 < HU < 250", 10.42, 1.72, 2.18, 1.6, C.blue);
  pipelineNode(slide, "CC", "连通域候选", "闭运算连接近邻\n每个白色区域生成 2D 候选", 8.02, 3.65, 4.58, 1.25, C.green);
  label(slide, "候选不是 ground truth", 0.82, 5.55, 2.4);
  body(slide, "红圈代表程序认为“可疑”的位置；真实结节需要通过 annotations.csv 的三维中心坐标进行距离验证。", 3.0, 5.48, 8.6, 0.42, 13);
}

function slide07() {
  const slide = pptx.addSlide();
  title(slide, "Stage4：二维特征与三维合并", 7, "interpretable features for false-positive reduction");
  const feats = [
    ["几何", "面积、等效直径、圆形度、外接框"],
    ["灰度", "meanHU、stdHU，反映组织密度与内部波动"],
    ["纹理", "GLCM contrast / energy / homogeneity"],
    ["跨层", "相邻切片位置接近者合并，得到 slice_count"],
  ];
  feats.forEach((f, i) => pipelineNode(slide, `F${i + 1}`, f[0], f[1], 0.82 + i * 3.08, 1.75, 2.55, 1.75, i === 0 ? C.red : C.ink));
  label(slide, "最终 tuned 过滤规则", 0.82, 4.25, 2.0);
  body(slide, "圆形度 ≥ 0.46；meanHU ∈ [-410, 60]；stdHU ∈ [25, 210]；GLCM contrast ≤ 3.3；homogeneity ≥ 0.45；slice_count ≤ 18；每例最多保留 180 个候选。", 0.82, 4.65, 11.0, 0.62, 13.5);
  slide.addShape(pptx.ShapeType.rect, { x: 0.82, y: 5.72, w: 11.25, h: 0.62, fill: { color: C.ink }, line: { color: C.ink } });
  slide.addText("目标：保持召回率不下降，同时显著减少红圈数量与假阳性候选。", {
    x: 1.05, y: 5.9, w: 10.6, h: 0.24, fontFace: font, fontSize: 12.5, color: C.white, bold: true, margin: 0,
  });
}

function slide08() {
  const slide = pptx.addSlide();
  title(slide, "验证设计：训练集调参，测试集验收", 8, "avoid tuning on the test set");
  metric(slide, "62", "训练集 CT 数", 0.82, 1.75, 1.4, C.red);
  metric(slide, "26", "测试集 CT 数", 2.62, 1.75, 1.4, C.blue);
  metric(slide, "78", "训练集标注结节", 4.42, 1.75, 1.65, C.green);
  metric(slide, "40", "测试集标注结节", 6.44, 1.75, 1.65, C.red);
  imageCard(slide, A.mip, "MIP：整例 CT 的最大密度投影概览", 9.15, 1.28, 3.0, 2.2);
  pipelineNode(slide, "1", "训练集搜索", "根据候选特征分布\n调整 HU / 纹理 / 层数规则", 0.82, 4.1, 2.75, 1.3, C.red);
  pipelineNode(slide, "2", "固定 tuned 参数", "写入 C++ 命令行参数\n保持实验可复现", 4.0, 4.1, 2.75, 1.3, C.blue);
  pipelineNode(slide, "3", "测试集只评估", "不再看测试集调参\n报告最终泛化结果", 7.18, 4.1, 2.75, 1.3, C.green);
  arrow(slide, 3.58, 4.76, 3.98, 4.76);
  arrow(slide, 6.76, 4.76, 7.16, 4.76);
}

function slide09() {
  const slide = pptx.addSlide();
  title(slide, "实验结果：召回保持，假阳性约减半", 9, "baseline vs tuned on train/test split");
  barChart(slide, [
    { label: "Train\nBaseline", value: 193.3, color: C.ink },
    { label: "Train\nTuned", value: 92.5, color: C.red },
    { label: "Test\nBaseline", value: 172.0, color: C.ink },
    { label: "Test\nTuned", value: 83.4, color: C.red },
  ], 0.9, 1.62, 5.2, 3.2, 210, "Strict false positives / scan");
  barChart(slide, [
    { label: "Train\nBaseline", value: 56.4, color: C.ink },
    { label: "Train\nTuned", value: 56.4, color: C.red },
    { label: "Test\nBaseline", value: 62.5, color: C.ink },
    { label: "Test\nTuned", value: 62.5, color: C.red },
  ], 7.0, 1.62, 4.8, 3.2, 75, "Strict recall (%)");
  label(slide, "关键结论", 0.9, 5.55, 1.2);
  body(slide, "在测试集上严格召回保持 25/40 = 62.5%，候选数从 263.0/例降到 135.4/例，严格假阳性从 172.0/例降到 83.4/例。", 1.8, 5.47, 10.1, 0.5, 13.5);
}

function slide10() {
  const slide = pptx.addSlide();
  title(slide, "消融与调参方向", 10, "what changed and why");
  const rows = [
    ["参数组", "调整方向", "目的"],
    ["meanHU", "[-410, 60]", "排除过暗空气纹理与过亮血管/骨性结构"],
    ["stdHU", "[25, 210]", "剔除过均匀噪声块与内部跳变过大的结构"],
    ["GLCM", "contrast ≤ 3.3；homogeneity ≥ 0.45", "保留相对均匀、不过度复杂的候选"],
    ["slice_count", "≤ 18", "抑制长条状血管或跨层粘连"],
    ["Top-K", "每例最多 180", "按解释性评分保留更像结节的候选"],
  ];
  const x = 0.82, y = 1.58;
  const widths = [2.1, 3.5, 6.0];
  rows.forEach((r, i) => {
    const yy = y + i * 0.64;
    slide.addShape(pptx.ShapeType.rect, { x, y: yy, w: 11.6, h: 0.58, fill: { color: i === 0 ? C.ink : C.white }, line: { color: C.line, width: 0.5 } });
    let cx = x + 0.18;
    r.forEach((txt, j) => {
      slide.addText(txt, { x: cx, y: yy + 0.15, w: widths[j] - 0.22, h: 0.24, fontFace: font, fontSize: i === 0 ? 10 : 9.5, bold: i === 0, color: i === 0 ? C.white : C.ink, fit: "shrink", margin: 0 });
      cx += widths[j];
    });
  });
  label(slide, "负向实验", 0.82, 5.95, 1.2);
  body(slide, "尝试放宽早期候选生成（min-diameter=2.5, min-circularity=0.35）后，测试集召回降至 24/40，候选与假阳性反而增加；因此不采用。", 1.78, 5.88, 10.2, 0.45, 12.5);
}

function slide11() {
  const slide = pptx.addSlide();
  title(slide, "系统输出与现场演示", 11, "what the viewer shows");
  imageCard(slide, A.window, "窗口图", 0.82, 1.55, 2.2, 2.2);
  imageCard(slide, A.mask, "肺掩膜", 3.28, 1.55, 2.2, 2.2);
  imageCard(slide, A.bandpass, "频域增强", 5.74, 1.55, 2.2, 2.2);
  imageCard(slide, A.overlay, "检测叠加", 8.2, 1.55, 2.2, 2.2);
  slide.addShape(pptx.ShapeType.rect, { x: 0.82, y: 4.45, w: 10.8, h: 1.08, fill: { color: C.ink }, line: { color: C.ink } });
  slide.addText("./build/lung_viewer data/demo_view", {
    x: 1.08, y: 4.77, w: 8.8, h: 0.28, fontFace: mono, fontSize: 16, bold: true, color: C.white, margin: 0,
  });
  body(slide, "界面四宫格对应：窗口图 / 肺掩膜 / 频域增强 / 检测叠加；另有 MIP 窗口用于三维概览。", 0.82, 5.95, 10.8, 0.42, 12.5);
}

function slide12() {
  const slide = pptx.addSlide();
  title(slide, "总结与不足", 12, "a complete, explainable, classical image processing system");
  metric(slide, "Stage0–5", "端到端传统图像处理链路已完成", 0.82, 1.72, 2.4, C.red);
  metric(slide, "88/88", "subset8 全量运行成功，无崩溃", 3.65, 1.72, 2.0, C.blue);
  metric(slide, "×0.49", "测试集严格假阳性约减半", 6.05, 1.72, 2.0, C.green);
  metric(slide, "62.5%", "测试集严格召回保持不变", 8.45, 1.72, 2.2, C.red);
  twoColumnText(
    slide,
    "贡献\n1. 纯 C++ 解析 MHD/RAW 并保留 HU。\n2. 用课程方法完成肺分割、频域增强、连通域检测与纹理描述。\n3. 用官方 annotations.csv 完成可复现验证与 train/test 调参。",
    "不足与后续\n1. 假阳性仍偏多，血管结构是主要干扰。\n2. MIP 可视化仍有饱和问题。\n3. 可继续加入长宽比、偏心率、Hessian vesselness 等传统特征。",
    0.82, 4.18, 9.7
  );
  slide.addText("Q&A", { x: 10.88, y: 5.32, w: 1.1, h: 0.42, fontFace: mono, fontSize: 20, bold: true, color: C.red, margin: 0 });
}

[
  slide01, slide02, slide03, slide04, slide05, slide06,
  slide07, slide08, slide09, slide10, slide11, slide12,
].forEach(fn => fn());

pptx.writeFile({ fileName: path.join(outDir, "lung_ct_nodule_detection_report.pptx") });

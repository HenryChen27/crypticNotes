# 新 baseline 评估计划（尚未实现）

1. 显式 evaluation manifest：screenshot、reference 身份、floor、手工 landmark 对、标注来源与质量。按 map 分组；同图多个 example 不视为独立地图。
2. 在像素输入之外加载 GT，仅供评估；人工 ROI 诊断和自动 ROI 端到端实验分别报告。
3. 假设：去除标注后的局部边界及墙体组合能跨域保留相对几何。先人工检查对应局部片段，再比较局部距离变换描述与线段相对几何。
4. 最小 baseline：ROI → visible / unknown / HUD evidence → 新 reference 局部片段索引 → 局部结构候选排名。不得以全图颜色、MSE 或 SSIM 排名。
5. 几何距离给 scale hypotheses 和 uncertainty；局部 anchor voting 给有限 pose hypotheses。只有 Top-K 进入后续 registration，不以全地图多尺度 XY 穷举作为最终架构。
6. 非对称验证只评价游戏可见 evidence，unknown 不提供负证据。无可靠证据时拒识。
7. 消融：未去标注 vs 去标注、无 HUD 排除 vs 排除、局部描述 vs 加相对空间一致性、单向验证 vs 对称诊断。一次只改变一个因素；阈值固定并记录。
8. 检索报告 Top-1/3/5（map 和 map-floor 两种粒度）；Top-5 不足先修 retrieval。另做 GT-map oracle registration 诊断，显式标记非生产指标。
9. 评估 scale 相对误差、translation 像素 L2、GT landmarks 重投影 RMSE（full pose）；缺少 GT 时 null，并报告有效分母。只有身份及楼层正确的 pose 才计入条件误差，同时报告端到端成功率。
10. Final Decision 报告 floor accuracy、UNKNOWN rate、wrong-lock / all samples 及 wrong-lock / accepted；本阶段没有 lock 则标为 N/A。
11. 固定 seed、排序和依赖版本，记录硬件、线程数、索引加载、提取、retrieval、registration 分阶段时延；分别报告全新进程 cold 和 warm 的 median/p95，包含样本数。

数据门槛：增加所有 difficulty / solo / duo、不同 floor、位置、scale、fog、混淆图和无地图负例。六张开发图的指标不能证明泛化或校准 confidence。

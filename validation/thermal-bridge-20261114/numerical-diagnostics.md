# 细网格诊断原始结果补记

工具控制台结果也在本记录保存，避免只保留成功输出。不是独立认证。

1. 初始 2 mm / 1 mm 网格最大温差位置 x=0.015997942386831276 m、y=0.03401470588235295 m，k=0.029；粗 13.748770246738221°C、细插值 14.026867679079936°C。
2. 临时将容量从 40000 提至 160000 的隔离性能试验，1 mm / 0.5 mm，5.719 s，拒绝：`Recomputed linear residual exceeds numerical tolerance`。见原 JSON。
3. 仅改为通量差矩阵作用仍拒绝：`Recomputed linear residual 9.62858e-10 exceeds numerical tolerance 6.00681e-10`。没有生成成功响应文件。
4. 加入真实残差替换重启后，1 mm / 0.5 mm 成功求线性方程；细网格 96000，2884 次迭代、1 次残差重启；真实残差 1.7781372709790284e-10，原阈值不变。全场差仍 0.13354370621775047 K，状态 needs_refinement。见原响应。
5. 初始边长进一步调至 0.8 mm，仍限 160000 单元、25 s 和 6000 次迭代；返回 `Conduction solver exceeded iteration/time budget; no converged result`，没有产生结果文件。停止本批继续调网格，不将预算拒绝算通过。

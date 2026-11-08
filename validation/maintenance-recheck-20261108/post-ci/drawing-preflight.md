# D08下一批预审结果（尚未运行）

上游固定提交929e7a309e300fbf1d8c77fb2277e5744cdca43e，https://github.com/art-programmer/FloorplanTransformation 。

官方PyTorch README声明该移植未充分测试，链接 checkpoint.pth 的Google Drive公开页面。2026-11-08匿名HTTP GET该页面成功200，标题checkpoint.pth；这不证明二进制可完整下载。浏览器工具无法读取该页，后续采用普通公开HTTP读取，没有启动本地浏览器或登录。

代码LICENSE为MIT。外链权重的独立商用授权范围尚未确定；不据此宣称产品可商用、不分发权重。当前只做固定公开预训练研究评估，不进行训练。

train.py保存model.state_dict；加载代码使用旧torch.load，下一步必须限定weights_only=True并严格校验键/形状/有限值，不能执行任意pickle。Model构造会pretrained=True自动下载DRN骨干；完整checkpoint评估应禁用该额外下载、严格加载完整状态，保留适配diff。原依赖torch1.0等过旧，不直接安装到产品环境。原推理脚本会先构建训练集且调用CUDA；不能原样运行。

官方页面：https://drive.google.com/file/d/1e5c7308fdoCMRv0w-XduWqyjYPV4JWHS/view
固定代码：https://github.com/art-programmer/FloorplanTransformation/tree/929e7a309e300fbf1d8c77fb2277e5744cdca43e/pytorch

下一步先有界获取并校验权重、审查推理依赖；仅当可安全加载时冻结新参考输入，才运行一次预定门槛筛查。旧Florence14图不是新盲测。不把论文指标、网络可达或MIT代码许可视作识别准确率/商用许可。若权重不可获取或无法受限加载，保存失败并结束本候选，不能改用不安全加载。

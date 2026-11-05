# OCR依赖、模型与样本来源

运行依赖由backend/requirements.txt固定：RapidOCR 3.10.0、ONNX Runtime 1.31.1、pypdfium2 5.14.0、Pillow 13.0.0，certifi 2026.10.23。传递依赖的已安装身份随DRAWING_OCR_EVIDENCE.json及本地OSV清单记录；尚未声称所有平台二进制供应链完全锁定。环境准备建议先运行 `python -m pip install --upgrade pip==26.3`，再安装requirements-dev。隔离测试pip已升级；未改系统Python。

模型来自官方PyPI RapidOCR包，其三模型文件哈希在backend/drawing_models.py强制校验。源代码与转换模型均由上游以Apache-2.0发布，模型版权仍属Baidu/PaddleOCR适用权利人。完整包内LICENSE和MODEL_LICENSES.md原样保留在third-party/rapidocr-3.10.0/。本仓库不另行拷贝权重，不在用户上传时访问模型下载服务。

ONNX Runtime、Pillow、PDFium/pypdfium2和其他传递依赖各有自身许可与捆绑原生依赖通知；安装包中的许可仍须随实际发布包保留。本文件不是全产品法务认证。打包安装器/容器前需检查实际依赖分发清单，不能只保留本模型的Apache许可。

固定公开旧图来源和公共领域声明见fixtures/drawing_gold/public-kinnear-truth.json及DRAWING_OCR_DELIVERY.md；只使用本地下载原件，不把公开图重发到仓库。合成夹具是自主绘制的测试图，不是工程项目。生成使用Windows系统Microsoft YaHei字体，只提交光栅结果和字体哈希，不复制字体文件；不同字体/渲染版本重新生成不得覆盖现有金标准。

安全扫描：`python scripts/audit_dependencies.py NEW_REPORT_JSON`仅向OSV发送当前Python包名称与版本，结果写入新文件，有命中退出1、请求失败不判通过。它不检查浏览器、OS、EnergyPlus及独立原生库，也不是渗透测试或生产安全证明。首次受影响版本及公告保留于validation/drawing-ocr-20261105/dependency-*.json。修复后53包零命中以查询时刻为限，不自动外推未来版本或其他机器。

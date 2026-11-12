# 本批证据重放

最终产品 1e39397e5356283b62cb971695ba1ad916a3917f；原完整HTTP产品 cc25d2adfcaaaf2bded42eeefda24a8190cd8236，PR71。浏览器未运行；测试均为公开/合成参考，不是实楼校准。

1. 在独立检出目录安装仓库requirements-dev。`python -m pytest tests/test_utility_comparison.py`读取fixtures/test/native_utility_projection.json.gz：数据为真实EnergyPlus输出的选定SQL表投影，包含来源SQL哈希；不是完整SQL。最终52项专项（包括协议来源seam）不能代替下面实际HTTP。
2. 冻结输入在frozen-v1/v2。将frozen-v2复制到新的隔离目录，解压其中weather.epw.gz为同名weather.epw，保留原压缩件；用frozen.json逐个核验列出的文件SHA，不改frozen.json。原CSV、IDF及预先计算的expected.json原样保留。
3. 设置ENERGYPLUS_EXE指向EnergyPlus9.0.1。仅在独立检出副本，把replay-scripts/verify_utility_reference.py逐字节复制到scripts同名路径（此副本保留冻结时CRLF；Git源码标准化LF会改变脚本哈希）。执行 `python scripts/verify_utility_reference.py --inputs <解压的冻结目录> --output <新输出目录>`。每例原生独立核验24个电/气月量，容差不改。不要覆盖本批native-v1/v2。首版失败脚本亦保留。
4. 用replay-scripts/verify_utility_http.py在独立检出副本替换同名脚本后执行 `python scripts/verify_utility_http.py <解压冻结目录> <新HTTP输出目录>`。新服务只监听回环地址，账号密码随机生成且不记录；三年度真实仿真和全部接口使用新数据库，finally停止服务。不指向原型或正式数据。输出summary.json中的runtime_path用于定位完整SQL。
5. 官方ZIP链接/哈希见public-source/archive-receipt.json。xlrd2.0.2是仅验证用读取器，未加入应用依赖。workbook-selected-facts.json保留原表前18行便于追溯；frozen-v2/public-monthly-reference.json明确选D7:D18以及S=1.1M算术变换，不冒充原生预测。原3.1 IDF未转换或原生验收。
6. `frontend`目录运行Node内置测试与Vite构建，日志见frontend-final.log/frontend-build.log。没有浏览器/视觉验收。

初次原生日志目录失败、首轮3个后端失败和后续修正日志全部保留。后端源码与真实HTTP输入/计算实现摘要见http-v1/inputs.json；逐次实际响应列表含匿名与其他账号，见summary.json。原生输出ERR/MTD及相关摘要可核对；原始PDF、ZIP、读取器、私有数据库和完整SQL留在C盘，不放入Git。manifest.json覆盖归档文件，不能据此宣称原始数据就是实测数据。

最终日期边界修复见final-date-guard.diff、calendar-upper-bound-first.json、backend-upperdate-final.log。它只改异常拒绝，不改合法账期积分。未重跑已通过原生批；http-v1/inputs.json中的源码SHA属于首轮HTTP产品，不是最终日期修复提交。旧后端CI被新提交取代并主动取消，superseded-ci.json保留原因；最终精确提交CI另存post-ci。

公开事实独立提取命令：`python public-source/reextract.py <52414-01.zip> <新的事实JSON> <隔离xlrd2.0.2目录>`。脚本先核验官方ZIP哈希及成员大小，再只提取原表前18行；extraction-receipt.json记录工作簿SHA和读取器版本。已与归档选定事实逐项相等，不执行工作簿宏。

# 环境与脚本失败保留

以下为工具输出复述，不冒充原始运行日志：首次手动解压manifold3d wheel后ImportError: DLL load failed while importing manifold3d，原因是未按wheel规范安置.data/platlib中的随包DLL；标准pip目标安装后成功。首次安装请求自动审批超时未执行，允许重试后成功，无未决授权。

integrate_api_v1.py前半段编辑已执行，随后读取extensions.py使用Windows默认GBK导致UnicodeDecodeError；只补做未执行的后半段并去掉未使用导入，没有重复追加依赖。后续编辑均显式UTF-8。应用真实测试的失败见tests-windows-v1/v2.log及linux-backend-v1.log，浏览器脚本失败见browser-union-v1/v2.log。

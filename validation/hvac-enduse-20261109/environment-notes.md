# 环境及记录边界

- 全部计算、账户和日志位于 C 盘隔离临时目录。原型、本机正式数据及 main 未修改。浏览器按用户决定未开启。
- 初次设计日冻结因 private_mkdir 的父目录不存在而报 WinError 3；建立专用父目录后才冻结，未产生原生结果。该首次工具输出未另存文件，不伪造原始日志。
- 读取进程清单的 Get-CimInstance 受沙箱限制失败；随后读取实际年度 receipt 的 completed/server_stopped 验证结束，没有再次启动旧运行。
- 前端使用上批已核对锁文件的 C 盘依赖目录和 Node24.22.1，无新增下载。既有 Three 构建大包警告未消除。
- 单元测试保留 Starlette/httpx 弃用警告。CI 使用项目依赖安装；本批不是依赖升级。
- annual-http-final/receipt.json 的 responses 只统计主客户端。8 次匿名/外账号 HTTP 请求未进入该主客户端 events，但逐项状态断言在 checks.json、实际请求在 server.log；不能将 events 称作全部请求日志。
- 大型 SQL 仅在 local-raw-sql-index.json 记录原路径、大小和 SHA。native_hvac_enduse_projection.json.gz 来自首次成功 M01 年度 SQL 的有限原生投影，用于 CI；不冒充再次原生运行。
- 年度 EPW 在归档中无损 gzip 压缩，复现前解压回同名 weather.epw；原文件哈希在各 frozen.json。五个年度工况来自设计日受控工况的延伸，不能计作另外五个独立物理模型。

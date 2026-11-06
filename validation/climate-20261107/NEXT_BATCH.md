# 下一批：天气输入可信度与设计日

本计划建立于IFC批次全量回归期间，尚未修改气候产品源码。原始反例见preflight-probe.json与脚本；源天气文件不变。六例中正常对照通过，五例异常也被validate_epw接受：99.9干球缺测、999湿度缺测、负气压、NaN直射辐射、900度纬度。随后认证API上传/依据确认/准入也已复现：六例can_simulate均true且无blocker。未提交仿真，数据库任务数0；不是实际能耗错误证据。

1. 冻结API复现：独立账号/项目/依据确认，验证INVALID_SOURCE是否缺失；保留原件及失败记录。不得直接运行不可信天气冒充可用结果。
2. 按固定EnergyPlus 9.0数据字典和本机引擎源码区分必需物理字段、缺测可推导字段、未使用字段；不可简单要求所有35列永无缺测，避免拒绝合法公开天气。
3. 校验站点坐标、时区、高程、关键天气数值、缺测标记及年度时钟；错误包含行号/字段/单位，保留用户原件，不自行插补。对可推导缺测制定显式政策和追溯回执。
4. 分别验证正常寒冷、温和、炎热公开站点；固定来源、版本、字节哈希和许可证。检查原生ERR/SQL及年度完整性。只同模型改变天气的情景不能代表规范设计或某个真实建筑。
5. 设计日与全年能耗分离。先审查IDF/配套DDY、定容与天气站点绑定，再建立独立简化模型的热平衡/负荷基准；设计日输出不得从全年总能耗推测。
6. 专项、双平台真实引擎、浏览器/报告、前后失效及原件保护验收后复评。input_validation参与物理版本哈希，因此改动后旧物理结果失效；不得改写历史manifest，需新运行留证。

参考：https://bigladdersoftware.com/epx/docs/9-0/auxiliary-programs/energyplus-weather-file-epw-data-dictionary.html 与 https://bigladdersoftware.com/epx/docs/9-0/input-output-reference/group-location-climate-weather-file-access.html 。新发现暂编CL-P01（高，API已复现/待修复），不当作IFC补丁引入的回归，也不在当前批次宣称关闭。

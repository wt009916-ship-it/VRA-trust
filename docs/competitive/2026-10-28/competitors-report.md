# 竞品对标与产品取舍：稀土智暖 VRA-Trust
*Skill: startup-competitors | Generated: 2026-10-28*

## 当前判断

[Opinion，置信中高] 自动建模、AI、API、材料比选、Pareto、校准和追溯报告都已存在于同类产品，不能单独定义本产品优势。我们的复杂形态覆盖有所扩大，但完整高楼、中央系统、现场校准和正式工程交付仍有缺口。优先服务的任务应是既有公共建筑改造前期的缺证处理与条件决策，让工程师看清输入范围、假设、版本变化及下一步资料要求。这是可验证的产品定位，尚无证据证明市场独有、能耗更准或工程工时更少。本轮据此实现[工程复核与交接](../../ENGINEERING_REVIEW.md)，并保留可运行的开放接口和原生计算依据。

## 证据规则与对象

[Data，官方陈述置信中至高，运行效果未验证] 下表来自官方产品、手册、发布与帮助页面；不是购买授权后的同题实跑。产品不同模块、版本及地区分开记录；未核实不等于缺失。没有以第三方更新时间、旧价格、破解环境或某一条抱怨代表当前产品。

|对象|可核实的能力与代际|我们应承认的差距 / 产品取舍|
|---|---|---|
|深圳斯维尔THS-Becs及设计院方案|官方有节能、日照、负荷等模型应用；当前精确Becs版本、SKU及详细授权未核实。[官方方案](https://www.thsware.com/FrontEndPlugin/Product/IndustrySolutions?IS=1)|[Opinion] 国内设计流程与模型复用是直接对照；应按具体节能模块同题验收，不能笼统声称自动建模领先。|
|PKPM绿色低碳/Agent|建研院2026年9月宣布Agent2.5、绿色低碳2027；产品中心有CAD/BIM、一模多用与溯源报告说明。[发布](https://www.cabr.cn/zgjyy/xwzx/xwdt/gswx/2026/9/I1550547907059384320.html)、[产品](https://product.pkpm.cn/productDetails?productId=14)|[Opinion] AI和报告追溯已是其方向；我们尚未完成国内规范审查、训练支持和工程签发，不能承诺替代。2026 PLUS与2027不拼成一款已实测软件。|
|广联达建筑性能分析平台/广碳云|官方课程配套页列数维/Revit/CAD、一模多算、全年负荷/系统能耗/碳；广碳云列材料成本与生命周期碳比选。[性能平台说明](https://www.glodon.com/product/486)、[广碳云](https://www.glodon.com/product/405)|[Opinion] 应比较其性能/碳模块，不能只找算量软件作对手。本项目当前没有完整LCA与生命周期经济评价。|
|DesignBuilder|官方更新页列v2027.1和EnergyPlus25.1；已有复杂几何交换、系统扩展；手册有优化、约束及不确定性/敏感性分析。[版本](https://support.designbuilder.co.uk/support/solutions/articles/103000294299-designbuilder-new-version-feature-list)、[分析类型](https://designbuilder.co.uk/helpv2025.1/Content/AnalysisTypeOptimisation.htm)|[Opinion] 我们仍限定EnergyPlus9.0.1与独立PTHP，物理系统范围、引擎代际和建模效率是差距。迁移引擎须重新验收，不只改版本号。|
|IESVE/iSCAN|官方有BIM导入检查/修复/选择和DXF到3D；iSCAN有运行数据、模型校准及审计型证据。[BIM](https://www.iesve.com/software/bim)、[ModelIT](https://www.iesve.com/software/virtual-environment/applications/modelit)、[iSCAN](https://www.iesve.com/products/iscan)|[Opinion] 不能说竞品只会算、本产品才有证据。我们没有客户账单校准和M&V闭环，先把当前假设和不成立条件交代完整。|
|Autodesk Forma Carbon Insights及协作模块|当前碳分析与Revit能量分析模型联动；协作模块另有Issue/BCF出口。[碳分析](https://www.autodesk.com/products/forma-carbon-insights/overview)、[问题导出](https://help.autodesk.com/cloudhelp/ENU/Build-Issues/files/Issues_Export.html)|[Opinion] 项目协同、问题管理、权限或BCF不是我们的独家能力；本轮仅实现问题文字交接，不冒称完整双向协同。|
|cove/analysis.tool|公开API有几何与结果接口；官方宣布学术许可于2025年底结束，当前服务方向变化。[API说明](https://help.covetool.com/en/articles/6022777-what-is-the-cove-tool-api)、[教育公告](https://cove.inc/education-resources/)|[Opinion] 不沿用旧免费教育账号/旧售价作为测试或价差依据；当前商业模块、区域和实际可用性需申请合法许可后验证。|
|Honeybee/OpenStudio开放工具链|本项目已复用Honeybee；其几何校验、HVAC与OpenStudio工作流生态更广。[Honeybee校验](https://www.ladybug.tools/honeybee-core/docs/cli/validate.html)、[OpenStudio](https://openstudio.net/)|[Opinion] 是集成基础也是替代方式；包装上游物理能力不能称原创。我们的工作应集中在来源责任链与工程操作，而非重复声称拥有仿真器。|

[Opinion，威胁判断置信中] PKPM、斯维尔、广联达在国内工程流程上应视为高相关对手；DesignBuilder/IES在性能工程深度上为高相关对手。Autodesk组合与Honeybee/OpenStudio是强相邻替代；cove当前业务代际需再核实。这里是任务重叠判断，没有市场份额或客户流失数据，不量化“威胁分数”。

## 本轮实际打造的侧重点

|工程师要回答的问题|本次落地|验证方式与边界|
|---|---|---|
|哪些输入还缺、哪些是假设？|自动生成用途、推导几何、边界/窗/运行/设备与材料验证条目；关联原件哈希、空间、楼层和源构件|[Data] 用公开FZK及真实结构高楼测试；不是任意输入的完备审查，不取代独立几何校验。|
|上一版复核还能沿用吗？|处置绑定资料快照、模型/建筑/证据/材料版本；变化后旧记录保留并需重新复核|[Data] 验收名称修订、来源损坏、建筑声明变化、旧快照提交409与修订历史。全局保守失效，未实现逐房间物理重算。|
|到底改了什么？|按稳定空间ID列新增/移除、几何、用途、热工、设备及来源字段变化|[Data] 不凭同名合并不同空间；变更分类解释影响，实际计算仍按整版绑定核验。|
|怎么交给使用其他工具的工程师？|JSON/HTML、BCF2.1问题文字、同题输入清单及SHA256交接包|[Data] 依据公开BCF Schema核验输出；不含源原件、相机、截图、签名或双向问题同步，没有商业BIM客户端实机导入成绩。|
|是否能据此推荐材料或对外承诺？|保留未签署状态、缺证与假设；接受处置不解除Gate、不升级来源性质|[Data] 当前材料候选/有限域结果仍受原有证据、预算与目标约束；没有实测稀土节能优势。|

[Opinion，置信中] 可争取的使用场景是资料残缺、多人接力、需要回源解释方案的公共建筑前期咨询，与现有设计软件并用。先把一次交接做好，比覆盖所有设计院工具更容易形成可验收价值。工程师是否愿意付费仍是待验证假设。

## 如何证明差异化成立

[Assumption，未验证] 下一次持有合法工具许可的工程师试点，固定同一原件、缺项、天气、范围和交付要求，对照“原有工具+表格”与本产品辅助流程，分别记录建模/找依据/复核/修订交接工时。记录源空间保留率、错误接受次数、旧版误用次数、回源次数、交接漏项与人工接管，不只看是否生成一张图。至少由另一位工程师在不看作者操作过程的条件下接手复核。

[Data] 本次没有竞品许可和客户工时数据，未填写任何节时百分比、预测误差优势或价格胜负。控制样本、不同楼层、重复运行不计作更多真实建筑。[本轮产品验收](../../ENGINEERING_REVIEW.md)与[既有复杂建筑计算证据](../../HIGHRISE_MODELING_ACCEPTANCE.md)分别给出范围。

## 尚待补齐的核心能力

[Opinion，优先级建议] 复杂原件失败闭环、完整幕墙/机电与现代引擎兼容、客户校准、稀土材料对照/老化证据、独立校核签发和团队生产运维，仍先于营销扩张。新的复核交接功能帮助暴露这些缺口，不替代它们。

## Data Gaps

[Data] 缺少同版本商用实跑、可比报价、真实用户复核工时/留存/付费、客户计量和材料现场对照。近期独立口碑样本不足；一条论坛反馈不能说明行业共性。IES部分页面403，斯维尔和部分国内产品为动态页面，需明确抓取限制；发布公告不等于所有模块已在我们机器可用。没有把两条同厂商页面当作独立效果验证。

## Red Flags

[Data] 完整高楼自动热模型、现场精度、正式审查和商业发行授权仍未完成；BCF、追溯、AI或API本身均非市场独有。不能据这份调研称本产品已超过工程软件。

## Yellow Flags

[Data] 模块组合、地区、授权和培训会改变总成本；公开能力未记载不能记为不存在。本轮侧重工程任务与实现，未估算市场集中度、营收或获客成本；应通过实际试点验证定位。

## Sources

所有链接于2026-10-28访问。功能来源为表内官方产品/手册；本项目能力以代码、隔离API和记录为依据。[能力矩阵](competitive-matrix.md)、[价格与进入路径](pricing-landscape.md)、[对照卡](battle-cards/)保留同样边界。

# CAD / PDF / OCR 解析隔离增量

承接 PR #23，将三个处理不可信文件的活动 API 接入 Windows LPAC / Linux Landlock+seccomp。原始文件、解析公式、模型及人工复核语义保留；本批不增加图纸修复、工程量规则或规范覆盖。源码及验收文件身份见 `PARSER_ISOLATION_EVIDENCE.json`，复评仍为 70/100。

## 调用链与边界

`cad.Cad.inspect / standards.Standards.preview / drawings.Drawings.save → parser_runtime.run → execution.supervise → engine_worker → parser_worker`。每个任务在新的私有目录复制输入，核验 SHA256；输入只读、输出可写，控制文件在授权范围外。子进程以 `-I -B -S -X utf8` 启动，只显式加入经过核验的代码与 wheel 路径。未安装依赖、版本不符、隔离缺失或回执缺失均拒绝，不退回普通权限执行。

Windows 每任务新建 LPAC profile，沿用挂起令牌/Job/能力与访问控制核验；Linux 要求非 root、Landlock ABI≥6、libseccomp，沿用只允许必要线程的系统调用规则。共享实现的限制仍适用：Linux 已知路径 stat 元数据及公共系统库可见，aarch64 尚无运行证据，不能描述为 VM 或完整操作系统隔离。

CAD/PDF/OCR 的强制依赖按已安装 wheel 元数据递归解析、检查环境标记和版本，拒绝不支持的 URL/extras 声明。公共运行库以进程内、每类最多一份的私有快照复用；每类最多 1 GiB / 20,000 文件，共三类。不包含客户原件、输出、数据库、账号或密钥。Windows 仅在新建公共副本上授予 ALL RESTRICTED APPLICATION PACKAGES 读取/执行，未修改原安装目录 ACL。输入和输出使用各自任务身份，不能因共享公共代码而跨任务读取业务资料。

首次复制限额并记录所有字节哈希，后续每次核查安装文件大小/mtime、缓存完整清单及全部缓存 SHA256；变化后拒绝并要求重启刷新。没有声称每次重新哈希整个原始安装。每次只读快照仍需校验，不能把 warm cache 描述为零成本。正常退出清理；强制杀死 API 后的孤儿回收仍未实现。

沿用 CAD 2 GiB/20 CPU 秒/30墙钟秒、PDF 512 MiB/20 CPU 秒/30墙钟秒、OCR 2 GiB/40 CPU 秒/60墙钟秒。额外限制共享解析并发2、单任务日志256 KiB、输出128文件和16 MiB（OCR64 MiB），监测 Windows profile 输出。冷缓存准备在解析墙钟计时外，复制阶段单独120秒预算和余量预检；这些不是端到端硬实时保证或硬磁盘配额。Windows 映射内存的既有缺口仍保留。

资源回执包含实际隔离身份、进程、输入副本身份、运行库哈希/大小/文件数、冷热缓存和阶段耗时。解析器版本包括此策略及依赖身份；旧 CAD/OCR/规范提取记录正确失效。物理核心未改，物理哈希保持 `24980c3a62cfba035267af7df98b7775fec71a9958c9049eec31218179f32199`；没有改写历史 manifest。

## 验收范围与独立答案

- 双平台实际文件正反控制：任务输入可读不可写、输出可写；外部合成原件、其他任务和监督控制文件拒读写，公共代码可读不可改。TCP/UDP × IPv4/IPv6 先以普通进程真实收包，再验证隔离拒绝且接收端为空；新增进程拒绝，合成密钥不继承。只使用本机回环，不对外攻击。
- 缓存篡改在执行前拒绝，恢复原字节后新解析成功；容量耗尽和缺文件后释放名额；缺依赖通过真实 API 返回409、原件保留。缺回执、CPU超限、超时及恢复由已有测试改接真实监督器核查。
- 公开 Duplex IFC 的295产品/空间关系、108矩形拉伸体及21声明面积与独立算法一致。217产品取得闭合网格近似量、78存在缺口，不相加冒充净工程量。
- 七张独立合成图覆盖清晰、模糊、低分辨率、倾斜、缺尺寸、噪声重叠和空白。公开 Kinnear 旧图预选12处命中10处、共43候选，保留高分误识别；隔离成功不提高 OCR 准确率。
- 已获授权的本机浏览器账号实际上传公开 IFC 和旧图，并提取合成 PDF 的 `Independent sandbox PDF 1234`。新记录可见、旧记录失效；合成 PDF 未登记成真实规范。截图、实际记录资源回执与控制台检查单独留证，不导出账号/会话表。
- Linux全量来自独立 ext4 源文件副本及自身真实 EnergyPlus 参考运行，Windows使用本机实际引擎。具体全量、前端、公开基准及耗时以证据索引为准；跳过不计通过。Linux全量后仅修改 Windows 专属故障测试的启动同步，不改变产品代码；源快照差异另行记录。

## 缺陷与失败记录

以下证据路径均位于 `validation/parser-isolation-20261105/`。所有失败原样保留，不以最后通过覆盖。

|编号 / 严重程度|功能与问题描述|复现步骤 / 预期结果|实际结果与证据|修复建议及状态|
|---|---|---|---|---|
|PARSER-01 高，已修复|三条解析链原先只有资源限额，没有文件/网络边界|从三个上传接口启动 worker；预期不能读取业务目录或联网|旧启动链普通 subprocess；本批双平台正反探针、API与资源回执验证实际边界|统一受限入口，缺条件拒绝；关闭 LINUX-L01 中解析器缺口|
|PARSER-02 中，已修复|Windows ezdxf 字体初始化探测用户缓存导致 LPAC 拒绝|解析含文本/单位的 DXF；预期不访问用户目录且正常解析|windows-focused-first.log：4失败70通过2跳过；windows-text-diagnostic.log 指向用户字体缓存 WinError5|隔离完成后、导入库前将 profile/cache 环境指向任务输出；不扩大原目录授权|
|PARSER-03 中，已修复|每任务重复制运行库造成冷启动开销|重复解析简单文件；预期有界准备并避免重复复制|windows-runtime-first.log：CAD失败48.83秒、PDF3.89秒、OCR26.0秒；首次无缓存实现|进程内复用经逐次哈希核验的公共快照；最终冷热实测另存，不能等同生产吞吐|
|PARSER-04 中，已修复|缺运行依赖可能成为内部错误|三个API分别注入缺依赖；预期409、原件不动|新增三个API反例断言通过；最终全量日志|转为明确不可用错误，无伪成功|
|PARSER-T01 中，测试已修复|Windows故障测试1秒预算可能在LPAC启动前耗尽|负载下运行原超时用例；预期检验运行中终止|windows-full-final.log：1失败527通过14跳过，calls_executed=None|超时预算8秒、子进程写ready后睡60秒；取消以ready触发，并断言真正启动、ready、错误原因、进程退出和恢复|
|PARSER-T02 低，测试已修复|新增断言误以为退出码包含在通用错误文本|运行退出码7用例；预期检查可信回执|windows-timeout-fixed.log：1失败2通过；文本不含7|直接断言receipt.exit_code==7；保留原失败|
|PARSER-05 中，未关闭|Windows缓存复用仍有较高核验延迟，warm比cold慢|新进程对三类样本各连续调用两次；预期复用后减少准备耗时|windows-cache-benchmark.json：CAD20.06/29.56秒、PDF3.80/5.00秒、OCR17.47/21.61秒；warm准备阶段24.25/4.17/15.88秒|瓶颈位于准备阶段，未精确归因某个系统调用；后续细分性能剖析，不删除缓存完整性断言换速度|
|PARSER-L01 高，未关闭|硬输出额度、API强杀孤儿回收及Windows映射内存仍缺|沿用既有RES/TASK/NATIVE资源反例；预期强制约束和异常恢复|本批只有有界副本、Job/rlimit及50ms输出监测，正常退出清理不等于强杀恢复|后续独立实现所有权清单/孤儿恢复和可支持的硬存储边界|
|PARSER-L02 中，限制|OCR漏检/高分误识别和IFC几何缺口仍在|运行公开基准；预期如实标注未知|Kinnear 10/12；Duplex78缺口；两平台公开输出|继续独立专业基准及算法改进，未训练/未伪造补齐|

初期 Linux 入口探针曾失败：挂载盘脚本读取 errno13、ext4脚本入口 errno1，根因未充分确认；后续显式 `-c`/runpy 与受控路径的实际调用通过。不能将未证实的 stdio/ioctl 推测写为已定位漏洞。原 preflight 日志保留，正式 API 验收才计通过。

最终本机全量：Windows **528 passed / 14 skipped / 6 subtests，646.70秒**；Linux **530 passed / 12 skipped / 6 subtests，312.28秒**。32项前端测试、lint/build、契约导出通过。缓存六次顺序调用和三份公共运行库正常关闭清理通过，但该小样本期间还存在其他本机验收负载，不据此外推生产吞吐或单用户延迟；上述性能缺陷保留。测试客户端弃用、故意重复ZIP成员警告与前端大分块提示保留。

追加只读计时诊断 `preparation-profile.json`：同一CAD样本三次总耗时16.62/26.30/6.81秒；第二次的缓存核验21.62秒，其中文件哈希读取累计21.05秒，第三次分别2.06/1.60秒。缓存文件数仍3943、完整性检查未移除。该证据将高延迟定位到文件读取/哈希阶段，但不能进一步断言磁盘、杀毒软件或内核为根因；PARSER-05继续保留，不把一次变快当稳定性能达标。

PR #24 首轮精确提交 `f242a96dcf38ac14af6298c2753de9606986e531` 六项 push/PR 检查成功；两份 Linux 后端日志均为524 passed / 18 skipped / 6 subtests，231.43/232.20秒。远程未安装 EnergyPlus，这18项跳过不计真实引擎通过。本段与证据索引更新后，最终提交仍须重新通过六项检查；最终 head、合并和日志身份记录在本地 release-receipt.json。

## 复现及下一步

安装锁定依赖，在 Windows 或符合前述条件的非 root Linux 上设置隔离 `VRA_DATA_DIR`。运行 `python -m pytest -q tests/test_parser_isolation.py tests/test_cad.py tests/test_drawings.py tests/test_standards.py tests/test_worker_limits.py`，再执行全量；真实 EnergyPlus 用例需要实际引擎和当前源码参考运行，否则明确跳过或拒绝。公开文件交叉验证用 `scripts/verify_ifc_reference.py` 与 `scripts/verify_drawing_reference.py`，来源及固定答案沿用 fixtures 中清单。

未开展外部攻击、生产压力测试、服务器部署、第二台实体电脑验收或内核漏洞评估。真实 Provider、实楼校准与专业签署仍待条件；评分不因本批通过率上升而自动加分。下一子批优先强杀恢复与硬额度，之后继续专业基准和 Agent，训练与全局前端重构按原路线后置。

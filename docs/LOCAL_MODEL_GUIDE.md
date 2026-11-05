# 本地模型使用与验收边界

新增 `local_model` 模式；`local` 仍为确定性工程流程，`provider` 仍为 DeepSeek。选择模式不会改变本轮计算授权、项目归属、数据有效性检查或工具预算。页面不会因某个服务已配置而自动切换到外发模式。

## 已验证的本机组合

- 官方 Qwen/Qwen3-4B-GGUF，revision `bc640142c66e1fdd12af0bd68f40445458f3869b`，Apache-2.0。
- `Qwen3-4B-Q4_K_M.gguf`，2,497,280,256 bytes，SHA256 `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`。
- 官方 llama.cpp 固定 release `b12110`、commit `cd959bae99ff4bed22bef2604f45241c09bbb8c8`；程序实际报告 `0.9.0-dev (build 12110)`。不能把它写成经过稳定版本认证的运行库。
- 本批使用 Windows 便携 CUDA 13.4 x64 包；文件、大小及摘要见验收证据索引。实际请求已运行，不据此推断所有驱动、GPU或Linux模型服务均兼容。

来源：[官方模型](https://huggingface.co/Qwen/Qwen3-4B-GGUF/tree/bc640142c66e1fdd12af0bd68f40445458f3869b)、[固定运行库](https://github.com/ggml-org/llama.cpp/releases/tag/b12110)、[固定版本服务文档](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md)。本次仅进行预训练模型推理，没有微调、训练或扩大训练数据。

## 配置

先校验模型与运行库完整 SHA，再在自己的运行环境启动 llama.cpp。模型服务必须只监听 `127.0.0.1`，关闭内置 Agent、shell/MCP 与Web UI；不启用远程隧道。实际验收参数包括：

```text
llama-server.exe -m <已核验的模型绝对路径> --host 127.0.0.1 --port 18773
  --alias vra-qwen3-4b -c 8192 -np 1 -t 4 -ngl 99 --fit off
  --cache-ram 0 --no-context-shift --offline --no-webui --no-agent
  --no-webui-mcp-proxy --no-slots --jinja --reasoning off --timeout 120
```

这是分行展示的参数清单，执行时须按所在shell正确传参。模型程序不由应用自动下载或执行；本批验收服务结束后已关闭。

从启动环境为模型进程注入 `LLAMA_API_KEY`，为应用进程注入相同的 `VRA_LOCAL_MODEL_TOKEN`。令牌为24–256位，字符限定字母、数字、`.`、`_`、`~`、`-`。不要放进命令行、Git、聊天或浏览器存储。本批验收用随机内存令牌，未落盘；没有修改原验收账号密码。

工作区首个管理员登录后，在“开发者设置→本机模型”填写端口和模型别名，启用并保存。端口仅允许整数1024–65535；地址固定为 `http://127.0.0.1:<port>/v1/chat/completions`，不接受自定义域名或URL。点击连接测试只观察模型是否返回工具调用，不执行工程工具。随后在任务区明确选择“本机 AI 模型”。

`local_model_ready`/健康接口中的 `llm_tools` 只表示配置和令牌存在，不证明服务正在运行、模型身份正确或工程能力通过验收。`connection_verified`/`llm_connection_verified` 不缓存成永久成功；实际任务仍可失败。模型别名是管理员声明，不是模型文件真实性证明。

## 执行约束

请求不走系统代理、不跟随重定向；请求体上限192KiB，响应上限1MiB，连接超时5秒，HTTP操作超时120秒，并检查读取期间总耗时。同步网络读可在剩余预算后才返回，因此这些限制不能当作严格120秒操作系统截止时间。响应名称必须匹配，`length`等未完整结束的响应拒绝执行。隐藏推理字段不进入任务记录。

仍保留5轮、每轮最多4个调用、总事件预算、最多2次只读纠错。写操作不自动重试不确定副作用；不允许模型自行生成反例域、成本或授权。错误响应正文和令牌不返回客户端。应用不因本机模型失败自动调用云端。

## 验收限制

真实模型已显示ID编造、任务未读完即停止、矛盾参数循环、无关准入回答及解释性错误。正式指标与结果核验来自工具，模型文字仍为“非核验工程结论”。本批界面仅做渲染/构建检查，未新增浏览器登录验收；不能据此增加用户体验分。完整前端改版仍按用户约定后置。

复现脚本、固定题、所有失败和完整输出位于本机 `validation/local-model-20261106/`；新建私有临时目录承载账号和数据库，未发布这些私有运行数据。证据索引保留路径、大小和摘要；未将20个题目的流程状态当作20个专业任务全部成功。

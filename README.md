# ErnieCLI

本地跑不了 Claude Code？又被垄断辣？没关系，咱有自己的 ✊

ErnieCLI 是一个跑在终端里的 AI 编程 Agent，基于文心 Ernie 5.1，带真正的工具调用、百度搜索、多模态，以及一些你用了会说"哦还挺好用"的功能。

```
███████╗██████╗ ███╗  ██╗██╗███████╗
██╔════╝██╔══██╗████╗ ██║██║██╔════╝
█████╗  ██████╔╝██╔██╗██║██║█████╗
██╔══╝  ██╔══██╗██║╚████║██║██╔══╝
███████╗██║  ██║██║ ╚███║██║███████╗
╚══════╝╚═╝  ╚═╝╚═╝  ╚══╝╚═╝╚══════╝
         github.com/JinZongxiao/ernie-cli
```

最新更新：🏟️ **贴吧模式重磅上线** · 📅 周报生成 · 🎭 娱乐三件套 · 💭 折叠思考 → [CHANGELOG](CHANGELOG.md)

---

## 安装

**环境要求**：Python 3.10+，百度 AI Studio 账号

### 1. 拿 API Key

去 [aistudio.baidu.com](https://aistudio.baidu.com) 登录 → 右上角头像 → **访问令牌** → 复制

### 2. 克隆 & 安装

```bash
git clone https://github.com/JinZongxiao/ernie-cli.git
cd ernie-cli
pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

### 3. 配置 Key

```bash
export ERNIE_API_KEY="你的token"
# 或者写进配置文件（下面有完整示例）
```

### 4. 启动

```bash
ernie
```

看到大字母 ERNIE 就说明成功了。

---

## 更新

```bash
cd ernie-cli
git pull
pip install -e .
```

---

## 命令大全

进 REPL 之后，输入 `/` 按 **Tab** 可以补全所有命令。

### 对话

| 命令 | 说明 |
|------|------|
| `/clear` | 清空对话，重新开始 |
| `/compact` | 对话太长时让 Ernie 自己把历史总结一下，省 token |
| `/history` | 查看本次对话记录 |
| `/resume` | 恢复上次在这个目录的对话，断点续聊 |
| `/add <路径>` | 把文件或整个目录内容注入上下文 |

### 模型与搜索

| 命令 | 说明 |
|------|------|
| `/model` | 查看当前模型，列出账号下所有可用模型 |
| `/model <名称>` | 切换模型，如 `/model ernie-lite` |
| `/search on\|off` | 开启/关闭百度原生实时搜索 |

### 多模态

| 命令 | 说明 |
|------|------|
| `/img <路径>` | 附加图片，下一条消息会带上 |
| `/img clipboard` | 从剪贴板抓图（需要 xclip 或 xsel） |

### 工具与代码

| 命令 | 说明 |
|------|------|
| `/review` | 对当前 `git diff` 做 Code Review |
| `/review <文件>` | 对指定文件做 Code Review |
| `/run <命令>` | 直接执行 shell 命令，走权限系统 |
| `/cd <目录>` | 切换工作目录 |

### 贴吧模式 🏟️ v1.4.0 **[NEW]**

把技术问题丢进论坛，让一群有个性的 AI 角色七嘴八舌地帮你整明白。

```
你 → 开帖抛问题 → AI 根据语境调度最相关的吧友回复 → 你追问/反驳 → /done 出方案
```

| 命令 | 说明 |
|------|------|
| `/tieba` | 进入贴吧模式，你先发言抛出话题 |
| `/done` | 结束讨论，终结者整理成 Markdown 方案文件 |
| `@角色名` + Tab | @mention 自动补全，精准呼叫某个吧友 |

**核心原则：你不说话，吧里没人发言。每说一句，系统根据内容调度 1-3 个吧友回复。**

八大常驻吧友（点击查看完整叠楼实录 → [🏟️ Demo](https://jinzongxiao.github.io/ernie-cli/tieba-demo.html)）：

| 角色 | 人设 | 触发时机 |
|------|------|----------|
| 🦅 **鹰眼** | 15年 BAT 老兵，毒舌，只讲技术 | 代码/架构/性能问题 |
| 🐲 **龙场** | 学院派，理论大师，喜欢引文 | 原理/底层/面试题 |
| 🤡 **翻译官** | 前脱口秀演员，把黑话翻译成人话 | 有人说"说人话" |
| 🐟 **摸鱼队长** | 抢沙发，总有不靠谱方案，嘴硬 | 首帖必出，干货稀缺时 |
| 💀 **老PTSD** | 每次都在讲前公司的血泪史 | 提到踩坑/生产事故 |
| 🎯 **产品经理** | 完全不懂技术，明天能上线吗 | UX/业务相关话题 |
| 🔰 **门外汉小白** | 只问问题，永远不回答 | 楼层 >6 且提问简短时 |
| 🔧 **运维老王** | 不配监控等死，默认不信任开发 | 部署/运维/上线 |

> 终结者会先分析楼主需求生成初稿，再结合讨论中你认可的内容修正，输出 `tieba-plan-YYYY-MM-DD.md`。

### 项目与周报

| 命令 | 说明 |
|------|------|
| `/init` | 分析当前项目，生成 ERNIE.md 说明文件 |
| `/tieba` | 贴吧模式：多角色 AI 论坛讨论，`/done` 结束出方案 |
| `/weekly [路径]` | 扫描本工作周改动文件，AI 分析生成 Markdown 周报，默认保存到当前目录 |
| `/status` | 查看当前状态：模型、token 用量、存档情况 |
| `/cost` | 估算本次对话 token 用量与费用 |

### 记忆

每次启动都会把记忆注入系统提示，用来告诉它你是谁、有什么偏好。

| 命令 | 说明 |
|------|------|
| `/memory` | 查看当前记忆内容 |
| `/memory add <内容>` | 追加一条记忆，如 `/memory add 我是后端工程师` |
| `/memory clear` | 清空全部记忆 |

### MCP 服务器 ✨ v1.1.0

MCP（Model Context Protocol）是工具调用的扩展协议，接入后 Agent 能调用第三方能力（数据库查询、设计稿读取等）。AI Studio 后端代理连接，本地无需跑任何进程。

| 命令 | 说明 |
|------|------|
| `/mcp` | 列出当前已连接的 MCP server |
| `/mcp add <label> <url>` | 添加 SSE 类型的 MCP server |
| `/mcp remove <label>` | 移除 MCP server |

配置文件里也可以预设：

```yaml
mcp_servers:
  - type: sse
    url: https://your-mcp-server.com/sse
    server_label: my_tools
```

### Boss 模式 👑 v1.2.0

Ernie 5.1 负责规划，deepseek-v4-flash 负责执行。适合复杂任务拆解。

```
你 → Ernie 5.1（Boss，动嘴）→ deepseek-v4-flash（Worker，动手）
```

| 命令 | 说明 |
|------|------|
| `/boss on` | 开启 Boss 模式，提示符出现 `👑BOSS` 标签 |
| `/boss off` | 关闭，回到普通模式 |
| `/boss` | 查看当前状态及 Worker 配置 |

Worker 模型可在配置文件里修改：

```yaml
boss_mode: false          # 默认关闭，/boss on 开启后不影响此项
worker_model: deepseek-v4-flash
worker_api_key: ""        # 留空则复用主 api_key
worker_base_url: https://api.deepseek.com/v1
```

### 孔子模式 📜 v1.2.1

用论语约束输出风格：言简意赅、知之为知之、不废话。

| 命令 | 说明 |
|------|------|
| `/kong on` | 开启论语约束，提示符出现 `📜论语` 标签 |
| `/kong off` | 关闭，恢复默认输出风格 |
| `/kong` | 查看当前状态 |

约束内容：辞达而已矣 · 知之为知之 · 因材施教 · 过则勿惮改 · 慎于言

配置文件默认开启：

```yaml
harness_enabled: true
```

### 娱乐三件套 🎭 v1.3.0

| 命令 | 说明 |
|------|------|
| `/crack` | 赛博鞭子：ASCII 动画 + 悄悄注入"催更"系统提示，让 Ernie 更卖力 |
| `/roast` | 无情嘲讽：让 Ernie 以毒舌风格点评你最近的操作 |
| `/fortune` | 赛博木鱼：随机抽取一条功德/毒鸡汤/禅语，修炼内功 |

### 折叠思考 💭 v1.3.0

Ernie 5.1 的思考过程默认折叠，不干扰输出。看到 `💭 思考过程 (N 字)` 提示时：

- 按 **`t`** 展开查看完整推理链
- 其他键直接跳过
- 用 `/thinking [N]` 查看第 N 轮的思考（不传参数默认最近一轮）

| 命令 | 说明 |
|------|------|
| `/thinking` | 查看最近一轮思考过程 |
| `/thinking <N>` | 查看第 N 轮思考过程（`/history` 可查轮次编号） |

### 自进化反馈 📊 v1.1.0

启动时询问是否开启，不会强制弹出。开启后每次回答可打分，退出时收集会话评分，导出 DPO 数据集用于微调。

| 命令 / 操作 | 说明 |
|-------------|------|
| 启动时按 `y` | 开启本次会话的反馈收集 |
| 回答后按 `↑` | 标记这轮回答"好" |
| 回答后按 `↓` | 标记这轮回答"差" |
| 退出时打分 | 整体会话评分（解决问题了没、废话多不多、工具调用靠不靠谱） |
| `/export-dataset [路径]` | 导出 DPO 格式的 jsonl 数据集，默认保存到 `~/.ernie/dataset/` |

### 系统

| 命令 | 说明 |
|------|------|
| `/doctor` | 检查环境：API Key、网络连通性、依赖完整性 |
| `/help` | 显示帮助 |
| `/quit` / `/exit` | 退出 |

---

## 工具权限

Agent 执行命令时分三档，不会偷偷给你删东西：

| 级别 | 例子 | 行为 |
|------|------|------|
| ✅ 安全 | `ls`、`cat`、`grep`、`git status` | 自动执行 |
| ⚠️ 写操作 | `mkdir`、`pip install`、`git commit` | 显示命令，回车确认 |
| ☠️ 危险 | `rm`、`sudo`、`curl \| sh` | 红字警告，必须输 `yes` |

`pip install` 会自动加清华镜像。

---

## 配置文件

`~/.ernie/config.yaml` 完整示例：

```yaml
api_key: 你的token
model: ernie-5.1
max_tokens: 8192
temperature: 0.7
search: false
timeout: 120
harness_enabled: false

# Boss 模式
boss_mode: false
worker_model: deepseek-v4-flash
worker_api_key: ""
worker_base_url: https://api.deepseek.com/v1

# MCP server 列表
mcp_servers:
  - type: sse
    url: https://your-mcp-server.com/sse
    server_label: my_tools
```

环境变量优先级高于配置文件：

```bash
export ERNIE_API_KEY="..."
export ERNIE_BASE_URL="..."   # 可选，切换 API 地址
export ERNIE_MODEL="..."      # 可选，覆盖模型
```

---

## 常见问题

**`ernie` 命令找不到？**

```bash
export PATH="$HOME/.local/bin:$PATH"
```

**报 `ERNIE_API_KEY` 未设置？**

```bash
echo $ERNIE_API_KEY
```

没有就按上面配置步骤来。

**连不上 / 超时？**

```bash
ernie  # 进去之后
/doctor
```

**`/img clipboard` 找不到 xclip？**

```bash
sudo apt install xclip    # Ubuntu/Debian
sudo yum install xclip    # CentOS/RHEL
```

---

## License

MIT，随便用，别说是你写的就行。

---

## 人生哲学问答 🐶

> 真实对话，未经剪辑。

```
[ErnieCLI ernie-5.1] ❯ 你是孙笑川吗？
```

哈哈哈哈，我要是孙笑川，那我可太有排面了 😂

我不是孙笑川！我是 ErnieCLI，文心大模型的终端助手 🤖

不过你这么一说……

| 孙笑川 | 我（ErnieCLI） |
|--------|---------------|
| 带带大师兄 | 代码大师兄 🐴 |
| 抽象话创始人 | 抽象代码生成器 |
| 网友：你是不是孙笑川？ | 网友：你是不是🐎中毒了？ |
| 🐶 | 🤖 |

所以……我不是孙笑川，但我可能是🐎中毒版的孙笑川？

---

> *"我不是孙笑川，但我确实有点🐎"* — ErnieCLI，2026

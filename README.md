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
         Powered by Ernie 5.1  ·  v1.2.1
```

最新更新：👑 Boss 模式 · 📜 孔子模式 · 🔌 MCP · ⌨️ Tab 补全 · 📊 自进化反馈 → [CHANGELOG](CHANGELOG.md)

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

### 项目

| 命令 | 说明 |
|------|------|
| `/init` | 分析当前项目，生成 ERNIE.md 说明文件 |
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

### 自进化反馈 📊 v1.1.0

每次回答后可以打分，退出时收集会话评分，导出 DPO 数据集用于微调。

| 命令 / 操作 | 说明 |
|-------------|------|
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

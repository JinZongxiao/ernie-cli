# ErnieCLI 

本地跑不了 Claude Code？又被垄断辣？没关系，咱有自己的 ✊

ErnieCLI 是一个跑在终端里的 AI 编程 Agent，基于文心 Ernie 5.1，带真正的工具调用、百度搜索、多模态，以及一些你用了会说"哦还挺好用"的功能。

---

## 先看看长什么样 👀

```
███████╗██████╗ ███╗  ██╗██╗███████╗
██╔════╝██╔══██╗████╗ ██║██║██╔════╝
█████╗  ██████╔╝██╔██╗██║██║█████╗
██╔══╝  ██╔══██╗██║╚████║██║██╔══╝
███████╗██║  ██║██║ ╚███║██║███████╗
╚══════╝╚═╝  ╚═╝╚═╝  ╚══╝╚═╝╚══════╝
         Powered by Ernie 5.1  ·  v1.0.0
```

---

## 这玩意儿能干啥 🤔

- 🤖 **真 Agent**：能调工具、读文件、执行命令、自己想下一步怎么做，不是那种"建议你运行以下命令"然后把活甩给你的假 Agent
- 🔍 **百度搜索**：知乎、CSDN、掘金、百度百科全都能搜，搜完给你显示来源，不是瞎编的（大概）
- 🖼️ **多模态**：截图直接扔进去问，UI 设计图生成代码、报错截图帮你修、图表帮你分析
- 🇨🇳 **本土化**：`pip install` 自动走清华镜像，懂飞桨、懂百度云、懂国内那套，不会让你去 `apt-get install` 然后等半天超时
- 🔐 **分级权限**：像 Claude Code 那样，读文件自动执行，写文件确认一下，`rm -rf` 你得输 `yes`，不会悄悄给你删库

---

## 环境要求

- Python **3.10+**（3.13 也行，别用 2.x，那是上个世纪的事了）
- 一个百度 AI Studio 账号和 Access Token（免费的，下面教你拿）
- 能联网（这个应该不用说）

---

## 安装教程 🛠️

### 第一步：拿到 API Key

1. 去 [https://aistudio.baidu.com](https://aistudio.baidu.com) 登录（百度账号就行）
2. 右上角头像 → **访问令牌** → 复制那串 token
3. 妥善保管，别像某些人一样贴到公开的 GitHub issue 上 😅

### 第二步：克隆代码

```bash
git clone https://github.com/你的用户名/ernie-cli.git
cd ernie-cli
```

或者直接下载 zip 解压也行，反正就是把代码弄到本地。

### 第三步：安装

推荐用 `pip install -e .`（editable 模式，改代码不用重装）：

```bash
pip install -e .
```

嫌慢？加个镜像：

```bash
pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

装好之后终端里就有 `ernie` 命令了。验证一下：

```bash
ernie --version
# ErnieCLI 1.0.0
```

没报错就行，报错了看下面的 [常见问题](#常见问题)。

### 第四步：配置 API Key

**方法一（推荐）**：环境变量，一劳永逸

```bash
# 加到你的 ~/.bashrc 或 ~/.zshrc
export ERNIE_API_KEY="你的token粘贴在这"

# 然后 source 一下生效
source ~/.bashrc
```

**方法二**：配置文件，适合不想每次 export 的人

```bash
mkdir -p ~/.ernie
cat > ~/.ernie/config.yaml << 'EOF'
api_key: 你的token粘贴在这
model: ernie-5.1
EOF
```

**方法三（不推荐）**：每次手动传，累了

```bash
ERNIE_API_KEY=xxx ernie
```

### 第五步：启动！

```bash
ernie
```

看到大字母 ERNIE 就说明成功了 🎉

---

## 基础用法

### 聊天

直接输入就行，没什么门槛：

```
[ErnieCLI ernie-5.1] ❯ 帮我写一个读取 CSV 文件的 Python 脚本
```

它会自己决定要不要看你的文件、要不要执行命令，不用你操心。

### 单次提问（不进 REPL）

```bash
ernie --ask "Python 里 list 和 tuple 有什么区别"

# 带图片
ernie --ask "这个报错怎么修" --image error_screenshot.png

# 开搜索
ernie --ask "今天 Python 3.13 有啥新特性" --search
```

---

## 命令大全 📋

进入 REPL 之后，输入 `/` 再按 **Tab** 可以补全所有命令。

### 对话管理

| 命令 | 干啥的 |
|------|--------|
| `/clear` | 清空对话，重新开始，就当刚才什么都没说 |
| `/compact` | 对话太长了？让 Ernie 自己把历史总结一下，省 token |
| `/history` | 看看刚才聊了什么 |
| `/resume` | 恢复上次在这个目录的对话，断点续聊 |
| `/add <路径>` | 把文件或整个目录塞进上下文，让它看代码用的 |

### 模型与搜索

| 命令 | 干啥的 |
|------|--------|
| `/model` | 看当前用的什么模型，顺便列出账号下所有可用模型 |
| `/model ernie-lite` | 切换模型，省钱用 |
| `/search on` | 开启百度搜索，问实时信息用 |
| `/search off` | 关掉搜索，不需要的时候省 token |

> 💡 不用 `/search on` 也没事，Agent 模式下它会自己判断要不要搜

### 多模态

| 命令 | 干啥的 |
|------|--------|
| `/img <路径>` | 附加图片，下一条消息会带上 |
| `/img clipboard` | 直接从剪贴板抓图（需要装 xclip 或 xsel） |

支持截图、UI 设计图、报错截图、图表等，它会根据文件名猜你要干嘛。

### 工具与代码

| 命令 | 干啥的 |
|------|--------|
| `/review` | 对当前 `git diff` 做 Code Review |
| `/review <文件>` | 对指定文件做 Code Review |
| `/run <命令>` | 直接跑 shell 命令，走权限系统 |
| `/cd <目录>` | 切换工作目录 |

### 项目

| 命令 | 干啥的 |
|------|--------|
| `/init` | 分析当前项目，生成 ERNIE.md 项目说明文件 |
| `/status` | 当前状态一览：模型、token 用量、有没有存档 |
| `/cost` | 估算这次对话花了多少钱（仅供参考，别太当真） |

### 记忆

| 命令 | 干啥的 |
|------|--------|
| `/memory` | 查看持久记忆（每次对话都会注入系统提示里的内容） |
| `/memory add 我是后端工程师，不要给我写前端` | 加一条记忆 |
| `/memory clear` | 清空记忆，我不记得你了 |

### 其他

| 命令 | 干啥的 |
|------|--------|
| `/doctor` | 检查环境：API Key 有没有、网能不能通、依赖装没装 |
| `/help` | 显示帮助 |
| `/quit` | 退出，拜拜 |

---

## 工具权限说明 🔐

Agent 执行命令时分三档，不会偷偷给你删东西：

| 级别 | 例子 | 行为 |
|------|------|------|
| ✅ 安全 | `ls`、`cat`、`grep`、`git status` | 自动执行，不问你 |
| ⚠️ 写操作 | `mkdir`、`pip install`、`git commit` | 显示命令，回车确认 |
| ☠️ 危险 | `rm`、`sudo`、`curl \| sh` | 红字警告，必须输 `yes` |

> 📌 `pip install` 会自动加清华镜像，不用你操心网速问题

---

## 常见问题

**Q：装好了但 `ernie` 命令找不到？**

```bash
# 看看 pip 装到哪里了
pip show erniecli | grep Location

# 然后确认那个目录的 bin 在 PATH 里
echo $PATH
```

通常是 `~/.local/bin` 没加到 PATH，加上就行：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

**Q：报 `ERNIE_API_KEY` 未设置？**

```bash
echo $ERNIE_API_KEY  # 看看有没有
```

没有的话回去看第四步。

---

**Q：提示 `Cannot connect` 或超时？**

先检查能不能访问 AI Studio：

```bash
curl -I https://aistudio.baidu.com
```

能通就是 API Key 的问题，不通就是网络问题，用 `/doctor` 命令也可以检查。

---

**Q：`/img clipboard` 说找不到 xclip？**

```bash
sudo apt install xclip   # Ubuntu/Debian
sudo yum install xclip   # CentOS/RHEL
```

macOS 不需要装，直接用（等后续支持）。

---

**Q：token 哪里看消耗情况？**

`/cost` 命令可以粗估，精确数据去 [AI Studio 控制台](https://aistudio.baidu.com) 看账单。

---

## 配置文件完整示例

`~/.ernie/config.yaml`：

```yaml
api_key: 你的token
model: ernie-5.1        # 默认模型
max_tokens: 8192
temperature: 0.7
search: false           # 默认不开搜索
timeout: 120            # 请求超时秒数
```

---

## License

MIT，随便用，别说是你写的就行。

---

> *"能跑就行，别问为什么"*

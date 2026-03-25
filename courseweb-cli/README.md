# courseweb-cli

`pkucw` 是一个面向北大教学网（`course.pku.edu.cn`）的命令行工具。  
它用真实浏览器维持登录状态，同时把课程、通知、教学内容、作业、课堂实录等常见操作整理成稳定可复用的 CLI。

项目同时兼顾两类使用者：

- 人类用户：在终端里直接查询和下载
- agent / 脚本：通过稳定子命令和 `--json` 输出调用

## 当前能力

- 主命令：`pkucw`
- 兼容别名：`cw`、`courseweb`
- 终端内登录
- 账号保存到 macOS Keychain
- Blackboard 会话状态本地持久化
- 课程上下文切换：`pkucw use`、`pkucw current`
- 人类可读输出 + `--json`
- `zsh` / `bash` / `fish` 补全
- 通知列表与详情
- 教学内容列表、树形查看、详情和下载
- 作业列表与详情
- 作业说明与附件下载
- 安全默认的作业提交流程
- 课堂实录列表、详情与下载

## 安装

```bash
git clone <GitHub 仓库地址> courseweb-cli
cd courseweb-cli
./install.sh
```

安装后验证：

```bash
pkucw --version
./scripts/smoke-test.sh
```

## OpenClaw 安装

如果你希望让 OpenClaw 同时安装 `pkucw` 工具和 `pkucw-cli` skill，可以直接运行：

```bash
git clone <GitHub 仓库地址> courseweb-cli
cd courseweb-cli
./scripts/install-openclaw.sh
```

默认行为：

- 安装 `pkucw` 本体
- 将 skill 安装到 `~/.openclaw/workspace/skills/pkucw-cli`
- 默认用符号链接方式挂载 skill，方便后续跟随仓库更新

常用覆写方式：

```bash
OPENCLAW_HOME=~/.openclaw ./scripts/install-openclaw.sh
OPENCLAW_SKILLS_DIR=./.openclaw-skills ./scripts/install-openclaw.sh
PKUCW_SKILL_INSTALL_MODE=copy ./scripts/install-openclaw.sh
PKUCW_SKIP_TOOL_INSTALL=1 ./scripts/install-openclaw.sh
```

安装后可验证：

```bash
pkucw --version
openclaw skills list | grep pkucw-cli
```

如果你要让 OpenClaw 代理自己完成安装，可以直接给它这段提示词：

```text
请在当前仓库安装 pkucw 和 pkucw-cli skill。
要求：
1. 运行 ./scripts/install-openclaw.sh
2. 确认 pkucw --version 可用
3. 确认 openclaw skills list 中能看到 pkucw-cli
4. 如果失败，优先修复 PATH、Python、skill 目录问题
5. 最后返回安装结果、pkucw 版本、skill 安装路径和验证命令输出摘要
```

## 首次使用

推荐流程：

```bash
pkucw accounts add
pkucw login
pkucw ls --current
```

如果你已经保存过默认账号，也可以直接：

```bash
pkucw login
```

常用账号命令：

```bash
pkucw accounts list
pkucw accounts show
pkucw accounts use <account>
pkucw accounts remove <account>
```

## 常用命令

```bash
pkucw login
pkucw ls --current
pkucw use "有机化学 (一)"
pkucw current
pkucw info
pkucw announcements list
pkucw contents tree
pkucw assignments list
pkucw assignments download "L4作业提交入口" --output ./downloads/assignment
pkucw recordings latest --output ./downloads/latest
```

在执行过 `pkucw use <course>` 之后，多数课程内命令都可以省略课程参数。

## 会话恢复

如果本地 Blackboard 会话过期，课程相关命令会先做一次快速探测，再尝试用已保存账号自动恢复。  
如果站点本身状态异常，命令会尽快返回明确错误，而不是长时间无响应。

## 面向 agent / 脚本

- 推荐统一加 `--json`
- 命令名保持稳定，不建议 agent 去猜课程名
- 建议先 `pkucw ls --current --json`，再 `pkucw use "<精确课程名>" --json`
- OpenClaw 可配合 [pkucw skill](skills/pkucw-cli/SKILL.md) 一起使用
- 仓库根目录提供 `./pkucw` 和 `./pkucw-cli` 包装脚本，PATH 不稳定时 agent 可直接调用

通知详情说明：

- `pkucw announcements show "<通知标题片段>" --json` 会返回完整通知详情
- 关键字段包括 `announcement.title`、`announcement.published_at`、`announcement.author`
- `body_text` 是去标签后的正文全文
- `body_html` 是原始 HTML 正文
- `announcement.asset_urls` 会列出通知中的附件或图片链接

## 远程部署

通用 SSH 部署：

```bash
./scripts/deploy-remote.sh user@host
```

如果你有固定目标主机，也可以：

```bash
PKUCW_DEPLOY_HOST=user@host ./scripts/deploy-host.sh
```

## 本地状态目录

默认状态目录：

```text
~/.courseweb
```

重要文件：

- `~/.courseweb/session.json`：当前会话元数据
- `~/.courseweb/storage_state.json`：Playwright 浏览器状态
- `~/.courseweb/accounts.json`：账号元数据

密码不会写进这些 JSON 文件；在 macOS 上，账号密码保存在系统 Keychain 中。

## 文档

- [使用说明](docs/overview.md)
- [架构说明](docs/architecture.md)
- [账号管理](docs/account-management.md)
- [技术报告](docs/technical-report.md)

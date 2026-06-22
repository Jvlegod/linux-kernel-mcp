# linux-kernel-mcp

`linux-kernel-mcp` 是一个 MCP server，让 Codex 可以查询 Linux 内核文档、主线源码、版本信息，以及可选的本地内核源码树。

English documentation is available in [README.md](./README.md).

用户不需要先准备本地 Linux 仓库。远程文档和主线源码查询可以直接使用；只有需要检查自己机器上的内核源码时，才需要配置本地路径。

## 快速开始

把 MCP server 注册到 Codex：

```bash
codex mcp add linux_kernel -- uvx linux-kernel-mcp
```

添加后重启 Codex。

之后可以直接向 Codex 提这类问题：

```text
Search the latest Linux kernel docs for GPIO descriptor APIs.
```

```text
Fetch the upstream implementation of drivers/gpio/gpiolib.c around line 200.
```

```text
What is the latest stable Linux kernel release?
```

## 没有本地 Linux 源码树时能做什么

安装后这些能力可以直接使用：

- 搜索 `docs.kernel.org`
- 抓取并摘要某个 `docs.kernel.org` 页面
- 查询 `kernel.org` 上的最新 stable / mainline 版本
- 返回在线源码浏览入口
- 通过 Gitiles 抓取 Torvalds 主线源码文件片段
- 为内核相关任务生成实现检查清单

这已经足够用于查文档、查 API、对比主线最新代码。

## 可选的本地源码树

如果用户本机也有 Linux 内核源码树，可以用下面任意一种方式启用本地查询。

启动 Codex 前设置默认路径：

```bash
export LINUX_KERNEL_TREE=/path/to/linux
```

或者在 Codex 会话中设置：

```text
set_kernel_root("/path/to/linux")
```

之后就可以查询本地源码树：

```text
search_local_kernel_api("devm_gpiod_get")
```

```text
read_local_kernel_file("drivers/gpio/gpiolib.c", start_line=200)
```

查看当前本地路径：

```text
get_kernel_root()
```

只给某次调用指定另一个源码树：

```text
search_local_kernel_api("platform_driver_register", root="/path/to/other/linux")
```

如果没有配置本地源码树，本地查询工具会返回清晰的配置错误；远程文档和主线源码工具仍然可以正常使用。

## 可用工具

远程查询工具：

- `latest_kernel_releases`
- `search_kernel_docs`
- `fetch_kernel_doc`
- `search_online_kernel_code`
- `fetch_upstream_kernel_file`
- `plan_kernel_implementation`

本地源码树工具：

- `get_kernel_root`
- `set_kernel_root`
- `search_local_kernel_code`
- `read_local_kernel_file`
- `search_local_kernel_api`
- `inspect_kernel_capabilities`
- `find_driver_examples`

驱动规划工具：

- `list_driver_template_blueprints_tool`
- `get_driver_template_blueprint_tool`
- `plan_driver_scaffold`

## 推荐用法

1. 先查最新官方文档，确认 API 和子系统语义。
2. 需要时抓取主线源码片段，对比最新实现方式。
3. 只有需要检查本机源码时，再设置本地 Linux 源码树。
4. 有本地源码树后，先检查本地内核 API 能力和回调签名。
5. 搜索附近的驱动样例和 API 调用点。
6. 让 Codex 规划实现步骤，并指出版本相关检查项。

## Codex 配置

`codex mcp add` 会写入类似下面的配置：

```toml
[mcp_servers.linux_kernel]
command = "uvx"
args = ["linux-kernel-mcp"]
```

如果某个项目总是使用固定的本地内核源码树，可以补充：

```toml
[mcp_servers.linux_kernel.env]
LINUX_KERNEL_TREE = "/path/to/linux"
```

## 本地开发

如果不是使用 PyPI 包，而是在本地 checkout 中开发这个 MCP，可以注册本地路径：

```bash
codex mcp add linux_kernel -- uvx --from /path/to/linux-kernel-mcp linux-kernel-mcp
```

在仓库内可以构建并测试包：

```bash
uv build
uvx --from dist/linux_kernel_mcp-0.1.0-py3-none-any.whl linux-kernel-mcp
```

这个命令会启动 MCP stdio server 并等待客户端握手，所以不会像普通 CLI 一样打印帮助信息。

## 限制

- 这个 server 提供查询和规划工具，不保证内核补丁一定正确。
- 当前驱动 scaffold 还是 metadata-first，不直接生成最终 C 源码。
- 主线源码抓取目前按文件路径读取，不是完整符号索引。
- `set_kernel_root` 是会话内状态；MCP 重启后需要重新设置，或者通过 `LINUX_KERNEL_TREE` 提供默认值。

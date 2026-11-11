# 插件目录

把一个 `.py` 文件丢进来，重启服务，里面的工具就会出现在 Worker 的工具表里。

## 最小插件

```python
def hello(name: str = "world") -> str:
    return "hello " + name

TOOLS = {
    "hello": (hello, {"name": "str"}, "打个招呼"),
}
```

## 约定

| 项 | 要求 |
|---|---|
| 变量名 | 必须是 `TOOLS` |
| 结构 | `{"工具名": (可调用, 参数字典, 一句话描述)}` |
| 可调用 | 签名 `fn(**args) -> str`，返回值会被截断后放进上下文 |
| 参数名 | 必须和 `fn` 的形参一致，类型写 `"str"` / `"int"` / `"float"` |
| 异常 | 抛异常会被捕获，Worker 看到错误信息，不会崩 |

## 注意

- 文件名以下划线开头的会被跳过
- 工具名与内置工具同名时会**覆盖**内置（内置：`list_dir` `read_file` `write_file` `run_shell` `publish` `recall` `finish`）
- 插件在本机跑，能读环境变量。**不要放不可信代码**
- 返回内容越长，吃掉的上下文越多。超过 800 字建议自己截断

## 让模型自己写（beta）

界面左侧「创造插件」里可以直接写，也可以直接在对话里说「给我造一个能……的工具」。
模型会调 `make_plugin`，链路是：名字校验 → 长度上限 12000 → 黑名单 → 写文件 →
编译 → 校验 `TOOLS` → 失败回滚 → 登记 `_made.json` → 热加载。

造完**下一步就能用**，不用重启。自制的会在 `_made.json` 里留一条记录，
界面上按 `made: true` 区分，可编辑、可删除。

黑名单挡的是 `subprocess` / `os.system` / `ctypes` / `socket` / `eval(` / `exec(` /
`__import__` 这类明显写法。它挡不住刻意变形的代码——威胁模型是「用户自己的模型」，
不是不可信第三方。

## 自带的

35 个文件、71 个工具，全部只用标准库。按用途分组：

| 组 | 文件 |
|---|---|
| 文件与代码 | `toolkit` `repomap` `treeview` `diffview` `guard` |
| 数据 | `csvsql` `jsonquery` `spark` `csvfix` `xlsxread` |
| 文档 | `docxread` |
| 文本 | `regexlab` `textstat` `tocgen` `zhproof` `encodec` |
| 工程 | `runtests` `gitlog` `changelog` `configfmt` `vercmp` |
| 网络 | `web_search` `httpreq` |
| 系统 | `sysinfo` `selfcheck` `hashsum` `ziputil` |
| 杂项 | `timeutil` `uuidgen` `cronparse` `imgmeta` `notepad` |
| 自省 | `tokenmeter` `costmeter` `contextpack` |

`web_search.py` 走 DuckDuckGo 的 html 端点，不依赖第三方库；企业环境要换成自建搜索，
改里面的 `ENDPOINT` 和解析正则即可。`xlsxread` / `docxread` 用 `zipfile` + `ElementTree`
直接解 OOXML，不装 openpyxl / python-docx。

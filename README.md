# Oberon 日志时间轴

本地网页工具：导入 Oberon（THA 髋导航）的 spdlog 日志，按 `docs/oberon-log-spec.md` 里的表格做步骤映射、重点标注和异常标注，并画成六轨时间轴。

分类规则只来自 spec 文件。改表保存后点界面「重新加载规则」，或刷新页面（服务会按文件 mtime 自动重载）。不必改代码。

**改 `app/nle.py`、解析器或前端之后必须重启 Python 进程。** 只改 spec 表刷新即可。

## 运行

需要 Python 3.10+（只用标准库，无需 pip）。

```bash
python3 -m app.main
```

浏览器打开 http://127.0.0.1:8765 （默认绑定 0.0.0.0:8765）。

可选端口：`python3 -m app.main 8765` 或 `python3 -m app.main 0.0.0.0:8765`。

医院现场日志在仓库外（例如 `../Oberon-log/`），用「导入日志」或 API `POST /api/logs/import-path` 指向绝对路径。不要把医院日志提交进 git。

## 用法

1. 左侧「导入日志」可多选文件。一次只查看一个文件。
2. 点文件名打开时间轴。默认隐藏噪声和未映射行。
3. 「显示噪声」/「显示全部」切换过滤。
4. 金色 = 重点（标注=key），红色 = 异常（标注=anomaly 或级别 E/C）。
5. 上方短终端（默认约 110px）显示原始日志；分割条只改终端高度。下方是按**行号**对齐的多轨时间轴；方案汇总卡片在 NLE 底部。
6. 缩放只用 − / + / 适应窗口。拖动和滚轮平移。
7. 删除只影响 `data/` 里的副本，不改原始文件。

## 日志格式

    [HH:MM:SS +08:00] [Daily_logger] [---L---] [thread N] message

L 为 T/D/I/W/E/C。文件名 `tha_log_file_YYYY-MM-DD.txt` 会取出日期；医院改名文件没有日期时用文件 mtime。崩溃堆栈（`CRASH DETECTED`、`Caught signal` 等非标准行）会收成一条异常事件。

启动句：`Oberon Application Startup  version …`（版本在同一行）。开始手术：`start operation`。身份键：`start load plan uuid: {uuid}`。源码拼写原样匹配（`sucess`、`anterversion`、`handguding`）。

## Spec 匹配顺序（硬编码）

1. 级别 E/C（含空的 ---E---，标签「空错误行」）
2. 异常表
3. 噪声表（默认隐藏）
4. 步骤映射表 + 关键信息表
5. 未匹配的已解析行：默认隐藏，可用「显示全部」打开

同一张表内从上到下，第一条命中即停。不解析「软件页面与步骤（业务顺序）」那张表。阈值列只用于误差幅值（探针/末端/髋配准 RMSE）；方案外展角和实测 RAS 的 |Δ| 在 `nle.py` 比较。

## API（本地）

- GET /api/logs 文件列表
- POST /api/logs multipart 上传
- POST /api/logs/import-path JSON `{"path": "/abs/file.txt"}` 或 `{"paths": [...]}`
- GET /api/logs/{id}/timeline?show_noise=0&show_all=0
- DELETE /api/logs/{id}
- GET /api/spec  /  POST /api/spec/reload

事件过多（>5 万）时时间轴返回默认过滤集并带 truncated 标记。大文件终端窗口化（`lines_windowed`）。

## 目录

- `docs/oberon-log-spec.md` — 唯一分类配置
- `docs/page-hierarchy.md` — 一级/二级/三级/设备轨道
- `app/` — 解析器与 HTTP 服务
- `web/` — 静态页面（无构建步骤）
- `data/` — 导入副本与索引（已 gitignore）
- `samples/` — 本地试跑用，不要提交

不要把医院现场日志提交进 git。

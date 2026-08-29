# log-tool-tha 项目上下文

> 本文档是从 Oberon 工程迁出时整理的全部背景信息（2026-08-26）。新会话/新协作者先读这里即可接续工作，无需回隔壁仓库翻代码。
>
> 来源：Oberon 工作区对话记录 + 主工程源码调研（`../Oberon/`）。

## 0. 项目背景

- **主工程**：Oberon —— THA（全髋关节置换）手术导航系统，Qt/Slicer 桌面应用，运行于导航台车 Ubuntu 18.04
- 与硬件守护进程 Sirius 通过 UDP :6666 / nanomsg IPC 通信
- 本工具目标：分析 Oberon 运行日志，可视化查看系统运行历史

## 1. 分析对象与格式

### 1.1 系统运行日志（主要分析对象）

产生方式：spdlog daily logger（多线程），初始化于 `Applications/OberonApp/Helpers/FITLogger.cpp`：

```cpp
g_sysLogger = spdlog::daily_logger_mt("Daily_logger", "tha_logs/tha_log_file.txt");
g_sysLogger->set_pattern("[%H:%M:%S %z] [%n] [%^---%L---%$] [thread %t] %v");
g_sysLogger->set_level(spdlog::level::trace);
spdlog::flush_every(std::chrono::seconds(1));
```

- **实际文件**：进程工作目录下 `tha_logs/tha_log_file_YYYY-MM-DD.txt`（每日 0 点轮转）
- **级别**：trace 全量记录，每秒 flush
- **行样例**：

```
[00:02:19 +0800] [Daily_logger] [---I---] [thread 49] robot stop teach
```

- **级别字段**：`---%L---` 渲染为单字母 T/D/I/W/E/C，对应 trace/debug/info/warning/error/critical
- **时间戳**：只有时分秒 + 时区（`+0800` 或 `+0000`，取决于设备环境），**没有日期和毫秒**

### 1.2 通信日志（HTML，次要）

- 单例类 `FITCommunicationLog`，宏 `LOGINFO/LOGWARNING/LOGERROR`
- **路径**：`~/Documents/log/<yyyy-MM-dd>/<yyyy-MM-dd hh-mm-ss>_Log.html`
- 文件骨架：`<html><head><title>日志记录</title></head><body>` + 每条一行 + 结尾 `</body>`
- 单条结构：`<br><font size="3" color="#RRGGBB" family="Source Han Sans SC">Index: N   Time-->hh:mm:ss <details><message></font>`
- 颜色分级：`#459EF6`=INFO，`#0000FF`=WARNING，`#FF0000`=ERROR
- details 形如 `<.文件名.>@<行号>=><函数名>:   `
- 使用极少（全工程仅 6 处：`FITAsker.cpp` 发送指令、`FITCommandHandler.cpp` 命令异常、`FITMsgProcess.cpp:669` 重启 Sirius、`FITHipReg`/`FITDevPre` standby）

### 1.3 其他留档（可作关联数据源）

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| 自动截屏 | `~/THA_Picture/<日期>-<患者姓名>-<侧别>/auto/*.png` | 约 10 个关键节点触发 + 手动按 P 键；实现于 `FITMainWindow::auto_screen_shot`（约 :2085） |
| 崩溃回溯 | 经 `g_sysLogger->error()` 写入 tha_logs | `Main.cxx` 注册 SIGSEGV/SIGABRT/SIGBUS/SIGILL/SIGFPE/SIGPIPE 六种信号，`Helpers/Backtrace.cpp` 输出堆栈 |
| 报告 PDF | `<程序目录>/tempreport.pdf` | 术后导出 |
| 标定/规划矩阵 | `~/.config/hzjj/`（QSettings Oberon.ini） | `[MATRIX]` 组及按方案 UUID 分组 |
| 标定原始点 | 工作目录 `probe_pivot.txt` | 探针尖标定导出 |

## 2. 业务语义关键词（从全工程约 160 处 `g_sysLogger` 调用归纳）

| 类别 | 典型消息样例 | 主要来源 |
| --- | --- | --- |
| 步骤/页面切换 | `switch install hip mark nail step`、`switch planviewer page`、`from login page switch to ...` | `Pages/FITHipReg.cpp`(~50)、`FITPlanEditor.cpp` |
| 手术主流程 | 开始手术、导入方案、病人信息、Sirius 重启 | `FITMainWindow.cpp`(~29) |
| 配准过程 | `probe2model sparse point:x:..`、`hipmarker2ct NDIDATA:..`、`clear sparse/dense/cup`、`undo dense/cup` | `Widgets/FITRegister.cpp`(24) |
| 标定 | `probe calibration error <rmse>`、`calibration reamer2effector matrix ..` | `Widgets/FITDevPreWorker.cpp` |
| 角度指标 | `plan inclination: X, plan anterversion: Y`（前倾/外展） | `FITPlanEditor.cpp:4092` 等 |
| 机械臂 | `robot stop teach joint, a1:0 ... a7:0`、示教开关状态机流转 | `Helpers/FITKukaCmd.cpp`(10) |
| 通信/故障 | KUKA 连接状态、急停按钮、NDI/KUKA 故障 | `Communication/FITMsgProcess.cpp`(16) |
| 启停 | `Application Startup`、`vesrion V2.9.1...`（源码即拼错为 vesrion） | 入口处 |

## 3. 已知坑（解析器/分析逻辑必须处理）

1. **大量错误用 info 级别记录** —— 不能只按级别筛异常，需要内容级规则识别错误事件
2. **`tha_logs/` 是相对路径** —— 取决于进程启动时的工作目录，日志可能落在意外位置；工具须支持手动指定路径 + 常见位置自动发现
3. **时间戳无日期、无毫秒** —— 跨天排序必须结合文件名中的日期；同一秒内按原始行序稳定排序
4. **多线程写入**（`daily_logger_mt`）—— 极端情况下消息可能交错
5. `FITAutoScreenCapture.cpp` 整个文件是被注释掉的废弃代码，真实截屏实现在 `FITMainWindow`
6. 源码存在拼写错误（如 `vesrion`），关键词匹配要做容错或收录变体

## 4. 参考文件索引（隔壁仓库，只读参考，勿改动）

```
../Oberon/Applications/OberonApp/Helpers/FITLogger.h            # g_sysLogger 声明、FITTimerPrinter
../Oberon/Applications/OberonApp/Helpers/FITLogger.cpp          # spdlog 初始化（pattern/level/flush）
../Oberon/Applications/OberonApp/Communication/FITCommunicationLog.h    # LOGINFO 等宏定义
../Oberon/Applications/OberonApp/Communication/FITCommunicationLog.cpp  # HTML 写入实现
../Oberon/Applications/OberonApp/Helpers/Backtrace.cpp          # 崩溃信号处理
../Oberon/Applications/OberonApp/FITMainWindow.cpp              # auto_screen_shot / manual_screen_shot
../Oberon/ARCHITECTURE.md                                       # §存储 一节有日志路径总表
```

## 5. 决策记录

| 日期 | 决策 |
| --- | --- |
| 2026-08-26 | 从 `../Oberon/log-tool/`（原 git 忽略的骨架子项目）迁出，转为独立项目开发 |
| 2026-08-26 | 定位：**仅服务 Oberon(THA)**，不做通用化 |
| 2026-08-26 | 项目路径曾为 `/home/sad/jjcode/jt-001/log-tool-tka` |
| 2026-08-29 | 本地目录改名为 `log-tool-tha`，与 GitHub 仓库 [TomasDo/log-tool-tha](https://github.com/TomasDo/log-tool-tha) 对齐 |
| 2026-08-26 | 技术选型沿用：Python + Flask Web 可视化（原对话默认方案，未被否决） |
| 备注 | 发现 `../jt-002/Titan/build/.../tka_logs/log_file_*.txt` 与 Oberon 格式完全相同；当前明确不纳入范围，仅记录 |

## 6. 待办 / 未决问题

- 功能清单尚未定义（上一段对话正停在“等你提功能需求”这一步）
- `requirements.txt` 中 `spdlog-parser` 为占位依赖，实现解析器时再确认是否真的使用

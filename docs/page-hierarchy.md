# Oberon 页面 / 步骤分级（时间轴轨道用）

> 和 `oberon-log-spec.md` 一起驱动工具。显示名以 spec 为准；本文件只定 **一级 / 二级 / 三级** 和轨道该画什么。
>
> 匹配串全部来自 `../Oberon-log/` 真实日志原文，不是 Titan 步骤名。

## 怎么用在时间轴上

横向时间轴（剪辑器风格）：

- 手术轨道：同一 `plan uuid` 一台手术（多次启动并在一块）
- 主轨道：日志全文（一行一个刻度）
- 一级轨道：方案预览、设备准备、髋导航、股骨导航（可选）、术后
- 二级轨道：当前一级页面下的任务清单
- 三级轨道：配准稀疏/密采集、杯验证点
- 设备轨道：设备准备 step、示教开关、急停、KUKA 连接
- 播放头对准原始日志某一行（terminal 跟着滚）

横轴按**日志行号**（不是墙钟）。缩放只用按钮；拖动和滚轮平移。

登录 / 方案管理是容器，**不单独占一级轨道**。现场日志几乎没有 `from login page` / `plan manage` 句。

---

## 一级

| 级别 | 显示名 | 日志匹配 | 说明 |
| --- | --- | --- | --- |
| 1 | 方案预览 | `switch planviewer page` / `enter planviewer page` | |
| 1 | 设备准备 | `enter device prepare page` | |
| 1 | 髋导航 | `enter hip navigation page` | |
| 1 | 股骨导航 | `enter femur navigation page` | 部分病例才有 |
| 1 | 术后 | `enter poster operation page` | |
| — | 设备准备 step / 示教 / 急停 / KUKA | `current device prepare step 1..5` 等 | **设备轨道**，不是手术 L1 |

`Oberon Application Startup` 结束上一段一级，本身不进入「登录」。`start operation` 不是一级切换。

---

## 二级：髋导航任务

| 级别 | 显示名 | 日志匹配 |
| --- | --- | --- |
| 2 | 安装髋标记钉 | `switch install hip mark nail step`；`enter hip navigation step 1 install nail` |
| 2 | 髋配准 | `switch register hip step`；`enter hip navigation step 2 register hip` |
| 2 | 髋臼打磨 | `switch polish hip step` |
| 2 | 安装髋臼杯 | `switch install hip cup step` |
| 2 | 验证髋臼杯 | `switch verify hip cup install step`；`enter hip navigation step 5 validate hip cup` |

髋配准完成证据：`hip register calculate error`，不是稀疏/密点计数，不要显示 3/5。

---

## 二级：股骨导航（可选）

未进入股骨导航的手术不评这些步。

| 级别 | 显示名 | 日志匹配 |
| --- | --- | --- |
| 2 | 安装股骨导航组件 | `install femur navigation component step` |
| 2 | 安装股骨钉 | `install femur nail step` |
| 2 | 股骨配准 | `register femur step` |
| 2 | 股骨截骨 | `cut femur step` |

---

## 三级：页内采集

坐标可进噪声表；轨道仍可画三级块。完成证据看 RMSE / 杯验证句。

| 级别 | 显示名 | 日志匹配 |
| --- | --- | --- |
| 3 | 配准稀疏采集 | `sparse point` |
| 3 | 配准密采集 | `dense point` |
| 3 | 配准验证点 | `verify point`（不含 cup verified） |
| 3 | 杯验证点 | `cup verified point` |

---

## 设备

| 显示名 | 日志匹配 |
| --- | --- |
| 设备准备 | `current device prepare step 1..5` |
| 示教开关 | hard/soft switch、`handguding` |
| 急停 | `robot emergency stop button` |
| KUKA | `kuka app is connected` / `disconnected` |
| 示踪器 | `marker data is invalid` |
| MXIO | `connect mxio` |
| 工具 | `set tool type new metal tool`、`set tool side left/right`、`set reamer rod:`、`set cup rod:` |

---

## 手术 vs 软件会话

一个 `tha_log_file_YYYY-MM-DD.txt` 或医院改名文件是当天（或该次导出）的全部记录：多台手术、同一台多次启动、空启动。

| 单位 | 切分点 | 合并规则 |
| --- | --- | --- |
| 会话 session | `Oberon Application Startup` → 下一次 Startup 或罕见的 Exit | 一次进程寿命 |
| 手术 case | `start load plan uuid: {uuid}` | **相同 uuid 的多个会话合成一台手术** |
| 未打开方案 | 会话里没有 uuid | 灰色空块，不并入任何手术，汇总不出卡 |

标签：`手术N · {杯型} · {左/右}`。不要把 `patient name` 写进轨道。

### 时间轴样式

- 不同手术：不同底色（同一 uuid 永远同色）
- 同一手术多次启动：色块不断开，内部竖线切「第 n 次」，对准 Startup
- 手术之间的空会话：灰带

轨道窗口底部 **方案汇总**：每张卡片一台已打开方案的手术。未打开方案不出卡。已加载未 `start operation`：卡片写「未开始手术」，不要把步骤画全红。

Terminal 会话边界：`── 手术 1 · 第 2 次启动 13:46:39 ──`

---

## 启动 / 版本旗标

`Oberon Application Startup  version x.x.x`（版本在**同一行**）钉在标尺和手术轨道上；版本徽章归属该次 Startup；Terminal 里这行单独高亮。

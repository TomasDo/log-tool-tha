# Oberon 日志分析：关键定义与步骤说明

> 本文件是日志分析工具的**唯一配置依据**。改完保存后点网页「重新加载规则」，或刷新页面即可生效（服务按文件 mtime 自动重载）。不必改代码。
>
> 改 `app/nle.py` / 解析器 / 前端后必须**重启** Python 进程。
>
> 工具按表格**从上到下**匹配，第一条命中即停。
>
> 标记约定：
> - 匹配方式：`contains`（默认，子串）| `prefix` | `regex`
> - 类别：`lifecycle` 生命周期 / `page` 大页面跳转 / `step` 页内步骤 / `key` 关键信息 / `robot` 机器人动作 / `noise` 噪声 / `other`
> - 时间轴：`show` 显示 | `hide` 默认隐藏
> - 标注：`none` 普通 | `key` 重点（金） | `anomaly` 异常（红） | `pin` 特殊旗标（启动 / 版本）
> - 阈值：可选。如 `>1` 表示日志里最后一个数字（单位 mm）大于 1 则升为异常。空着=不做数值判断。
>   **阈值只用于误差幅值**（探针标定、末端标定、髋配准 RMSE）。方案外展/前倾角和 `ras coordinate realtime` **不要**填阈值；|实测−方案| 在 `nle.py` 比较。

## 日志格式

日常文件：进程工作目录下 `tha_logs/tha_log_file_YYYY-MM-DD.txt`。医院现场常改名为 `医院-病例-姓名-侧-后缀.txt`，内容格式相同。

行格式（spdlog Daily_logger）：

```
[HH:MM:SS +08:00] [Daily_logger] [---L---] [thread N] message
```

`L`：T / D / I / W / E / C。UTF-8。按天滚动。崩溃时会出现非标准行（`CRASH DETECTED`、`Caught signal`、堆栈），收成一块异常。

源码拼写原样匹配：`sucess`、`handguding`、`anterversion`、`triggerred`。

身份键：`start load plan uuid: {uuid}`。同一 uuid 跨多次 `Oberon Application Startup` 合成一台手术。标签用杯型（`switch cup type`）+ 手术侧（`operation side`），**轨道不写患者姓名**。

---

## 软件页面与步骤（业务顺序）

本表**不参与**日志匹配（没有「日志匹配」列）。时间轴一级页面：方案预览、设备准备、髋导航、股骨导航（可选）、术后。登录 / 方案管理是容器，不单独占轨道。

| 顺序 | 软件步骤（显示名） | 日志中的实际名称 | 说明 |
| --- | --- | --- | --- |
| 0 | 启动 | Oberon Application Startup  version … | 版本在同一行；现场日志几乎没有 Exit |
| 1 | 方案预览 | switch/enter planviewer page | 一级 |
| 2 | 开始手术 | start operation | 不是 click start operation |
| 3 | 加载方案 | start load plan uuid | 身份键 |
| 4 | 导入方案 | import plan path … sucess | 保留拼写 sucess |
| 5 | 设备准备 | enter device prepare page | 一级；页内 step 1..5 进设备轨道 |
| 6 | 髋导航 | enter hip navigation page | 一级 |
| 6.1 | 安装髋标记钉 | switch install hip mark nail step | 二级 |
| 6.2 | 髋配准 | switch register hip step | 完成证据：hip register calculate error |
| 6.3 | 髋臼打磨 | switch polish hip step | 二级 |
| 6.4 | 安装髋臼杯 | switch install hip cup step | 二级 |
| 6.5 | 验证髋臼杯 | switch verify hip cup install step | 二级 |
| 7 | 股骨导航 | enter femur navigation page | 一级，部分病例才有 |
| 7.1 | 安装股骨钉 | install femur nail step | 二级，可选 |
| 7.2 | 股骨配准 | register femur step | 二级，可选 |
| 7.3 | 股骨截骨 | cut femur step | 二级，可选 |
| 8 | 术后 | enter poster operation page | 一级 |

---

## 步骤映射（时间轴主事件）

改「软件步骤」列即改时间轴上的中文标签。

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| Oberon Application Startup | contains | 软件启动 | lifecycle | show | pin | 会话旗标；版本在同一行 |
| start operation | contains | 开始手术 | step | show | key | 方案预览点开始手术 |
| start load plan uuid | contains | 开始加载方案 | step | show | key | 消息含 UUID，手术身份键 |
| start import plan path | contains | 开始导入方案 | step | show | key | |
| import plan path | contains | 导入方案结果 | step | show | key | 源码拼写 sucess |
| read plan path | contains | 读取外部方案 | step | show | none | |
| switch cup type | contains | 杯型 | key | show | key | 标签用杯型，不写姓名 |
| operation side | contains | 手术侧 | key | show | key | 同行可能有 patient name，轨道只用侧别 |
| switch planviewer page | contains | 方案预览 | page | show | key | |
| enter planviewer page | contains | 方案预览 | page | show | key | |
| enter device prepare page | contains | 设备准备 | page | show | key | |
| enter hip navigation page | contains | 髋导航 | page | show | key | |
| enter femur navigation page | contains | 股骨导航 | page | show | key | 部分病例才有 |
| enter poster operation page | contains | 术后 | page | show | key | |
| enter hip navigation step 1 install nail | contains | 安装髋标记钉 | step | show | key | 与 switch 同义 |
| switch install hip mark nail step | contains | 安装髋标记钉 | step | show | key | |
| enter hip navigation step 2 register hip | contains | 髋配准 | step | show | key | |
| switch register hip step | contains | 髋配准 | step | show | key | |
| switch polish hip step | contains | 髋臼打磨 | step | show | key | |
| switch install hip cup step | contains | 安装髋臼杯 | step | show | key | |
| enter hip navigation step 5 validate hip cup | contains | 验证髋臼杯 | step | show | key | |
| switch verify hip cup install step | contains | 验证髋臼杯 | step | show | key | |
| install femur navigation component step | contains | 安装股骨导航组件 | step | show | key | 股骨导航，可选 |
| install femur nail step | contains | 安装股骨钉 | step | show | key | 未进股骨导航的手术不评 |
| register femur step | contains | 股骨配准 | step | show | key | |
| cut femur step | contains | 股骨截骨 | step | show | key | |
| current device prepare step | contains | 设备准备步骤 | robot | show | none | 设备轨道，不是手术 L1 |
| kuka app is connected | contains | KUKA 已连接 | robot | show | key | |
| kuka app is disconnected | contains | KUKA 断开 | robot | show | anomaly | 仅 start operation 之后、术后页或进程结束之前 |
| robot emergency stop button external is released | contains | 急停松开 | robot | show | none | |
| connect mxio sucess | contains | MXIO 连接成功 | key | show | none | 源码拼写 sucess |
| set effector side | contains | 末端侧别 | robot | show | none | |
| set tool type: | contains | 工具类型编号 | key | hide | none | 与「选择工具类型」同时打的数字回显 |
| set tool type \d | regex | 工具类型编号 | key | hide | none | |
| set tool side \d | regex | 工具侧别编号 | key | hide | none | |

---

## 关键信息（重点标注）

距离单位 **mm**。标定 / 配准误差 **>1 mm 升为异常**。方案外展角本身（常见约 40°）**不**套阈值。

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 阈值 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| probe calibration error | contains | 探针标定误差 | key | show | key | >1 | 取消息最后一个数字，单位 mm |
| probe calibration result | contains | 探针标定结果 | key | show | none |  | |
| effector calibration error | contains | 末端标定误差 | key | show | key | >1 | |
| hip register calculate error | contains | 髋配准误差 | key | show | key | >1 | 髋配准完成证据；不要对点计数显示 3/5 |
| planviewer hand over,plan inclination | contains | 规划外展/前倾 | key | show | key |  | 源码拼写 anterversion；规划窗内才算规划完成 |
| ras coordinate realtime | contains | 实测外展/前倾/深度 | key | show | none |  | 全 0 已被噪声表吃掉；|Δ| 在 nle.py |
| ras coordinate plan | contains | 方案外展/前倾回显 | key | hide | none |  | 不是实测 |
| cup verified point | contains | 杯验证点 | key | show | key |  | 坐标；完成证据看本句或进入 verify 步 |
| sparse point | contains | 配准稀疏采集 | key | hide | none |  | 三级；完成看 RMSE |
| dense point | contains | 配准密采集 | key | hide | none |  | 三级 |
| verify point | contains | 配准验证点 | key | hide | none |  | 勿与 cup verified point 混淆（表内更长串优先） |
| set tool type new metal tool | contains | 选择工具类型 | key | show | key |  | 设备准备 / 髋导航；现场几乎都是 new metal tool |
| set tool side left | contains | 选择工具侧别 | key | show | key |  | |
| set tool side right | contains | 选择工具侧别 | key | show | key |  | |
| set reamer rod: | contains | 选择磨头杆 | key | show | key |  | 髋臼打磨页内选杆 |
| set cup rod: | contains | 选择装杯杆 | key | show | key |  | 安装髋臼杯页内选杆 |

---

## 异常操作（红色重点标注）

匹配顺序（硬编码）：级别 E/C（含空 `---E---`，标签「空错误行」）→ 本异常表 → 噪声表 → 步骤映射 + 关键信息 → 未匹配隐藏。

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| CRASH DETECTED | contains | 软件崩溃 | other | show | anomaly | 非标准行，堆栈跟在后面 |
| Caught signal | contains | 捕获信号崩溃 | other | show | anomaly | 常见 SIGABRT / SIGSEGV |
| robot emergency stop button external is pressed | contains | 急停按下 | robot | show | anomaly | |
| marker data is invalid | contains | 标记钉数据无效 | other | show | anomaly | |
| kuka app is disconnected | contains | KUKA 断开 | robot | show | anomaly | 仅术中标异常；非术中由解析器隐藏 |
| kuka states are fault | contains | KUKA 故障 | robot | show | anomaly | |
| connect mxio failed | contains | MXIO 连接失败 | other | show | anomaly | |

Oberon 主集现场日志没有 `connect ndi failed`（那是混入的 Titan 拷贝），**不要**写进本表。

---

## 噪声（默认从时间轴隐藏）

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| record torque | contains | 扭矩转储 | noise | hide | none | |
| detect net ip | contains | 网卡 IP 探测 | noise | hide | none | |
| current joint | contains | 关节角转储 | noise | hide | none | |
| send kuka cmd: standbyStepChange | contains | 待机步骤切换指令 | noise | hide | none | |
| send kuka cmd: | contains | 发送 KUKA 指令 | noise | hide | none | 连接结果用步骤表 |
| handle kuka instruct | contains | 处理 KUKA 指令 | noise | hide | none | |
| pedal-released UI | contains | 脚踏松开界面 | noise | hide | none | |
| pedal-pressed UI | contains | 脚踏按下界面 | noise | hide | none | |
| ras coordinate realtime anteversion:0 , inclination:0, depth:0 | contains | 页面切换零 RAS | noise | hide | none | 不当实测 |
| rebooting sirius | contains | 重启 Sirius | noise | hide | none | 加载方案常态 |
| reboot sirius | contains | 重启 Sirius | noise | hide | none | |
| terminated sirius | contains | 结束 Sirius | noise | hide | none | |
| terminating sirius | contains | 结束 Sirius | noise | hide | none | |
| send teach cmd and try to open hard switch | contains | 示教开硬开关 | noise | hide | none | |
| send stop cmd and try to close hard switch | contains | 示教关硬开关 | noise | hide | none | |
| send open soft switch cmd | contains | 开软开关 | noise | hide | none | |
| reading handguding button | contains | 手导按钮 | noise | hide | none | 源码拼写 handguding |
| RobotTeachState | contains | 示教状态机 | noise | hide | none | |
| hipmarker2ndi | contains | 髋标记 NDI | noise | hide | none | |
| calibration reamer2effector matrix | contains | 磨头标定矩阵 | noise | hide | none | |
| standby cmd called by step change | contains | 步骤切换待机 | noise | hide | none | |
| follow-up motion is | contains | 跟随运动 | noise | hide | none | |
| switch app coordinate | contains | 切换应用坐标系 | noise | hide | none | |
| switch ras coordinate | contains | 切换 RAS 坐标系 | noise | hide | none | |
| QCoreApplication | contains | Qt 路径 | noise | hide | none | |
| start fix | contains | 开始定点/定线运动 | noise | hide | none | |

---

## 方案 vs 实测 Δ

`ras coordinate realtime anteversion / inclination / depth`（**非**全 0）对照**本会话最近一次** `planviewer hand over,plan inclination` / `plan anterversion`。

- `Oberon Application Startup` 清空方案快照。
- |Δ| **>1** 标重点（key / 金），**>2** 标异常（红）。|Δ| ≤ 1 不加额外标记。
- **不要**对计划外展 40° 套阈值列。
- 页面切换时的 `0,0,0` 是噪声，不当实测。
- 悬停二级块（髋臼打磨 / 安装髋臼杯 / 验证髋臼杯）显示 目标 / 实测 / Δ。

规划窗：`planviewer hand over,plan inclination` 只在进入髋打磨 / 装杯**之前**算规划目标快照；术后再打开方案预览不算规划完成。

## 必要步骤 / 方案汇总

同一 `plan uuid` 的多次会话合成一台手术。只评估出现过 `start operation` 的 uuid；已加载但未开始显示「未开始手术」，不把每步标成未做。没有 uuid 的空启动不出卡片。

必要步骤（仅 `start operation` 之后）：

1. **设备准备**（术前）：`enter device prepare page` 或 `current device prepare step` 任一。
2. **探针标定**（术前）：`probe calibration error` 任一即完成。
3. **规划目标**（规划窗）：进入髋打磨 / 装杯之前的 `planviewer hand over,plan inclination`。
4. **安装髋标记钉**：`switch install hip mark nail step` 或 `enter hip navigation step 1 install nail`。
5. **髋配准**：`hip register calculate error`（不是点计数）。
6. **髋臼打磨**：`switch polish hip step`。
7. **安装髋臼杯**：`switch install hip cup step`。
8. **验证髋臼杯**：`cup verified point` 或进入 verify 步。

股骨导航：仅当出现 `enter femur navigation page` 时才评安装股骨钉 / 股骨配准 / 股骨截骨。

## 维护

改表后点「重新加载规则」。层级、汇总、Δ 比较在 `app/nle.py`，改那些要动代码并同步本文件。

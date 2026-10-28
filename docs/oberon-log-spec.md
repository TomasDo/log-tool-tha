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

身份键：`start load plan uuid: {uuid}`。同一 uuid 跨多次 `Oberon Application Startup` 合成一张方案汇总，轨道保留其实际区间。标签用杯型（`switch cup type`）+ 手术侧（`operation side`），**轨道不写患者姓名**。

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

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 说明 | 事件ID | 轨道 | 父页面 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Oberon Application Startup | contains | 软件启动 | lifecycle | show | pin | 会话旗标；版本在同一行 | startup |  |  |
| ^start operation\s*$ | regex | 开始手术 | step | show | key | 方案预览点开始手术 | operation_start |  |  |
| start load plan uuid | contains | 开始加载方案 | step | show | key | 消息含 UUID，手术身份键 | plan_load |  |  |
| start import plan path | contains | 开始导入方案 | step | show | key |  | plan_import_start |  |  |
| import plan path | contains | 导入方案结果 | step | show | key | 源码拼写 sucess | plan_import_result |  |  |
| read plan path | contains | 读取外部方案 | step | show | none |  | plan_read |  |  |
| switch cup type | contains | 杯型 | key | show | key | 标签用杯型，不写姓名 | cup_type |  |  |
| operation side | contains | 手术侧 | key | show | key | 同行可能有 patient name，轨道只用侧别 | operation_side |  |  |
| switch planviewer page | contains | 方案预览 | page | show | key |  | page_plan | l1 |  |
| enter planviewer page | contains | 方案预览 | page | show | key |  | page_plan | l1 |  |
| enter device prepare page | contains | 设备准备 | page | show | key |  | page_prepare | l1 |  |
| enter hip navigation page | contains | 髋导航 | page | show | key |  | page_hip | l1 |  |
| enter femur navigation page | contains | 股骨导航 | page | show | key | 部分病例才有 | page_femur | l1 |  |
| enter poster operation page | contains | 术后 | page | show | key |  | page_postop | l1 |  |
| enter hip navigation step 1 install nail | contains | 安装髋标记钉 | step | show | key | 与 switch 同义 | hip_nail | l2 | page_hip |
| switch install hip mark nail step | contains | 安装髋标记钉 | step | show | key |  | hip_nail | l2 | page_hip |
| enter hip navigation step 2 register hip | contains | 髋配准 | step | show | key |  | hip_register | l2 | page_hip |
| switch register hip step | contains | 髋配准 | step | show | key |  | hip_register | l2 | page_hip |
| switch polish hip step | contains | 髋臼打磨 | step | show | key |  | hip_polish | l2 | page_hip |
| switch install hip cup step | contains | 安装髋臼杯 | step | show | key |  | hip_cup | l2 | page_hip |
| enter hip navigation step 5 validate hip cup | contains | 验证髋臼杯 | step | show | key |  | hip_verify | l2 | page_hip |
| switch verify hip cup install step | contains | 验证髋臼杯 | step | show | key |  | hip_verify | l2 | page_hip |
| install femur navigation component step | contains | 安装股骨导航组件 | step | show | key | 股骨导航，可选 | femur_component | l2 | page_femur |
| install femur nail step | contains | 安装股骨钉 | step | show | key | 未进股骨导航的手术不评 | femur_nail | l2 | page_femur |
| register femur step | contains | 股骨配准 | step | show | key |  | femur_register | l2 | page_femur |
| cut femur step | contains | 股骨截骨 | step | show | key |  | femur_cut | l2 | page_femur |
| current device prepare step | contains | 设备准备步骤 | robot | show | none | 设备轨道，不是手术 L1 | prepare_step | device | page_prepare |
| ^kuka app is connected\s*$ | regex | KUKA 已连接 | robot | show | key |  | kuka_connected | device |  |
| ^kuka app is disconnected\s*$ | regex | KUKA 断开 | robot | show | anomaly | 明确手术开始后为异常；人工重启首次断开或缺少开始证据保留提醒，详见复核约定 | kuka_disconnected | device |  |
| robot emergency stop button external is released | contains | 急停松开 | robot | show | none |  | emergency_released | device |  |
| ^connect mxio sucess\s*$ | regex | MXIO 连接成功 | key | show | none | 源码拼写 sucess | mxio_normal | device |  |
| set effector side | contains | 设置末端侧别 | robot | show | key | 样本与源码 | effector_side | device | |
| set tool type: | contains | 设置工具类型编号 | key | show | key | 样本与源码；数字值保留为操作证据 | tool_type_code | device | |
| set tool type \d | regex | 设置工具类型编号 | key | show | key | 样本与源码 | tool_type_code | device | |
| set tool side \d | regex | 设置工具侧别编号 | key | show | key | 样本与源码 | tool_side_code | device | |

---

## 关键信息（重点标注）

距离单位 **mm**。标定 / 配准误差 **>1 mm 升为异常**。方案外展角本身（常见约 40°）**不**套阈值。

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 阈值 | 说明 | 事件ID | 轨道 | 父页面 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ^probe calibration error\s+\S+\s*$ | regex | 探针标定误差 | key | show | key | >1 | 消息末尾误差值，单位 mm；无效值另报异常 | probe_error |  | page_prepare |
| probe calibration result | contains | 探针标定结果 | key | show | none |  |  | probe_result |  | page_prepare |
| ^effector calibration error\s+\S+\s*$ | regex | 末端标定误差 | key | show | key | >1 |  | effector_error |  | page_prepare |
| ^hip register calculate error\s+\S+\s*$ | regex | 髋配准误差 | key | show | key | >1 | 髋配准完成证据；不要对点计数显示 3/5 | hip_error |  | page_hip |
| ^planviewer hand over,plan inclination\b | regex | 规划外展/前倾 | key | show | key |  | 源码拼写 anterversion；规划窗内才算规划完成 | plan_legacy |  |  |
| ^ras coordinate realtime\b | regex | 实测外展/前倾/深度 | key | show | none |  | 过程位姿快照，非最终验证；全零忽略，偏差仅提示，错误级/无效数值仍红色 | measured_ras |  |  |
| ^ras coordinate plan\b | regex | 方案外展/前倾回显 | key | show | none |  | 不是实测 | target_ras |  |  |
| cup verified point | contains | 杯验证点 | key | show | key |  | 坐标；完成证据看本句或进入 verify 步 | cup_sample | l3 | page_hip |
| sparse point | contains | 配准稀疏采集 | key | hide | none |  | 三级；完成看 RMSE | sparse_sample | l3 |  |
| dense point | contains | 配准密采集 | key | hide | none |  | 三级 | dense_sample | l3 |  |
| verify point | contains | 配准验证点 | key | hide | none |  | 勿与 cup verified point 混淆（表内更长串优先） | verify_sample | l3 |  |
| set tool type new metal tool | contains | 选择工具类型 | key | show | key |  | 设备准备 / 髋导航；现场几乎都是 new metal tool | tool | device |  |
| set tool side left | contains | 选择工具侧别 | key | show | key |  | | tool | device |  |
| set tool side right | contains | 选择工具侧别 | key | show | key |  | | tool | device |  |
| set reamer rod: | contains | 选择磨头杆 | key | show | key |  | 髋臼打磨页内选杆 | tool | device |  |
| set cup rod: | contains | 选择装杯杆 | key | show | key |  | 安装髋臼杯页内选杆 | tool | device |  |

---

## 异常操作（红色重点标注）

匹配顺序（硬编码）：级别 E/C（含空 `---E---`）保留最高严重程度。内容先匹配异常表；设置、切换及设备控制操作优先于噪声，并保留已有页面/步骤/具名参数的分类；其他记录按噪声表 → 步骤映射 + 关键信息 → 未匹配隐藏。

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 说明 | 事件ID | 轨道 | 父页面 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (?m)^[= ]*CRASH DETECTED[= ]*$ | regex | 软件崩溃 | other | show | anomaly | 非标准行，堆栈跟在后面 | crash |  |  |
| (?m)^Caught signal\s+\d+\b | regex | 捕获信号崩溃 | other | show | anomaly | 常见 SIGABRT / SIGSEGV | crash |  |  |
| ^robot emergency stop button external is pressed\s*$ | regex | 急停按下 | robot | show | anomaly |  | emergency_pressed | device |  |
| ^marker data is invalid(?:, pausing .+ motion)?\s*$ | regex | 标记钉数据无效 | other | show | anomaly |  | marker_invalid | device |  |
| ^kuka app is disconnected\s*$ | regex | KUKA 断开 | robot | show | anomaly | 明确开始手术后断开标异常；缺少开始证据或人工重启后首次断开保留提醒；E/C 始终红色 | kuka_disconnected | device |  |
| ^kuka states are fault\s*$ | regex | KUKA 故障 | robot | show | anomaly |  | kuka_fault | device |  |
| ^connect mxio failed\s*$ | regex | MXIO 连接失败 | other | show | anomaly |  | mxio_fault | device |  |

Oberon 主集现场日志没有 `connect ndi failed`（那是混入的 Titan 拷贝），**不要**写进本表。

---

## 噪声（默认从时间轴隐藏）

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 说明 | 事件ID | 轨道 | 父页面 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| record torque | contains | 扭矩转储 | noise | hide | none | |  |  |  |
| current joint | contains | 关节角转储 | noise | hide | none | |  |  |  |
| ^ras coordinate realtime anteversion:0 , inclination:0, depth:0\s*$ | regex | 页面切换零 RAS | noise | hide | none | 不当实测 |  |  |  |
| hipmarker2ndi | contains | 髋标记 NDI | noise | hide | none | |  |  |  |

---

## 方案 vs 实测 Δ

RAS/APP 实测分别对照同一方案、同一会话内最近的同坐标系显式目标；RAS 无显式目标时兼容旧版 hand-over。深度只显示原值。

- 启动、退出、崩溃与加载方案边界清空方案快照。
- 角度偏差使用下方统一阈值配置；默认大于 1° 提醒，大于 2° 显示偏差超阈值。realtime 为过程位姿快照（定位前、停止、切页均会记录），偏差保留为重点，不据此把正常操作标成故障；指标保留 anomaly 阈值级别。
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

改表后点「重新加载规则」。事件ID、轨道、必要步骤证据和阈值由本文件配置；区间归属和数值计算在 `app/nle.py`。

## 统一阈值配置

下列角度阈值供解析、轨道和计数共同读取；严格大于才触发。误差幅值仍使用关键信息表的阈值列。

<!-- threshold:angle_key=1 -->
<!-- threshold:angle_anomaly=2 -->

阈值用于售后排查提示。角度单位为度，误差和深度单位为 mm。

## 异常补全（当前源码与样本）

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 事件ID | 轨道 | 父页面 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ^kuka and ndi states are fault\s*$ | regex | KUKA / NDI 联合故障 | robot | show | anomaly | devices_fault | device |  | 当前 OberonV2 源码实际日志输出 |
| ^ndi states are fault\s*$ | regex | NDI 故障 | robot | show | anomaly | ndi_fault | device |  | 样本与源码 |
| ^[A-Za-z]+ marker offset is too big, fix[- ][A-Za-z]+ motion stops\s*$ | regex | 标记偏移过大，机器人停止 | robot | show | anomaly | marker_offset | device |  | 样本与源码 |
| ^standby cmd called by hip/cart marker with huge offset\s*$ | regex | 标记偏移触发待机 | robot | show | anomaly | marker_standby | device |  | 样本与源码 |
| ^robot command response exception catched: Motion Failed\.\s*$ | regex | 机器人运动失败 | robot | show | anomaly | motion_failed | device |  | 当前 OberonV2 源码实际日志输出 |
| ^probe compensate reamer fail\s*$ | regex | 探针补偿失败 | robot | show | anomaly | compensate_failed | device |  | 当前 OberonV2 源码实际日志输出 |
| ^cannot send teach stop command because robot application is disconnected\s*$ | regex | 示教停止指令发送失败 | robot | show | anomaly | teach_stop_failed | device |  | 当前 OberonV2 源码实际日志输出 |
| teach module unavailable; waiting for cart teach button | contains | 示教模块不可用 | robot | show | key | teach_unavailable | device |  | 当前 OberonV2 源码实际日志输出 |
| ^send teach cmd but robot app is disconnect\s*$ | regex | 示教时机器人断开 | robot | show | anomaly | teach_disconnected | device |  | 当前 OberonV2 源码实际日志输出 |
| ^read plan path .+ from external fail\s*$ | regex | 读取方案失败 | other | show | anomaly | plan_read_failed |  |  | 当前 OberonV2 源码实际日志输出 |
| ^can't read\s+.+ | regex | 配置读取失败 | other | show | anomaly | config_failed |  |  | 当前 OberonV2 源码实际日志输出 |

## 步骤映射补全（操作历史）

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 事件ID | 轨道 | 父页面 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ^kuka and ndi states are normal\s*$ | regex | KUKA / NDI 状态正常 | robot | show | none | devices_normal | device |  | 样本与源码；当前源码新增变体按源码测试 |
| cart teach button is pressed | contains | 示教按钮按下 | robot | show | none | teach_pressed | device |  | 样本与源码；当前源码新增变体按源码测试 |
| cart teach button is released | contains | 示教按钮松开 | robot | show | none | teach_released | device |  | 样本与源码；当前源码新增变体按源码测试 |
| physical q-key/pedal is pressed | contains | 脚踏按下 | robot | show | none | pedal_pressed | device |  | 样本与源码；当前源码新增变体按源码测试 |
| physical q-key/pedal is released | contains | 脚踏松开 | robot | show | none | pedal_released | device |  | 样本与源码；当前源码新增变体按源码测试 |
| start fix | contains | 开始定线／定点 | robot | show | none | fix_start | device |  | 样本与源码；当前源码新增变体按源码测试 |
| follow-up motion is activated | contains | 随动启用 | robot | show | none | follow_start | device |  | 样本与源码；当前源码新增变体按源码测试 |
| follow-up motion is deactivated | contains | 随动停用 | robot | show | none | follow_stop | device |  | 样本与源码；当前源码新增变体按源码测试 |
| standby cmd called by mask UI | contains | 操作触发待机 | robot | show | none | manual_standby | device |  | 样本与源码；当前源码新增变体按源码测试 |
| robot stop teach | contains | 示教停止 | robot | show | none | teach_stop | device |  | 样本与源码；当前源码新增变体按源码测试 |
| probe compensate reamer sucess | contains | 探针补偿成功 | robot | show | none | compensate_success | device |  | 样本与源码；当前源码新增变体按源码测试 |
| update probe para | contains | 修改探针参数 | robot | show | none | probe_parameter | device |  | 样本与源码；当前源码新增变体按源码测试 |
| update marker z offset | contains | 修改标记偏移 | robot | show | none | marker_parameter | device |  | 样本与源码；当前源码新增变体按源码测试 |
| marker z offset applied | contains | 应用标记偏移 | robot | show | none | marker_parameter | device |  | 样本与源码；当前源码新增变体按源码测试 |
| switch drill rod | contains | 切换打磨杆 | robot | show | key | tool | device |  | 样本与源码；当前源码新增变体按源码测试 |
| switch install rod | contains | 切换安装杆 | robot | show | key | tool | device |  | 样本与源码；当前源码新增变体按源码测试 |
| click parameter setting button | contains | 打开参数设置 | robot | show | none | parameter_open | device |  | 样本与源码；当前源码新增变体按源码测试 |
| ^use custom module control robot teach\s*$ | regex | 自定义模块示教 | robot | show | none | teach_custom | device |  | 样本与源码；当前源码新增变体按源码测试 |
| ^manual rebooting sirius triggerred | regex | 人工请求重启 Sirius | robot | show | key | sirius_manual_restart | device |  | 当前源码 FITMainWindow::slot_reboot_sirius；请求不代表故障或重启成功 |
| rebooting sirius | contains | Sirius 重启 | robot | show | none | sirius_restart | device |  | 样本与源码；当前源码新增变体按源码测试 |
| reboot sirius | contains | Sirius 重启 | robot | show | none | sirius_restart | device |  | 样本与源码；当前源码新增变体按源码测试 |
| terminating sirius | contains | Sirius 结束中 | robot | show | none | sirius_stop | device |  | 样本与源码；当前源码新增变体按源码测试 |
| terminated sirius | contains | Sirius 已结束 | robot | show | none | sirius_stop | device |  | 样本与源码；当前源码新增变体按源码测试 |
| clear sparse | contains | 清空粗配准点 | key | show | key | clear_sparse | l3 |  | 样本／当前源码；保留操作历史，不当作新的配准结果 |
| clear coarse register points on unlock | contains | 解锁清空粗配准点 | key | show | key | clear_sparse | l3 |  | 样本／当前源码；保留操作历史，不当作新的配准结果 |
| clear dense | contains | 清空精配准点／回退粗配准 | key | show | key | clear_dense | l3 |  | 样本／当前源码；保留操作历史，不当作新的配准结果 |
| undo sparse | contains | 撤销粗配准采集 | key | show | key | undo_sparse | l3 |  | 样本／当前源码；保留操作历史，不当作新的配准结果 |
| undo dense | contains | 撤销精配准采集 | key | show | key | undo_dense | l3 |  | 样本／当前源码；保留操作历史，不当作新的配准结果 |
| clear cup | contains | 清空杯验证点 | key | show | key | clear_cup | l3 |  | 样本／当前源码；保留操作历史，不当作新的配准结果 |
| undo cup | contains | 撤销杯验证采集 | key | show | key | undo_cup | l3 |  | 样本／当前源码；保留操作历史，不当作新的配准结果 |
| Oberon Application Exit | contains | 软件退出 | lifecycle | show | none | exit |  |  | 旧版生命周期兼容 |
| ^app coordinate plan\b | regex | APP 目标角度 | key | show | none | target_app |  |  | 当前 OberonV2 源码实际日志输出 |
| ^app coordinate realtime\b | regex | APP 实测角度与深度 | key | show | none | measured_app |  |  | 当前 OberonV2 源码实际日志输出 |
| delete plan uuid | contains | 删除方案记录 | key | show | none | plan_delete | | | 样本与源码；不改变当前方案归属 |


## 噪声补全

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 事件ID | 轨道 | 父页面 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current torque | contains | 实时力矩转储 | noise | hide | none | torque | | | 样本与源码；显示噪声或原文搜索可查看 |

## 本轮分析约定

- 事件ID、轨道和父页面驱动层级；中文标签可改，不改变业务身份。
- 同一次进程可以加载多个方案；以加载 UUID 为边界，片段会话注明缺少启动行。
- RAS/APP 各自与本方案本会话最近的同坐标系目标比较；显式目标优先于旧版 hand-over 目标。目标缺失时不计算 Δ。深度仅显示 mm 原值。
- `完成/未做` 表示是否找到所配置的日志证据；查看结果需结合证据行、异常和清空/撤销历史。没有开始手术的方案不评必要步骤。
- 清空与撤销不抹除曾经执行过的步骤；结果被明确清除后不再作为当前有效配准结果显示。
- 样本日志覆盖旧版本，源码补全规则通过脱敏合成日志验证；不把 stdout/qDebug 或注释当成日志输出。

## 必要步骤配置

证据为逗号分隔的事件ID，任一命中即满足；条件为空表示所有已开始的方案，条件为页面ID表示仅进入该页面时检查。规划目标另受规划窗口限制。

| 要求ID | 显示名 | 证据事件ID | 条件事件ID |
| --- | --- | --- | --- |
| device_prepare | 设备准备 | page_prepare,prepare_step | |
| probe_cal | 探针标定 | probe_error | |
| plan_target | 规划目标 | plan_legacy,target_ras,target_app | |
| hip_nail | 安装髋标记钉 | hip_nail | |
| hip_register | 髋配准 | hip_error | |
| hip_polish | 髋臼打磨 | hip_polish | |
| hip_cup | 安装髋臼杯 | hip_cup | |
| hip_verify | 验证髋臼杯 | cup_sample,hip_verify | |
| femur_nail | 安装股骨钉 | femur_nail | page_femur |
| femur_register | 股骨配准 | femur_register | page_femur |
| femur_cut | 股骨截骨 | femur_cut | page_femur |

## 设置与切换（默认重点显示）

这些是操作记录，不作为噪声。先保留已配置的页面、步骤、工具和参数含义，再使用本表兜底；宽泛的发送指令或示教状态机噪声规则不能隐藏它们。关键字按操作开头或明确的开关语句识别，不因 `offset`、`setup` 或 `setting` 等子串误判。

硬/软开关的“发送指令”与“已打开/关闭反馈”分开命名，不把发送请求当作成功反馈。

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 事件ID | 轨道 | 父页面 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| switch app coordinate | contains | 切换 APP 坐标系 | key | show | key | coordinate_app | device | | 样本与源码 |
| switch ras coordinate | contains | 切换 RAS 坐标系 | key | show | key | coordinate_ras | device | | 样本与源码 |
| send teach cmd and try to open hard switch | contains | 示教硬开关开启请求 | robot | show | key | hard_switch_open_request | device | | 样本与源码；仅表示请求 |
| send stop cmd and try to close hard switch | contains | 示教硬开关关闭请求 | robot | show | key | hard_switch_close_request | device | | 样本与源码；保留原文中的状态机状态 |
| send open soft switch cmd | contains | 示教软开关开启请求 | robot | show | key | soft_switch_open_request | device | | 样本与源码；仅表示请求 |
| reading handguding button is pressed so hard switch has open sucess | contains | 硬开关已打开反馈 | robot | show | key | hard_switch_opened | device | | 样本与源码；保留原拼写 |
| reading handguding button is released so hard switch has close sucess | contains | 硬开关已关闭反馈 | robot | show | key | hard_switch_closed | device | | 样本与源码；保留原拼写 |
| hard switch | contains | 示教硬开关状态 | robot | show | key | hard_switch_state | device | | 具体请求/成功反馈优先；其他硬开关记录保留原文 |
| soft switch | contains | 示教软开关状态 | robot | show | key | soft_switch_state | device | | 具体请求优先；其他软开关记录保留原文 |
| RobotTeachState:: | prefix | 示教开关状态记录 | robot | show | key | teach_switch_state | device | | 当前源码；具体状态见原文 |
| ^\s*(?i:set)(?![a-z]) | regex | 设置参数或状态 | key | show | key | setting_change | device | | 用户确认：set 操作默认显示；具名参数优先，兼容 setTarget 等指令 |
| ^\s*(?i:switch)(?![a-z]) | regex | 切换参数或状态 | key | show | key | switch_change | device | | 用户确认：switch 操作默认显示；已知页面/步骤分类优先 |
| ^send kuka cmd:\s*(?i:set)(?![a-z]) | regex | 发送 KUKA 设置指令 | robot | show | key | setting_command | device | | 源码存在通用指令输出；只表示发送，具体参数见原文 |
| ^send kuka cmd:\s*(?i:switch)(?![a-z]) | regex | 发送 KUKA 切换指令 | robot | show | key | switch_command | device | | 用户确认的切换指令兜底 |
| ^handle kuka instruct\s*:?[ ]*(?i:set)(?![a-z]) | regex | 处理 KUKA 设置指令 | robot | show | key | setting_command | device | | 源码通用指令输出；不被 handle kuka instruct 噪声吞掉 |
| ^handle kuka instruct\s*:?[ ]*(?i:switch)(?![a-z]) | regex | 处理 KUKA 切换指令 | robot | show | key | switch_command | device | | 用户确认的切换指令兜底 |

## 设备控制操作（优先于噪声）

以下均为发送/处理请求的记录，不代表机器人已经完成动作。具体参数保留原文；未知控制指令也默认显示，防止后续版本增加指令后再次被宽泛噪声规则吞掉。切页待机属于正常流程信息，不据此判断故障。

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 事件ID | 轨道 | 父页面 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ^send kuka cmd:\s*:?[ ]*compensateGravity(?:_[0-9]+)?\b | regex | 重力补偿选择请求 | robot | show | key | gravity_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*compensateGravity(?:_[0-9]+)?\b | regex | 重力补偿选择请求 | robot | show | key | gravity_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*fixLine\b | regex | 定线请求 | robot | show | key | fix_line_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*fixLine\b | regex | 定线请求 | robot | show | key | fix_line_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*fixPoint\b | regex | 定点请求 | robot | show | key | fix_point_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*fixPoint\b | regex | 定点请求 | robot | show | key | fix_point_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*moveToolHandGuiding\b | regex | 工具手导请求 | robot | show | key | tool_hand_guiding_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*moveToolHandGuiding\b | regex | 工具手导请求 | robot | show | key | tool_hand_guiding_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*moveKukaToPatientDirection\b | regex | 对齐患者方向请求 | robot | show | key | align_direction_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*moveKukaToPatientDirection\b | regex | 对齐患者方向请求 | robot | show | key | align_direction_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*moveKukaToPatientPosition\b | regex | 移动到患者目标位置请求 | robot | show | key | move_patient_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*moveKukaToPatientPosition\b | regex | 移动到患者目标位置请求 | robot | show | key | move_patient_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*moveToRecord\b | regex | 移动到预设位请求 | robot | show | key | move_preset_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*moveToRecord\b | regex | 移动到预设位请求 | robot | show | key | move_preset_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*moveToStorage\b | regex | 移动到收纳位请求 | robot | show | key | move_storage_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*moveToStorage\b | regex | 移动到收纳位请求 | robot | show | key | move_storage_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*specialTeachStop\b | regex | 特殊示教停止请求 | robot | show | key | special_teach_stop_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*specialTeachStop\b | regex | 特殊示教停止请求 | robot | show | key | special_teach_stop_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*teachStop\b | regex | 示教停止请求 | robot | show | key | teach_stop_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*teachStop\b | regex | 示教停止请求 | robot | show | key | teach_stop_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*braketestCurrent\b | regex | 制动测试请求（braketestCurrent） | robot | show | key | brake_current_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*braketestCurrent\b | regex | 制动测试请求（braketestCurrent） | robot | show | key | brake_current_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*braketest\b | regex | 制动测试请求 | robot | show | key | brake_test_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*braketest\b | regex | 制动测试请求 | robot | show | key | brake_test_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*standbyMarkerOffsetted\b | regex | 标记偏移触发待机请求 | robot | show | anomaly | marker_standby_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*standbyMarkerOffsetted\b | regex | 标记偏移触发待机请求 | robot | show | anomaly | marker_standby_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*standbyStepChange\b | regex | 切页触发待机请求 | robot | show | none | step_standby_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*standbyStepChange\b | regex | 切页触发待机请求 | robot | show | none | step_standby_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*standby\b | regex | 操作触发待机请求 | robot | show | key | standby_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*standby\b | regex | 操作触发待机请求 | robot | show | key | standby_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*stopMotion\b | regex | 停止运动请求 | robot | show | key | stop_motion_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*stopMotion\b | regex | 停止运动请求 | robot | show | key | stop_motion_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*stop\b | regex | 停止操作请求 | robot | show | key | stop_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*stop\b | regex | 停止操作请求 | robot | show | key | stop_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*:?[ ]*Register\b | regex | 设备注册请求 | robot | show | key | device_register_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^handle kuka instruct\s*:?[ ]*Register\b | regex | 设备注册请求 | robot | show | key | device_register_request | device | | 样本与源码（未在样本出现的指令按源码测试）；仅为请求，参数/编号见原文 |
| ^send kuka cmd:\s*\S+ | regex | 发送机器人指令 | robot | show | key | robot_command_request | device | | 源码通用输出；未知指令保留，不推断动作成功 |
| ^handle kuka instruct\s*:?[ ]*\S+ | regex | 处理机器人指令 | robot | show | key | robot_command_handle | device | | 源码通用输出；未知指令保留，不推断动作成功 |

## 关键信息：结果、停止原因及运行环境

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 事件ID | 轨道 | 父页面 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pedal-pressed UI is displayed | contains | 脚踏按下界面反馈 | robot | show | key | pedal_ui_pressed | device | | 样本与源码；界面状态不等于物理踏板信号或机器人动作完成 |
| pedal-released UI is displayed | contains | 脚踏松开界面反馈 | robot | show | key | pedal_ui_released | device | | 样本与源码；保留响应链路，物理踏板事件仍单独记录 |
| robot no motion joint | prefix | 机器人停止状态反馈（含关节角） | robot | show | key | robot_stopped | device | | 样本与源码；由 robotStatusStop 消息触发，不能仅凭此判断停止原因或急停故障 |
| standby cmd called by step change | contains | 切页触发待机原因 | robot | show | none | step_standby_reason | device | | 样本与源码；正常切页保护，不当作故障 |
| calibration reamer2effector matrix | prefix | 磨头与末端标定矩阵记录 | key | show | key | effector_matrix | device | | 样本与源码；保留结果矩阵，不由矩阵推断误差或完成状态 |
| hipmarker2ct: | prefix | 髋骨配准变换矩阵记录 | key | show | key | hip_registration_matrix | l3 | page_hip | 样本与源码；可能是发布或回退后的矩阵，不替代 RMSE 完成证据 |
| femurmarker2ct: | prefix | 股骨配准变换矩阵记录 | key | show | key | femur_registration_matrix | l3 | page_femur | 当前源码通用输出；不替代配准结果证据 |
| detect net ip | prefix | 探测到的网卡地址 | key | show | none | network_address | device | | 样本与源码；地址枚举，不代表最终选用接口或连接成功 |
| QCoreApplication applicationDirPath | prefix | 程序运行目录 | key | show | none | application_path | | | 样本与源码；用于核对运行版本及资源路径 |
| ^\s*read .+ offset | regex | 假体偏移配置读取 | key | show | none | config_echo | device | | 样本与源码；读取回显，不代表本次实际采用的型号；读取失败仍由异常规则优先识别 |

## 噪声复核原则

- 仅持续记录的原始力矩、关节角、NDI 位姿与全零角度占位快照默认折叠；可通过噪声开关和全文搜索查看。
- 控制请求、停止原因、脚踏界面响应、标定/配准矩阵、环境和配置读取默认可见。
- 警告级 W 即使命中转储规则也作为提醒显示；E/C 始终为异常。全零快照仍不参与角度偏差计算，但不能因此隐藏警告或错误。
- 未经明确日志证据，不把补偿编号解释成已采用的载荷，不把测试请求解释成测试通过，不把矩阵发布解释成配准通过。

## 异常补全：自定义示教模块保护

以下三类来自当前 OberonV2 源码，现有现场样本未出现。它们原先只以通用 W 警告展示，现在分别给出设备事件和保护原因；不据此认定关闭或停止动作已经完成。

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 事件ID | 轨道 | 父页面 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| teach module reported that teach mode is closed; teach stop command sent | prefix | 示教意外关闭，触发停止保护 | robot | show | anomaly | teach_module_unexpected_close | device | | 当前源码 FITKukaCmd::slot_teach_module_status_result；异常关闭反馈触发保护，不等于机器人已停止 |
| teach module connection lost; teach stop command sent | prefix | 示教模块断连，触发停止保护 | robot | show | anomaly | teach_module_lost_stop | device | | 当前源码 FITKukaCmd::slot_teach_module_status_result；保留断连原因，不把停止保护日志当成动作完成 |
| custom module teach mode is open after heartbeat recovery; sending close command | prefix | 心跳恢复后示教仍开启，触发关闭保护 | robot | show | anomaly | teach_module_recovery_close | device | | 当前源码 CustomRobotTeachModule::finish_teach_status_query；只记录异常状态和关闭处理，不代表关闭成功 |

## 关键信息：源码中的未映射信息补全

本节来自源码输出，现有 15 份有效日志中未出现；以合成日志验证，不宣称在现场样本中恢复了这些事件。

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 事件ID | 轨道 | 父页面 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| custom module version query attempt: | prefix | 自定义示教模块版本查询尝试 | robot | show | none | teach_module_version_query | device | | 当前源码 TKAMxio.cpp；查询序号见原文，不按尝试次数推断失败 |
| custom module version: | prefix | 自定义示教模块版本 | key | show | key | teach_module_version | device | | 当前源码 TKAMxio.cpp；用于核对模块能力，不作为 Oberon 软件启动或版本旗标 |
| robot is not teaching state and manual close mask | prefix | 非示教状态下手动关闭遮罩 | robot | show | key | teach_mask_closed | device | | 当前源码 FITKukaCmd::manual_stop_robot_teach；仅记录遮罩处理，断连和停止结果须看独立日志 |
| ^prepar step\s | regex | 设备准备步骤与指令上下文 | robot | show | key | prepare_command_context | device | page_prepare | 当前源码 FITDevPre::slot_sendCommand；保留源码 prepar 拼写及原文参数，不推断注册、标定完成 |

## 噪声补全：股骨原始 NDI 位姿

| 日志匹配 | 匹配方式 | 软件步骤 | 类别 | 时间轴 | 标注 | 事件ID | 轨道 | 父页面 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| femurmarker2ndi NDIDATA: | prefix | 股骨追踪器原始 NDI 位姿 | noise | hide | none | femur_ndi_pose | | | 当前源码 FITRegister 中 marker_name 为 femurmarker 的分支；原始位姿可按噪声/全文搜索查看，对应采集操作、警告和错误仍独立可见 |


## 异常复核约定（2026-10-28）

- 失败规则匹配实际日志语句的开头/结尾；成功读取的路径含 `fail`、`CRASH DETECTED` 或设备状态关键字时，不作为故障证据。崩溃合并也按独立标记行判断。
- 人工重启请求使用 `sirius_manual_restart`；同一连续上下文的首次 KUKA 断开保留提醒，后续断开仍按术中规则判断。连接正常、设备故障、会话/方案/开始手术/术后边界清除人工重启上下文。自动重启不能证明断开属于正常流程。
- `mxio_fault` 仅在后续明确记录 `teach_custom`、且未跨启动/方案/开始手术/退出/崩溃或新的 MXIO 结果时降为提醒。详情记录监听证据行，不断定连接恢复或示教可用。
- 缺少明确手术开始时的断开及急停状态保留提醒；明确术中状态按原异常规则处理，E/C 始终优先。
- realtime 角度记录是过程位姿快照。`metrics[].threshold_level` 保留配置的 1°/2° 偏差等级；`assessment=process_snapshot` 和说明解释其来源。过程角度越界为重点提示，不直接计入软件故障事件；同条 E/C 仍为异常。
- 标定/配准阈值规则派生 `probe_error_invalid` / `effector_error_invalid` / `hip_error_invalid`。负误差、非有限数或无法解析的误差为异常，不满足有效结果证据。
- 坐标分析派生 `plan_legacy_invalid` / `target_ras_invalid` / `target_app_invalid` / `measured_ras_invalid` / `measured_app_invalid`；无效目标清除该坐标系的旧目标，无效实测不保留为当前有效快照。旧有效记录仍可在原文查看。
- 当前现场样本没有无效数值，新规则使用合成边界样例验证。详见 [异常识别复核记录](anomaly-review-2026-10-28.md)。

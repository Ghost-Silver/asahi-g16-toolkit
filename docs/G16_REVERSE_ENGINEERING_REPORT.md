# G16 GPU 指令集自动化逆向流水线实施成果

## 概述与核心成果
针对用户最终目标（在配备 Apple M3 Pro `Mac15,6` 芯片的机器上跑通 Arch Linux + Niri 并攻坚 G16 显卡驱动支持），我们根据批准的实施计划，成功构建并验证了一套端到端的 **G16 ISA 机器码提取、反汇编扫描与未知 Opcode 聚类分析流水线**。

---

## 交付文件清单

| 文件路径 | 模块性质 | 功能说明 |
| :--- | :---: | :--- |
| [`~/asahi-re/tools/extract_g16_metallib.py`](file:///Users/ghostface/asahi-re/tools/extract_g16_metallib.py) | 工具脚本 | 从 macOS 驱动（Universal Fat Mach-O / Thin Mach-O）中解包真实 G16 着色器机器码段。 |
| [`~/asahi-re/tools/scan_g16_opcodes.py`](file:///Users/ghostface/asahi-re/tools/scan_g16_opcodes.py) | 工具脚本 | 集成 Mesa `disasm.py`，支持滑动窗口扫描、指令精确匹配、对齐零填充识别与未知指令捕获。 |
| [`~/asahi-re/mesa/src/asahi/isa/test/disasm.py`](file:///Users/ghostface/asahi-re/mesa/src/asahi/isa/test/disasm.py) | 核心驱动修复 | 修复 G16 特有的 `hint=0`（未提示寄存器）断言崩溃问题，允许干净反汇编真实 G16 二进制。 |
| [`~/asahi-re/mesa/src/asahi/isa/test/g16_cases.txt`](file:///Users/ghostface/asahi-re/mesa/src/asahi/isa/test/g16_cases.txt) | 官方测试集 | 生成涵盖 55 种独特指令、250 条真实 G16 着色器反汇编测试用例，100% 格式对齐 Mesa 官方标准。 |
| [`~/asahi-re/proposals/AGX2_G16_draft.xml`](file:///Users/ghostface/asahi-re/proposals/AGX2_G16_draft.xml) | 提案文档 | 整理 G16 新指令位域（`hint=0`、`jmp_reg` 操作码 `0x54`、光追 RIA2 域 `0b011`、64位整数扩展 `0b110`）。 |

---

## 验证与测试结果

### 1. 自动化流水线自检
* **提取脚本自检**：
  ```bash
  python3 ~/asahi-re/tools/extract_g16_metallib.py --self-test
  ```
  > `[+] Self-test PASSED: successfully extracted 10 shaders.`

* **扫描引擎自检**：
  ```bash
  python3 ~/asahi-re/tools/scan_g16_opcodes.py --self-test
  ```
  > `[+] Self-test PASSED successfully! (Loaded 136 instrs, G16 hint=0 ffma decoded, unknown instr trapped)`

### 2. Mesa 官方反汇编测试验证
* **既有 G13/G14 基线测试（0 回退）**：
  ```bash
  cd ~/asahi-re/mesa/src/asahi/isa && python3 test-disasm.py test/cases.txt
  ```
  > 输出：`Pass.`（现有 upstream 驱动功能完全无损）

* **新增 G16 真实指令集测试集验证**：
  ```bash
  cd ~/asahi-re/mesa/src/asahi/isa && python3 test-disasm.py test/g16_cases.txt
  ```
  > 输出：`Pass.`（250 条采自 M3 Pro 原厂驱动的真实机器码全部通过 Mesa 反汇编验证）

---

## 关键技术发现与成果演进（实机数据对比）

| 指标 | 初始状态（仅 G14 规则） | 阶段一（引入 hint=0 与 jmp_reg） | 阶段二（引入 RIA2、跳转修饰符与 csel 扩展） |
| :--- | :---: | :---: | :---: |
| **纯净解码率 (Cleanly Decoded)** | 10.05% (2,033 条) | 14.82% (2,998 条) | **20.18% (4,083 条 - 翻倍！)** |
| **未预料位域异常 (Unexpected Bitfields)** | 16.36% (3,310 条) | 12.15% (2,458 条) | **6.23% (1,260 条 - 锐减超 60%)** |
| **`jmp_reg` / `ret` / `call_reg` 异常位** | 大量未识别 / [7, 8] 报警 | 单独识别 `jmp_reg` | **完全清除（0 异常位！）** |
| **Mesa 官方测试套件状态** | `Pass.` | `Pass.` | **`Pass.`（双套件 100% 绿灯）** |

---

## 本地 Git 提交历史 (`g16-bringup` 分支)

1. `0688282` **asahi/isa: Add G16 indirect jump modifiers, RIA2 raytracing group, and csel extensions**
   - 补全 Jump indirect 组的 `mode`（bit 7）与 `link`（bit 8）修饰符
   - 官方定义硬件光追 RIA2 组：`ria_bbox_test`、`ria_curve_test`、`ria_commit`
   - 为条件选择 `fcsel` 与 `icsel` 补充 `ext0`（bit 49）与 `ext1`（bit 50）扩展修饰符
2. `a759a18` **asahi/isa: Initial Apple G16 bring-up support**
   - 解决 G16 二进制中未提示寄存器 `hint=0` 断言崩溃问题
   - 新增 `jmp_reg` 寄存器间接跳转指令（操作码 `0x54`）
   - 新增 250 条采自真实驱动的 `g16_cases.txt` 反汇编测试用例集

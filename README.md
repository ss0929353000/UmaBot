# 赛马娘助手（UmaBot）

PC 版《赛马娘》（DMM / Steam）的挂机辅助脚本，靠截图识别和模拟鼠标点击运作，不修改游戏文件，也不读写游戏内存。

> ⚠️ 使用第三方工具违反游戏用户协议，账号有被处罚或封禁的风险，请自行判断。本项目仅供学习交流。

## 功能

| 功能 | 说明 |
| --- | --- |
| 定时重开自动育成 | 按设定间隔结束游戏内置的自主训练养成：确定因子、领奖励、再次育成，开始新一轮后回到主页 |
| TP 自动回复 | TP 不足时只用「体力饮料(30)」，每轮上限可设 |
| 自动启动游戏 | 每轮结束后关闭游戏，下一轮前从加速器加速并启动（默认支持 UU，其他加速器可自订按钮顺序），避免挂太久被强制重登 |
| 育成收益统计 | 自动记录每轮粉丝数和彩色萝卜增加量，按日期汇总，附 14 天图表，可导出 CSV |
| 剧情跳过领奖励 | 自动打开未读剧情、跳过、领取首次阅读奖励 |
| 自定义执行模式 | 自己建立模式，在模板页为它添加专属按钮步骤，按顺序找到就点 |
| 安全机制 | 游戏不在最前面时暂停；F10 或鼠标移到屏幕左上角立即停止；各流程有超时 |

## 安装

需要 Windows 10/11 和 [Python 3.10+](https://www.python.org/downloads/)（安装时勾选 Add Python to PATH）。

```bat
git clone https://github.com/<你的用户名>/UmaBot.git
cd UmaBot
build.bat
```

完成后运行 `dist\UmaBot.exe`。也可以不打包，直接运行：

```bat
pip install -r requirements.txt
python uma_bot.py
```

## 使用

1. 在游戏里开好一轮自主训练养成，回到主页。
2. 打开程序，「运行」页选「定时重开自动育成」，设定间隔（建议 50～53 分钟）。
3. 点「启动」。倒计时期间不会动鼠标；需要点击的那几分钟请让游戏留在最前面。

### 第一次使用：截取模板

仓库不附带按钮模板（游戏画面截图），第一次使用前请在「模板」页自己截取。让游戏停在有该按钮的画面，选中项目点「截取」，再框住按钮即可。截一次之后会按窗口大小自动缩放。

定时重开自动育成需要的模板：

| 阶段 | 模板 |
| --- | --- |
| 开始流程 | `flow_home`、`flow_home_running`、`flow_next`、`flow_ikusei_start`、`flow_tp_recover`、`flow_tp_drink`、`flow_tp_use`、`flow_ok`、`flow_close`、`flow_decide`、`flow_auto_start`、`flow_running`、`flow_menu`、`flow_menu_home`、`flow_jewel` |
| 结束流程 | `end_go`、`end_finish_btn`、`end_finish`、`end_factor_ok`、`end_confirm`、`end_close`、`end_again`、`end_fans`、`end_next`、`end_next_b` |
| 自动启动 | UU：`uu_tile`、`uu_start`；其他加速器：在「添加按钮到」选「自动启动：加速器按钮」按顺序添加（截整个桌面） |

至少要有 `flow_home`、`flow_next`、`flow_ikusei_start`、`flow_auto_start` 才能启动，其余缺少时对应步骤会被跳过。每个模板要框的内容，在「模板」页的说明栏都有写。

## 文件

| 文件 | 说明 |
| --- | --- |
| `uma_bot.py` | 程序本体 |
| `build.bat` | 一键安装依赖并打包成 exe |
| `templates/` | 自己截取的按钮模板放这里（不上传）；`topbar_digits.npz` 是数字识别特征 |
| `config.json` / `fans.json` / `state.json` | 运行后自动生成的个人设置与记录，已在 `.gitignore` 中排除 |

## 打赏与反馈

使用顺畅的话，可以在程序的「打赏」页扫码打赏一瓶可乐支持一下。

Bug 反馈：363111444@qq.com（附上运行日志截图和卡住的游戏画面）

## 声明

- 本仓库不包含游戏画面截图；游戏相关名称与素材版权归 Cygames 所有。
- 脚本会消耗体力饮料等道具，请确认设置后再挂机。

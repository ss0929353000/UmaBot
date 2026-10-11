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

完成后运行 `dist\UmaBot.exe`。**exe 只需要打包这一次**：以后有新版本，打开程序时会自动提示，点「是」就会从 GitHub 下载更新并重新打开（也可以在「设置」页点「检查更新」）。设置、模板、粉丝和萝卜记录都会保留。

也可以不打包，直接运行（这种方式请用 `git pull` 更新）：

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
| `uma_bot.py` | 程序本体（exe 版会放在 `dist\app\uma_bot.py`，自动更新就是换掉这个文件） |
| `launcher.py` | exe 启动器：exe 里只打包启动器和依赖，启动时载入 `app\uma_bot.py` |
| `version.json` | 最新版本号和更新内容，程序靠它判断有没有新版本 |
| `make_release.py` | 发布新版本时生成 `version.json` |
| `build.bat` | 一键安装依赖并打包成 exe |
| `templates/` | 自己截取的按钮模板放这里（不上传）；`topbar_digits.npz` 是数字识别特征 |
| `config.json` / `fans.json` / `state.json` | 运行后自动生成的个人设置与记录，已在 `.gitignore` 中排除 |

## 发布新版本（作者用）

1. 改好 `uma_bot.py`，把里面的 `VERSION = "x.y"` 调大。
2. 运行 `python make_release.py "这次更新了什么"`，会生成 `version.json`（含版本号、更新内容和校验码）。
3. 把 `uma_bot.py` 和 `version.json` 一起上传到 GitHub 的 `main` 分支。

用户下次打开程序就会收到更新提示。程序会先连 GitHub，连不上再改用 jsDelivr 镜像（镜像可能晚几分钟到几小时才同步）。下载的文件要校验码一致、而且能正常编译才会替换，旧版会备份到 `app\backup\`；新版万一打不开，启动器会自动退回 exe 内附的版本。

> 如果新版本用到了新的 Python 库，旧 exe 里没有打包，就需要重新运行 `build.bat`。

## 打赏与反馈

使用顺畅的话，可以在程序的「打赏」页扫码打赏一瓶可乐支持一下。

Bug 反馈：363111444@qq.com（附上运行日志截图和卡住的游戏画面）

## 声明

- 本仓库不包含游戏画面截图；游戏相关名称与素材版权归 Cygames 所有。
- 脚本会消耗体力饮料等道具，请确认设置后再挂机。

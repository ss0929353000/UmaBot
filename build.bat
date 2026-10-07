@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 当前文件夹：%cd%

if not exist uma_bot.py (
  echo [错误] 找不到 uma_bot.py，请先把压缩包完整解压
  pause & exit /b 1
)
where python >nul 2>nul || (
  echo [错误] 未找到 Python，请先安装 Python 3.10 以上，并勾选 Add Python to PATH
  pause & exit /b 1
)

echo [1/2] 安装依赖...
python -m pip install opencv-python numpy mss pyautogui pywin32 pillow pynput ttkbootstrap pyinstaller || (
  echo [错误] 依赖安装失败
  pause & exit /b 1
)

set ICON_ARGS=
if exist icon.png if not exist icon.ico (
  echo 把 icon.png 转换成 icon.ico...
  python -c "from PIL import Image; Image.open('icon.png').convert('RGBA').save('icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
)
if exist icon.ico (
  echo 使用自定义图标 icon.ico
  set ICON_ARGS=--icon icon.ico --add-data "icon.ico;."
)

set DONATE_ARGS=
if exist donate.jpg set DONATE_ARGS=--add-data "donate.jpg;."

echo [2/2] 打包 exe...
python -m PyInstaller --onefile --noconsole --clean --name UmaBot %ICON_ARGS% %DONATE_ARGS% ^
  --collect-all ttkbootstrap ^
  --hidden-import pynput.keyboard._win32 ^
  --hidden-import pynput.mouse._win32 ^
  uma_bot.py || (
  echo [错误] 打包失败
  pause & exit /b 1
)

if exist templates xcopy /e /i /y templates dist\templates >nul
if exist config.json copy /y config.json dist\ >nul
if exist icon.ico copy /y icon.ico dist\ >nul
if exist theme.png copy /y theme.png dist\ >nul

echo.
echo 完成！程序位于 %cd%\dist\UmaBot.exe
explorer dist
pause

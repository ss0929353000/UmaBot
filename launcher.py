"""赛马娘助手 启动器。

exe 里打包的是这个启动器和所有依赖（OpenCV、界面库等）；真正的程序代码放在
exe 旁边的 app\\uma_bot.py。自动更新时只要换掉这个文件，不用重新打包 exe。
"""
import os
import re
import shutil
import sys
import traceback

# pyautogui 一载入就会把程序设成「系统 DPI」模式；先设成每个屏幕各自的缩放，坐标才不会被换算错
try:
    import ctypes as _ct
    _ct.windll.user32.SetProcessDpiAwarenessContext(_ct.c_void_p(-4))
except Exception:
    pass

# ---- 下面这些 import 是给 PyInstaller 看的：程序代码要用的库都要先打包进 exe ----
import base64, csv, ctypes, glob, hashlib, io, json, math, queue, random, ssl, struct  # noqa: E401,F401
import subprocess, tempfile, threading, time, urllib.request, urllib.error, webbrowser, zipfile  # noqa: E401,F401
from collections import Counter, OrderedDict, defaultdict, deque  # noqa: F401
from datetime import date, datetime, timedelta  # noqa: F401
import tkinter as tk  # noqa: F401
from tkinter import filedialog, messagebox, simpledialog  # noqa: F401
import cv2  # noqa: F401
import mss  # noqa: F401
import numpy  # noqa: F401
import pyautogui  # noqa: F401
import ttkbootstrap  # noqa: F401
import ttkbootstrap.constants  # noqa: F401
import ttkbootstrap.style  # noqa: F401
import win32api, win32con, win32gui, win32process  # noqa: E401,F401
import win32com.client  # noqa: F401
import pythoncom  # noqa: F401
from PIL import Image, ImageTk  # noqa: F401
try:
    import pynput.keyboard  # noqa: F401
    import pynput.mouse  # noqa: F401
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
APP_DIR = os.path.join(BASE, "app")
APP_PY = os.path.join(APP_DIR, "uma_bot.py")
BUNDLED = os.path.join(getattr(sys, "_MEIPASS", BASE), "uma_bot.py")


def read_version(path):
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r'^VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
        return tuple(int(x) for x in re.findall(r"\d+", m.group(1))) if m else (0,)
    except Exception:
        return (0,)


def compiles(path):
    try:
        with open(path, encoding="utf-8") as f:
            compile(f.read(), path, "exec")
        return True
    except Exception:
        return False


def pick_code():
    """用 app\\uma_bot.py；没有、坏掉或比 exe 内附的还旧，就用 exe 内附的那份放回去。"""
    os.makedirs(APP_DIR, exist_ok=True)
    have_bundled = os.path.exists(BUNDLED) and os.path.abspath(BUNDLED) != os.path.abspath(APP_PY)
    if os.path.exists(APP_PY):
        if not compiles(APP_PY):
            os.replace(APP_PY, APP_PY + ".broken")
        elif not have_bundled or read_version(APP_PY) >= read_version(BUNDLED):
            return APP_PY
    if have_bundled:
        shutil.copy2(BUNDLED, APP_PY)
        return APP_PY
    return APP_PY if os.path.exists(APP_PY) else None


def main():
    os.chdir(BASE)
    sys.argv[0] = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    code = pick_code()
    if not code:
        messagebox.showerror("赛马娘助手", "找不到程序文件 app\\uma_bot.py，请重新下载完整的程序。")
        return
    try:
        # 不用 runpy.run_path：它会把 sys.argv[0] 改成 app\uma_bot.py，程序就会去 app 文件夹找设置和模板
        with open(code, encoding="utf-8") as f:
            src = f.read()
        g = {"__name__": "__main__", "__file__": code, "__builtins__": __builtins__}
        exec(compile(src, code, "exec"), g)
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        try:
            with open(os.path.join(BASE, "crash.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("\n==== %Y-%m-%d %H:%M:%S ====\n") + err)
        except Exception:
            pass
        # 更新后的版本打不开：退回 exe 内附的版本，下次打开就正常
        rolled = ""
        if os.path.exists(BUNDLED) and read_version(code) > read_version(BUNDLED):
            try:
                os.replace(code, code + ".broken")
                rolled = "\n\n已退回原本的版本，请重新打开程序。"
            except Exception:
                pass
        messagebox.showerror("赛马娘助手", "程序出错了，错误记录在 crash.log。" + rolled + "\n\n" + err[-800:])


if __name__ == "__main__":
    main()

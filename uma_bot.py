# -*- coding: utf-8 -*-
"""
赛马娘助手 v2（PC：DMM / Steam）
- 定时结束并重开游戏内置自动育成
- 剧情跳过领奖励
原理：截取游戏窗口 → OpenCV 模板比对 → 模拟鼠标点击。模板需在程序内自行截取。
紧急停止：F10，或把鼠标移到屏幕左上角。
"""
import base64
import csv
import ctypes
import json
import os
import queue
import random
import re
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import filedialog, messagebox

import cv2
import mss
import numpy as np
import pyautogui
import ttkbootstrap as tb
import win32api
import win32con
import win32gui
import win32process
from PIL import Image, ImageTk
from ttkbootstrap.constants import BOTH, BOTTOM, DISABLED, LEFT, NORMAL, RIGHT, TOP, VERTICAL, W, X, Y

try:
    from pynput import keyboard as pynput_kb
except ImportError:
    pynput_kb = None

try:  # 高 DPI 坐标修正
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0

APP_NAME = "赛马娘助手"
VERSION = "3.0"
SUBTITLE = "by-Yung"
FEEDBACK_EMAIL = "363111444@qq.com"
FONT = "Microsoft YaHei UI"

BASE = os.path.dirname(os.path.abspath(sys.argv[0]))
TPL_DIR = os.path.join(BASE, "templates")
CFG_PATH = os.path.join(BASE, "config.json")
FANS_PATH = os.path.join(BASE, "fans.json")
STATE_PATH = os.path.join(BASE, "state.json")


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
    except Exception:
        pass
os.makedirs(TPL_DIR, exist_ok=True)

MODES = {
    "auto_cycle": "⏱  定时重开自动育成",
    "story": "☰  剧情跳过领奖励",
}
MODE_HINT = {
    "auto_cycle": "先在游戏里开好自动育成，再点启动",
    "story": "先让游戏停在剧情列表，再点启动",
}
REQUIRED = {
    "auto_cycle": ["flow_home", "flow_next", "flow_ikusei_start", "flow_auto_start"],
    "story": ["story_list", "story_new", "story_skip"],
}
TEMPLATE_GROUPS = [
    ("自动育成：开始流程（已内置）", "flow_", {
        "flow_home": "主页「育成」按钮",
        "flow_home_running": "主页「自主训练中」标记",
        "flow_next": "「下项」",
        "flow_ikusei_start": "「育成开始！」",
        "flow_tp_recover": "TP 不足时的「回复」",
        "flow_tp_drink": "TP 回复清单里的「体力饮料(30)」",
        "flow_tp_use": "「使用」按钮",
        "flow_tp_jewel": "TP 回复清单里的「宝石」（饮料用完时才会用）",
        "flow_ok": "「OK」",
        "flow_close": "「关闭」",
        "flow_decide": "「决定」",
        "flow_auto_start": "「自主训练养成开始！」",
        "flow_running": "自主训练画面底部「自主トレ中」",
        "flow_menu": "自主训练画面右下角菜单",
        "flow_menu_home": "菜单里的「返回主页」",
        "flow_jewel": "顶部栏的彩色萝卜（宝石）图标",
    }),
    ("自动育成：结束流程（已内置）", "end_", {
        "end_go": "「前往育成」",
        "end_finish_btn": "「育成完成！」",
        "end_finish": "育成结束确认里的「结束」",
        "end_factor_ok": "因子获取的「确定因子」",
        "end_confirm": "确定因子确认的「确定」",
        "end_close": "赛马娘信息的「关闭」",
        "end_again": "「再次育成」",
        "end_fans": "获得奖励里的「获得粉丝总数」标题（用来记录粉丝数）",
        "end_next": "领奖画面的「下项」（左半边，避开闪光圈）",
        "end_next_b": "结算画面的「下项」（左半边，避开闪光圈）",
    }),
    ("自动启动游戏（加速器）", "uu_", {
        "uu_tile": "（UU 专用）首页里「赛马娘Pretty Derby」这几个字",
        "uu_start": "（UU 专用）加速后的「启动游戏」按钮",
    }),
    ("剧情跳过", "story_", {
        "story_list": "剧情列表的标题，用来判断在列表画面",
        "story_new": "列表里的「NEW」标记",
        "story_skip": "播放中的跳过按钮",
        "story_skip_confirm": "跳过确认框的「确定」",
        "btn_story_play": "打开剧情时的「播放」确认",
    }),
    ("通用按钮（看到就点）", "btn_", {
        "btn_next": "「下一步」",
        "btn_ok": "「确定」",
        "btn_skip": "「略过」",
        "btn_close": "「关闭」",
    }),
]

def mode_label(cfg, mode):
    if mode in MODES:
        return MODES[mode].strip()
    m = cfg.get("custom_modes", {}).get(mode)
    return f"★ {m['name']}" if m else mode


def mode_required(cfg, mode):
    if mode in REQUIRED:
        return REQUIRED[mode]
    return list(cfg.get("custom_modes", {}).get(mode, {}).get("order", []))


def step_name(key):
    """m_cm1_关闭 → 关闭"""
    parts = key.split("_", 2)
    return parts[2] if key.startswith("m_") and len(parts) == 3 else key


DEFAULT_CFG = {
    "dmm_only": False,         # 不开加速器，每次都直接用 DMM 快捷方式打开游戏
    "humanize": True,          # 点击位置在按钮范围内随机、速度随机
    "minimize_others": True,   # 开游戏 / 开始操作时，把游戏以外的窗口全部最小化
    "minimize_on_start": True,  # 点启动后程序自己缩到任务栏，不挡住游戏
    "custom_modes": {},
    "auto_launch": False,      # 每轮结束后关游戏，下一轮前用 UU 加速器重新启动
    "uu_path": "",             # 加速器（或游戏启动器）的位置
    "game_path": "",           # DMM 游戏快捷方式
    "acc_order": [],           # 其他加速器：要依序点的按钮
    "launch_lead": 5,          # 提前几分钟启动游戏
    "launch_wait": 5,          # 启动后最多等几分钟进入主页
    "auto_focus": False,
    "mode": "auto_cycle",
    "cycle_minutes": 50,
    "cycle_run_now": False,
    "cycle_timeout": 600,
    "tp_auto_drink": True,
    "tp_max_drinks": 2,
    "tp_use_jewel": False,     # 体力饮料用完时用宝石回复
    "tp_max_jewel": 1,
    "story_max_episodes": 0,
    "story_max_scroll": 5,
    "story_new_region": None,
    "window_title": "umamusume",
    "delay": 0.3,
    "cfg_version": 4,
    "match_threshold": 0.85,
    "capture_size": None,
    "custom_templates": {},
    "fan_reset_hour": 0,
}

# 配色：里见家的祖母绿、金色与象牙白
PALETTE = {
    "primary": "#1f6b4a",   # 祖母绿
    "secondary": "#8a7b5c",
    "success": "#2f8f5b",
    "info": "#3a7ca5",
    "warning": "#c9a227",   # 金
    "danger": "#b23a48",    # 酒红
    "light": "#f4efe1",
    "dark": "#1d2b24",
    "bg": "#fbf8ef",        # 象牙白
    "fg": "#22302a",
    "selectbg": "#1f6b4a",
    "selectfg": "#fffdf6",
    "border": "#d9cfb3",
    "inputfg": "#22302a",
    "inputbg": "#fffdf6",
    "active": "#efe6cc",
}
GOLD = "#e3c46b"
LOG_BG = "#17251e"


def load_cfg():
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    if os.path.exists(CFG_PATH):
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    if cfg.get("cfg_version", 0) < 4:  # 旧版本的等待时间太长，升级时自动调快
        cfg["delay"] = min(cfg.get("delay", 0.3), 0.3)
        cfg["cfg_version"] = 4
    if cfg.get("mode") not in MODES and cfg.get("mode") not in cfg.get("custom_modes", {}):
        cfg["mode"] = "auto_cycle"
    return cfg


def save_cfg(cfg):
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ================= 窗口、截图、识别 =================
def find_window(title):
    title = title.lower()
    found = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and title in win32gui.GetWindowText(h).lower():
            try:
                unity = win32gui.GetClassName(h) == "UnityWndClass"
            except Exception:
                unity = False
            found.append((0 if unity else 1, h))

    win32gui.EnumWindows(cb, None)
    return min(found)[1] if found else None


def grab_screen():
    """截整个桌面（含多屏），回传图像和左上角坐标。"""
    with mss.mss() as s:
        mon = s.monitors[0]
        shot = s.grab(mon)
    return np.ascontiguousarray(np.array(shot)[:, :, :3]), mon["left"], mon["top"]


def force_foreground(hwnd):
    """Windows 会挡住后台程序抢前台，先按一下 Alt 再切换。"""
    try:
        win32api.keybd_event(0x12, 0, 0, 0)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    finally:
        try:
            win32api.keybd_event(0x12, 0, 2, 0)
        except Exception:
            pass


SKIP_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW",
                "Windows.UI.Core.CoreWindow", "NotifyIconOverflowWindow"}


def minimize_other_windows(keep_hwnd):
    """把桌面上除了游戏以外、看得见的普通窗口全部最小化。回传最小化了几个。"""
    keep_pid = None
    try:
        _, keep_pid = win32process.GetWindowThreadProcessId(keep_hwnd)
    except Exception:
        pass
    targets = []

    def cb(h, _):
        try:
            if h == keep_hwnd or not win32gui.IsWindowVisible(h) or win32gui.IsIconic(h):
                return
            if not win32gui.GetWindowText(h) or win32gui.GetClassName(h) in SKIP_CLASSES:
                return
            if win32gui.GetWindow(h, win32con.GW_OWNER):  # 对话框、弹出层跟着主窗口走
                return
            ex = win32gui.GetWindowLong(h, win32con.GWL_EXSTYLE)
            if ex & win32con.WS_EX_TOOLWINDOW:  # 悬浮工具条、托盘小窗
                return
            if keep_pid and win32process.GetWindowThreadProcessId(h)[1] == keep_pid:
                return  # 游戏自己的其他窗口
            targets.append(h)
        except Exception:
            pass

    win32gui.EnumWindows(cb, None)
    for h in targets:
        try:
            win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
        except Exception:
            pass
    return len(targets)


def shortcut_target(path):
    """.lnk 快捷方式 → 真正的 exe 路径；其他文件原样回传。"""
    if path.lower().endswith(".lnk"):
        try:
            import win32com.client
            t = win32com.client.Dispatch("WScript.Shell").CreateShortCut(path).Targetpath
            if t:
                return t
        except Exception:
            pass
    return path


def process_running(exe_name):
    """用 tasklist 看某个程序有没有在跑。"""
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return exe_name.lower() in out.lower()
    except Exception:
        return False


def rand_point(pt, box, on=True):
    """在按钮范围内随机挑一点：靠中间的机率高，不会点到边缘外。box = (宽, 高)。"""
    if not on:
        return pt
    w, h = box if box else (16, 10)
    dx = max(-0.35, min(0.35, random.gauss(0, 0.15))) * w
    dy = max(-0.3, min(0.3, random.gauss(0, 0.13))) * h
    return int(pt[0] + dx), int(pt[1] + dy)


def human_press(x, y, on=True):
    """移动过去再按下放开；开了随机化时，移动快慢、按住时间都不固定。"""
    if on:
        pyautogui.moveTo(x, y, duration=random.uniform(0.08, 0.28), tween=pyautogui.easeOutQuad)
        time.sleep(random.uniform(0.02, 0.09))
        pyautogui.mouseDown()
        time.sleep(random.uniform(0.045, 0.14))
        pyautogui.mouseUp()
    else:
        pyautogui.moveTo(x, y)
        pyautogui.mouseDown()
        time.sleep(0.05)
        pyautogui.mouseUp()


def own_windows():
    """本程序自己的窗口（找加速器按钮时要排除）。"""
    me = os.getpid()
    out = []

    def cb(h, _):
        try:
            if win32gui.IsWindowVisible(h) and not win32gui.IsIconic(h) \
                    and win32process.GetWindowThreadProcessId(h)[1] == me:
                out.append(h)
        except Exception:
            pass

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return out


def is_foreground(hwnd):
    try:
        fg = win32gui.GetForegroundWindow()
        return bool(fg) and (fg == hwnd or win32gui.GetAncestor(fg, 2) == hwnd)
    except Exception:
        return False


def client_rect(hwnd):
    l, t, r, b = win32gui.GetClientRect(hwnd)
    x, y = win32gui.ClientToScreen(hwnd, (0, 0))
    return x, y, r - l, b - t


def grab(rect):
    x, y, w, h = rect
    with mss.mss() as s:
        shot = s.grab({"left": x, "top": y, "width": w, "height": h})
    return np.ascontiguousarray(np.array(shot)[:, :, :3])


def tpl_path(key):
    return os.path.join(TPL_DIR, f"{key}.png")


def load_templates():
    tpls = {}
    for fn in os.listdir(TPL_DIR):
        if fn.lower().endswith(".png"):
            img = cv2.imdecode(np.fromfile(os.path.join(TPL_DIR, fn), np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                tpls[fn[:-4]] = img
    return tpls


META_PATH = os.path.join(TPL_DIR, "meta.json")


def load_meta():
    try:
        with open(META_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_meta(meta):
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


WORK_H = 760  # 识别时把画面缩到这个高度以内，速度快很多


def prepare_templates(cur_h, cfg):
    """按截取时的窗口高度，把模板缩放到当前窗口大小。"""
    meta = load_meta()
    fallback = (cfg.get("capture_size") or [0, 0])[1]
    out = {}
    for k, img in load_templates().items():
        ref = meta.get(k) or fallback or cur_h
        f = cur_h / ref
        if abs(f - 1) > 0.01:
            img = cv2.resize(img, (max(1, round(img.shape[1] * f)), max(1, round(img.shape[0] * f))),
                             interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)
        out[k] = img
    return out


def match(img, tpl, thr):
    if tpl is None or tpl.shape[0] > img.shape[0] or tpl.shape[1] > img.shape[1]:
        return None, 0.0
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    h, w = tpl.shape[:2]
    pt = (loc[0] + w // 2, loc[1] + h // 2)
    return (pt if mx >= thr else None), mx


def match_all(img, tpl, thr):
    if tpl is None or tpl.shape[0] > img.shape[0] or tpl.shape[1] > img.shape[1]:
        return []
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    h, w = tpl.shape[:2]
    ys, xs = np.where(res >= thr)
    cands = sorted(zip(res[ys, xs], xs, ys), reverse=True)
    kept = []
    for _, x, y in cands:
        if all(abs(x - kx) > w // 2 or abs(y - ky) > h // 2 for kx, ky in kept):
            kept.append((x, y))
    return sorted([(x + w // 2, y + h // 2) for x, y in kept], key=lambda p: p[1])


# ================= 粉丝数识别 =================
# 游戏数字字形（30×30 点阵），用来读「(+1,308,575人)」这种橙色数字
GLYPHS = {k: np.unpackbits(np.frombuffer(base64.b64decode(v), np.uint8))[:900].reshape(30, 30)
          for k, v in {"+": "AA/AAAB/AAAD/AAAD/AAAD/AAAD/AAAD/AAAD/AAAD/AAAD/AAAH/4AAH/4A//////////////////////////////AD/wAAD/gAAD/AAAD/AAAD/AAAD/AAAD/AAAD/AAAD/AAAD/AAAB/AAAA/AAA=", "1": "AAH4AAAf8AAD/8AAP/8AAP/8AAP/8AAH/8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAH8AAAD8AA=", "3": "AAIAAAH/4AAf/+AA///AB///AD///gD+A/wD+AfwD4AfwAAAfwAAAfgAAAfgAAB/AAA//AAA/+AAB/8AAA/+AAA//gAAA/wAAAfwAAAPwAAAP4D4AP4H8Af4H+AfwD///wD///gA///AAf//AAP/8AA=", "0": "AAIAAAH/wAAP/4AAf/8AA///AB///AD/B/AD+A/gD8AfgD8AfwH8APwH4APwH4APwH4APwH4APwH4APwH4APwH4APwH4APwH4APwH8APwD8AfwD8AfgD+A/gD/B/gB///AA///AAf/+AAf/8AAH/wAA=", "8": "AAYAAAH/wAAf/8AA//+AB///AB/j/AB/B/AB+A/gB+A/gB+A/gB+A/AB/B/AA//+AAf/8AAP/4AAf/8AA///AB/D/AD+A/gD8AfgH8AfwH8AfwH8AfwD+A/gD/B/gB///gB///AAf/+AAP/4AAAcAAA=", "5": "A///AA///gA///gA///gB///gB/gAAB/AAAB+AAAB+AAAB+AAAB+AAAD//8AD///AD///gD///wD///wB/h/4A8Af4AAAP4AAAP4AAAP4AAAP4AAAP4H+Af4H/A/wD///wB///gA///AAf/+AAP/8AA=", "7": "D///wH///4H///4H///wD///wAAB/wAAA/gAAA/AAAB+AAAD+AAAD8AAAH8AAAH4AAAP4AAAP4AAAfwAAAfwAAA/wAAA/gAAA/gAAB/gAAB/AAAB/AAAD/AAAD/AAAD/AAAD/AAAD+AAAD+AAAD+AAA=", "2": "AAeAAAH/8AAf/+AA///AB///AB///gD+A/gD+AfwD8AfwAAAfwAAAfwAAA/gAAA/gAAB/AAAH/AAAP+AAAf4AAB/wAAD/gAAH+AAAP8AAA/4AAA/gAAB/AAAB/AAAD///wD///wD///wH///wD///wA=", "9": "AA+AAAH/gAAf/wAA//4AB//8AB/n+AD+B+AD8B/AD8A/AD8AfgD8AfgD8AfgD8AfgD8A/gD/n/gD///gB///gA///gAH4fgAAAfgAAAfgAAA/AAAA/AD+B+AD/H+AB//8AB//8AA//4AAP/gAAA8AAA=", "6": "AAPgAAD/4AAH/+AAP//AAf//gA/7/gB/gPgB/AAAB+AAAB+AAAB8AAAB8AAAD+P4AD///AD///gD///gD/5/wD/gfwD+APwB8AHwB8AHwB+AHwB+APwB+APwA/wfwA///gAf//AAP/+AAD/8AAA/wAA=", "4": "AAf+AAA/+AAA/+AAA/+AAB/+AAB/+AAD9+AAH5+AAHx+AAPh+AAfh+AA/B+AA/B+AB+B+AD+B+AD8B+AH4B+AP4B+AP8B/AP///4P///4P///4P///4EAH/AAAB+AAAB+AAAB+AAAB+AAAB+AAAA+AA="}.items()}


def _norm_glyph(m):
    h, w = m.shape
    nw = min(30, max(1, round(w * 30 / h)))
    g = cv2.resize(m.astype(np.float32), (nw, 30), interpolation=cv2.INTER_AREA)
    c = np.zeros((30, 30), np.float32)
    o = (30 - nw) // 2
    c[:, o:o + nw] = g
    return (c > 0.4).astype(np.uint8)


def read_fan_gain(img):
    """在画面里找「+数字人」这一行橙色字，回传数字；找不到回传 None。"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = ((h >= 5) & (h <= 22) & (s > 150) & (v > 200)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    cs = [(st[i][0], st[i][1], st[i][2], st[i][3], i) for i in range(1, n) if st[i][4] >= 8 and st[i][3] >= 6]
    lines = []
    for c in sorted(cs, key=lambda c: c[1]):
        cy = c[1] + c[3] / 2
        for L in lines:
            if abs(L["cy"] - cy) < L["h"] * 0.6:
                L["c"].append(c)
                break
        else:
            lines.append({"cy": cy, "h": c[3], "c": [c]})
    for L in sorted(lines, key=lambda L: L["cy"]):
        items = sorted(L["c"], key=lambda c: c[0])
        H = float(np.median([c[3] for c in items]))
        txt = ""
        for x, y, w, hh, i in items:
            if hh < 0.6 * H and w < 0.5 * H:
                txt += ","
                continue
            if w >= 0.95 * H and hh >= 0.95 * H:
                txt += "人"
                continue
            g = _norm_glyph(lab[y:y + hh, x:x + w] == i)
            best, score = "?", 0.5
            for k, r in GLYPHS.items():
                sc = (g & r).sum() / max(1, (g | r).sum())
                if sc > score:
                    best, score = k, sc
            txt += best
        mt = re.search(r"\+([\d,]{1,15})人", txt)
        if mt:
            return int(mt.group(1).replace(",", ""))
    return None


_TOPBAR = None


def topbar_refs():
    """顶部栏数字的参考字形（templates/topbar_digits.npz），含多种大小。"""
    global _TOPBAR
    if _TOPBAR is None:
        try:
            z = np.load(os.path.join(TPL_DIR, "topbar_digits.npz"))
            f = z["feats"].astype(np.float32).reshape(len(z["labels"]), -1)
            f /= np.linalg.norm(f, axis=1, keepdims=True) + 1e-6
            _TOPBAR = ([str(c) for c in z["labels"]], f)
        except Exception:
            _TOPBAR = False
    return _TOPBAR


def _digit_feat(gray, x, y, w, h, size=24):
    """用灰阶（保留抗锯齿细节）做特征，小字也分得清 5 和 6。"""
    crop = gray[max(0, y - 1):y + h + 1, max(0, x - 1):x + w + 1]
    d = crop.max() - crop
    d = d / max(1e-6, float(d.max()))
    hh, ww = d.shape
    nw = min(size, max(1, round(ww * size / hh)))
    g = cv2.resize(d, (nw, size), interpolation=cv2.INTER_AREA)
    c = np.zeros((size, size), np.float32)
    o = (size - nw) // 2
    c[:, o:o + nw] = g
    v = (c - c.mean()).flatten()
    return v / (np.linalg.norm(v) + 1e-6)


def read_jewels(img, icon, thr=0.8):
    """找到顶部栏的彩色萝卜图标，读取它右边的宝石数量。"""
    if icon is None or icon.shape[0] > img.shape[0] or icon.shape[1] > img.shape[1]:
        return None
    _, mx, _, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(img, icon, cv2.TM_CCOEFF_NORMED))
    if mx < thr:
        return None
    h, w = icon.shape[:2]
    roi = img[max(0, y - int(0.1 * h)):y + int(1.1 * h), x + w:min(img.shape[1], x + w + int(3.2 * w))]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 0] >= 3) & (hsv[..., 0] <= 25) & (hsv[..., 1] > 90)
         & (hsv[..., 2] < 170) & (hsv[..., 2] > 40)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    cs = [(st[i][0], st[i][1], st[i][2], st[i][3], i) for i in range(1, n) if st[i][4] >= 6 and st[i][3] >= 4]
    if not cs:
        return None
    H = max(c[3] for c in cs)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)
    refs = topbar_refs()
    txt = ""
    for X, Y, W, Hh, i in sorted(c for c in cs if c[3] >= 0.25 * H):
        if Hh < 0.6 * H and W < 0.6 * H:
            continue  # 逗号
        if refs:
            sims = refs[1] @ _digit_feat(gray, X, Y, W, Hh)
            k = int(np.argmax(sims))
            txt += refs[0][k] if sims[k] > 0.5 else "?"
            continue
        g = _norm_glyph(lab[Y:Y + Hh, X:X + W] == i)
        best, score = "?", 0.45
        for key, r in GLYPHS.items():
            if key == "+":
                continue
            sc = (g & r).sum() / max(1, (g | r).sum())
            if sc > score:
                best, score = key, sc
        txt += best
    return int(txt) if txt.isdigit() and len(txt) <= 9 else None


class FanStore:
    """粉丝记录，存在程序旁边的 fans.json。"""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.changed = True
        try:
            with open(path, encoding="utf-8") as f:
                self.records = json.load(f)
        except Exception:
            self.records = []

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=1)

    def add(self, gain=None, jewels=None):
        with self.lock:
            self.records.append({"t": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                 "gain": None if gain is None else int(gain),
                                 "jewels": None if jewels is None else int(jewels)})
            self._save()
            self.changed = True

    def remove(self, indexes):
        with self.lock:
            for i in sorted(indexes, reverse=True):
                if 0 <= i < len(self.records):
                    self.records.pop(i)
            self._save()
            self.changed = True

    @staticmethod
    def day_of(t, reset_hour):
        dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S") if isinstance(t, str) else t
        return (dt - timedelta(hours=reset_hour)).date()

    def daily(self, reset_hour):
        out = {}
        with self.lock:
            for r in self.records:
                d = self.day_of(r["t"], reset_hour)
                s, j, c = out.get(d, (0, 0, 0))
                out[d] = (s + (r.get("gain") or 0), j + (r.get("jewels") or 0), c + 1)
        return out


def fmt_fans(n):
    if n >= 100000000:
        return f"{n / 100000000:.2f}亿"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


# ================= 自动化线程 =================
class Bot(threading.Thread):
    def __init__(self, cfg, log, fans=None):
        super().__init__(daemon=True)
        self.fans = fans
        self.cfg = json.loads(json.dumps(cfg))
        self.log = log
        self.stop_evt = threading.Event()
        self.tpls = {}
        self.rect = None
        self.next_run = None
        self.paused = 0.0
        self.state_text = None
        self.last_box = {}
        self.launched_once = False
        self.next_label = "下次执行"
        self.uu_scale = None
        self.screen_scale = {}
        self.screen_best = {}
        self.screen_last = {}
        self.f = 1.0
        self.full = None
        self.last_small = None
        self.prep_h = None
        self.jewel_icon_full = None
        self.jewel_scale = None
        self.jewel_scan_at = 0.0
        self.jewel_best = 0.0
        self.jewel_prev = None
        self.cycles = 0
        self.story_count = 0
        self.scrolls = 0

    # ---- 基础 ----
    def wait(self, t):
        self.stop_evt.wait(t)

    def ensure_active(self):
        """游戏不在最前面时暂停，直到切回游戏（或开了自动切换）。"""
        hwnd = find_window(self.cfg["window_title"])
        if not hwnd:
            return None
        if is_foreground(hwnd):
            return hwnd
        if self.cfg.get("auto_focus"):
            force_foreground(hwnd)
            self.wait(0.5)
            if is_foreground(hwnd):
                return hwnd
        self.log("游戏窗口不在最前面，已暂停点击。切回游戏后会自动继续", "warn")
        self.state_text = "已暂停：请切回游戏"
        t0 = time.time()
        while not self.stop_evt.is_set():
            self.wait(1)
            hwnd = find_window(self.cfg["window_title"])
            if not hwnd:
                self.state_text = None
                return None
            if is_foreground(hwnd):
                self.paused += time.time() - t0
                self.state_text = None
                self.log("已切回游戏，继续执行", "ok")
                self.wait(0.8)
                return hwnd
        self.state_text = None
        return None

    def prepare(self, full_h):
        """按窗口高度准备模板：识别用缩小版，萝卜图标保留原尺寸版。"""
        self.f = min(1.0, WORK_H / full_h) if full_h else 1.0
        self.tpls = prepare_templates(round(full_h * self.f), self.cfg)
        self.jewel_icon_full = prepare_templates(full_h, self.cfg).get("flow_jewel")
        self.prep_h = full_h
        self.jewel_scale = None

    def capture(self):
        hwnd = self.ensure_active()
        if not hwnd:
            return None
        self.rect = client_rect(hwnd)
        full = grab(self.rect)
        self.full = full
        h, w = full.shape[:2]
        if h != self.prep_h:
            self.prepare(h)
        small = full if self.f == 1.0 else cv2.resize(full, (round(w * self.f), round(h * self.f)),
                                                     interpolation=cv2.INTER_AREA)
        self.last_small = small
        return small

    # 这些按钮一旦点错影响很大，不管设置里的严格度多低，至少要这么像
    MIN_THR = {"flow_auto_start": 0.85, "flow_ikusei_start": 0.85, "end_finish": 0.9}

    def find(self, img, key, thr=None):
        t = self.tpls.get(key)
        thr = max(thr or self.cfg["match_threshold"], self.MIN_THR.get(key, 0))
        pt, _ = match(img, t, thr)
        if pt is None:
            return None
        # 被弹窗盖住、变模糊的按钮不算（例如弹窗后面那个「自主训练养成开始！」）
        h, w = t.shape[:2]
        x0, y0 = pt[0] - w // 2, pt[1] - h // 2
        reg = img[max(0, y0):y0 + h, max(0, x0):x0 + w]
        if reg.shape[:2] == t.shape[:2]:
            lap = lambda a: cv2.Laplacian(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
            base = lap(t)
            if base > 1 and lap(reg) / base < 0.25:
                return None
        self.last_box[pt] = (w, h)
        return pt

    def click(self, pt, label):
        """pt 是缩小画面里的坐标。点完后等画面发生变化（最多 2.5 秒），不再死等固定时间。"""
        prev = self.last_small
        hwnd = self.ensure_active()
        if not hwnd or self.stop_evt.is_set():
            return
        self.rect = client_rect(hwnd)
        x, y, w, h = self.rect
        on = self.cfg.get("humanize", True)
        rp = rand_point(pt, self.last_box.get(pt), on)
        self.last_box.clear()
        px, py = int(rp[0] / self.f), int(rp[1] / self.f)
        if not (0 <= px < w and 0 <= py < h):
            px, py = int(pt[0] / self.f), int(pt[1] / self.f)
            if not (0 <= px < w and 0 <= py < h):
                return
        human_press(x + px, y + py, on)
        self.log(f"点击 {label}", "ok")
        changed = prev is None
        if prev is not None:
            t0 = time.time()
            while time.time() - t0 < 2.5 and not self.stop_evt.is_set():
                self.wait(0.12)
                cur = self.capture()
                if cur is None:
                    break
                if cur.shape == prev.shape and float(cv2.absdiff(cur, prev).mean()) > 3:
                    changed = True
                    break
        extra = random.uniform(0, 0.35) if self.cfg.get("humanize", True) else 0
        self.wait(self.cfg["delay"] + extra)
        return changed

    def run(self):
        try:
            self.main()
        except pyautogui.FailSafeException:
            self.log("鼠标移到了屏幕左上角，已紧急停止", "warn")
        except Exception as e:
            self.log(f"出错：{e!r}", "err")
        finally:
            self.next_run = None
            self.log("已停止")

    def main(self):
        mode = self.cfg["mode"]
        hwnd = find_window(self.cfg["window_title"])
        if self.cfg.get("_launch_test"):
            self.prepare(client_rect(hwnd)[3] if hwnd else 1080)
            if hwnd:
                self.close_game()
            if self.launch_game():
                self.log("测试成功：游戏已自动启动并进入主页", "ok")
            return
        if not hwnd:
            if mode == "auto_cycle" and self.cfg.get("auto_launch"):
                self.log("游戏现在没开，下一轮前会自动启动")
                self.prepare(1080)
            else:
                self.log("找不到游戏窗口。请确认游戏已打开，或到「设置」检查窗口标题", "err")
                return
        else:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            self.prepare(client_rect(hwnd)[3])
        custom = mode in self.cfg.get("custom_modes", {})
        missing = [k for k in mode_required(self.cfg, mode) if k not in self.tpls]
        if custom:
            order = mode_required(self.cfg, mode)
            if not order or len(missing) == len(order):
                self.log("这个模式还没有截好的步骤。请到「模板」页添加并截取", "err")
                return
            if missing:
                self.log("这些步骤还没截取，会先跳过：" + "、".join(step_name(k) for k in missing), "warn")
        elif missing:
            self.log("还缺这些模板：" + "、".join(missing) + "。请到「模板」页截取", "err")
            return
        self.log(f"开始运行：{mode_label(self.cfg, mode)}（已载入 {len(self.tpls)} 个模板）")
        btn_keys = sorted(k for k in self.tpls if k.startswith("btn_"))
        if mode == "auto_cycle":
            self.cycle_loop()
        elif custom:
            self.custom_loop(mode)
        else:
            self.story_loop(btn_keys)

    # ---- 定时重开自动育成 ----
    def countdown(self, minutes):
        return self.countdown_until(time.time() + minutes * 60)

    def countdown_until(self, end, what="执行"):
        if end <= time.time():
            return True
        self.next_run = end
        self.next_label = f"下次{what}"
        self.log(f"下次{what}时间 {time.strftime('%H:%M:%S', time.localtime(end))}")
        while not self.stop_evt.is_set():
            if time.time() >= end:
                self.next_run = None
                return True
            self.wait(min(end - time.time(), 1))
        return False

    STEPS = [
        ("flow_ok", "OK"),
        ("flow_decide", "决定"),
        ("flow_auto_start", "自主训练养成开始！"),
        ("end_confirm", "确定"),
        ("end_factor_ok", "确定因子"),
        ("end_finish", "结束育成"),
        ("end_finish_btn", "育成完成！"),
        ("end_again", "再次育成"),
        ("end_go", "前往育成"),
        ("__drink", ""),
        ("__jewel", ""),
        ("flow_tp_recover", "回复 TP"),
        ("flow_close", "关闭"),
        ("end_close", "关闭"),
        ("flow_ikusei_start", "育成开始！"),
        ("flow_next", "下项"),
        ("end_next", "下项"),
        ("end_next_b", "下项"),
        ("__running", ""),
        ("flow_home_running", "育成"),
        ("flow_home", "育成"),
    ]

    # 领奖画面的「下项」右边常盖着一个闪光圈，用只框左半边的模板、门槛放宽
    STEP_THR = {"end_next": 0.78, "end_next_b": 0.78, "end_finish": 0.9}
    # 只有前一步点过之后才可能出现的按钮：没育成时不会去点「结束」
    NEEDS = {"end_finish": "end_finish_btn", "end_factor_ok": "end_finish", "end_confirm": "end_factor_ok"}

    def find_drink_use(self, img):
        """找到「体力饮料(30)」那一行的「使用」按钮。"""
        return self.find_row_use(img, "flow_tp_drink")

    def find_row_use(self, img, title_key):
        """找到某个道具标题那一行的「使用」按钮。"""
        pt = self.find(img, title_key)
        if not pt:
            return None
        use = self.tpls.get("flow_tp_use")
        if use is None:
            return None
        rows = [p for p in match_all(img, use, self.cfg["match_threshold"])
                if p[0] > pt[0] and abs(p[1] - pt[1]) < use.shape[0] * 1.5]
        return min(rows, key=lambda p: abs(p[1] - pt[1])) if rows else None

    def read_fans(self):
        """数字出来后连续两次读到一样的值才算数。"""
        last = None
        for _ in range(12):
            img = self.capture()
            if img is None:
                return None
            val = read_fan_gain(self.full)
            if val is not None and val == last:
                return val
            last = val
            self.wait(0.5)
        return last

    def tap_blank(self):
        """有些动画画面要点一下才会继续。点游戏画面中间偏下的空白处。"""
        _, _, w, h = self.rect
        self.click((int(w * self.f * 0.28), int(h * self.f * 0.6)), "画面（继续）")

    JEWEL_SCALES = (1.0, 0.95, 1.05, 0.9, 1.1, 0.85, 1.15, 0.8, 1.2, 0.75, 1.25, 0.7, 1.3, 0.65, 1.35)

    def jewel_read(self, img):
        """读取宝石数量。图标大小对不上时会自动试不同缩放，找到后记住。"""
        base = self.jewel_icon_full
        if base is None:
            return None
        if self.jewel_scale:
            scales = [self.jewel_scale]
        elif time.time() - self.jewel_scan_at > 6:
            self.jewel_scan_at = time.time()
            scales = self.JEWEL_SCALES
        else:
            return None
        cands = []
        for sc in scales:
            ic = base if sc == 1.0 else cv2.resize(base, (max(1, round(base.shape[1] * sc)), max(1, round(base.shape[0] * sc))),
                                                  interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_LINEAR)
            if ic.shape[0] > img.shape[0] or ic.shape[1] > img.shape[1]:
                continue
            score = float(cv2.matchTemplate(img, ic, cv2.TM_CCOEFF_NORMED).max())
            self.jewel_best = max(self.jewel_best, score)
            cands.append((score, sc, ic))
        for score, sc, ic in sorted(cands, key=lambda c: -c[0])[:3]:  # 先试最像的缩放
            val = read_jewels(img, ic, 0.75)
            if val is not None:
                self.jewel_scale = sc
                return val
        return None

    def track_jewels(self, img, after):
        """连续两次读到相同数字才采用。after=False 记为本轮开始前，True 记为结束后。"""
        v = self.jewel_read(self.full if self.full is not None else img)
        if v is None:
            self.jewel_prev = None
            return
        if v == self.jewel_prev:
            r = self.result
            if not after and r["jewels_before"] is None:
                r["jewels_before"] = v
                self.log(f"开始前宝石：{v:,}")
            elif after:
                r["jewels_after"] = v
        self.jewel_prev = v

    def read_jewels_stable(self):
        for _ in range(6):
            img = self.capture()
            if img is None:
                return
            self.track_jewels(img, True)
            if self.result["jewels_after"] is not None and self.jewel_prev == self.result["jewels_after"]:
                return
            self.wait(0.5)

    def clear_desktop(self, hwnd=None):
        if not self.cfg.get("minimize_others", True):
            return
        hwnd = hwnd or find_window(self.cfg["window_title"])
        if not hwnd:
            return
        n = minimize_other_windows(hwnd)
        if n:
            self.log(f"已把其他 {n} 个窗口最小化，只留游戏")
        force_foreground(hwnd)
        self.wait(0.5)

    def restart_auto(self):
        self.clear_desktop()
        self.result = {"gain": None, "jewels_before": None, "jewels_after": None}
        self.jewel_prev = None
        self.jewel_best = 0.0
        try:
            return self._restart_auto()
        finally:
            r = self.result
            jewels = None
            st = load_state()
            if r["jewels_before"] is None and st.get("jewels") is not None:
                r["jewels_before"] = st["jewels"]
                self.log(f"本轮开始前没读到宝石，改用上一轮结束时的 {st['jewels']:,}")
            if r["jewels_before"] is not None and r["jewels_after"] is not None:
                jewels = r["jewels_after"] - r["jewels_before"]
                if abs(jewels) > 3000:
                    self.log(f"宝石变化 {jewels:+,} 不太合理，可能读错数字，这轮不记录宝石", "warn")
                    jewels = None
                    r["jewels_after"] = None
                else:
                    self.log(f"本轮宝石（彩色萝卜）{r['jewels_before']:,} → {r['jewels_after']:,}，增加 {jewels:+,}", "ok")
            elif self.stop_evt.is_set():
                pass  # 手动停止，不提示
            elif "flow_jewel" in self.tpls:
                miss = "开始前" if r["jewels_before"] is None else "结束后"
                self.log(f"这轮没算出宝石：{miss}没读到数字（图标最高相似度 {self.jewel_best:.2f}）。"
                         f"可在「模板」页重截 flow_jewel，只框萝卜图标", "warn")
            if r["jewels_after"] is not None:
                st["jewels"] = r["jewels_after"]
                st["jewels_t"] = datetime.now().strftime("%H:%M")
                day = FanStore.day_of(datetime.now(), self.cfg.get("fan_reset_hour", 0)).isoformat()
                log = st.setdefault("jewel_log", {})
                if day not in log:
                    first = r["jewels_before"] if r["jewels_before"] is not None else r["jewels_after"]
                    log[day] = {"n": int(first), "manual": False}
                save_state(st)
            if (r["gain"] is not None or jewels is not None) and self.fans:
                self.fans.add(r["gain"], jewels)

    def _restart_auto(self):
        timeout = self.cfg["cycle_timeout"]
        deadline = time.time() + timeout
        self.paused = 0.0
        start_activity = False
        started = False
        drinks = 0
        jewel_uses = 0
        clicked = set()       # 这一轮点过的按钮
        jewel_seen = 0
        banned = {}           # 点了没反应的按钮 → 暂停到这个时间
        last_key, same_cnt = None, 0
        no_drink = False
        fans_done = False
        rewards_passed = False
        first = True
        idle = 0
        waiting_logged = False
        user_keys = [k for k in sorted(self.tpls) if k.startswith(("auto_", "btn_"))]
        while not self.stop_evt.is_set():
            if time.time() > deadline + self.paused:
                self.log("超时：流程卡住了。可以用「测试识别」看看是哪个画面认不出", "warn")
                return False
            img = self.capture()
            if img is None:
                self.log("游戏窗口不见了", "err")
                return False

            # 宝石：领奖之前看到的算「开始前」，领奖之后看到的算「结束后」
            if "flow_jewel" in self.tpls:
                self.track_jewels(img, rewards_passed)
            if first:
                first = False
                self.wait(0.5)
                continue

            # 获得奖励画面：记录本次粉丝数
            if not fans_done and "end_fans" in self.tpls and self.find(img, "end_fans"):
                fans_done = True
                rewards_passed = True
                gain = self.read_fans()
                if gain is not None:
                    self.result["gain"] = gain
                    self.log(f"本次育成获得粉丝 +{gain:,}", "ok")
                else:
                    self.log("没读到这次的粉丝数，可以到「粉丝统计」页手动补记", "warn")
                continue

            # 已经按下开始：回主页即完成
            if started:
                if self.find(img, "flow_home_running") or self.find(img, "flow_home"):
                    if "flow_jewel" in self.tpls:
                        self.wait(1)
                        self.read_jewels_stable()
                    return True
                for key, label, thr in (("flow_ok", "OK", None), ("flow_menu_home", "返回主页", 0.8),
                                        ("flow_menu", "菜单", 0.8)):
                    pt = self.find(img, key, thr)
                    if pt:
                        self.click(pt, label)
                        break
                else:
                    self.wait(0.4)
                continue

            acted = False
            for key, label in self.STEPS + [(k, k) for k in user_keys]:
                if key == "__drink":
                    pt = None if no_drink else self.find_drink_use(img)
                    if pt:
                        if drinks >= self.cfg["tp_max_drinks"]:
                            self.log(f"这一轮已经喝了 {drinks} 瓶，达到上限，先停在这里", "warn")
                            return False
                        drinks += 1
                        if not self.click(pt, f"使用体力饮料（本轮第 {drinks} 瓶）"):
                            no_drink = True  # 点了没反应：饮料用完、按钮变灰
                            drinks -= 1
                            self.log("体力饮料好像用完了", "warn")
                        acted = True
                        break
                    continue
                if key == "__jewel":
                    # 必须真的在 TP 回复清单：宝石那一行很清楚、旁边有「使用」，而且饮料确实用完（点了没反应）
                    # 或饮料那一行完全不像（不是只差一点没认到），并且连续 3 次都这样
                    in_list = (self.find(img, "flow_tp_jewel", 0.9) and self.find_row_use(img, "flow_tp_jewel"))
                    drink_score = match(img, self.tpls.get("flow_tp_drink"), 0.99)[1]
                    if in_list and (no_drink or drink_score < 0.6):
                        jewel_seen += 1
                    else:
                        jewel_seen = 0
                    if 0 < jewel_seen < 3:  # 再看几次确认，先别去点「关闭」
                        self.wait(0.4)
                        acted = True
                        break
                    if jewel_seen >= 3:
                        if not self.cfg.get("tp_use_jewel"):
                            self.log("体力饮料用完了，而且没开「饮料用完时用宝石回复」，先停在这里", "warn")
                            return False
                        if jewel_uses >= self.cfg.get("tp_max_jewel", 1):
                            self.log(f"这一轮已经用宝石回复 {jewel_uses} 次，达到上限，先停在这里", "warn")
                            return False
                        pt = self.find_row_use(img, "flow_tp_jewel")
                        if pt:
                            jewel_uses += 1
                            self.click(pt, f"用宝石回复 TP（本轮第 {jewel_uses} 次）")
                            acted = True
                            break
                    continue
                if key == "__running":
                    if self.find(img, "flow_running", 0.8):
                        if start_activity:
                            started = True
                            acted = True
                            break
                        if not waiting_logged:
                            self.log("自动育成还没结束，等它跑完")
                            waiting_logged = True
                        deadline = time.time() + timeout - self.paused
                        self.wait(10)
                        acted = True
                        break
                    continue
                if banned.get(key, 0) > time.time():
                    continue
                need = self.NEEDS.get(key)
                if need and need not in clicked:
                    continue
                pt = self.find(img, key, self.STEP_THR.get(key))
                if not pt:
                    continue
                if key == "flow_tp_recover" and not self.cfg["tp_auto_drink"]:
                    self.log("TP 不足，而且没开「自动喝体力饮料」，先停在这里", "warn")
                    return False
                changed = self.click(pt, label)
                clicked.add(key)
                # 同一个按钮连点 3 次画面都没变：多半是认错了，先跳过它 60 秒
                if key == last_key and not changed:
                    same_cnt += 1
                else:
                    same_cnt = 0 if changed else 1
                last_key = key
                if same_cnt >= 3:
                    banned[key] = time.time() + 60
                    same_cnt = 0
                    self.log(f"「{label}」连点 3 次画面都没反应，可能认错了，先跳过它", "warn")
                if key == "flow_auto_start":
                    started = True
                if key in ("flow_ikusei_start", "flow_auto_start", "flow_decide"):
                    start_activity = True
                if key in ("end_finish", "end_factor_ok", "end_confirm", "end_again", "flow_next") and fans_done:
                    rewards_passed = True
                if key in ("end_again", "end_finish"):
                    rewards_passed = rewards_passed or key == "end_again"
                acted = True
                break

            if acted:
                idle = 0
                continue
            idle += 1
            if idle == 25:  # 约 10 秒都没东西可点，记录最像的几个按钮方便排查
                scores = sorted(((match(img, t, 0.99)[1], k) for k, t in self.tpls.items()), reverse=True)[:3]
                self.log("卡住约 10 秒，画面上认不出可点的按钮。最接近的："
                         + "、".join(f"{k} {v:.2f}" for v, k in scores), "warn")
            self.wait(0.4)
        return False

    def cycle_loop(self):
        auto = self.cfg.get("auto_launch")
        while not self.stop_evt.is_set():
            first = self.cycles == 0
            if not (first and self.cfg["cycle_run_now"]):
                target = time.time() + self.cfg["cycle_minutes"] * 60
                if auto and not find_window(self.cfg["window_title"]):
                    lead = max(1, self.cfg.get("launch_lead", 5)) * 60
                    if not self.countdown_until(target - lead, "启动游戏"):
                        return
                    self.launch_game()
                if not self.countdown_until(target):
                    return
            elif auto and not find_window(self.cfg["window_title"]):
                self.launch_game()
            self.cycles += 1
            self.log(f"第 {self.cycles} 次：结束并重开自动育成")
            ok = self.restart_auto()
            if ok:
                self.log("新的自动育成已开始，已回到主页", "ok")
            elif not self.stop_evt.is_set():
                self.save_debug_shot()
                self.log("这次没重开成功，游戏先不关，下个周期再试", "warn")
            if ok and auto and not self.stop_evt.is_set() and find_window(self.cfg["window_title"]):
                self.close_game()

    def save_debug_shot(self):
        """出错时把当前游戏画面存到 debug 文件夹，反馈问题时一起附上。"""
        try:
            if self.full is None:
                return
            d = os.path.join(BASE, "debug")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, time.strftime("%Y%m%d_%H%M%S") + ".png")
            ok, buf = cv2.imencode(".png", self.full)
            if ok:
                buf.tofile(p)
                self.log(f"已保存出错时的画面：debug\\{os.path.basename(p)}")
        except Exception:
            pass

    # ---- 自动启动 / 关闭游戏 ----
    SCREEN_SCALES = [1.0, 0.9, 1.1, 0.8, 1.25, 0.75, 1.33, 1.5, 0.67, 1.75, 2.0]

    def find_on_screen(self, key, thr=0.75):
        """在整个桌面找加速器的按钮。每个按钮各自记住合适的缩放；先在半尺寸画面上找，速度快很多。"""
        path = tpl_path(key)
        tpl = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR) if os.path.exists(path) else None
        if tpl is None:
            return None
        img, left, top = grab_screen()
        img = img.copy()
        for h_ in own_windows():
            try:
                l, t_, r, b = win32gui.GetWindowRect(h_)
                img[max(0, t_ - top):max(0, b - top), max(0, l - left):max(0, r - left)] = 0
            except Exception:
                pass
        small = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        known = self.screen_scale.get(key)
        scales = [known] if known else self.SCREEN_SCALES
        best = None
        for sc in scales:
            f = sc * 0.5
            t = cv2.resize(tpl, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
            if t.shape[0] < 8 or t.shape[1] < 8 or t.shape[0] > small.shape[0] or t.shape[1] > small.shape[1]:
                continue
            _, mx, _, loc = cv2.minMaxLoc(cv2.matchTemplate(small, t, cv2.TM_CCOEFF_NORMED))
            if best is None or mx > best[0]:
                best = (mx, sc, loc, t.shape)
        if best is None:
            return None
        self.screen_best[key] = max(self.screen_best.get(key, 0), best[0])
        self.screen_last[key] = best[0]
        if best[0] < thr:
            if known:  # 记住的缩放不灵了（窗口大小变了），下次重新试
                self.screen_scale.pop(key, None)
            return None
        self.screen_scale[key] = best[1]
        self.uu_scale = best[1]
        (x, y), (h, w) = best[2], best[3][:2]
        pt = left + (x + w // 2) * 2, top + (y + h // 2) * 2
        self.last_box[pt] = (w * 2, h * 2)
        return pt

    def click_screen(self, pt, label):
        on = self.cfg.get("humanize", True)
        rp = rand_point(pt, self.last_box.get(pt), on)
        self.last_box.clear()
        human_press(rp[0], rp[1], on)
        self.log(f"点击 {label}", "ok")

    def launch_by_steps(self, steps):
        """自己设定的加速器按钮：按顺序找到就点，每一步最多等 60 秒。"""
        for n, key in enumerate(steps, 1):
            end = time.time() + 60
            while not self.stop_evt.is_set():
                pt = self.find_on_screen(key)
                if pt:
                    self.click_screen(pt, f"加速器第 {n} 步：{key[4:]}")
                    self.wait(3)
                    break
                if time.time() > end:
                    self.log(f"加速器里等了 60 秒都没看到「{key[4:]}」（最高相似度 {self.screen_best.get(key, 0):.2f}）。"
                             f"可到「模板」页重截", "warn")
                    return False
                self.wait(1.5)
        return not self.stop_evt.is_set()

    def wait_game_started(self, secs):
        """点了启动后，看游戏有没有真的开始启动（游戏窗口或游戏程序出现）。"""
        end = time.time() + secs
        while time.time() < end and not self.stop_evt.is_set():
            if find_window(self.cfg["window_title"]) or process_running("umamusume.exe"):
                return True
            self.wait(2)
        return False

    def save_click_shot(self, pt, name):
        """把这次点击的位置画在截图上存到 debug 文件夹，方便确认到底点到哪里。"""
        try:
            img, left, top = grab_screen()
            img = img.copy()
            x, y = pt[0] - left, pt[1] - top
            cv2.circle(img, (x, y), 18, (0, 0, 255), 4)
            cv2.line(img, (x - 30, y), (x + 30, y), (0, 0, 255), 2)
            cv2.line(img, (x, y - 30), (x, y + 30), (0, 0, 255), 2)
            d = os.path.join(BASE, "debug")
            os.makedirs(d, exist_ok=True)
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                buf.tofile(os.path.join(d, f"click_{name}_{time.strftime('%H%M%S')}.jpg"))
        except Exception:
            pass

    def launch_by_uu(self):
        """UU 加速器：点封面开始加速，再点「启动游戏」。"""
        deadline = time.time() + 240
        last_report = time.time()
        tile_at = 0.0   # 上次点封面的时间
        start_clicks = 0
        while time.time() < deadline and not self.stop_evt.is_set():
            pt = self.find_on_screen("uu_start", thr=0.88)
            if pt and not tile_at and self.screen_last.get("uu_start", 0) < 0.93:
                pt = None  # 还没点封面加速，又不是非常像：多半认错了
            if pt:
                # 详情页刚滑进来、加速刚连上时按钮可能还没反应：先等一下再确认位置
                self.wait(2)
                pt = self.find_on_screen("uu_start", thr=0.88) or pt
                start_clicks += 1
                self.click_screen(pt, f"UU：启动游戏（第 {start_clicks} 次）")
                self.save_click_shot(pt, "uu_start")
                self.state_text = "等 DMM 启动游戏…"
                if self.wait_game_started(45):
                    self.log("游戏已开始启动", "ok")
                    return True
                if start_clicks >= 3:
                    self.log("点了 3 次「启动游戏」游戏都没开。debug 文件夹里有点击位置的截图，可以发给作者看", "warn")
                    return False
                self.log("点了「启动游戏」45 秒都没看到游戏启动，再点一次", "warn")
                continue
            # 点了封面后 UU 要转圈加速几秒，期间封面还在，不能再点（再点会取消加速）
            if time.time() - tile_at < 25:
                self.state_text = "UU 正在加速，等「启动游戏」出现…"
                self.wait(1)
                continue
            pt = self.find_on_screen("uu_tile")
            if pt:
                t = cv2.imdecode(np.fromfile(tpl_path("uu_tile"), np.uint8), cv2.IMREAD_COLOR)
                if t is not None and t.shape[1] > t.shape[0] * 3:
                    # 截的是「赛马娘Pretty Derby」文字：点它正上方的封面图（约 165 像素 × 缩放）
                    pt = (pt[0], pt[1] - int(165 * self.screen_scale.get("uu_tile", 1.0)))
                self.click_screen(pt, "UU：赛马娘封面（立即加速）")
                tile_at = time.time()
                self.wait(3)
                continue
            if time.time() > last_report + 15:
                last_report = time.time()
                self.log("还在找加速器里的按钮（最像的：" + "、".join(
                    f"{k} {v:.2f}" for k, v in self.screen_best.items()) + "）。确认加速器窗口没被挡住", "warn")
            self.wait(1)
        if not self.stop_evt.is_set():
            self.log("UU 加速器里找不到「启动游戏」。不是用 UU 的话，请到「模板」页把你加速器的按钮按顺序加到"
                     "「自动启动：加速器按钮」", "warn")
        return False

    def launch_game(self):
        """打开加速器 → 依序点按钮（加速、启动游戏）→ 等游戏窗口 → 进入主页。"""
        path = self.cfg.get("uu_path", "")
        game = self.cfg.get("game_path", "")
        has_game = bool(game) and os.path.exists(game)
        acc_exe = os.path.basename(shortcut_target(path)) if path else ""
        if self.cfg.get("dmm_only"):
            if not has_game:
                self.log("开了「不开加速器，直接用 DMM 快捷方式」但还没选快捷方式的位置。请到「设置」页选择", "err")
                return False
            self.state_text = "正在启动游戏…"
            self.log("直接用 DMM 快捷方式打开游戏（不开加速器）")
            try:
                os.startfile(game)
            except OSError as e:
                self.log(f"打开 DMM 快捷方式失败：{e}", "err")
                self.state_text = None
                return False
        # 第一次：从加速器点「启动游戏」；之后：加速器还开着就直接打开 DMM 快捷方式
        elif self.launched_once and has_game and (not acc_exe.lower().endswith(".exe") or process_running(acc_exe)):
            self.state_text = "正在启动游戏…"
            self.log("再次启动：直接用 DMM 快捷方式打开游戏")
            try:
                os.startfile(game)
            except OSError as e:
                self.log(f"打开 DMM 快捷方式失败：{e}", "err")
                self.state_text = None
                return False
        else:
            if self.launched_once and has_game:
                self.log("加速器好像已经关了，这次重新从加速器启动", "warn")
            if not path or not os.path.exists(path):
                self.log("没有设置加速器的位置，无法自动启动。请到「设置」页选择", "err")
                return False
            self.log("自动启动游戏：打开加速器")
            self.state_text = "正在启动游戏…"
            try:
                os.startfile(path)
            except OSError as e:
                self.log(f"打开加速器失败：{e}", "err")
                self.state_text = None
                return False
            self.wait(3)
            steps = [k for k in self.cfg.get("acc_order", []) if os.path.exists(tpl_path(k))]
            is_uu = "uu" in acc_exe.lower() and os.path.exists(tpl_path("uu_tile")) and os.path.exists(tpl_path("uu_start"))
            ok = self.launch_by_uu() if (is_uu or not steps) else self.launch_by_steps(steps)
            if not ok:
                self.state_text = None
                return False
            self.launched_once = True

        # 等游戏窗口出现（DMM 会自己启动游戏）
        end = time.time() + 180
        hwnd = None
        while time.time() < end and not self.stop_evt.is_set():
            hwnd = find_window(self.cfg["window_title"])
            if hwnd:
                break
            self.wait(2)
        if not hwnd:
            self.state_text = None
            if not self.stop_evt.is_set():
                self.log("等了 3 分钟游戏窗口都没出现", "warn")
            return False
        self.log("游戏窗口已出现，等待进入主页")
        self.wait(5)
        self.clear_desktop(hwnd)
        force_foreground(hwnd)
        old = self.cfg.get("auto_focus")
        self.cfg["auto_focus"] = True  # 启动阶段没人看着，允许自动切到游戏
        try:
            ok = self.enter_home()
        finally:
            self.cfg["auto_focus"] = old
        self.state_text = None
        return ok

    def enter_home(self):
        """标题画面需要点一下才进游戏；公告、登录奖励用关闭/确定类按钮处理。"""
        end = time.time() + max(1, self.cfg.get("launch_wait", 5)) * 60
        keys = ["flow_close", "end_close", "flow_ok", "flow_decide"] + \
               [k for k in sorted(self.tpls) if k.startswith(("btn_", "boot_"))]
        last_tap = 0.0
        while time.time() < end and not self.stop_evt.is_set():
            hwnd = find_window(self.cfg["window_title"])
            if not hwnd:
                self.wait(2)
                continue
            if not is_foreground(hwnd):
                force_foreground(hwnd)
            img = self.capture()
            if img is None:
                self.wait(2)
                continue
            if self.find(img, "flow_home") or self.find(img, "flow_home_running"):
                self.log("已进入主页", "ok")
                return True
            for k in keys:
                pt = self.find(img, k)
                if pt:
                    self.click(pt, k)
                    break
            else:
                if time.time() - last_tap > 4:  # 只在启动阶段：点标题画面中间进入游戏
                    last_tap = time.time()
                    _, _, w, h = self.rect
                    self.click((int(w * self.f * 0.3), int(h * self.f * 0.55)), "标题画面")
                else:
                    self.wait(1)
        if not self.stop_evt.is_set():
            self.log("启动后一直没进入主页，可能卡在没见过的画面。可新增 boot_ 开头的模板", "warn")
        return False

    def close_game(self):
        """先正常关闭游戏窗口，关不掉再强制结束。"""
        hwnd = find_window(self.cfg["window_title"])
        if not hwnd:
            return
        self.log("本轮完成，关闭游戏，下一轮前再自动启动")
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = None
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
        for _ in range(15):
            self.wait(1)
            if not find_window(self.cfg["window_title"]):
                return
        if pid:
            try:
                h = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                win32api.TerminateProcess(h, 0)
                win32api.CloseHandle(h)
                self.log("游戏没有响应关闭，已强制结束")
            except Exception as e:
                self.log(f"关闭游戏失败：{e}", "warn")

    # ---- 自定义模式 ----
    def custom_loop(self, mode):
        m = self.cfg["custom_modes"][mode]
        while not self.stop_evt.is_set():
            self.run_custom_once(m)
            rep = int(m.get("repeat_min", 0) or 0)
            if not rep or self.stop_evt.is_set():
                break
            if not self.countdown(rep):
                break

    def run_custom_once(self, m):
        steps = [k for k in m.get("order", []) if k in self.tpls]
        finish = m.get("finish") or ""
        idle_stop = max(3, int(m.get("idle_stop", 30) or 30))
        self.log(f"执行「{m['name']}」：共 {len(steps)} 个步骤，{idle_stop} 秒没东西可点就结束")
        last_act = time.time()
        clicks = 0
        while not self.stop_evt.is_set():
            img = self.capture()
            if img is None:
                self.log("游戏窗口不见了", "err")
                return
            if finish and finish in self.tpls and self.find(img, finish):
                self.log(f"看到完成标志「{step_name(finish)}」，本次结束（共点击 {clicks} 次）", "ok")
                return
            for k in steps:
                if k == finish:
                    continue
                pt = self.find(img, k)
                if pt:
                    self.click(pt, step_name(k))
                    clicks += 1
                    last_act = time.time()
                    break
            else:
                if time.time() - last_act > idle_stop:
                    self.log(f"{idle_stop} 秒没有可点的按钮，本次结束（共点击 {clicks} 次）", "ok")
                    return
                self.wait(0.4)

    # ---- 剧情跳过 ----
    def drag_list(self):
        hwnd = self.ensure_active()
        if not hwnd or self.stop_evt.is_set():
            return
        self.rect = client_rect(hwnd)
        x, y, w, h = self.rect
        cx = x + w // 2
        pyautogui.moveTo(cx, y + int(h * 0.7))
        pyautogui.mouseDown()
        pyautogui.moveTo(cx, y + int(h * 0.35), duration=0.4)
        time.sleep(0.2)
        pyautogui.mouseUp()
        self.log(f"往下滚动找未读剧情（{self.scrolls}/{self.cfg['story_max_scroll']}）")
        self.wait(self.cfg["delay"])

    def find_new(self, img):
        region = self.cfg.get("story_new_region")
        if not region:
            return self.find(img, "story_new")
        x, y, w, h = (round(v * self.f) for v in region)
        pts = match_all(img[y:y + h, x:x + w], self.tpls.get("story_new"), self.cfg["match_threshold"])
        return (pts[0][0] + x, pts[0][1] + y) if pts else None

    def step_story(self, img, btn_keys):
        for key, label in (("story_skip_confirm", "确认跳过"), ("story_skip", "跳过剧情")):
            pt = self.find(img, key)
            if pt:
                self.click(pt, label)
                return True
        for key in btn_keys:
            pt = self.find(img, key)
            if pt:
                self.click(pt, key)
                return True
        if self.find(img, "story_list"):
            pt = self.find_new(img)
            if pt:
                mx = self.cfg.get("story_max_episodes", 0)
                if mx and self.story_count >= mx:
                    self.log(f"已经看了 {mx} 话，达到设定上限", "ok")
                    return "end"
                self.story_count += 1
                self.scrolls = 0
                self.click(pt, f"未读剧情（本次第 {self.story_count} 话）")
                return True
            if self.scrolls >= self.cfg.get("story_max_scroll", 5):
                self.log(f"没有更多未读剧情了，本次共看了 {self.story_count} 话", "ok")
                return "end"
            self.scrolls += 1
            self.drag_list()
            return True
        return False

    def story_loop(self, btn_keys):
        idle = 0
        while not self.stop_evt.is_set():
            img = self.capture()
            if img is None:
                self.log("游戏窗口不见了", "err")
                return
            r = self.step_story(img, btn_keys)
            if r == "end":
                return
            idle = 0 if r else idle + 1
            if idle and idle % 15 == 0:
                self.log("一直认不出当前画面。可用「模板」页的「测试识别」检查，或补截这个画面的按钮", "warn")
            self.wait(0.3)


# ================= 框选窗口 =================
class RegionSelector(tk.Toplevel):
    def __init__(self, master, img_bgr, title, callback):
        super().__init__(master)
        self.title(title)
        self.callback = callback
        h, w = img_bgr.shape[:2]
        self.scale = min(1.0, self.winfo_screenheight() * 0.82 / h, self.winfo_screenwidth() * 0.85 / w)
        disp = cv2.resize(img_bgr, (int(w * self.scale), int(h * self.scale)))
        self.photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)))
        tb.Label(self, text="按住鼠标左键拖框，松开即保存。按 Esc 取消",
                 bootstyle="inverse-dark", padding=(10, 6), font=(FONT, 10)).pack(fill=X)
        self.cv = tk.Canvas(self, width=disp.shape[1], height=disp.shape[0], cursor="cross", highlightthickness=0)
        self.cv.pack()
        self.cv.create_image(0, 0, anchor="nw", image=self.photo)
        self.start = None
        self.rect_id = None
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.focus_force()

    def on_press(self, e):
        self.start = (e.x, e.y)
        if self.rect_id:
            self.cv.delete(self.rect_id)
        self.rect_id = self.cv.create_rectangle(e.x, e.y, e.x, e.y, outline="#ffcc33", width=3)

    def on_drag(self, e):
        if self.start:
            self.cv.coords(self.rect_id, *self.start, e.x, e.y)

    def on_release(self, e):
        if not self.start:
            return
        x0, x1 = sorted((self.start[0], e.x))
        y0, y1 = sorted((self.start[1], e.y))
        if x1 - x0 < 5 or y1 - y0 < 5:
            return
        s = self.scale
        region = (int(x0 / s), int(y0 / s), int((x1 - x0) / s), int((y1 - y0) / s))
        self.destroy()
        self.callback(region)


# ================= 自定义模式编辑窗口 =================
class ModeEditor(tk.Toplevel):
    def __init__(self, app, mid, m, new=False):
        super().__init__(app.root)
        self.app, self.mid, self.new = app, mid, new
        self.order = list(m.get("order", []))
        self.title("新建模式" if new else f"编辑模式：{m['name']}")
        self.v_name = tk.StringVar(value=m["name"])
        self.v_idle = tk.IntVar(value=int(m.get("idle_stop", 30)))
        self.v_rep = tk.IntVar(value=int(m.get("repeat_min", 0)))
        self.v_finish = tk.StringVar()
        f = tb.Frame(self, padding=16)
        f.pack(fill=BOTH, expand=True)
        app.row(f, "模式名称", lambda p: tb.Entry(p, textvariable=self.v_name, width=22))
        app.row(f, "多少秒没东西可点就结束本次",
                lambda p: tb.Spinbox(p, from_=3, to=3600, textvariable=self.v_idle, width=7))
        app.row(f, "每隔几分钟重复（0 为只执行一次）",
                lambda p: tb.Spinbox(p, from_=0, to=1440, textvariable=self.v_rep, width=7))
        tb.Label(f, text="步骤顺序（越上面越优先；步骤在「模板」页添加和截取）").pack(anchor=W, pady=(12, 4))
        lf = tb.Frame(f)
        lf.pack(fill=BOTH, expand=True)
        self.lb = tk.Listbox(lf, height=8, font=(FONT, 10), activestyle="none")
        self.lb.pack(side=LEFT, fill=BOTH, expand=True)
        bf = tb.Frame(lf)
        bf.pack(side=LEFT, padx=(8, 0), fill=Y)
        tb.Button(bf, text="上移", bootstyle="secondary-outline", command=lambda: self.move(-1)).pack(fill=X)
        tb.Button(bf, text="下移", bootstyle="secondary-outline", command=lambda: self.move(1)).pack(fill=X, pady=6)
        fr = tb.Frame(f)
        fr.pack(fill=X, pady=(12, 0))
        tb.Label(fr, text="完成标志（看到就结束）").pack(side=LEFT)
        self.cmb = tb.Combobox(fr, textvariable=self.v_finish, state="readonly", width=18)
        self.cmb.pack(side=RIGHT)
        self.fill(m.get("finish", ""))
        btns = tb.Frame(f)
        btns.pack(fill=X, pady=(16, 0))
        tb.Button(btns, text="保存", bootstyle="success", command=self.save).pack(side=RIGHT)
        tb.Button(btns, text="取消", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=8)
        self.grab_set()

    def fill(self, finish=None):
        sel = self.lb.curselection()
        self.lb.delete(0, "end")
        for n, k in enumerate(self.order, 1):
            ok = "✓" if os.path.exists(tpl_path(k)) else "✗ 未截取"
            self.lb.insert("end", f"{n}. {step_name(k)}   {ok}")
        if sel:
            self.lb.selection_set(sel[0])
        names = ["（无）"] + [step_name(k) for k in self.order]
        self.cmb.configure(values=names)
        if finish is not None:
            self.v_finish.set(step_name(finish) if finish in self.order else "（无）")

    def move(self, d):
        sel = self.lb.curselection()
        if not sel:
            return
        i, j = sel[0], sel[0] + d
        if 0 <= j < len(self.order):
            self.order[i], self.order[j] = self.order[j], self.order[i]
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(i)
            self.fill()
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(j)

    def save(self):
        name = self.v_name.get().strip()
        if not name:
            messagebox.showerror(APP_NAME, "请输入模式名称", parent=self)
            return
        try:
            idle, rep = int(self.v_idle.get()), int(self.v_rep.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_NAME, "秒数和分钟数要填数字", parent=self)
            return
        fin = self.v_finish.get()
        finish = next((k for k in self.order if step_name(k) == fin), "")
        cfg = self.app.cfg
        cfg.setdefault("custom_modes", {})[self.mid] = {
            "name": name, "order": self.order, "idle_stop": idle, "repeat_min": rep, "finish": finish}
        if self.new:
            cfg["mode"] = self.mid
            self.app.v_mode.set(self.mid)
        save_cfg(cfg)
        self.destroy()
        self.app.modes_changed()
        if self.new:
            self.app.v_prefix.set(f"模式：{name}")
            self.app.log(f"已建立模式「{name}」。到「模板」页在底部选「模式：{name}」添加步骤并截取", "ok")


# ================= 主界面 =================
class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_cfg()
        self.log_q = queue.Queue()
        self.bot = None
        self.fans = FanStore(FANS_PATH)

        self.v_mode = tk.StringVar(value=self.cfg["mode"])
        self.v_cycle_min = tk.IntVar(value=self.cfg["cycle_minutes"])
        self.v_cycle_timeout = tk.IntVar(value=self.cfg["cycle_timeout"])
        self.v_cycle_now = tk.BooleanVar(value=self.cfg["cycle_run_now"])
        self.v_tp_drink = tk.BooleanVar(value=self.cfg["tp_auto_drink"])
        self.v_tp_max = tk.IntVar(value=self.cfg["tp_max_drinks"])
        self.v_tp_jewel = tk.BooleanVar(value=self.cfg.get("tp_use_jewel", False))
        self.v_tp_jewel_max = tk.IntVar(value=self.cfg.get("tp_max_jewel", 1))
        self.v_story_max = tk.IntVar(value=self.cfg["story_max_episodes"])
        self.v_story_scroll = tk.IntVar(value=self.cfg["story_max_scroll"])
        self.v_title = tk.StringVar(value=self.cfg["window_title"])
        self.v_thr = tk.DoubleVar(value=self.cfg["match_threshold"])
        self.v_delay = tk.DoubleVar(value=self.cfg["delay"])
        self.v_auto_focus = tk.BooleanVar(value=self.cfg.get("auto_focus", False))
        self.v_minimize = tk.BooleanVar(value=self.cfg.get("minimize_on_start", True))
        self.v_min_others = tk.BooleanVar(value=self.cfg.get("minimize_others", True))
        self.v_humanize = tk.BooleanVar(value=self.cfg.get("humanize", True))
        self.v_auto_launch = tk.BooleanVar(value=self.cfg.get("auto_launch", False))
        self.v_uu_path = tk.StringVar(value=self.cfg.get("uu_path", ""))
        self.v_game_path = tk.StringVar(value=self.cfg.get("game_path", ""))
        self.v_dmm_only = tk.BooleanVar(value=self.cfg.get("dmm_only", False))
        self.v_launch_lead = tk.IntVar(value=self.cfg.get("launch_lead", 5))
        self.v_launch_wait = tk.IntVar(value=self.cfg.get("launch_wait", 5))
        self.v_autoscroll = tk.BooleanVar(value=True)
        self.v_prefix = tk.StringVar(value="btn_")
        self.v_custom = tk.StringVar()
        self.v_fan_reset = tk.IntVar(value=self.cfg.get("fan_reset_hour", 0))
        self.v_fan_manual = tk.StringVar()
        self.v_jewel_now = tk.StringVar()
        self.v_jewel_manual = tk.StringVar()
        self.v_chart = tk.StringVar(value="fans")

        self.setup_fonts()
        self.build_header()
        tb.Label(root, text="按 F10 或把鼠标移到屏幕左上角，可以随时紧急停止",
                 bootstyle="secondary", padding=(16, 6)).pack(side=BOTTOM, fill=X)
        self.nb = tb.Notebook(root, bootstyle="primary")
        self.nb.pack(fill=BOTH, expand=True, padx=14, pady=(10, 0))
        self.build_run_tab()
        self.build_fans_tab()
        self.build_tpl_tab()
        self.build_settings_tab()
        self.build_donate_tab()
        self.on_mode_change()

        root.after(150, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if pynput_kb:
            pynput_kb.Listener(on_press=self.on_key).start()
        self.log(f"{APP_NAME} v{VERSION} 已就绪")

    # ---------- 外观 ----------
    def setup_fonts(self):
        st = self.root.style
        for name in ("TLabel", "TButton", "TCheckbutton", "TRadiobutton", "TEntry", "TSpinbox",
                     "TCombobox", "Treeview", "TLabelframe.Label"):
            st.configure(name, font=(FONT, 10))
        st.configure("TNotebook.Tab", font=(FONT, 11), padding=(18, 6))
        st.configure("Treeview.Heading", font=(FONT, 10, "bold"))
        st.configure("Treeview", rowheight=int(30 * self.ui_scale()))
        st.configure("TLabelframe.Label", font=(FONT, 10, "bold"), foreground=PALETTE["primary"])

    def ui_scale(self):
        return max(1.0, self.root.winfo_fpixels("1i") / 96)

    def build_header(self):
        hdr = tb.Frame(self.root, bootstyle="primary", padding=(18, 12))
        hdr.pack(fill=X, side=TOP)
        tb.Label(hdr, text=APP_NAME, font=(FONT, 17, "bold"), bootstyle="inverse-primary").pack(side=LEFT)
        tb.Label(hdr, text=f"v{VERSION}", font=(FONT, 9), bootstyle="inverse-primary").pack(side=LEFT, padx=(8, 0), pady=(8, 0))

        self.btn_stop = tb.Button(hdr, text="■  停止", bootstyle="danger", width=9, command=self.stop, state=DISABLED)
        self.btn_stop.pack(side=RIGHT)
        self.btn_start = tb.Button(hdr, text="▶  启动", bootstyle="light", width=9, command=self.start)
        self.btn_start.pack(side=RIGHT, padx=8)
        self.lbl_next = tb.Label(hdr, text="", font=(FONT, 11), bootstyle="inverse-primary")
        self.lbl_next.pack(side=RIGHT, padx=14)
        self.lbl_state = tb.Label(hdr, text="待机中", bootstyle="inverse-dark", padding=(12, 3), font=(FONT, 10))
        self.lbl_state.pack(side=RIGHT)
        self.lbl_fans = tb.Label(hdr, text="", font=(FONT, 11, "bold"), bootstyle="inverse-primary", foreground=GOLD)
        self.lbl_fans.pack(side=RIGHT, padx=14)

        # 标题栏下方的白色护栏条
        rail = tk.Canvas(self.root, height=12, highlightthickness=0, bg=PALETTE["primary"])
        rail.pack(fill=X)

        def draw(_=None):
            rail.delete("all")
            w = rail.winfo_width()
            rail.create_rectangle(0, 5, w, 7, fill=GOLD, width=0)
            for x in range(24, w, 48):  # 金色钻石纹
                rail.create_polygon(x, 0, x + 6, 6, x, 12, x - 6, 6, fill=GOLD, outline=PALETTE["primary"])

        rail.bind("<Configure>", draw)

    def row(self, parent, label, make):
        fr = tb.Frame(parent)
        fr.pack(fill=X, pady=4)
        tb.Label(fr, text=label).pack(side=LEFT)
        make(fr).pack(side=RIGHT)

    # ---------- 运行页 ----------
    def build_run_tab(self):
        f = tb.Frame(self.nb, padding=14)
        self.nb.add(f, text="运行")
        left = tb.Frame(f, width=int(320 * self.ui_scale()))
        left.pack(side=LEFT, fill=Y, padx=(0, 14))
        left.pack_propagate(False)
        right = tb.Frame(f)
        right.pack(side=LEFT, fill=BOTH, expand=True)

        mf = tb.Labelframe(left, text="执行模式", padding=12)
        mf.pack(fill=X)
        self.mode_box = tb.Frame(mf)
        self.mode_box.pack(fill=X)
        self.build_mode_buttons()
        mb = tb.Frame(mf)
        mb.pack(fill=X, pady=(6, 0))
        tb.Button(mb, text="＋ 新建模式", bootstyle="success-outline", command=self.new_mode).pack(side=LEFT)
        self.btn_edit_mode = tb.Button(mb, text="编辑", bootstyle="secondary-outline", command=self.edit_mode)
        self.btn_edit_mode.pack(side=LEFT, padx=6)
        self.btn_del_mode = tb.Button(mb, text="删除", bootstyle="danger-outline", command=self.delete_mode)
        self.btn_del_mode.pack(side=LEFT)
        self.lbl_hint = tb.Label(mf, text="", bootstyle="secondary", font=(FONT, 9))
        self.lbl_hint.pack(anchor=W, pady=(6, 0))

        holder = tb.Frame(left)
        holder.pack(fill=X, pady=12)
        self.box_cycle = tb.Labelframe(holder, text="定时", padding=12)
        self.row(self.box_cycle, "每隔多少分钟重开",
                 lambda p: tb.Spinbox(p, from_=1, to=600, textvariable=self.v_cycle_min, width=7))
        self.row(self.box_cycle, "单次流程最长（秒）",
                 lambda p: tb.Spinbox(p, from_=30, to=1800, increment=30, textvariable=self.v_cycle_timeout, width=7))
        tb.Checkbutton(self.box_cycle, text="启动后马上执行一次", variable=self.v_cycle_now,
                       bootstyle="success-round-toggle").pack(anchor=W, pady=(8, 0))
        tb.Checkbutton(self.box_cycle, text="TP 不足时自动喝体力饮料", variable=self.v_tp_drink,
                       bootstyle="success-round-toggle").pack(anchor=W, pady=(6, 0))
        self.row(self.box_cycle, "每轮最多喝几瓶",
                 lambda p: tb.Spinbox(p, from_=0, to=10, textvariable=self.v_tp_max, width=7))
        tb.Checkbutton(self.box_cycle, text="饮料用完时用宝石回复（会消耗宝石）", variable=self.v_tp_jewel,
                       bootstyle="warning-round-toggle").pack(anchor=W, pady=(6, 0))
        self.row(self.box_cycle, "每轮最多用几次宝石",
                 lambda p: tb.Spinbox(p, from_=0, to=10, textvariable=self.v_tp_jewel_max, width=7))
        self.box_story = tb.Labelframe(holder, text="剧情", padding=12)
        self.row(self.box_story, "最多看几话（0 为不限）",
                 lambda p: tb.Spinbox(p, from_=0, to=999, textvariable=self.v_story_max, width=7))
        self.row(self.box_story, "找不到 NEW 时滚动几次",
                 lambda p: tb.Spinbox(p, from_=0, to=50, textvariable=self.v_story_scroll, width=7))

        self.box_custom = tb.Labelframe(holder, text="自定义模式", padding=12)
        self.lbl_custom = tb.Label(self.box_custom, text="", justify=LEFT, wraplength=int(270 * self.ui_scale()))
        self.lbl_custom.pack(anchor=W)

        rf = tb.Labelframe(left, text="模板准备", padding=12)
        rf.pack(fill=X)
        self.ready_bar = tb.Progressbar(rf, bootstyle="success-striped", maximum=1.0)
        self.ready_bar.pack(fill=X)
        self.lbl_ready = tb.Label(rf, text="", wraplength=int(270 * self.ui_scale()), justify=LEFT)
        self.lbl_ready.pack(anchor=W, pady=(8, 0))
        tb.Button(rf, text="去截模板", bootstyle="primary-link",
                  command=lambda: self.nb.select(2)).pack(anchor=W)


        # 主题图：把自己喜欢的图片命名为 theme.png 放在程序旁边即可显示
        self.theme_photo = None
        theme = os.path.join(BASE, "theme.png")
        if os.path.exists(theme):
            try:
                s = self.ui_scale()
                im = Image.open(theme).convert("RGBA")
                im.thumbnail((int(290 * s), int(320 * s)))
                bg = Image.new("RGBA", im.size, PALETTE["bg"])
                bg.alpha_composite(im)
                self.theme_photo = ImageTk.PhotoImage(bg.convert("RGB"))
                tb.Label(left, image=self.theme_photo).pack(side=BOTTOM, pady=(8, 0))
            except Exception:
                self.theme_photo = None
        if self.theme_photo is None:
            self.build_emblem(left)

        jf = tb.Labelframe(right, text="彩色萝卜", padding=(12, 8))
        jf.pack(fill=X, pady=(0, 10))
        # 两行排版：第一行 输入 / 当前 / 今天已获得，第二行 提示 / 今天开始 / 昨天获得（在今天正下方）
        inp = tb.Frame(jf)
        inp.grid(row=0, column=0, sticky=W)
        tb.Label(inp, text="现在的萝卜").pack(side=LEFT)
        ent = tb.Entry(inp, textvariable=self.v_jewel_now, width=10)
        ent.pack(side=LEFT, padx=6)
        ent.bind("<Return>", lambda e: self.record_jewel_now())
        tb.Button(inp, text="记录", bootstyle="success", command=self.record_jewel_now).pack(side=LEFT)
        tb.Label(jf, text="填一次后会随每轮育成自动更新", bootstyle="secondary",
                 font=(FONT, 9)).grid(row=1, column=0, sticky=W, pady=(6, 0))
        self.lbl_jnow = tb.Label(jf, text="", font=(FONT, 12, "bold"), foreground=PALETTE["fg"])
        self.lbl_jnow.grid(row=0, column=1, sticky=W, padx=(24, 0))
        self.lbl_jtoday = tb.Label(jf, text="", bootstyle="secondary")
        self.lbl_jtoday.grid(row=1, column=1, sticky=W, padx=(24, 0), pady=(6, 0))
        self.lbl_jgain = tb.Label(jf, text="", font=(FONT, 12, "bold"), foreground=PALETTE["success"])
        self.lbl_jgain.grid(row=0, column=2, sticky=W, padx=(24, 0))
        self.lbl_jyest = tb.Label(jf, text="", font=(FONT, 12, "bold"), foreground=PALETTE["primary"])
        self.lbl_jyest.grid(row=1, column=2, sticky=W, padx=(24, 0), pady=(6, 0))
        jf.columnconfigure(3, weight=1)
        self.tick_jewel()

        lf = tb.Labelframe(right, text="运行日志", padding=10)
        lf.pack(fill=BOTH, expand=True)
        bar = tb.Frame(lf)
        bar.pack(fill=X, pady=(0, 8))
        tb.Checkbutton(bar, text="自动滚到最新", variable=self.v_autoscroll,
                       bootstyle="info-round-toggle").pack(side=LEFT)
        tb.Button(bar, text="清空", bootstyle="secondary-outline", width=6, command=self.clear_log).pack(side=RIGHT)
        tf = tb.Frame(lf)
        tf.pack(fill=BOTH, expand=True)
        self.txt = tk.Text(tf, bg=LOG_BG, fg="#f1ead6", relief="flat", font=(FONT, 10), wrap="word",
                           padx=12, pady=10, state=DISABLED, spacing1=2, spacing3=2, highlightthickness=0)
        sb = tb.Scrollbar(tf, orient=VERTICAL, command=self.txt.yview, bootstyle="round")
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        self.txt.pack(side=LEFT, fill=BOTH, expand=True)
        self.txt.tag_configure("time", foreground="#8fa596")
        self.txt.tag_configure("info", foreground="#f1ead6")
        self.txt.tag_configure("ok", foreground="#8ed9a4")
        self.txt.tag_configure("warn", foreground=GOLD)
        self.txt.tag_configure("err", foreground="#ff8a80")

    def build_emblem(self, parent):
        """左下角的装饰徽章：金边祖母绿钻石与金色皇冠。"""
        cv = tk.Canvas(parent, bg=PALETTE["bg"], highlightthickness=0)
        cv.pack(side=BOTTOM, fill=BOTH, expand=True, pady=(8, 0))
        emerald, deep, dgold, ruby = "#3aa77a", PALETTE["primary"], "#a8842a", PALETTE["danger"]

        def star(x, y, r):
            cv.create_polygon(x, y - r, x + r * 0.25, y - r * 0.25, x + r, y, x + r * 0.25, y + r * 0.25,
                              x, y + r, x - r * 0.25, y + r * 0.25, x - r, y, x - r * 0.25, y - r * 0.25,
                              fill=GOLD, outline="")

        def draw(_=None):
            cv.delete("all")
            w, h = cv.winfo_width(), cv.winfo_height()
            if w < 50 or h < 50:
                return
            k = min(w / 300, h / 170, 1.6)
            cy = h / 2
            # 钻石
            x = w / 2 - 70 * k
            top = [(x - 28 * k, cy - 30 * k), (x + 28 * k, cy - 30 * k), (x + 46 * k, cy - 10 * k), (x - 46 * k, cy - 10 * k)]
            cv.create_polygon(*top, fill=emerald, outline=GOLD, width=2)
            cv.create_polygon(x - 46 * k, cy - 10 * k, x + 46 * k, cy - 10 * k, x, cy + 48 * k,
                              fill=deep, outline=GOLD, width=2)
            for a, b in (((x - 28 * k, cy - 30 * k), (x - 14 * k, cy - 10 * k)), ((x, cy - 30 * k), (x - 14 * k, cy - 10 * k)),
                         ((x, cy - 30 * k), (x + 14 * k, cy - 10 * k)), ((x + 28 * k, cy - 30 * k), (x + 14 * k, cy - 10 * k)),
                         ((x - 14 * k, cy - 10 * k), (x, cy + 48 * k)), ((x + 14 * k, cy - 10 * k), (x, cy + 48 * k))):
                cv.create_line(*a, *b, fill=GOLD, width=1)
            # 皇冠
            x = w / 2 + 70 * k
            cv.create_polygon(x - 42 * k, cy + 22 * k, x - 48 * k, cy - 24 * k, x - 22 * k, cy - 2 * k, x, cy - 36 * k,
                              x + 22 * k, cy - 2 * k, x + 48 * k, cy - 24 * k, x + 42 * k, cy + 22 * k,
                              fill=GOLD, outline=dgold, width=2)
            cv.create_rectangle(x - 42 * k, cy + 22 * k, x + 42 * k, cy + 36 * k, fill=GOLD, outline=dgold, width=2)
            for px, py in ((x - 48 * k, cy - 24 * k), (x, cy - 36 * k), (x + 48 * k, cy - 24 * k)):
                cv.create_oval(px - 5 * k, py - 5 * k, px + 5 * k, py + 5 * k, fill=ruby, outline=dgold)
            cv.create_polygon(x, cy + 23 * k, x + 6 * k, cy + 29 * k, x, cy + 35 * k, x - 6 * k, cy + 29 * k,
                              fill=emerald, outline=dgold)
            # 点缀的星光
            for sx, sy, r in ((w / 2, cy - 40 * k, 7), (w / 2 - 128 * k, cy + 34 * k, 5),
                              (w / 2 + 128 * k, cy + 40 * k, 5), (w / 2, cy + 30 * k, 4)):
                star(sx, sy, r * k)

        cv.bind("<Configure>", draw)

    # ---------- 粉丝统计页 ----------
    def build_fans_tab(self):
        s = self.ui_scale()
        f = tb.Frame(self.nb, padding=14)
        self.nb.add(f, text="育成收益")
        top = tb.Frame(f)
        top.pack(fill=X)
        self.fan_cards = {}
        for key, title in (("today", "今天"), ("yesterday", "昨天"), ("week", "近 7 天"), ("avg", "平均每次育成")):
            card = tb.Labelframe(top, text=title, padding=(14, 8))
            card.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
            v = tb.Label(card, text="0", font=(FONT, 16, "bold"), foreground=PALETTE["primary"])
            v.pack(anchor=W)
            sub = tb.Label(card, text="", bootstyle="secondary", font=(FONT, 9))
            sub.pack(anchor=W)
            self.fan_cards[key] = (v, sub)

        mid = tb.Labelframe(f, text="最近 14 天", padding=10)
        mid.pack(fill=X, pady=12)
        sw = tb.Frame(mid)
        sw.pack(anchor=W, pady=(0, 6))
        for val, label in (("fans", "粉丝"), ("jewels", "宝石")):
            tb.Radiobutton(sw, text=label, value=val, variable=self.v_chart, command=self.refresh_fans,
                           bootstyle="primary-outline-toolbutton", width=6).pack(side=LEFT, padx=(0, 4))
        self.fan_chart = tk.Canvas(mid, height=int(170 * s), bg=PALETTE["bg"], highlightthickness=0)
        self.fan_chart.pack(fill=X)
        self.fan_chart.bind("<Configure>", lambda e: self.draw_fan_chart())

        bottom = tb.Frame(f)
        bottom.pack(fill=BOTH, expand=True)
        side = tb.Frame(bottom, width=int(260 * s))
        side.pack(side=RIGHT, fill=Y, padx=(12, 0))
        side.pack_propagate(False)
        inner = tb.Notebook(bottom, bootstyle="secondary")
        inner.pack(side=LEFT, fill=BOTH, expand=True)
        df = tb.Frame(inner, padding=(0, 6))
        inner.add(df, text="每日汇总")
        self.day_tree = tb.Treeview(df, columns=("date", "count", "fans", "jewels", "avg"), show="headings",
                                    bootstyle="primary", height=6)
        self.day_tree.heading("date", text="日期")
        self.day_tree.column("date", width=int(170 * s), anchor="w")
        for col, title, width in (("count", "育成次数", 90), ("fans", "粉丝", 160),
                                  ("jewels", "彩色萝卜", 120), ("avg", "平均每次粉丝", 140)):
            self.day_tree.heading(col, text=title)
            self.day_tree.column(col, width=int(width * s), anchor="e")
        self.day_tree.tag_configure("today", background=PALETTE["active"])
        self.day_tree.tag_configure("total", font=(FONT, 10, "bold"), foreground=PALETTE["primary"])
        dsb = tb.Scrollbar(df, orient=VERTICAL, command=self.day_tree.yview, bootstyle="round")
        self.day_tree.configure(yscrollcommand=dsb.set)
        dsb.pack(side=RIGHT, fill=Y)
        self.day_tree.pack(side=LEFT, fill=BOTH, expand=True)

        tf = tb.Frame(inner, padding=(0, 6))
        inner.add(tf, text="每次明细")
        self.fan_tree = tb.Treeview(tf, columns=("gain", "jewels"), show="tree headings", bootstyle="primary", height=6)
        self.fan_tree.heading("#0", text="育成结束时间")
        self.fan_tree.heading("gain", text="获得粉丝")
        self.fan_tree.heading("jewels", text="宝石增加")
        self.fan_tree.column("jewels", width=int(120 * s), anchor="e")
        self.fan_tree.column("#0", width=int(220 * s))
        self.fan_tree.column("gain", width=int(160 * s), anchor="e")
        sb = tb.Scrollbar(tf, orient=VERTICAL, command=self.fan_tree.yview, bootstyle="round")
        self.fan_tree.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        self.fan_tree.pack(side=LEFT, fill=BOTH, expand=True)

        box = tb.Labelframe(side, text="记录", padding=10)
        box.pack(fill=X)
        tb.Label(box, text="漏记时手动补记：").pack(anchor=W)
        for label, var in (("粉丝", self.v_fan_manual), ("宝石", self.v_jewel_manual)):
            row = tb.Frame(box)
            row.pack(fill=X, pady=(4, 0))
            tb.Label(row, text=label, width=4).pack(side=LEFT)
            tb.Entry(row, textvariable=var, width=12).pack(side=LEFT, fill=X, expand=True)
        tb.Button(box, text="补记", bootstyle="success", command=self.add_fans_manual).pack(anchor=W, pady=8)
        tb.Button(box, text="删除选中记录", bootstyle="danger-outline", command=self.delete_fans).pack(anchor=W)
        tb.Button(box, text="导出表格（Excel 可打开）", bootstyle="info-outline",
                  command=self.export_fans).pack(anchor=W, pady=(8, 0))
        box2 = tb.Labelframe(side, text="统计方式", padding=10)
        box2.pack(fill=X, pady=(10, 0))
        r2 = tb.Frame(box2)
        r2.pack(fill=X)
        tb.Label(r2, text="每天几点算新的一天").pack(side=LEFT)
        sp = tb.Spinbox(r2, from_=0, to=23, textvariable=self.v_fan_reset, width=5, command=self.on_fan_reset)
        sp.pack(side=RIGHT)
        sp.bind("<FocusOut>", lambda e: self.on_fan_reset())
        self.refresh_fans()
        self.root.after(60000, self.tick_fans)

    def tick_fans(self):
        self.refresh_fans()
        self.root.after(60000, self.tick_fans)

    def on_fan_reset(self):
        try:
            self.cfg["fan_reset_hour"] = max(0, min(23, int(self.v_fan_reset.get())))
        except (tk.TclError, ValueError):
            return
        save_cfg(self.cfg)
        self.refresh_fans()

    def add_fans_manual(self):
        def num(var):
            t = var.get().replace(",", "").replace("，", "").replace("+", "").strip()
            return int(t) if t.lstrip("-").isdigit() else None
        gain, jewels = num(self.v_fan_manual), num(self.v_jewel_manual)
        if gain is None and jewels is None:
            messagebox.showerror(APP_NAME, "请至少填一个数字，例如粉丝 1308575、宝石 150")
            return
        self.fans.add(gain, jewels)
        self.v_fan_manual.set("")
        self.v_jewel_manual.set("")
        self.log("已手动补记一条育成收益", "ok")

    def export_fans(self):
        rh = self.cfg.get("fan_reset_hour", 0)
        daily = self.fans.daily(rh)
        if not daily:
            messagebox.showinfo(APP_NAME, "还没有任何记录")
            return
        path = filedialog.asksaveasfilename(
            title="导出育成收益", defaultextension=".csv", filetypes=[("CSV 表格", "*.csv")],
            initialfile=f"育成收益_{datetime.now():%Y%m%d}.csv")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["日期", "育成次数", "粉丝", "彩色萝卜", "平均每次粉丝"])
                for d in sorted(daily, reverse=True):
                    fsum, jsum, cnt = daily[d]
                    w.writerow([f"{d:%Y-%m-%d}", cnt, fsum, jsum, fsum // cnt if cnt else 0])
                w.writerow([])
                w.writerow(["育成结束时间", "粉丝", "彩色萝卜"])
                for r in reversed(self.fans.records):
                    w.writerow([r["t"], "" if r.get("gain") is None else r["gain"],
                                "" if r.get("jewels") is None else r["jewels"]])
        except OSError as e:
            messagebox.showerror(APP_NAME, f"导出失败：{e}")
            return
        self.log(f"已导出表格：{path}", "ok")

    def delete_fans(self):
        sel = [int(i) for i in self.fan_tree.selection()]
        if sel and messagebox.askyesno(APP_NAME, f"删除选中的 {len(sel)} 条记录？"):
            self.fans.remove(sel)

    def jewel_day(self, offset=0):
        return (FanStore.day_of(datetime.now(), self.cfg.get("fan_reset_hour", 0)) - timedelta(days=offset)).isoformat()

    def record_jewel_now(self):
        t = self.v_jewel_now.get().replace(",", "").replace("，", "").strip()
        if not t.isdigit():
            messagebox.showerror(APP_NAME, "请输入现在的萝卜数量，例如 33806")
            return
        st = load_state()
        st.setdefault("jewel_log", {})[self.jewel_day()] = {"n": int(t), "manual": True}
        st["jewels"] = int(t)
        st["jewels_t"] = datetime.now().strftime("%H:%M")
        save_state(st)
        self.v_jewel_now.set("")
        self.log(f"已记录今天开始的萝卜：{int(t):,}", "ok")
        self.refresh_jewel_box()

    def tick_jewel(self):
        self.refresh_jewel_box()
        self.root.after(3000, self.tick_jewel)

    def refresh_jewel_box(self):
        if not hasattr(self, "lbl_jyest"):
            return
        st = load_state()
        log = st.get("jewel_log", {})
        today, yest = log.get(self.jewel_day()), log.get(self.jewel_day(1))
        cur = st.get("jewels")
        if cur is not None:
            t = st.get("jewels_t")
            self.lbl_jnow.configure(text=f"当前：{cur:,}" + (f"（{t} 更新）" if t else ""))
            self.lbl_jgain.configure(text=f"今天已获得：{cur - today['n']:+,}" if today else "")
        else:
            self.lbl_jnow.configure(text="当前：—")
            self.lbl_jgain.configure(text="")
        if today:
            self.lbl_jtoday.configure(text=f"今天开始：{today['n']:,}（{'手动' if today.get('manual') else '自动'}）")
        else:
            self.lbl_jtoday.configure(text="今天开始：还没记录")
        if today and yest:
            d = today["n"] - yest["n"]
            self.lbl_jyest.configure(text=f"昨天获得：{d:+,}")
        else:
            j = self.fans.daily(self.cfg.get("fan_reset_hour", 0)).get(
                FanStore.day_of(datetime.now(), self.cfg.get("fan_reset_hour", 0)) - timedelta(days=1))
            if j and j[2]:
                self.lbl_jyest.configure(text=f"昨天获得：{j[1]:+,}（按每轮统计）")
            else:
                self.lbl_jyest.configure(text="昨天获得：暂无数据")

    def refresh_fans(self):
        self.refresh_jewel_box()
        rh = self.cfg.get("fan_reset_hour", 0)
        daily = self.fans.daily(rh)
        today = FanStore.day_of(datetime.now(), rh)
        z = (0, 0, 0)
        t_sum, t_j, t_cnt = daily.get(today, z)
        y_sum, y_j, y_cnt = daily.get(today - timedelta(days=1), z)
        w = [daily.get(today - timedelta(days=i), z) for i in range(7)]
        w_sum, w_j, w_cnt = (sum(x[k] for x in w) for k in range(3))
        cards = {
            "today": (f"粉丝 +{fmt_fans(t_sum)}", f"宝石 {t_j:+,}，{t_cnt} 次育成"),
            "yesterday": (f"粉丝 +{fmt_fans(y_sum)}", f"宝石 {y_j:+,}，{y_cnt} 次育成"),
            "week": (f"粉丝 +{fmt_fans(w_sum)}", f"宝石 {w_j:+,}，{w_cnt} 次育成"),
            "avg": (f"粉丝 +{fmt_fans(w_sum // w_cnt) if w_cnt else 0}",
                    f"宝石 {(w_j // w_cnt) if w_cnt else 0:+,}，按近 7 天计算"),
        }
        for k, (a, b) in cards.items():
            self.fan_cards[k][0].configure(text=a)
            self.fan_cards[k][1].configure(text=b)
        # 每日汇总表
        self.day_tree.delete(*self.day_tree.get_children())
        wk = "一二三四五六日"
        all_f = all_j = all_c = 0
        for d in sorted(daily, reverse=True):
            fsum, jsum, cnt = daily[d]
            all_f, all_j, all_c = all_f + fsum, all_j + jsum, all_c + cnt
            self.day_tree.insert("", "end", values=(
                f"{d:%Y-%m-%d}（周{wk[d.weekday()]}）", cnt, f"+{fsum:,}", f"{jsum:+,}",
                f"+{fsum // cnt:,}" if cnt else "0"), tags=("today",) if d == today else ())
        if daily:
            self.day_tree.insert("", "end", values=(
                f"合计（{len(daily)} 天）", all_c, f"+{all_f:,}", f"{all_j:+,}",
                f"+{all_f // all_c:,}" if all_c else "0"), tags=("total",))
        self.lbl_fans.configure(text=f"今日粉丝 +{fmt_fans(t_sum)}　宝石 {t_j:+,}")
        self.fan_tree.delete(*self.fan_tree.get_children())
        recs = self.fans.records
        for i in range(len(recs) - 1, max(-1, len(recs) - 301), -1):
            g, j = recs[i].get("gain"), recs[i].get("jewels")
            self.fan_tree.insert("", "end", iid=str(i), text=recs[i]["t"],
                                 values=("—" if g is None else f"+{g:,}", "—" if j is None else f"{j:+,}"))
        col = 0 if self.v_chart.get() == "fans" else 1
        self.fan_days = [(today - timedelta(days=i), daily.get(today - timedelta(days=i), z)[col])
                         for i in range(13, -1, -1)]
        self.draw_fan_chart()

    def draw_fan_chart(self):
        cv = self.fan_chart
        cv.delete("all")
        days = getattr(self, "fan_days", [])
        w, h = cv.winfo_width(), cv.winfo_height()
        if not days or w < 50:
            return
        top_pad, bot_pad = 22, 22
        mx = max(abs(v) for _, v in days) or 1
        slot = w / len(days)
        bw = slot * 0.56
        cv.create_line(0, h - bot_pad, w, h - bot_pad, fill=PALETTE["border"])
        for i, (d, v) in enumerate(days):
            cx = slot * i + slot / 2
            bh = (h - top_pad - bot_pad) * max(v, 0) / mx
            color = GOLD if i == len(days) - 1 else PALETTE["primary"]
            if v:
                cv.create_rectangle(cx - bw / 2, h - bot_pad - bh, cx + bw / 2, h - bot_pad, fill=color, width=0)
                cv.create_text(cx, h - bot_pad - bh - 9, text=fmt_fans(v), font=(FONT, 8), fill=PALETTE["fg"])
            cv.create_text(cx, h - bot_pad + 11, text=d.strftime("%m/%d"), font=(FONT, 8),
                           fill=PALETTE["fg"] if i == len(days) - 1 else PALETTE["secondary"])

    # ---------- 模板页 ----------
    def build_tpl_tab(self):
        f = tb.Frame(self.nb, padding=14)
        self.nb.add(f, text="模板")
        tb.Label(f, text="让游戏停在有那个按钮的画面，在下方选中对应项目，点「截取」，然后在弹出的截图里框住按钮。",
                 bootstyle="inverse-light", padding=(12, 8), wraplength=int(820 * self.ui_scale())).pack(fill=X)

        tf = tb.Frame(f)
        tf.pack(fill=BOTH, expand=True, pady=10)
        self.tree = tb.Treeview(tf, columns=("desc", "ok"), show="tree headings", bootstyle="primary")
        self.tree.heading("#0", text="模板名")
        self.tree.heading("desc", text="要框的内容")
        self.tree.heading("ok", text="状态")
        s = self.ui_scale()
        self.tree.column("#0", width=int(220 * s))
        self.tree.column("desc", width=int(400 * s))
        self.tree.column("ok", width=int(100 * s), anchor="center")
        self.tree.tag_configure("group", font=(FONT, 10, "bold"), background=PALETTE["light"])
        self.tree.tag_configure("ok", foreground=PALETTE["success"])
        self.tree.tag_configure("miss", foreground=PALETTE["danger"])
        sb = tb.Scrollbar(tf, orient=VERTICAL, command=self.tree.yview, bootstyle="round")
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda e: self.capture_template())

        bf = tb.Frame(f)
        bf.pack(fill=X)
        tb.Button(bf, text="截取", bootstyle="primary", width=10, command=self.capture_template).pack(side=LEFT)
        tb.Button(bf, text="设定 NEW 范围", bootstyle="info-outline", command=self.capture_new_region).pack(side=LEFT, padx=6)
        tb.Button(bf, text="测试识别", bootstyle="success-outline", command=self.test_match).pack(side=LEFT)
        tb.Button(bf, text="设为完成标志", bootstyle="warning-outline",
                  command=self.toggle_finish).pack(side=LEFT, padx=6)
        tb.Button(bf, text="删除", bootstyle="danger-outline", command=self.delete_template).pack(side=RIGHT)

        cf = tb.Frame(f)
        cf.pack(fill=X, pady=(10, 0))
        tb.Label(cf, text="添加按钮到：").pack(side=LEFT)
        self.cmb_prefix = tb.Combobox(cf, textvariable=self.v_prefix, width=18, state="readonly")
        self.cmb_prefix.pack(side=LEFT)
        tb.Label(cf, text="名称").pack(side=LEFT, padx=(8, 0))
        tb.Entry(cf, textvariable=self.v_custom, width=14).pack(side=LEFT, padx=4)
        tb.Button(cf, text="添加", bootstyle="secondary", command=self.add_custom).pack(side=LEFT)
        tb.Label(cf, text="选「模式：…」就是这个模式专属的步骤，按添加顺序执行",
                 bootstyle="secondary", font=(FONT, 9)).pack(side=LEFT, padx=10)
        self.update_prefix_choices()
        self.refresh_tree()

    # ---------- 设置页 ----------
    def scrollable(self, parent, padding=14):
        """可上下滚动的区域：回传 (外框, 内容框)。鼠标在上面时滚轮可以滚。"""
        outer = tb.Frame(parent)
        cv = tk.Canvas(outer, highlightthickness=0, bg=PALETTE["bg"])
        sb = tb.Scrollbar(outer, orient=VERTICAL, command=cv.yview, bootstyle="round")
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        cv.pack(side=LEFT, fill=BOTH, expand=True)
        inner = tb.Frame(cv, padding=padding)
        win = cv.create_window(0, 0, window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))

        def wheel(e):
            if cv.yview() != (0.0, 1.0):
                cv.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")

        outer.bind("<Enter>", lambda e: cv.bind_all("<MouseWheel>", wheel))
        outer.bind("<Leave>", lambda e: cv.unbind_all("<MouseWheel>"))
        return outer, inner

    def build_settings_tab(self):
        outer, f = self.scrollable(self.nb)
        self.nb.add(outer, text="设置")
        box = tb.Labelframe(f, text="基本", padding=14, width=int(460 * self.ui_scale()))
        box.pack(anchor=W, fill=Y)
        self.row(box, "游戏窗口标题（包含即可）  ", lambda p: tb.Entry(p, textvariable=self.v_title, width=18))
        self.row(box, "识别严格度（0.6～0.99）",
                 lambda p: tb.Spinbox(p, from_=0.6, to=0.99, increment=0.01, textvariable=self.v_thr, width=7))
        self.row(box, "每次点击后等待（秒）",
                 lambda p: tb.Spinbox(p, from_=0.1, to=5, increment=0.1, textvariable=self.v_delay, width=7))
        tb.Checkbutton(box, text="需要点击时自动把游戏切到最前面（关闭则暂停，等你切回游戏）",
                       variable=self.v_auto_focus, bootstyle="success-round-toggle").pack(anchor=W, pady=(10, 0))
        tb.Checkbutton(box, text="点启动后程序自己缩到任务栏（停止后再弹回来）",
                       variable=self.v_minimize, bootstyle="success-round-toggle").pack(anchor=W, pady=(6, 0))
        tb.Checkbutton(box, text="开游戏和每轮开始操作时，把游戏以外的窗口全部最小化",
                       variable=self.v_min_others, bootstyle="success-round-toggle").pack(anchor=W, pady=(6, 0))
        tb.Checkbutton(box, text="点击位置在按钮范围内随机、点击速度随机",
                       variable=self.v_humanize, bootstyle="success-round-toggle").pack(anchor=W, pady=(6, 0))
        tb.Button(box, text="保存设置", bootstyle="success", command=self.save_settings).pack(anchor=W, pady=(12, 0))

        lb = tb.Labelframe(f, text="自动启动游戏（加速器）", padding=14)
        lb.pack(anchor=W, fill=X, pady=(14, 0))
        tb.Checkbutton(lb, text="每轮结束后关闭游戏，下一轮前自动从加速器启动",
                       variable=self.v_auto_launch, bootstyle="success-round-toggle").pack(anchor=W)
        pr = tb.Frame(lb)
        pr.pack(fill=X, pady=(10, 4))
        tb.Label(pr, text="加速器位置").pack(side=LEFT)
        tb.Entry(pr, textvariable=self.v_uu_path).pack(side=LEFT, fill=X, expand=True, padx=6)
        tb.Button(pr, text="浏览…", bootstyle="secondary-outline", command=self.pick_uu).pack(side=LEFT)
        gr = tb.Frame(lb)
        gr.pack(fill=X, pady=(4, 4))
        tb.Label(gr, text="DMM 游戏快捷方式").pack(side=LEFT)
        tb.Entry(gr, textvariable=self.v_game_path).pack(side=LEFT, fill=X, expand=True, padx=6)
        tb.Button(gr, text="浏览…", bootstyle="secondary-outline", command=self.pick_game).pack(side=LEFT)
        tb.Checkbutton(lb, text="不开加速器，每次都直接用 DMM 快捷方式打开游戏",
                       variable=self.v_dmm_only, bootstyle="success-round-toggle").pack(anchor=W, pady=(6, 0))
        tb.Label(lb, text="没开上面这个时：第一次从加速器点「启动游戏」；之后加速器还开着，就直接打开 DMM 快捷方式（没填就每次都走加速器）",
                 bootstyle="secondary").pack(anchor=W, pady=(4, 0))
        self.lbl_acc = tb.Label(lb, text="", bootstyle="secondary", justify=LEFT)
        self.lbl_acc.pack(anchor=W, pady=(6, 4))
        self.refresh_acc_hint()
        self.row(lb, "提前几分钟启动游戏",
                 lambda p: tb.Spinbox(p, from_=1, to=30, textvariable=self.v_launch_lead, width=7))
        self.row(lb, "启动后最多等几分钟进入主页",
                 lambda p: tb.Spinbox(p, from_=1, to=15, textvariable=self.v_launch_wait, width=7))
        tb.Button(lb, text="测试：关闭并自动启动一次", bootstyle="info-outline",
                  command=self.test_launch).pack(anchor=W, pady=(8, 0))

        tips = tb.Labelframe(f, text="识别不到时", padding=14)
        tips.pack(anchor=W, fill=X, pady=14)
        for t in ("截完模板后，不要再改游戏窗口大小和 Windows 显示缩放。",
                  "按钮只框文字和图标，不要框到会变的数字和人物。",
                  "「测试识别」里分数在 0.75～0.85 之间的，可以把识别严格度调低一点。"):
            tb.Label(tips, text=t).pack(anchor=W, pady=2)

    # ---------- 打赏页 ----------
    def build_donate_tab(self):
        s = self.ui_scale()
        f = tb.Frame(self.nb, padding=20)
        self.nb.add(f, text="打赏")
        inner = tb.Frame(f)
        inner.pack(expand=True)
        self.donate_photo = None
        path = resource_path("donate.jpg")
        if not os.path.exists(path):
            path = os.path.join(BASE, "donate.jpg")
        if os.path.exists(path):
            try:
                im = Image.open(path).convert("RGB")
                im.thumbnail((int(300 * s), int(410 * s)))
                self.donate_photo = ImageTk.PhotoImage(im)
                tb.Label(inner, image=self.donate_photo).pack()
            except Exception:
                pass
        tb.Label(inner, text="使用顺畅的话，可以打赏一瓶可乐支持一下 ☺",
                 font=(FONT, 13, "bold"), foreground=PALETTE["primary"]).pack(pady=(14, 4))
        tb.Label(inner, text="微信扫一扫即可", bootstyle="secondary").pack()

        fb = tb.Labelframe(inner, text="Bug 反馈", padding=(14, 10))
        fb.pack(pady=(18, 0), fill=X)
        row = tb.Frame(fb)
        row.pack()
        tb.Label(row, text="邮箱：").pack(side=LEFT)
        tb.Label(row, text=FEEDBACK_EMAIL, font=(FONT, 11, "bold")).pack(side=LEFT)
        tb.Button(row, text="复制", bootstyle="secondary-outline", command=self.copy_email).pack(side=LEFT, padx=(10, 4))
        tb.Button(row, text="写邮件", bootstyle="primary-outline",
                  command=lambda: webbrowser.open(f"mailto:{FEEDBACK_EMAIL}?subject=赛马娘助手 Bug 反馈")).pack(side=LEFT)
        tb.Label(fb, text="反馈时附上运行日志截图和卡住的游戏画面，能更快找到问题",
                 bootstyle="secondary", font=(FONT, 9)).pack(pady=(8, 0))

    def copy_email(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(FEEDBACK_EMAIL)
        self.log(f"已复制反馈邮箱 {FEEDBACK_EMAIL}", "ok")

    # ---------- 状态 ----------
    def build_mode_buttons(self):
        for w in self.mode_box.winfo_children():
            w.destroy()
        items = list(MODES.items()) + [(mid, f"★  {m['name']}") for mid, m in self.cfg.get("custom_modes", {}).items()]
        for key, label in items:
            tb.Radiobutton(self.mode_box, text=label, value=key, variable=self.v_mode, command=self.on_mode_change,
                           bootstyle="primary-outline-toolbutton").pack(fill=X, pady=3, ipady=7)

    def on_mode_change(self):
        mode = self.v_mode.get()
        modes = self.cfg.get("custom_modes", {})
        if mode not in MODES and mode not in modes:
            mode = "auto_cycle"
            self.v_mode.set(mode)
        for b in (self.box_cycle, self.box_story, self.box_custom):
            b.pack_forget()
        custom = mode in modes
        if mode == "auto_cycle":
            self.box_cycle.pack(fill=X)
        elif custom:
            m = modes[mode]
            rep = int(m.get("repeat_min", 0) or 0)
            lines = [f"步骤：{len(m.get('order', []))} 个（按顺序优先）",
                     f"{m.get('idle_stop', 30)} 秒没东西可点就结束本次",
                     f"每隔 {rep} 分钟重复执行" if rep else "只执行一次"]
            if m.get("finish"):
                lines.append(f"看到「{step_name(m['finish'])}」就结束")
            self.lbl_custom.configure(text="\n".join(lines))
            self.box_custom.configure(text=f"自定义模式：{m['name']}")
            self.box_custom.pack(fill=X)
        else:
            self.box_story.pack(fill=X)
        self.lbl_hint.configure(text=MODE_HINT.get(mode, "按步骤顺序找按钮，看到就点"))
        self.btn_edit_mode.configure(state=NORMAL if custom else DISABLED)
        self.btn_del_mode.configure(state=NORMAL if custom else DISABLED)
        self.refresh_ready()

    # ---------- 自定义模式管理 ----------
    def new_mode(self):
        modes = self.cfg.setdefault("custom_modes", {})
        n = 1
        while f"cm{n}" in modes:
            n += 1
        ModeEditor(self, f"cm{n}", {"name": f"我的模式{n}", "order": [], "idle_stop": 30,
                                    "repeat_min": 0, "finish": ""}, new=True)

    def edit_mode(self):
        mid = self.v_mode.get()
        m = self.cfg.get("custom_modes", {}).get(mid)
        if m:
            ModeEditor(self, mid, m)

    def delete_mode(self):
        mid = self.v_mode.get()
        modes = self.cfg.get("custom_modes", {})
        m = modes.get(mid)
        if not m or not messagebox.askyesno(APP_NAME, f"删除模式「{m['name']}」和它的 {len(m.get('order', []))} 个模板？"):
            return
        meta = load_meta()
        for k in m.get("order", []):
            if os.path.exists(tpl_path(k)):
                os.remove(tpl_path(k))
            meta.pop(k, None)
            self.cfg.get("custom_templates", {}).pop(k, None)
        save_meta(meta)
        modes.pop(mid, None)
        self.v_mode.set("auto_cycle")
        self.cfg["mode"] = "auto_cycle"
        save_cfg(self.cfg)
        self.modes_changed()

    def modes_changed(self):
        self.build_mode_buttons()
        self.update_prefix_choices()
        self.refresh_tree()
        self.on_mode_change()

    def refresh_ready(self):
        req = mode_required(self.cfg, self.v_mode.get())
        if not req:
            self.ready_bar.configure(value=0)
            self.lbl_ready.configure(text="这个模式还没有步骤：到「模板」页底部选这个模式添加", bootstyle="danger")
            return
        missing = [k for k in req if not os.path.exists(tpl_path(k))]
        done = len(req) - len(missing)
        self.ready_bar.configure(value=done / len(req))
        if missing:
            self.lbl_ready.configure(text=f"已截 {done}/{len(req)} 个必需模板，还缺：" + "、".join(missing),
                                     bootstyle="danger")
        else:
            self.lbl_ready.configure(text=f"必需模板 {done}/{len(req)} 已齐，可以启动", bootstyle="success")

    def save_settings(self, quiet=False):
        try:
            self.cfg.update(
                mode=self.v_mode.get(),
                cycle_minutes=int(self.v_cycle_min.get()),
                cycle_timeout=int(self.v_cycle_timeout.get()),
                cycle_run_now=bool(self.v_cycle_now.get()),
                tp_auto_drink=bool(self.v_tp_drink.get()),
                tp_max_drinks=int(self.v_tp_max.get()),
                tp_use_jewel=bool(self.v_tp_jewel.get()),
                tp_max_jewel=int(self.v_tp_jewel_max.get()),
                story_max_episodes=int(self.v_story_max.get()),
                story_max_scroll=int(self.v_story_scroll.get()),
                window_title=self.v_title.get().strip() or "umamusume",
                match_threshold=float(self.v_thr.get()),
                delay=float(self.v_delay.get()),
                auto_focus=bool(self.v_auto_focus.get()),
                minimize_on_start=bool(self.v_minimize.get()),
                minimize_others=bool(self.v_min_others.get()),
                humanize=bool(self.v_humanize.get()),
                auto_launch=bool(self.v_auto_launch.get()),
                uu_path=self.v_uu_path.get().strip().strip('"'),
                game_path=self.v_game_path.get().strip().strip('"'),
                dmm_only=bool(self.v_dmm_only.get()),
                launch_lead=int(self.v_launch_lead.get()),
                launch_wait=int(self.v_launch_wait.get()),
            )
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_NAME, "有设置项不是有效数字，请检查后再保存")
            return False
        save_cfg(self.cfg)
        if not quiet:
            self.log("设置已保存", "ok")
        return True

    # ---------- 模板操作 ----------
    def refresh_tree(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        custom = self.cfg.get("custom_templates", {})
        for i, (gname, prefix, items) in enumerate(TEMPLATE_GROUPS):
            gid = f"grp{i}"
            self.tree.insert("", "end", iid=gid, text=gname, open=True, tags=("group",))
            merged = dict(items)
            for k, d in custom.items():
                if prefix == "btn_" and k.startswith(("btn_", "auto_")):
                    merged[k] = d
            if prefix == "uu_":
                for n, k in enumerate(self.cfg.get("acc_order", []), 1):
                    merged[k] = f"加速器第 {n} 步（设定后优先用这些，不用 UU 那两个）"
            for k, d in merged.items():
                ok = os.path.exists(tpl_path(k))
                self.tree.insert(gid, "end", iid=k, text=k, values=(d, "✓ 已截取" if ok else "✗ 未截取"),
                                 tags=("ok" if ok else "miss",))
            if prefix == "story_":
                ok = bool(self.cfg.get("story_new_region"))
                self.tree.insert(gid, "end", iid="__newregion", text="NEW 搜索范围",
                                 values=("框住剧情列表，避免点到菜单上的 NEW", "✓ 已设定" if ok else "✗ 未设定"),
                                 tags=("ok" if ok else "miss",))
        for mid, m in self.cfg.get("custom_modes", {}).items():
            gid = f"grpm_{mid}"
            self.tree.insert("", "end", iid=gid, text=f"★ 模式：{m['name']}", open=True, tags=("group",))
            for n, k in enumerate(m.get("order", []), 1):
                ok = os.path.exists(tpl_path(k))
                desc = f"第 {n} 步" + ("（完成标志：看到就结束）" if k == m.get("finish") else "")
                self.tree.insert(gid, "end", iid=k, text=step_name(k), values=(desc, "✓ 已截取" if ok else "✗ 未截取"),
                                 tags=("ok" if ok else "miss",))
            if not m.get("order"):
                self.tree.insert(gid, "end", iid=f"grpm_{mid}_empty", text="（还没有步骤）",
                                 values=("在下方「添加按钮到」选这个模式", ""))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        if hasattr(self, "ready_bar"):
            self.refresh_ready()

    def selected_key(self):
        sel = self.tree.selection()
        if not sel or sel[0].startswith("grp"):
            return None
        return sel[0]

    def update_prefix_choices(self):
        self.prefix_map = {"通用按钮（看到就点）": "btn_", "育成结束阶段": "auto_end_", "育成开始阶段": "auto_start_",
                           "自动启动：加速器按钮（按顺序）": "acc_"}
        for mid, m in self.cfg.get("custom_modes", {}).items():
            self.prefix_map[f"模式：{m['name']}"] = f"m_{mid}_"
        if hasattr(self, "cmb_prefix"):
            self.cmb_prefix.configure(values=list(self.prefix_map))
            if self.v_prefix.get() not in self.prefix_map:
                cur = self.v_mode.get()
                pick = next((k for k, v in self.prefix_map.items() if v == f"m_{cur}_"), "通用按钮（看到就点）")
                self.v_prefix.set(pick)

    def toggle_finish(self):
        key = self.selected_key()
        if not key or not key.startswith("m_"):
            messagebox.showinfo(APP_NAME, "先选中一个自定义模式里的步骤。看到它时，这个模式就结束本次执行")
            return
        mid = key.split("_", 2)[1]
        m = self.cfg["custom_modes"].get(mid)
        if not m:
            return
        m["finish"] = "" if m.get("finish") == key else key
        save_cfg(self.cfg)
        self.refresh_tree()
        self.on_mode_change()

    def add_custom(self):
        name = self.v_custom.get().strip()
        if not name or not name.isidentifier():
            messagebox.showerror(APP_NAME, "名称只能用文字、字母、数字和下划线，不能有空格或符号")
            return
        prefix = self.prefix_map.get(self.v_prefix.get(), "btn_")
        key = prefix + name
        if prefix == "acc_":
            order = self.cfg.setdefault("acc_order", [])
            if key not in order:
                order.append(key)
            desc = f"加速器第 {order.index(key) + 1} 步"
            self.refresh_acc_hint()
        elif prefix.startswith("m_"):
            mid = prefix[2:-1]
            m = self.cfg["custom_modes"][mid]
            if key not in m["order"]:
                m["order"].append(key)
            desc = f"「{m['name']}」的步骤"
        else:
            desc = {"btn_": "自定义：看到就点",
                    "auto_end_": "自定义：结束育成时点",
                    "auto_start_": "自定义：开始育成时点"}[prefix]
        self.cfg.setdefault("custom_templates", {})[key] = desc
        save_cfg(self.cfg)
        self.on_mode_change()
        prefix = key
        self.v_custom.set("")
        self.refresh_tree()
        self.tree.selection_set(prefix)
        self.tree.see(prefix)

    def delete_template(self):
        key = self.selected_key()
        if not key or key == "__newregion":
            if key == "__newregion" and self.cfg.get("story_new_region"):
                self.cfg["story_new_region"] = None
                save_cfg(self.cfg)
                self.refresh_tree()
            return
        custom = self.cfg.get("custom_templates", {})
        if not os.path.exists(tpl_path(key)) and key not in custom:
            return
        if not messagebox.askyesno(APP_NAME, f"删除 {key}？"):
            return
        if os.path.exists(tpl_path(key)):
            os.remove(tpl_path(key))
            meta = load_meta()
            meta.pop(key, None)
            save_meta(meta)
        custom.pop(key, None)
        if key in self.cfg.get("acc_order", []):
            self.cfg["acc_order"].remove(key)
            self.refresh_acc_hint()
        if key.startswith("m_"):
            for m in self.cfg.get("custom_modes", {}).values():
                if key in m.get("order", []):
                    m["order"].remove(key)
                if m.get("finish") == key:
                    m["finish"] = ""
        save_cfg(self.cfg)
        self.refresh_tree()
        self.on_mode_change()

    def grab_game(self, then):
        if not self.save_settings(quiet=True):
            return
        hwnd = find_window(self.cfg["window_title"])
        if not hwnd:
            messagebox.showerror(APP_NAME, "找不到游戏窗口。请先打开游戏，或到「设置」检查窗口标题")
            return
        self.root.iconify()

        def do():
            rect = client_rect(hwnd)
            img = grab(rect)
            self.root.deiconify()
            then(img, list(rect[2:]))

        self.root.after(500, do)

    def capture_template(self):
        key = self.selected_key()
        if key == "__newregion":
            return self.capture_new_region()
        if not key:
            messagebox.showinfo(APP_NAME, "先在列表里选中要截的模板")
            return
        if key.startswith(("uu_", "acc_")):  # 加速器的按钮在桌面上，截整个屏幕
            self.root.iconify()

            def do():
                img, _, _ = grab_screen()
                self.root.deiconify()

                def done(r):
                    x, y, w, h = r
                    ok, buf = cv2.imencode(".png", img[y:y + h, x:x + w])
                    if ok:
                        buf.tofile(tpl_path(key))
                        self.log(f"已保存模板 {key}（{w}×{h}）", "ok")
                        self.refresh_tree()

                RegionSelector(self.root, img, f"框选：{key}", done)

            self.root.after(500, do)
            return

        def then(img, size):
            def done(r):
                x, y, w, h = r
                ok, buf = cv2.imencode(".png", img[y:y + h, x:x + w])
                if ok:
                    buf.tofile(tpl_path(key))
                    meta = load_meta()
                    meta[key] = size[1]
                    save_meta(meta)
                    self.cfg["capture_size"] = size
                    save_cfg(self.cfg)
                    self.log(f"已保存模板 {key}（{w}×{h}）", "ok")
                    self.refresh_tree()

            RegionSelector(self.root, img, f"框选：{key}", done)

        self.grab_game(then)

    def capture_new_region(self):
        def then(img, size):
            def done(r):
                self.cfg["story_new_region"] = list(r)
                self.cfg["capture_size"] = size
                save_cfg(self.cfg)
                x, y, w, h = r
                tpl = prepare_templates(size[1], self.cfg).get("story_new")
                n = len(match_all(img[y:y + h, x:x + w], tpl, self.cfg["match_threshold"])) if tpl is not None else 0
                self.log(f"NEW 搜索范围已设定，范围内现在有 {n} 个 NEW", "ok")
                self.refresh_tree()

            RegionSelector(self.root, img, "框住剧情列表（不要框到右侧菜单和底部按钮）", done)

        self.grab_game(then)

    def test_match(self):
        def then(img, size):
            tpls = prepare_templates(size[1], self.cfg)
            thr = self.cfg["match_threshold"]
            self.log(f"测试识别（窗口 {size[0]}×{size[1]}，严格度 {thr}）")
            if not tpls:
                self.log("还没有任何模板", "warn")
            for k, t in sorted(tpls.items()):
                pt, score = match(img, t, thr)
                level = "ok" if pt else ("warn" if score >= thr - 0.1 else "info")
                self.log(f"{'✓' if pt else '  '} {k}  {score:.2f}", level)
            if "flow_jewel" in tpls:
                probe = Bot(self.cfg, lambda *a: None)
                probe.tpls = tpls
                probe.jewel_icon_full = tpls.get("flow_jewel")
                val = probe.jewel_read(img)
                if val is not None:
                    self.log(f"宝石数量读取：{val:,}（图标缩放 {probe.jewel_scale}）", "ok")
                else:
                    self.log(f"宝石数量读取：没读到（图标最高相似度 {probe.jewel_best:.2f}），"
                             f"请在主页测试；仍读不到就重截 flow_jewel", "warn")
            fan = read_fan_gain(img)
            if fan is not None:
                self.log(f"粉丝数读取：+{fan:,}", "ok")
            self.nb.select(0)

        self.grab_game(then)

    def refresh_acc_hint(self):
        if not hasattr(self, "lbl_acc"):
            return
        order = self.cfg.get("acc_order", [])
        if order:
            names = " → ".join(step_name(k)[4:] if k.startswith("acc_") else k for k in order)
            self.lbl_acc.configure(text=f"加速器按钮（按顺序点）：{names}。在「模板」页可增删和重截")
        else:
            self.lbl_acc.configure(text="默认按 UU 加速器的流程点击。\n"
                                        "用其他加速器（雷神、奇游等）：到「模板」页「添加按钮到」选「自动启动：加速器按钮（按顺序）」，\n"
                                        "把要点的按钮（例如「开始加速」「启动游戏」）按顺序加进去并截图。")

    def pick_game(self):
        p = filedialog.askopenfilename(title="选择 DMM 游戏快捷方式（桌面上的赛马娘图标）",
                                       filetypes=[("快捷方式或程序", "*.lnk *.url *.exe"), ("所有文件", "*.*")])
        if p:
            self.v_game_path.set(os.path.normpath(p))
            self.save_settings(quiet=True)

    def pick_uu(self):
        p = filedialog.askopenfilename(title="选择加速器（程序或桌面快捷方式）",
                                       filetypes=[("程序或快捷方式", "*.exe *.lnk"), ("所有文件", "*.*")])
        if p:
            self.v_uu_path.set(os.path.normpath(p))
            self.save_settings(quiet=True)

    def test_launch(self):
        if self.bot and self.bot.is_alive():
            messagebox.showinfo(APP_NAME, "请先停止正在运行的任务")
            return
        if not self.save_settings(quiet=True):
            return
        cfg = dict(self.cfg, _launch_test=True)
        self.bot = Bot(cfg, self.log, self.fans)
        self.bot.start()
        self.set_running(True)
        self.auto_minimize()
        self.nb.select(0)

    # ---------- 运行控制 ----------
    def start(self):
        if self.bot and self.bot.is_alive():
            return
        if not self.save_settings(quiet=True):
            return
        self.bot = Bot(self.cfg, self.log, self.fans)
        self.bot.start()
        self.set_running(True)
        self.auto_minimize()

    def stop(self):
        if self.bot:
            self.bot.stop_evt.set()

    def auto_minimize(self):
        """启动后缩到任务栏；停止后再弹回来。"""
        if self.cfg.get("minimize_on_start", True):
            self.minimized_by_me = True
            self.root.after(300, self.root.iconify)

    def set_running(self, running):
        self.btn_start.configure(state=DISABLED if running else NORMAL)
        self.btn_stop.configure(state=NORMAL if running else DISABLED)
        self.lbl_state.configure(text="运行中" if running else "待机中",
                                 bootstyle="inverse-warning" if running else "inverse-dark")
        if not running:
            self.lbl_next.configure(text="")
            if getattr(self, "minimized_by_me", False):
                self.minimized_by_me = False
                self.root.deiconify()

    def on_key(self, key):
        if pynput_kb and key == pynput_kb.Key.f10:
            self.stop()

    # ---------- 日志 ----------
    def log(self, msg, level="info"):
        self.log_q.put((time.strftime("%H:%M:%S"), level, msg))

    def clear_log(self):
        self.txt.configure(state=NORMAL)
        self.txt.delete("1.0", "end")
        self.txt.configure(state=DISABLED)

    def poll(self):
        if not self.log_q.empty():
            self.txt.configure(state=NORMAL)
            while not self.log_q.empty():
                ts, level, msg = self.log_q.get()
                self.txt.insert("end", ts + "  ", "time")
                self.txt.insert("end", msg + "\n", level)
            if int(self.txt.index("end-1c").split(".")[0]) > 2000:
                self.txt.delete("1.0", "500.0")
            self.txt.configure(state=DISABLED)
            if self.v_autoscroll.get():
                self.txt.see("end")

        if self.bot and not self.bot.is_alive():
            self.bot = None
            self.set_running(False)
        elif self.bot and self.bot.state_text:
            self.lbl_next.configure(text=self.bot.state_text)
        elif self.bot and self.bot.next_run:
            remain = max(0, int(self.bot.next_run - time.time()))
            at = time.strftime("%H:%M:%S", time.localtime(self.bot.next_run))
            self.lbl_next.configure(text=f"{self.bot.next_label} {at}（还剩 {remain // 60:02d}:{remain % 60:02d}）")
        elif self.bot:
            self.lbl_next.configure(text="正在操作游戏…")
        if self.fans.changed:
            self.fans.changed = False
            self.refresh_fans()
        self.root.after(200, self.poll)

    def on_close(self):
        self.stop()
        self.root.destroy()


def resource_path(name):
    """打包后从 exe 内部读取资源，未打包时从程序所在文件夹读取。"""
    return os.path.join(getattr(sys, "_MEIPASS", BASE), name)


def make_window():
    root = tb.Window(title=f"{APP_NAME}  {SUBTITLE}", themename="minty")
    # 优先使用 exe 旁边的 icon.ico，方便打包后直接替换
    ico = os.path.join(BASE, "icon.ico")
    if not os.path.exists(ico):
        ico = resource_path("icon.ico")
    if os.path.exists(ico):
        try:
            root.iconbitmap(default=ico)
        except Exception:
            pass
    try:
        from ttkbootstrap.style import ThemeDefinition
        root.style.register_theme(ThemeDefinition(name="uma", themetype="light", colors=PALETTE))
        root.style.theme_use("uma")
    except Exception:
        pass
    s = max(1.0, root.winfo_fpixels("1i") / 96)
    root.geometry(f"{int(1000 * s)}x{int(680 * s)}")
    root.minsize(int(880 * s), int(600 * s))
    return root


def fit_window(root):
    """按内容需要的大小打开窗口，保证文字都显示得完整；屏幕放不下就直接最大化。"""
    root.update_idletasks()
    need_w, need_h = root.winfo_reqwidth() + 20, root.winfo_reqheight() + 20
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight() - 60  # 扣掉任务栏
    cur_w, cur_h = root.winfo_width(), root.winfo_height()
    w, h = max(cur_w, need_w), max(cur_h, need_h)
    if w > sw or h > sh:
        try:
            root.state("zoomed")
            return
        except tk.TclError:
            w, h = min(w, sw), min(h, sh)
    root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
    root.minsize(min(need_w, sw), min(need_h, sh))


if __name__ == "__main__":
    app_root = make_window()
    App(app_root)
    fit_window(app_root)
    app_root.mainloop()

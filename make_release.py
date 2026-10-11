"""发布新版本前运行：python make_release.py "这次更新了什么"

会读 uma_bot.py 里的 VERSION，算出校验码，生成 version.json。
然后把 uma_bot.py 和 version.json 一起上传到 GitHub，用户打开软件就会收到更新提示。
"""
import hashlib
import json
import re
import sys

FILES = ["uma_bot.py"]  # 要一起更新的文件（相对于仓库根目录），例如再加 "templates/topbar_digits.npz"

src = open("uma_bot.py", encoding="utf-8").read()
compile(src, "uma_bot.py", "exec")  # 有语法错误就不要发布
ver = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M).group(1)
notes = " ".join(sys.argv[1:]).replace("\\n", "\n").strip()
info = {
    "version": ver,
    "notes": notes,
    "files": FILES,
    "sha256": {p: hashlib.sha256(open(p, "rb").read()).hexdigest() for p in FILES},
}
with open("version.json", "w", encoding="utf-8", newline="\n") as f:
    json.dump(info, f, ensure_ascii=False, indent=2)
print(f"已生成 version.json：v{ver}")
print(json.dumps(info, ensure_ascii=False, indent=2))

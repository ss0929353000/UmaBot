"""发布新版本前运行：python make_release.py

会读 uma_bot.py 里的 VERSION 和 CHANGELOG（更新公告），算出校验码，生成 version.json。
更新提示里显示的内容就是 CHANGELOG 最上面那一条；也可以在后面加文字临时改写：
    python make_release.py "这次更新了什么"
然后把 uma_bot.py 和 version.json 一起上传到 GitHub，用户打开软件就会收到更新提示。
"""
import ast
import hashlib
import json
import re
import sys

FILES = ["uma_bot.py"]  # 要一起更新的文件（相对于仓库根目录），例如再加 "templates/topbar_digits.npz"

src = open("uma_bot.py", encoding="utf-8").read()
tree = ast.parse(src, "uma_bot.py")  # 有语法错误就不要发布
ver = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M).group(1)

changelog = []
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "CHANGELOG" for t in node.targets):
        changelog = ast.literal_eval(node.value)

notes = " ".join(sys.argv[1:]).replace("\\n", "\n").strip()
if not notes:
    entry = next((e for e in changelog if e[0] == ver), None)
    if not entry:
        sys.exit(f"CHANGELOG 里没有 v{ver} 的更新内容：请先在 uma_bot.py 的 CHANGELOG 最上面加一条")
    notes = "\n".join(entry[2])

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

# -*- coding: utf-8 -*-
"""临时探针：在 CI 上诊断 CartoonHelp 构造失败（用完即删）。"""
import sys
import traceback

sys.path.insert(0, "src")

import tkinter as tk

from ulpp.ui.calibrate import CartoonHelp
from ulpp.ui.flow import Flow
from ulpp.ui.shell import Shell

print("default root before:", tk._default_root)
root = tk.Tk()
root.withdraw()
print("default root after Tk():", tk._default_root)
shell = Shell(root, flow=Flow(), lang=None)
root.update_idletasks()
try:
    win = CartoonHelp(shell)
    import inspect
    print("constructed; attrs:", sorted(vars(win)))
    print("class:", type(win).__module__, type(win).__name__)
    print("class methods:", [n for n in sorted(vars(type(win)))
                             if not n.startswith("__")])
    print("init source:\n", inspect.getsource(type(win).__init__)[:400])
    win.show(1)
    print("show ok; playing:", win.playing)
except Exception:
    traceback.print_exc()
root.destroy()
print("default root after destroy:", tk._default_root)

for i in range(2):
    r = tk.Tk()
    r.withdraw()
    s = Shell(r, flow=Flow(), lang=None)
    w = CartoonHelp(s)
    r.destroy()
    print("round", i, "default:", tk._default_root)

r = tk.Tk()
r.withdraw()
s = Shell(r, flow=Flow(), lang=None)
try:
    w = CartoonHelp(s)
    print("final attrs:", sorted(vars(w))[:5])
except Exception:
    traceback.print_exc()
r.destroy()

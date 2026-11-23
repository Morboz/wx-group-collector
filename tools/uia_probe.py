# -*- coding: utf-8 -*-
"""诊断微信 4.x UIA 控件树是否可访问。

1. 找到微信主窗口
2. 统计 UIA 子节点数(微信健康状态应为几十上百,2 = Qt 无障碍未加载)
3. 用 MSAA/WM_GETOBJECT 方式主动"戳"一下窗口,再统计一次
"""
import sys
import time

sys.path.insert(0, r"F:\dev\wx-group-collector\.venv\Lib\site-packages")

import win32gui
import win32con
import win32api
import comtypes
from wx4py.core import uiautomation as uia


def find_wechat_hwnd():
    result = []

    def cb(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        if "微信" in title and "Qt" in cls:
            result.append((hwnd, title, cls))

    win32gui.EnumWindows(cb, None)
    return result


def count_descendants(ctrl, max_depth=6, limit=500):
    count = 0
    stack = [(ctrl, 0)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if count >= limit:
            return count
        if depth >= max_depth:
            continue
        try:
            for ch in node.GetChildren():
                stack.append((ch, depth + 1))
        except Exception:
            pass
    return count


def poke_msaa(hwnd):
    """通过 WM_GETOBJECT / AccessibleObjectFromWindow 触发 Qt 懒加载无障碍树。"""
    import ctypes
    from ctypes import POINTER, byref, c_long
    import comtypes.client

    OBJID_CLIENT = 0xFFFFFFFC
    IID_IAccessible = comtypes.GUID("{618736e0-3c3d-11cf-810c-00aa00389b71}")

    class POINT( ctypes.Structure ):
        _fields_ = [("x", c_long), ("y", c_long)]

    acc = ctypes.POINTER(comtypes.IUnknown)()
    hr = ctypes.windll.oleacc.AccessibleObjectFromWindow(
        hwnd, OBJID_CLIENT, byref(IID_IAccessible), byref(acc)
    )
    return hr


def main():
    wins = find_wechat_hwnd()
    if not wins:
        print("未找到微信窗口(标题含'微信'且类名含'Qt')")
        return
    for hwnd, title, cls in wins:
        print(f"窗口: HWND={hwnd} title={title!r} class={cls!r}")

    hwnd = wins[0][0]
    root = uia.ControlFromHandle(hwnd)
    if root is None:
        print("UIA ControlFromHandle 失败")
        return
    n1 = count_descendants(root)
    print(f"UIA 节点数(查询前): {n1}")

    print("发送 WM_GETOBJECT / MSAA 查询触发懒加载...")
    poke_msaa(hwnd)
    time.sleep(2)

    root2 = uia.ControlFromHandle(hwnd)
    n2 = count_descendants(root2) if root2 else -1
    print(f"UIA 节点数(戳过之后): {n2}")

    if n2 > 5:
        print("结论: 懒加载有效,控件树可用")
        # 列出前两层子控件名称,验证可读性
        try:
            for ch in root2.GetChildren():
                print("  L1:", ch.ClassName, repr(ch.Name)[:40])
                for gc in ch.GetChildren()[:5]:
                    print("    L2:", gc.ClassName, repr(gc.Name)[:40])
        except Exception as e:
            print("遍历失败:", e)
    else:
        print("结论: 控件树仍未加载")


if __name__ == "__main__":
    main()

"""
Modern Native Folder Dialog Picker
Uses Windows COM IFileOpenDialog (FOS_PICKFOLDERS) for 100% modern Explorer UI on Windows 10/11,
with automatic fallback to Tkinter askdirectory on other platforms.
"""
import sys
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("houmi-folder-dialog")

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes, Structure, byref, c_void_p, c_ulong, c_wchar_p, POINTER, WINFUNCTYPE, HRESULT

    class GUID(Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8),
        ]

    CLSID_FileOpenDialog = GUID(0xDC1C5A9C, 0xE88A, 0x4DDE, (wintypes.BYTE * 8)(0xA5, 0xA1, 0x60, 0xF8, 0x2A, 0x20, 0xAE, 0xF7))
    IID_IFileOpenDialog = GUID(0x42F85136, 0xDB7E, 0x439C, (wintypes.BYTE * 8)(0x85, 0xF1, 0xE4, 0x07, 0x5D, 0x13, 0x5F, 0xC8))
    IID_IShellItem = GUID(0x43826D1E, 0xE718, 0x42EE, (wintypes.BYTE * 8)(0xBC, 0x55, 0xA1, 0xE2, 0x61, 0xC3, 0x7B, 0xFE))

    ole32 = ctypes.oledll.ole32
    shell32 = ctypes.windll.shell32


def ask_modern_folder_dialog(
    title: str = "เลือกโฟลเดอร์",
    initialdir: Optional[str] = None,
) -> Optional[str]:
    """
    Opens modern Windows Explorer folder picker (IFileOpenDialog) with navigation pane,
    breadcrumbs, and quick access.
    """
    if sys.platform == "win32":
        try:
            ole32.CoInitialize(None)
            p_dialog = c_void_p()
            hr = ole32.CoCreateInstance(
                byref(CLSID_FileOpenDialog),
                None,
                1,  # CLSCTX_INPROC_SERVER
                byref(IID_IFileOpenDialog),
                byref(p_dialog),
            )
            if hr == 0 and p_dialog:
                try:
                    vptr = ctypes.cast(p_dialog, POINTER(POINTER(c_void_p))).contents

                    # SetOptions (index 9): FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM
                    SetOptions_Proto = WINFUNCTYPE(HRESULT, c_void_p, c_ulong)
                    SetOptions = SetOptions_Proto(vptr[9])
                    FOS_PICKFOLDERS = 0x00000020
                    FOS_FORCEFILESYSTEM = 0x00000040
                    SetOptions(p_dialog, FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM)

                    # SetTitle (index 17)
                    if title:
                        SetTitle_Proto = WINFUNCTYPE(HRESULT, c_void_p, c_wchar_p)
                        SetTitle = SetTitle_Proto(vptr[17])
                        SetTitle(p_dialog, title)

                    # SetFolder (index 12)
                    if initialdir and Path(initialdir).is_dir():
                        p_item = c_void_p()
                        hr_item = shell32.SHCreateItemFromParsingName(
                            str(initialdir), None, byref(IID_IShellItem), byref(p_item)
                        )
                        if hr_item == 0 and p_item:
                            SetFolder_Proto = WINFUNCTYPE(HRESULT, c_void_p, c_void_p)
                            SetFolder = SetFolder_Proto(vptr[12])
                            SetFolder(p_dialog, p_item)
                            
                            # Release p_item
                            item_vptr = ctypes.cast(p_item, POINTER(POINTER(c_void_p))).contents
                            Release_Proto = WINFUNCTYPE(c_ulong, c_void_p)
                            Release_Proto(item_vptr[2])(p_item)

                    # Show (index 3) with foreground window as parent to guarantee top visibility
                    Show_Proto = WINFUNCTYPE(HRESULT, c_void_p, wintypes.HWND)
                    Show = Show_Proto(vptr[3])
                    user32 = ctypes.windll.user32
                    hwnd_parent = user32.GetForegroundWindow() or None
                    hr_show = Show(p_dialog, hwnd_parent)

                    if hr_show == 0:  # S_OK
                        # GetResult (index 20)
                        GetResult_Proto = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))
                        GetResult = GetResult_Proto(vptr[20])
                        p_res_item = c_void_p()
                        hr_res = GetResult(p_dialog, byref(p_res_item))
                        if hr_res == 0 and p_res_item:
                            try:
                                res_vptr = ctypes.cast(p_res_item, POINTER(POINTER(c_void_p))).contents
                                # IShellItem::GetDisplayName (index 5)
                                GetDisplayName_Proto = WINFUNCTYPE(HRESULT, c_void_p, c_ulong, POINTER(c_wchar_p))
                                GetDisplayName = GetDisplayName_Proto(res_vptr[5])
                                pszPath = c_wchar_p()
                                SIGDN_FILESYSPATH = 0x80058000
                                hr_name = GetDisplayName(p_res_item, SIGDN_FILESYSPATH, byref(pszPath))
                                if hr_name == 0 and pszPath.value:
                                    selected_path = str(pszPath.value)
                                    ole32.CoTaskMemFree(pszPath)
                                    return selected_path
                            finally:
                                Release_Proto = WINFUNCTYPE(c_ulong, c_void_p)
                                Release_Proto(res_vptr[2])(p_res_item)
                finally:
                    Release_Proto = WINFUNCTYPE(c_ulong, c_void_p)
                    Release_Proto(vptr[2])(p_dialog)
        except Exception as exc:
            logger.warning("IFileOpenDialog COM call failed: %s. Using Tkinter fallback...", exc)
        finally:
            try:
                ole32.CoUninitialize()
            except Exception:
                pass

    # Fallback to Tkinter filedialog
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title=title, initialdir=initialdir)
        root.destroy()
        if selected and Path(selected).is_dir():
            return selected
    except Exception as tk_exc:
        logger.warning("Tkinter askdirectory failed: %s", tk_exc)

    return None

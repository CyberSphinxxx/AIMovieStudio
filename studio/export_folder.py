"""Reveal a verified finished movie by asset ID, never by a client-supplied path."""

import os
import ctypes
from ctypes import wintypes

from studio.storage import digest


def open_selected_file(path):
    """Use the documented shell API with a full item ID and cidl=0."""
    ole = ctypes.OleDLL("ole32")
    shell = ctypes.OleDLL("shell32")
    ole.CoInitialize.argtypes = [ctypes.c_void_p]
    ole.CoInitialize.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    shell.SHParseDisplayName.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    shell.SHParseDisplayName.restype = ctypes.c_long
    shell.SHOpenFolderAndSelectItems.argtypes = [
        ctypes.c_void_p,
        wintypes.UINT,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    shell.SHOpenFolderAndSelectItems.restype = ctypes.c_long
    initialized = False
    item = ctypes.c_void_p()
    try:
        try:
            ole.CoInitialize(None)
            initialized = True
        except OSError as error:
            # This thread may already use MTA. Do not change its apartment or uninitialize it.
            if getattr(error, "winerror", 0) & 0xFFFFFFFF != 0x80010106:
                raise
        shell.SHParseDisplayName(str(path), None, ctypes.byref(item), 0, None)
        shell.SHOpenFolderAndSelectItems(item, 0, None, 0)
    finally:
        if item.value:
            ole.CoTaskMemFree(item)
        if initialized:
            ole.CoUninitialize()


def reveal_export(store, asset_id):
    path, asset = store.asset_path(asset_id)
    if asset["role"] not in {"export", "export-edition", "export-variant"} or path.suffix.lower() != ".mp4":
        raise ValueError("Only finished MP4 exports can be shown in a folder")
    if not path.is_file() or digest(path) != asset["sha256"]:
        raise ValueError("Export is missing or changed; keep the original and review diagnostics")
    if os.name != "nt":
        raise RuntimeError("FOLDER_UNAVAILABLE: Show in folder currently requires Windows")
    try:
        open_selected_file(path)
    except OSError as error:
        raise RuntimeError(
            "FOLDER_UNAVAILABLE: File Explorer could not be opened; download the MP4 instead"
        ) from error
    # A launch request is observable; do not claim the external window is visible.
    return {"asset_id": asset_id, "launch_requested": True}

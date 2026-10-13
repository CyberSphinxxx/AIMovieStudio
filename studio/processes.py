"""Own child process lifetimes without modifying Windows system settings."""

import ctypes
import os
from contextlib import contextmanager
from ctypes import wintypes


@contextmanager
def owned_process(process, *, completed_leaf=False):
    handle = None
    if os.name == "nt":

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t),
                ("active_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class IOCounters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in ["reads", "writes", "other", "read_bytes", "write_bytes", "other_bytes"]
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io", IOCounters),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateJobObjectW(None, None)
        info = ExtendedLimits()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        configured = handle and kernel.SetInformationJobObject(
            handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        )
        assigned = configured and kernel.AssignProcessToJobObject(
            handle, wintypes.HANDLE(int(process._handle))
        )
        if not assigned:
            error = ctypes.get_last_error()
            # A trusted short-lived media leaf may finish before job assignment.
            # Do not generalize this exception to arbitrary processes or live children.
            if configured and completed_leaf and error == 5 and process.poll() is not None:
                kernel.CloseHandle(handle)
                handle = None
            else:
                process.terminate()
                process.wait(timeout=5)
                if handle:
                    kernel.CloseHandle(handle)
                raise RuntimeError(f"PROCESS_CONTAINMENT_FAILED: Windows job error {error}")
    try:
        yield process
    finally:
        if handle:
            kernel.CloseHandle(handle)

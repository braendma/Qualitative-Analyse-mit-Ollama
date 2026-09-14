"""Supervisor-only Windows job: contain descendants before starting any child.

The job handle lives until supervisor exit. Closing it also terminates the
supervisor, so it must never be used in the desktop/main analysis process.
"""
import ctypes
from ctypes import wintypes
import os
import time


class SupervisorJob:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Windows process jobs are available only on Windows.')
        k = self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        prototypes = {
            'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            'QueryInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            'GetCurrentProcess': ([], wintypes.HANDLE),
            'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            'IsProcessInJob': ([wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
            'TerminateProcess': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in prototypes.items():
            function = getattr(k, name); function.argtypes = args; function.restype = result
        class BasicLimits(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', wintypes.DWORD), ('min_working', ctypes.c_size_t), ('max_working', ctypes.c_size_t),
                ('active_limit', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('basic', BasicLimits), ('io', ctypes.c_uint64 * 6),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits(); limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error(); k.CloseHandle(self.handle); raise ctypes.WinError(error)
        if not k.AssignProcessToJobObject(self.handle, k.GetCurrentProcess()):
            error = ctypes.get_last_error(); k.CloseHandle(self.handle); raise ctypes.WinError(error)
        # Deliberately no __del__/CloseHandle: this handle contains our own process.

    def descendants(self):
        capacity = 32
        while capacity <= 65536:
            class ProcessList(ctypes.Structure):
                _fields_ = [('assigned', wintypes.DWORD), ('count', wintypes.DWORD),
                            ('pids', ctypes.c_size_t * capacity)]
            value = ProcessList()
            ok = self.kernel.QueryInformationJobObject(self.handle, 3, ctypes.byref(value), ctypes.sizeof(value), None)
            error = ctypes.get_last_error()
            if ok and value.count >= value.assigned:
                return [pid for pid in value.pids[:value.count] if pid != os.getpid()]
            if not ok and error != 234:  # ERROR_MORE_DATA
                raise ctypes.WinError(error)
            capacity = max(capacity * 2, value.assigned)
        raise RuntimeError('Zu viele Prozesse für eine sichere Abschlussprüfung.')

    def stop_descendants(self, timeout=15):
        deadline = time.monotonic() + timeout
        while True:
            pids = self.descendants()
            if not pids:
                return
            for pid in pids:
                handle = self.kernel.OpenProcess(0x100001 | 0x1000, False, pid)
                if not handle:
                    continue  # May have exited after the snapshot; recheck the job.
                try:
                    inside = wintypes.BOOL()
                    if not self.kernel.IsProcessInJob(handle, self.handle, ctypes.byref(inside)):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if inside.value:  # Recheck ownership on this handle, avoiding PID reuse.
                        self.kernel.TerminateProcess(handle, 130)
                        self.kernel.WaitForSingleObject(handle, 100)
                finally:
                    self.kernel.CloseHandle(handle)
            if time.monotonic() >= deadline:
                raise RuntimeError('Prozessende konnte nicht vollständig bestätigt werden.')
            time.sleep(.02)

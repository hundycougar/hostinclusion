"""HostInclusion: Distributed host daemon for remote terminal sessions and resource access over Tailscale."""

import ctypes
import os
import sys

# On Android Termux, pre-load compiler-rt to provide emulated TLS (__emutls_v) for Rust extensions like pydantic_core
if "com.termux" in sys.executable or "TERMUX_VERSION" in os.environ or os.path.exists("/data/data/com.termux"):
    prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    for rt_name in ("libclang_rt.builtins-aarch64-android.so", "libclang_rt.builtins-arm-android.so"):
        rt_path = os.path.join(prefix, "lib", rt_name)
        if os.path.exists(rt_path):
            try:
                ctypes.CDLL(rt_path, mode=ctypes.RTLD_GLOBAL)
                break
            except Exception:
                pass

__version__ = "0.1.0"

"""Make app-local NVIDIA runtime DLLs visible to CTranslate2 on Windows."""

import os
from pathlib import Path
import sys


_directory_handles = []
_configured = False


def prepare_gpu_runtime() -> list[str]:
    global _configured
    if os.name != "nt" or _configured:
        return []
    roots = [Path(sys.prefix) / "Lib" / "site-packages"]
    if getattr(sys, "frozen", False):
        roots.insert(0, Path(sys._MEIPASS))
    directories = []
    for root in roots:
        for package in ("cuda_runtime", "cuda_nvrtc", "cublas", "cudnn"):
            path = root / "nvidia" / package / "bin"
            if path.is_dir():
                directories.append(str(path))
                # Retain handles for the entire process lifetime.
                _directory_handles.append(os.add_dll_directory(str(path)))
    if directories:
        # CTranslate2 and cuDNN also use LoadLibrary by name for optional DLLs.
        os.environ["PATH"] = os.pathsep.join(directories + [os.environ.get("PATH", "")])
    _configured = True
    return directories

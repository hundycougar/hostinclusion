#!/usr/bin/env python3
import os
import pathlib
import plistlib
import subprocess
import sys

def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    venv_python = root / ".venv" / "bin" / "python"
    
    if not venv_python.exists():
        # Fall back to sys.executable if .venv doesn't exist
        venv_python = pathlib.Path(sys.executable)

    plist_dir = pathlib.Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "com.hostinclusion.daemon.plist"

    data = {
        "Label": "com.hostinclusion.daemon",
        "ProgramArguments": [
            str(venv_python),
            "-m",
            "hostinclusion.daemon",
            "--host",
            "0.0.0.0",
            "--port",
            "8765",
        ],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": "/tmp/hostinclusion.stdout.log",
        "StandardErrorPath": "/tmp/hostinclusion.stderr.log",
    }

    plist_path.write_bytes(plistlib.dumps(data))
    print(f"Created LaunchAgent plist at: {plist_path}")

    # Unload first if previously loaded
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    
    # Load
    res = subprocess.run(["launchctl", "load", "-w", str(plist_path)], capture_output=True, text=True)
    if res.returncode == 0:
        print("Successfully loaded LaunchAgent com.hostinclusion.daemon!")
        print("Logs: tail -f /tmp/hostinclusion.stdout.log")
    else:
        print(f"launchctl load output: {res.stderr or res.stdout}")

if __name__ == "__main__":
    main()

"""Keepalive: tells Windows the system is always busy (blocks Modern Standby).
Runs forever in background. ES_CONTINUOUS | ES_SYSTEM_REQUIRED.
"""
import ctypes
import time

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040

ctypes.windll.kernel32.SetThreadExecutionState(
    ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
)
from pathlib import Path

log = Path(__file__).parent / "data" / "keepalive.log"
with open(log, "a", encoding="utf-8") as f:
    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} keepalive started\n")

while True:
    # re-assert every 5 min (cheap, defensive)
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    time.sleep(300)

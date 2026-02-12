import os
import time
from datetime import datetime as dt
from pathlib import Path

USER = "hallamlab"
MODULE_ROOT = Path(os.path.realpath(__file__)).parent
NAME = MODULE_ROOT.name.lower()
ENTRY_POINTS = [NAME]

def _get_version() -> str:
    with open(MODULE_ROOT.joinpath("version.txt")) as v:
        return v.readline().strip()
VERSION = _get_version()

class StdTime:
    FORMAT = '%Y-%m-%d_%H-%M-%S'

    @classmethod
    def Timestamp(cls, timestamp: dt|None = None):
        ts = dt.now() if timestamp is None else timestamp
        return f"{ts.strftime(StdTime.FORMAT)}"
    
    @classmethod
    def Parse(cls, timestamp: str|int):
        if isinstance(timestamp, str):
            return dt.strptime(timestamp, StdTime.FORMAT)
        else:
            return dt.fromtimestamp(timestamp/1000)
    
    @classmethod
    def CurrentTimeMillis(cls):
        return round(time.time() * 1000)
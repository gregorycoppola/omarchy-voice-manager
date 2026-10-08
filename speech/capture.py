"""Capture child: close the device if its preview parent dies or the hold ended."""
import ctypes
import os
from pathlib import Path
import signal
import sys


def main():
    parent=int(sys.argv[1])
    libc=ctypes.CDLL(None,use_errno=True)
    # Linux PR_SET_PDEATHSIG survives exec of pw-record.
    if libc.prctl(1,signal.SIGKILL,0,0,0)!=0:
        raise OSError(ctypes.get_errno(),'Cannot bind recorder lifetime to preview')
    if os.getppid()!=parent:return
    gate=Path(os.environ['XDG_RUNTIME_DIR'])/'skipper-voice-held'
    if gate.read_text().strip()!='1':return
    os.execvp('pw-record',['pw-record','--latency=10ms','--rate=16000','--channels=1',
                          '--format=s16','--raw','--sample-count=480000','-'])


if __name__=='__main__':main()

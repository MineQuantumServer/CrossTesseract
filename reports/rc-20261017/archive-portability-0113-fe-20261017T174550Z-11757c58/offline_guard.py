import sys,runpy,os,json
from pathlib import Path
origin=Path(sys.argv[1]);root=Path(sys.argv[2]);script=Path(sys.argv[3]);args=sys.argv[4:]
sys.dont_write_bytecode=True
def guard(event,values):
 if event=="open" and isinstance(values[0],(str,bytes,os.PathLike)):
  p=Path(os.fsdecode(values[0]));p=(Path.cwd()/p).resolve() if not p.is_absolute() else p.resolve()
  if p.is_relative_to(origin):raise PermissionError("Original repository inaccessible during isolated archive reproduction")
 if event in ("subprocess.Popen","socket.__new__","os.system","os.exec","os.posix_spawn"):
  raise PermissionError("Offline archive-only reproduction forbids process/network actions")
sys.addaudithook(guard)
try:open(origin/"scratch/portability-deny-self-check","rb")
except PermissionError:print("ORIGINAL_REPOSITORY_AND_SCRATCH_DENIED",flush=True)
else:raise AssertionError("Original scratch unexpectedly accessible")
os.chdir(root);sys.argv=[str(script),*args];runpy.run_path(str(script),run_name="__main__")

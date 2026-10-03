#!/usr/bin/env python3
"""Freeze a NeoForge development launch while holding the shared build lock.
Restart tests must never load a directory that Gradle is simultaneously rebuilding.
"""
from pathlib import Path
import shutil,sys,uuid
root=Path(__file__).resolve().parents[1]
script=root/sys.argv[1]
if script.parent!=root/'build/moddev' or not script.is_file():raise ValueError('generated local launch script required')
match=script.name.replace('runServer','server').replace('.sh','RunVmArgs.txt')
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:
        argv=(proc/'cmdline').read_bytes().split(b'\0')
        if argv and argv[0].endswith(b'/java') and any(match.encode() in arg for arg in argv):raise RuntimeError('previous Minecraft process still running; wait for complete shutdown')
    except (FileNotFoundError,PermissionError):pass
directory=root/'scratch/dev-launch'/uuid.uuid4().hex
directory.mkdir(parents=True)
text=script.read_text()
for source,name in ((root/'build/classes/java/main','classes'),(root/'build/resources/main','resources')):
    if not source.is_dir():raise ValueError('build outputs missing; compile first')
    shutil.copytree(source,directory/name);text=text.replace(str(source),str(directory/name))
for argument in ('RunClasspath.txt','RunVmArgs.txt','RunProgramArgs.txt'):
    paths=[p for p in (root/'build/moddev').glob('*'+argument) if str(p) in text]
    if len(paths)!=1:raise ValueError('unrecognized generated launch format')
    p=paths[0];shutil.copy2(p,directory/p.name);text=text.replace(str(p),str(directory/p.name))
# Keep recognizable filenames in argv for the isolated fault-test process matcher.
launcher=directory/script.name;launcher.write_text(text);print(launcher)

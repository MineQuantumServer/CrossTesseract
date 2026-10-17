#!/usr/bin/env python3
"""Compile a pinned, opt-in test agent. It never enters the shipped mod JAR."""
from pathlib import Path
import hashlib,json,subprocess,zipfile,uuid,shutil,urllib.request

ROOT=Path(__file__).resolve().parents[1]
ASM_SHA='876eab6a83daecad5ca67eb9fcabb063c97b5aeb8cf1fca7a989ecde17522051'
def main():
    out=ROOT/'scratch/rc-probe'/uuid.uuid4().hex;out.mkdir(parents=True)
    candidates=list((Path.home()/'.gradle/caches/modules-2/files-2.1/org.ow2.asm/asm/9.8').glob('*/*.jar'))
    asm=out/'asm-9.8.jar'
    if candidates:shutil.copyfile(candidates[0],asm)
    else:
        with urllib.request.urlopen('https://repo.maven.apache.org/maven2/org/ow2/asm/asm/9.8/asm-9.8.jar',timeout=60) as stream:asm.write_bytes(stream.read(1048576))
    assert hashlib.sha256(asm.read_bytes()).hexdigest()==ASM_SHA
    jdk=ROOT/'scratch/jdk/jdk-21.0.8+9/bin';classes=out/'classes';classes.mkdir()
    sources=sorted((ROOT/'scripts/rcprobe').glob('*.java'))
    subprocess.run([str(jdk/'javac'),'--release','21','-cp',str(asm),'-d',str(classes),*[str(p) for p in sources]],check=True)
    subprocess.run([str(jdk/'java'),'-Xverify:all','-cp',str(classes),'dev.crosstesseract.rcprobe.WindowStats'],check=True)
    subprocess.run([str(jdk/'java'),'-Xverify:all','-cp',str(classes)+':'+str(asm),'dev.crosstesseract.rcprobe.ProbeSelfTest'],check=True)
    for suffix,klass in [('stats','WindowStats'),('agent','ProbeAgent')]:
        path=out/('rc-probe-'+suffix+'.jar')
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            if suffix=='agent':z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: dev.crosstesseract.rcprobe.ProbeAgent\nClass-Path: asm-9.8.jar\n\n')
            for p in sorted(classes.rglob(klass+'*.class')):z.write(p,str(p.relative_to(classes)))
    result={'schema':2,'recorder_revision':'v2_mod_roots','test_agent':True,'mod_JAR_modified':False,'directory':str(out),'ASM':{'version':'9.8','sha256':ASM_SHA,'license':'BSD-3-Clause; external test dependency, not included in mod'},'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'artifacts':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.glob('*.jar'))]}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

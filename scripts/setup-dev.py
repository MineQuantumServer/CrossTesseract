#!/usr/bin/env python3
"""Create isolated development configs without overwriting existing world/config files."""
from pathlib import Path
import argparse
import uuid

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--accept-eula',action='store_true',help='You have read and accepted the Minecraft EULA')
parser.add_argument('--cluster',default='dev_three_v1')
args=parser.parse_args()
if not args.cluster.startswith(('dev_','test_')): raise ValueError('development clusters only')
def backend(cluster,server):
    return f'''backend.enabled=true
cluster.id={cluster}
server.id={server}
mysql.url=jdbc:mysql://127.0.0.1:13306/cross_tesseract?sslMode=DISABLED&allowPublicKeyRetrieval=true&connectTimeout=1500&socketTimeout=3000
mysql.user=ct_dev
mysql.password=ct_dev_only
redis.uri=redis://127.0.0.1:16379
chunkLoading.maxPerPlayer=2
'''
def create(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists(): path.write_text(text)
for i,suffix in enumerate(('A','B','C','perf')):
    directory=ROOT/f'run-{suffix}'
    create(directory/'cross-tesseract.properties',backend(args.cluster if suffix!='perf' else 'dev_perf_v1',f'dev-{suffix}'))
    create(directory/'server.properties',f'''server-port={25565+i}
server-ip=127.0.0.1
online-mode=true
enable-rcon=true
rcon.port={25575+i}
rcon.password=ct_dev_rcon_only
level-type=minecraft:flat
generator-settings={{"biome":"minecraft:plains","layers":[{{"block":"minecraft:bedrock","height":1}},{{"block":"minecraft:dirt","height":2}},{{"block":"minecraft:grass_block","height":1}}]}}
view-distance=3
simulation-distance=3
spawn-chunk-radius=0
max-players=4
motd=CrossServer Tesseract isolated development
''')
    if args.accept_eula:create(directory/'eula.txt','eula=true\n')
create(ROOT/'config/gametest.properties',backend('test_gametest_'+uuid.uuid4().hex[:10],'gametest'))
print('Existing files preserved. Minecraft startup requires an accepted EULA in each run directory.')

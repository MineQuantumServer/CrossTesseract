#!/usr/bin/env python3
"""Read-only audit of the retained128FE from the exact68 fallback validator failure.
Uses only the isolated ct-dev-mysql backend and frozen failed-report UUIDs.
Never inputs, extracts, refunds, resets or changes worlds/SQL.
Refuses to overwrite an audit report. SQL LOCAL and WAL are mirrors, not additive assets.
"""
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec
import json,hashlib,datetime,sys,argparse
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'scripts'))
parser=argparse.ArgumentParser();parser.add_argument('--output',default='reports/optimization-restart-fallback-first-failure-audit.json');args=parser.parse_args()
src=root/'reports/optimization-restart-fallback-68f32db-20261006T192436Z-9e30ef6d.json';failed_raw=src.read_bytes();assert hashlib.sha256(failed_raw).hexdigest()=='1e4b7550dafad1382009a3cceb4658cf5d71eccd37c4aaf269ef1a82d30d15f7';failed=json.loads(failed_raw)
def module(name,file):
 s=spec_from_file_location(name,root/'scripts'/file);m=module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
b=module('failure_audit_bench','optimization-benchmark.py');t=module('failure_audit_top','optimization-topology-test.py');f=module('failure_audit_wal','optimization-restart-fallback-test.py')
fixture=failed['fixtures'][0];channel=fixture['channel'];endpoints=fixture['sources']+fixture['sinks']
assert len(failed['business_events'])==1 and failed['business_events'][0]['actual_FE']==128 and failed['business_events'][0]['kind']=='input'
assert not failed['config_switches']
rows=b.sql("SELECT 'transfer',transfer_id,endpoint_id,resource_id,kind,state,CAST(amount AS CHAR),CAST(remaining AS CHAR),CAST(epoch AS CHAR) FROM ct_transfers WHERE cluster_id='dev_three_v1' AND channel_id='"+channel+"' UNION ALL SELECT 'balance',resource_id,'',resource_id,'','',CAST(amount AS CHAR),'0','0' FROM ct_balances WHERE cluster_id='dev_three_v1' AND channel_id='"+channel+"' ORDER BY 1,2")
assets=t.asset_totals(rows);assert assets['pool']==0 and assets['owned']==128 and assets['deposited']==128 and not assets['quarantined']
transfers=assets['transfers'];assert len(transfers)==2 and {x['kind'] for x in transfers}=={'DEPOSIT','ALLOCATE'}
assert all(x['state']==('COMMITTED' if x['kind']=='DEPOSIT' else 'LOCAL') for x in transfers)
ids=','.join("'"+x['id']+"'" for x in endpoints)
ep_rows=b.sql("SELECT endpoint_id,server_id,world_id,COALESCE(channel_id,''),state,checkpoint,last_epoch,recovery_generation FROM ct_endpoints WHERE cluster_id='dev_three_v1' AND endpoint_id IN ("+ids+") ORDER BY endpoint_id")
assert len(ep_rows)==2 and all(row[3]==channel and row[4]=='ACTIVE' for row in ep_rows)
server_ids=[failed['identity'][x]['server_id'] for x in 'ABC'];server_list=','.join("'"+x+"'" for x in server_ids)
server_rows=b.sql("SELECT server_id,world_id,session_id,fencing_epoch,status,clean_stop,lease_until>CURRENT_TIMESTAMP(6) FROM ct_servers WHERE cluster_id='dev_three_v1' AND server_id IN ("+server_list+") ORDER BY server_id")
assert len(server_rows)==3 and all(row[4:]==['STOPPED','1','0'] for row in server_rows)
wals=[]
for endpoint in endpoints:
 path=root/('run-'+endpoint['server'])/failed['identity'][endpoint['server']]['level_name']/'cross_tesseract/journal'/(endpoint['id']+'.ctj')
 assert path.is_file() and not path.is_symlink() and path.stat().st_size<=8388608
 raw=path.read_bytes();wal=f.decode_fe_wal(raw);row=next(row for row in ep_rows if row[0]==endpoint['id'])
 assert wal['endpoint']==endpoint['id'] and wal['world']==row[2] and wal['generation']==int(row[7]) and wal['revision']<=int(row[5]) and not wal['deposits']
 credits=wal['credits'];expected=128 if endpoint['id']==fixture['sinks'][0]['id'] else 0
 assert sum(x['remaining'] for x in credits)==expected
 wals.append({'path':str(path.relative_to(root)),'sha256':hashlib.sha256(raw).hexdigest(),'decoded':wal})
report={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'failed_report':str(src.relative_to(root)),'failed_report_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'read_only':True,'native_test_status':'FAILED_VALIDATOR_BEFORE_CONFIG_SWITCH','confirmed_actual_input_FE':128,'confirmed_actual_output_FE':0,'ownership':{'SQL_available':0,'SQL_exclusive_LOCAL':128,'WAL_mirror_of_SQL_LOCAL':128,'total_effective_asset_FE':128,'mirrors_not_added':True},'transfers':transfers,'endpoint_rows':ep_rows,'stopped_servers':server_rows,'WAL':wals,'decision':'Keep this fixture untouched. Corrected test must use fresh IDs, no original input/pull replay. Recheck original ownership after recovery.'}
p=root/args.output;assert p.parent==root/'reports' and not p.exists();p.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('read_only','confirmed_actual_input_FE','confirmed_actual_output_FE','ownership','decision')},indent=2))

#!/usr/bin/env python3
"""Opt-in FE benchmark with full-window test-agent prefixes and complete cost.
No shipped Java changes. Input cadence/amounts and low-flow loop are inherited.
A single continuous session covers steady input through the final quiet barrier;
its fixed-window prefix is exported by the agent daemon before the final drain.
"""
import argparse,hashlib,importlib.util,json,math,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
def file_meta(path):return {'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
class ProbeWindows:
    def __init__(self,manifest,servers=('A','B','C')):
        self.path=Path(manifest).resolve();self.manifest=json.loads(self.path.read_text());self.servers=servers;self.token=None;self.commands=[]
    def command(self,text):
        spans={}
        for server in self.servers:
            path=Path(self.manifest['launches'][server]['control']);start=time.monotonic();temporary=path.with_suffix('.pending-'+uuid.uuid4().hex)
            temporary.write_text(text+'\n');temporary.replace(path);spans[server]={'start':start,'end':time.monotonic()}
        self.commands.append({'command':text,'observer_monotonic_intervals':spans});return spans
    def wait_files(self,suffix):
        result={};deadline=time.monotonic()+15
        while len(result)<len(self.servers):
            for server in self.servers:
                if server in result:continue
                path=Path(self.manifest['launches'][server]['output'])/(self.token+suffix)
                if path.is_file():
                    body=json.loads(path.read_text())
                    if body['token']!=self.token or body.get('transform_failures'):raise AssertionError('Probe transform failure/token mismatch')
                    if suffix!='.start.json':
                        if body['frame_depth_mismatches'] or body['trace_errors']:raise AssertionError('Probe recorder depth/trace error')
                        if body['ticks']<1 or body['spans']['server_tick']['inclusive']['count']!=body['ticks'] or body['spans']['runtime_tick']['inclusive']['count']<1:raise AssertionError('Whole-MC/Runtime methods not truly invoked')
                        if 'tickServer(Ljava/util/function/BooleanSupplier;)V' not in body['transformed_classes'].get('net/minecraft/server/MinecraftServer',{}).get('methods',''):raise AssertionError('Missing actual MC transform')
                    result[server]={'source':file_meta(path),'data':body,'observer_file_read_monotonic':time.monotonic()}
            if time.monotonic()>deadline:raise AssertionError('Probe control deadline: '+suffix)
            if len(result)<len(self.servers):time.sleep(.01)
        return result
    def start(self,trace=False):
        if self.token is not None:raise AssertionError('Existing probe window active')
        self.token=str(uuid.uuid4());self.command('start '+self.token+(' item' if trace else ''));return self.wait_files('.start.json')
    def fixed(self):self.command('snapshot '+self.token+' fixed');return self.wait_files('.fixed.json')
    def stop(self):
        self.command('stop '+self.token);result=self.wait_files('.json');self.token=None;return result

def driver(args):
    physical=load('rc_fe_physical_provenance',ROOT/'scripts/optimization-container-benchmark.py');base=physical.load_helpers();y,evidence=physical.harness_height();template=physical.make_driver(args,y,evidence)
    class Probed(type(template)):
        endpoint=base.Benchmark.endpoint
        setup=base.Benchmark.setup
        activate=base.Benchmark.activate
        run=base.Benchmark.run
        def __init__(self):
            super().__init__();self.target=self.target.with_name(self.target.name.replace('optimization-container-','optimization-rc-probe-',1));self.windows=ProbeWindows(args.probe_manifest);self.extra_snapshot=False
            self.report['conditions']=base.Benchmark(args).report['conditions'];self.report['conditions']['full_cost_quiet_seconds']=max(2.2,args.probe_idle)
            self.report.update(report_kind='native_FE_full_window_probe',probe_manifest=file_meta(self.windows.path),probe_configuration=self.windows.manifest,operator_runtime_revision=args.operator_revision)
            self.report['measurement']={'workload':'Unchanged inherited fixed FE inputs/extractions and low-flow observer. Same-chunk primary geometry retained.','scope':'Every input and true output retained; new whole-window probe and separate complete-cost/quiet barrier. No physical chest/peak/world-save claim.','clock':'Single external Python monotonic observer for RCON and control spans. Never subtract raw nanoTime between JVMs. Probe local wall/nano anchors have1ms realtime quantization; each JVM histogram is independent.','probe':'One continuous session from before initial counters through drain/quiet/final counters; fixed prefix copied by daemon after fixed counters. Every complete tickServer call in that prefix, not rolling/target TPS. Prefix endpoint is daemon copy time; crossing calls excluded.','cost':'Fixed-window counter_end precedes final drain. Full lifecycle additionally includes2.2s static empty guard and final counter snapshot. SQL/WAL/local mirrors not summed as assets.','quantiles':'Sparse histogram p50/p95/p99 upper-bin bounds; exact count/sum/max. Actual low-flow n and steady repeats retained.'}
        def deltas(self,first,last):
            result=base.Benchmark.deltas(self,first,last)
            for key in ('db_statements','db_transaction_attempts','wal_writes','wal_bytes','wal_identical_skipped','batch_devices','batch_records','batch_payload_bytes','local_wakes','remote_hint_wakes','poll_fallback','empty_batches','allocation_misses','local_credit_publications'):
                values={s:last['servers'][s]['metrics'].get(key) for s in base.PORTS};old={s:first['servers'][s]['metrics'].get(key) for s in base.PORTS}
                if all(values[s] is not None and old[s] is not None for s in base.PORTS):
                    differences={s:values[s]-old[s] for s in base.PORTS}
                    if min(differences.values())<0:raise AssertionError('Optional counters reset')
                    result[key]=sum(differences.values())
                    for s,value in differences.items():result['per_server'][s][key]=value
                else:result[key]=None
            return result
        def snapshot(self):
            sample=self.report['samples'][-1] if self.report['samples'] else None
            if not self.extra_snapshot and sample is not None and 'warmup_drain' in sample and 'counter_start' not in sample:
                sample['probe_start']=self.windows.start();self.save()
            result=base.Benchmark.snapshot(self)
            if not self.extra_snapshot and sample is not None and 'counter_start' in sample and 'counter_end' not in sample and 'drive' in sample:
                sample['probe_fixed_window']=self.windows.fixed();self.save()
            return result
        def quiet(self,lanes):
            started=time.monotonic();snapshots=[]
            while True:
                point=self.residue(lanes);snapshots.append(point)
                if point['sql_pool_FE'] or point['sql_allocation_remaining_FE'] or any(v['txFE'] or v['rxFE'] for v in point['local_buffers'].values()):raise AssertionError('Assets reappeared during complete-cost quiet barrier')
                if time.monotonic()-started>=max(2.2,self.args.probe_idle):return {'seconds':time.monotonic()-started,'snapshots':snapshots,'passed':True}
                time.sleep(max(.1,self.args.poll))
        def drain(self,lanes,events,seconds=None):
            result=base.Benchmark.drain(self,lanes,events,seconds);sample=self.report['samples'][-1] if self.report['samples'] else None
            if sample is not None and (events is sample.get('warmup_events') or events is sample.get('drain_events')):
                result['quiet_barrier']=self.quiet(lanes)
            if sample is not None and events is sample.get('drain_events') and 'counter_end' in sample:
                self.extra_snapshot=True
                try:sample['counter_after_drain']=base.Benchmark.snapshot(self)
                finally:self.extra_snapshot=False
                sample['lifecycle_counter_delta']=self.deltas(sample['counter_start'],sample['counter_after_drain']);sample['probe_full_lifecycle']=self.windows.stop();sample['probe_control_commands']=list(self.windows.commands);self.save()
            return result
        def measure(self,name,repetition):
            try:return base.Benchmark.measure(self,name,repetition)
            finally:
                if self.windows.token is not None:
                    try:self.report['samples'][-1]['probe_incomplete_window']=self.windows.stop()
                    except Exception as e:self.report['failures'].append('Probe stop: '+repr(e))
                    self.save()
        def cleanup(self):
            if self.report['samples'] and not self.report['failures']:self.verify_final_identity()
            return base.Benchmark.cleanup(self)
    return Probed()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--probe-manifest',type=Path);p.add_argument('--label',default='rc-baseline-fast');p.add_argument('--operator-revision',default='unknown');p.add_argument('--world-prefix',default='world-opt-rc-fe-');p.add_argument('--warmup',type=float,default=30);p.add_argument('--seconds',type=float,default=120);p.add_argument('--repeats',type=int,default=1);p.add_argument('--probes',type=int,default=40);p.add_argument('--probe-idle',type=float,default=2.2);p.add_argument('--poll',type=float,default=.1);p.add_argument('--feed-period',type=float,default=.5);p.add_argument('--scenarios',default='same,cross,mixed');p.add_argument('--baseline',type=Path);p.add_argument('--max-regression-percent',type=float,default=10);p.add_argument('--self-test',action='store_true');args=p.parse_args();args.scenarios=args.scenarios.split(',');args.timeout=1200;args.quiet=2.2
    if args.self_test:
        base=load('rc_probe_offline_primary',ROOT/'scripts/optimization-benchmark.py');base.self_test();print('Probe driver offline import/CLI PASS; no native calls');return 0
    if not args.execute:print(json.dumps({'execution':'NOT_RUN','requires':'--execute --probe-manifest; stopped/fresh operator-prepared test worlds'}));return 0
    if args.probe_manifest is None or args.scenarios!=list(dict.fromkeys(args.scenarios)) or any(s not in ('same','cross','mixed') for s in args.scenarios) or not 0<=args.warmup<=120 or not 1<=args.seconds<=600 or not 1<=args.repeats<=3 or not 0<=args.probes<=100 or not .05<=args.poll<=1 or not .25<=args.feed_period<=1:p.error('Bounded three-layout native test only')
    return driver(args).run()
if __name__=='__main__':sys.exit(main())

#!/usr/bin/env python3
"""Original deterministic pixel art and native resources. No upstream images are read."""
import json, math, struct, zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'src/main/resources'
def write(path,value):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def png(path,pixels,size):
    def chunk(t,b):return struct.pack('>I',len(b))+t+b+struct.pack('>I',zlib.crc32(t+b)&0xffffffff)
    raw=b''.join(b'\0'+bytes(sum(row,())) for row in pixels)
    out=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(out)
def line(p,x0,y0,x1,y1,color):
    length=max(abs(x1-x0),abs(y1-y0))
    for i in range(length+1):p[round(y0+(y1-y0)*i/max(1,length))][round(x0+(x1-x0)*i/max(1,length))]=color
for face in ['side','top']:
    n=32;p=[[(24+(x+y)%3,32+(x*3+y)%4,47+(x+y*2)%4) for x in range(n)] for y in range(n)]
    for inset,col in [(1,(92,111,134)),(3,(12,18,27)),(6,(78,210,199)),(11,(182,108,240))]:
        for edge in [(inset,inset,n-1-inset,inset),(inset,n-1-inset,n-1-inset,n-1-inset),(inset,inset,inset,n-1-inset),(n-1-inset,inset,n-1-inset,n-1-inset)]:line(p,*edge,col)
    for x,y in [(6,6),(25,6),(6,25),(25,25)]:
        end=(11 if x==6 else 20,11 if y==6 else 20);line(p,x,y,*end,(108,179,215))
    for x,y in [(2,2),(29,2),(2,29),(29,29)]:p[y][x]=(232,191,105)
    if face=='top':
        for x,y in [(15,0),(16,0),(15,31),(16,31),(0,15),(0,16),(31,15),(31,16)]:p[y][x]=(108,233,214)
    png(Path('assets/cross_tesseract/textures/block')/f'tesseract_{face}.png',p,n)
write(Path('assets/cross_tesseract/blockstates/tesseract.json'),{'variants':{'':{'model':'cross_tesseract:block/tesseract'}}})
write(Path('assets/cross_tesseract/models/block/tesseract.json'),{'parent':'minecraft:block/cube','textures':{'particle':'cross_tesseract:block/tesseract_side','down':'cross_tesseract:block/tesseract_top','up':'cross_tesseract:block/tesseract_top','north':'cross_tesseract:block/tesseract_side','south':'cross_tesseract:block/tesseract_side','west':'cross_tesseract:block/tesseract_side','east':'cross_tesseract:block/tesseract_side'}})
write(Path('assets/cross_tesseract/models/item/tesseract.json'),{'parent':'cross_tesseract:block/tesseract'})
write(Path('data/cross_tesseract/recipe/tesseract.json'),{'type':'minecraft:crafting_shaped','category':'redstone','pattern':['IOI','OEO','IOI'],'key':{'I':{'item':'minecraft:iron_ingot'},'O':{'item':'minecraft:obsidian'},'E':{'item':'minecraft:ender_pearl'}},'result':{'id':'cross_tesseract:tesseract','count':1}})
write(Path('data/cross_tesseract/loot_table/blocks/tesseract.json'),{'type':'minecraft:block','pools':[{'rolls':1,'entries':[{'type':'minecraft:item','name':'cross_tesseract:tesseract'}],'conditions':[{'condition':'minecraft:survives_explosion'}]}]})
write(Path('data/minecraft/tags/block/mineable/pickaxe.json'),{'replace':False,'values':['cross_tesseract:tesseract']})
write(Path('data/minecraft/tags/block/needs_iron_tool.json'),{'replace':False,'values':['cross_tesseract:tesseract']})
write(Path('pack.mcmeta'),{'pack':{'pack_format':34,'description':'CrossServer Tesseract original assets'}})

en={'block.cross_tesseract.tesseract':'CrossServer Tesseract','itemGroup.cross_tesseract':'CrossServer Tesseract',
    'ct.gui.identity':'Device %s · Server %s','ct.gui.owners':'Device owner %s · Channel owner %s','ct.gui.binding':'Resource channel %s · %s',
    'ct.gui.quota':'Persistent device slots: %s / %s','ct.gui.target_uuid':'Enter the authenticated player UUID.','ct.gui.empty':'No entries.','ct.gui.input':'Name / UUID / filter IDs / rate',
    'ct.command.help':'/ct channels | create <name> | invites | accept/decline <invite UUID> | invite/transfer/remove <channel UUID> <player UUID> | quota | load | off <device UUID> | bind <channel UUID> | mode <resource ID> <OFF/SEND/RECEIVE/BOTH> | status. Admin: /ct admin health | metrics | trace <channel/endpoint/transfer/quarantine> <UUID> | quota <player UUID> | recover <device UUID> <version> ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY',
    'ct.command.status':'Server %s · backend %s · actual tickets %s','ct.command.channel':'%s · %s · owner %s · version %s · %s',
    'ct.command.created':'Created resource channel %s','ct.command.invite':'Invite %s · channel %s · %s · expires %s',
    'ct.command.quota':'Cluster loading slots used: %s / %s','ct.command.device':'%s · %s · %s · (%s,%s,%s) · %s · %s'}
zh={'block.cross_tesseract.tesseract':'跨服超立方体','itemGroup.cross_tesseract':'跨服超立方体',
    'ct.gui.identity':'设备 %s · 子服 %s','ct.gui.owners':'方块主人 %s · 频道主人 %s','ct.gui.binding':'资源频道 %s · %s',
    'ct.gui.quota':'持久加载名额：%s / %s','ct.gui.target_uuid':'输入由服务器认证的玩家 UUID。','ct.gui.empty':'暂无记录。','ct.gui.input':'名称 / UUID / 过滤 ID / 速率',
    'ct.command.help':'/ct channels | create <名称> | invites | accept/decline <邀请 UUID> | invite/transfer/remove <频道 UUID> <玩家 UUID> | quota | load | off <设备 UUID> | bind <频道 UUID> | mode <资源 ID> <OFF/SEND/RECEIVE/BOTH> | status。管理：/ct admin health | metrics | trace <channel/endpoint/transfer/quarantine> <UUID> | quota <玩家 UUID> | recover <设备 UUID> <版本> ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY',
    'ct.command.status':'子服 %s · 后端 %s · 实际票据 %s','ct.command.channel':'%s · %s · 主人 %s · 版本 %s · %s',
    'ct.command.created':'已创建资源频道 %s','ct.command.invite':'邀请 %s · 频道 %s · %s · 到期 %s',
    'ct.command.quota':'全群组加载名额：%s / %s','ct.command.device':'%s · %s · %s · (%s,%s,%s) · %s · %s'}
buttons={'tab.device':('Device','设备'),'tab.channels':('Channels','频道'),'tab.invites':('Invites','邀请'),'tab.members':('Members','成员'),'tab.quota':('Quota','配额'),'tab.endpoints':('Endpoints','端点'),
    'refresh':('Refresh','刷新'),'bind':('Bind','绑定'),'unbind':('Unbind','解绑'),'chunk_on':('Enable loading','开启加载'),'chunk_off':('Disable loading','关闭加载'),
    'filter':('Set blacklist','设置黑名单'),'whitelist':('Set whitelist','设置白名单'),'rate':('Set rate','设置速率'),'create':('Create','创建'),'invite':('Invite','邀请'),
    'rename':('Rename','改名'),'freeze':('Freeze','冻结'),'thaw':('Unfreeze','解冻'),'delete':('Delete empty','删除空频道'),'leave':('Leave','退出'),
    'accept':('Accept','接受'),'decline':('Decline','拒绝'),'members':('Load members','读取成员'),'remove':('Remove','移除'),'transfer':('Offer ownership','转移邀请'),
    'remote_off':('Disable selected device','关闭选中设备'),'endpoints':('Load endpoint list','读取端点列表')}
buttons.update({'ae_on':('Enable AE storage','开启 AE 物资桥'),'ae_off':('Disable AE storage','关闭 AE 物资桥'),'whitelist':('Use whitelist','使用白名单'),'blacklist':('Use blacklist','使用黑名单'),'rate':('Set rate','设置限速'),'eu':('Set V,A','设置电压/安培'),'revoke':('Revoke invite','撤销邀请')})
buttons.update({'tab.stock':('Stock','库存'),'stock_fetch':('Request','调货'),'stock_first':('First page','首页'),'stock_next':('Next batch','下批'),'stock_cancel':('Cancel pending intent','取消待分配需求')})
for key,(e,z) in {'stock_advisory':('Remote figures are advisory; enter a quantity to request.','远端库存仅供参考；输入数量申请调货。'),'stock_quantities':('Ready %s · Remote %s · Reserved %s · Transit %s · Unreachable %s','可取 %s · 远端 %s · 预留 %s · 在途 %s · 不可达 %s'),'stock_request':('%s: %s · unreserved %s','%s：%s · 未分配 %s')}.items():en['ct.gui.'+key]=e;zh['ct.gui.'+key]=z
en['ct.status.stock_queued']='Demand recorded; allocation and arrival are pending.';zh['ct.status.stock_queued']='需求已记录；等待独占划拨及到货。'
for key,(e,z) in {'pending':('Pending allocation','待分配'),'partial':('Partly reserved','部分已预留'),'fulfilled':('Fully reserved; arrival may be pending','已全部预留；到货仍可能在途'),'cancelled':('Unallocated intent cancelled','未分配需求已取消'),'expired':('Unallocated intent expired','未分配需求已过期')}.items():en['ct.stock.'+key]=e;zh['ct.stock.'+key]=z
for key,(e,z) in {'buffers':('Send %s · Local ready %s · Limit %s/t','发送 %s · 本地可取 %s · 限速 %s/t'),'pause':('Pause: %s','暂停：%s')}.items():en['ct.gui.'+key]=e;zh['ct.gui.'+key]=z
for key,(e,z) in {'disabled':('AE storage disabled','AE 物资桥已关闭'),'local_storage':('Local exclusive AE inventory','AE 本地独占库存'),'unpowered':('ME network has no power','ME 网络失电'),'booting':('ME network rebuilding','ME 网络正在重建'),'channel_shortage':('ME channels exhausted','ME 频道不足'),'ae_proxy_experimental':('Experimental proxy; native grids are separate','实验代理；原生网格仍独立'),'ae_proxy_rebuilding':('Experimental proxy rebuilding','实验代理正在重建'),'ae_peer_unconfirmed':('Remote native state unconfirmed','远端原生状态待确认')}.items():en['ct.ae.state.'+key]=e;zh['ct.ae.state.'+key]=z
for k,(e,z) in buttons.items():en['ct.gui.'+k]=e;zh['ct.gui.'+k]=z
for k,(e,z) in {'item':('Items','物品'),'fluid':('Fluid','流体'),'fe':('FE','FE'),'gt_eu':('GT EU','GT EU'),'mek_chemical':('Chemicals','化学品'),'mek_heat':('Heat','热量')}.items():en['ct.resource.'+k]=e;zh['ct.resource.'+k]=z
for k,(e,z) in {'down':('Down','下'),'up':('Up','上'),'north':('North','北'),'south':('South','南'),'west':('West','西'),'east':('East','东')}.items():en['ct.side.'+k]=e;zh['ct.side.'+k]=z
for k,(e,z) in {'success':('Confirmed','已确认'),'processing':('Processing…','处理中…'),'connecting':('Connecting…','连接中…'),'online':('Connected','已连接')}.items():en['ct.status.'+k]=e;zh['ct.status.'+k]=z
errors={
'forbidden':('Permission denied.','没有权限。'),'device_owner_required':('Only the device owner may do this.','仅方块所有者可以操作。'),
'backend_disabled':('Configure the server backend first.','请先配置服务端后端。'),'backend_busy':('Backend queue full; retry later.','后端队列已满，请稍后重试。'),
'database_unavailable':('MySQL unavailable; operation unconfirmed.','MySQL 不可用；操作未确认。'),'redis_unavailable':('Redis unavailable; operation paused.','Redis 不可用；操作暂停。'),
'journal_unavailable':('Local journal unavailable; recovery required.','本地日志不可用，需恢复。'),'backend_error':('Backend error; inspect server diagnostics.','后端异常，请查询服务端诊断。'),
'quota_exhausted':('Cluster loading quota exhausted.','全群组加载名额已用完。'),'revocation_pending':('Revocation pending; slot remains occupied.','待确认撤销；名额仍被占用。'),
'duplicate_server_id':('Duplicate server ID; instance fenced.','子服 ID 重复；实例已阻止加入。'),'world_id_mismatch':('World identity mismatch; instance paused.','世界身份不匹配；实例暂停。'),
'session_fenced':('Session expired or replaced; restart and inspect.','会话过期或被替换，请检查后重启。'),'policy_mismatch':('Local config differs from cluster policy.','本地配置与群组权威政策不一致。'),
'backup_generation_conflict':('Backup generation conflict; recovery required.','备份代次冲突，需恢复。'),'cloned_endpoint':('Copied device identity rejected.','复制的设备身份已拒绝。'),
'channel_not_found':('Channel unavailable.','频道不可用。'),'channel_frozen':('Channel is frozen.','频道已冻结。'),'stale_version':('State changed; refresh and retry.','状态已变更，请刷新重试。'),
'invite_expired':('Invitation expired or no longer pending.','邀请已过期或不再待接受。'),'invite_revoked':('Invitation was revoked.','邀请已撤销。'),'invite_not_found':('Invitation unavailable.','邀请不可用。'),
'channel_not_empty':('Drain balances and allocations first.','请先排空余额及独占划拨。'),'endpoints_bound':('Unbind all endpoints first.','请先解绑所有端点。'),
'endpoint_not_empty':('Drain this device and wait for pending jobs first.','请先排空设备并等待在途操作。'),'endpoint_not_found':('Device unavailable.','设备不可用。'),'endpoint_unloaded':('Device unloaded; state remains pending.','设备已卸载；状态仍待确认。'),
'ticket_install_failed':('Ticket installation failed; reservation compensated.','票据安装失败；预留已补偿。'),'unclean_external_io':('Unclean shutdown: review external inventory saves.','非正常停机：请核查外部容器存档。'),
'world_checkpoint_behind':('Chunk checkpoint older than ledger; quarantined.','区块检查点落后于账本；已隔离。'),'registry_missing':('Resource registry/component missing; allocation isolated.','资源注册项或组件缺失；划拨已隔离。'),
'payload_corrupt':('Invalid payload; paused.','载荷不合法；已暂停。'),'payload_too_large':('Payload exceeds configured safety limits.','载荷超出大小或嵌套限制。'),
'quantity_overflow':('Quantity overflow rejected.','数量溢出已拒绝。'),'resource_unsupported':('This resource adapter is unavailable.','该资源适配器不可用。'),
'rate_limited':('Too many management requests.','管理请求过于频繁。'),'invalid_action':('Invalid command or parameter.','命令或参数不合法。'),
'owner_cannot_leave':('Owner must transfer ownership before leaving.','主人须先完成所有权转移。'),'owner_required':('Channel owner required.','需要频道主人权限。'),
'freeze_first':('Freeze the empty channel before deleting.','删除前须冻结空频道。'),'already_owner':('Target is already the owner.','目标已是主人。'),
'unbound':('Select an authorized resource channel.','请选择有权使用的资源频道。'),'connecting':('Waiting for authoritative state.','等待权威状态确认。'),
'recovery_confirmation_required':('Explicit recovery confirmation token required.','需要明确的恢复确认文本。'),'old_lease_unconfirmed':('Old server/runtime leases still unconfirmed.','旧子服或运行租约尚未确认失效。')}
errors.update({'operation_expired':('Operation key expired; inspect before a new request.','操作标识已过期；发起新请求前请核查。'),'operation_unconfirmed':('Result unconfirmed; refresh and inspect the operation.','结果待确认；请刷新并核查操作记录。'),'history_limit':('Persistent history limit reached; operator archive required.','持久历史达到上限，需管理员检查及归档。'),'binding_pending':('Channel binding is being confirmed; resource input is paused.','频道绑定正在确认；资源输入已暂停。')})
errors.update({'stock_stale':('Inventory snapshot expired; refresh before requesting.','库存快照已失效；请刷新后申请。'),'stock_request_limit':('At most eight pending stock requests per device.','每设备最多八个待分配调货请求。'),'receive_disabled':('Receive direction is disabled for this resource.','当前资源的接收方向已关闭。')})
errors.update({'unpowered':('ME network has no power.','ME 网络失电。'),'booting':('ME network is rebuilding.','ME 网络正在重建。'),'channel_shortage':('ME channels exhausted.','ME 频道不足。'),'ae_suspended':('AE gateway is suspended.','AE 网关已暂停。'),'ae_proxy_rebuilding':('Experimental AE proxy is rebuilding.','实验 AE 代理正在重建。'),'ae_peer_unconfirmed':('Remote AE state is unconfirmed.','远端 AE 状态待确认。'),'ae_channel_conflict':('One local grid is bound to different resource channels.','同一本地网格绑定了不同资源频道。')})
for key in ('ae_suspended','ae_channel_conflict'):en['ct.ae.state.'+key]=errors[key][0];zh['ct.ae.state.'+key]=errors[key][1]
for k,(e,z) in errors.items():en['ct.error.'+k]=e;zh['ct.error.'+k]=z
# Every remaining stable domain code gets a readable fallback in both locales.
import re
codes=set()
for p in (ROOT.parent/'java').rglob('*.java'):
    codes.update(re.findall(r'(?:require|DomainException|pause)\([^;\n]*?"([a-z][a-z_]+)"',p.read_text()))
for k in codes:
    en.setdefault('ct.error.'+k,k.replace('_',' ').capitalize()+'.');zh.setdefault('ct.error.'+k,'操作未确认：'+k+'。')
for mode,e,z in [('off','Off','关闭'),('send','Send','发送'),('receive','Receive','接收'),('both','Both','双向')]:en['ct.mode.'+mode]=e;zh['ct.mode.'+mode]=z
write(Path('assets/cross_tesseract/lang/en_us.json'),en);write(Path('assets/cross_tesseract/lang/zh_cn.json'),zh)

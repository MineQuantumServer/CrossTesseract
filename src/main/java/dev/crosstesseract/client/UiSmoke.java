package dev.crosstesseract.client;

import dev.crosstesseract.CrossTesseract;
import dev.crosstesseract.block.TesseractBlockEntity;
import dev.crosstesseract.core.*;
import dev.crosstesseract.runtime.RuntimeService;
import java.util.UUID;
import net.minecraft.client.*;
import net.minecraft.core.BlockPos;
import net.neoforged.neoforge.client.event.ClientTickEvent;

/** Explicit dev-only integrated client test. Uses real menus, C2S packets, actor UUID and SQL. */
final class UiSmoke {
    private static int phase,ticks,totalTicks,respawns;private static BlockPos pos;private static UUID player;
    private static final String name="UI_"+BusinessIds.next().toString().substring(28,36);
    private static volatile boolean setup;
    static void tick(ClientTickEvent.Post event){
        if(!Boolean.getBoolean("cross_tesseract.uiSmoke"))return;var mc=Minecraft.getInstance();
        if(mc.player==null || mc.level==null || mc.getSingleplayerServer()==null)return;
        if(++totalTicks>8000){CrossTesseract.LOG.error("CT_UI_SMOKE_FAIL total timeout phase={}",phase);System.exit(2);return;}
        if(mc.screen instanceof net.minecraft.client.gui.screens.DeathScreen){if(++respawns>3){CrossTesseract.LOG.error("CT_UI_SMOKE_FAIL repeated fixture deaths");System.exit(2);return;}mc.player.respawn();mc.setScreen(null);phase=0;setup=false;ticks=0;return;}
        if(++ticks>4000){CrossTesseract.LOG.error("CT_UI_SMOKE_FAIL phase={} timeout",phase);System.exit(2);return;}
        if(ticks%200==0){CrossTesseract.LOG.info("CT_UI_PROGRESS phase={} screen={} {}",phase,mc.screen==null?"none":mc.screen.getClass().getSimpleName(),mc.screen instanceof TesseractScreen s?s.smokeDebug():"");if(pos!=null)mc.getSingleplayerServer().execute(()->{var sp=mc.getSingleplayerServer().getPlayerList().getPlayer(player);if(sp!=null && sp.serverLevel().getBlockEntity(pos) instanceof TesseractBlockEntity be)CrossTesseract.LOG.info("CT_UI_SERVER_DEVICE id={} registered={} registering={} removed={} pause={}",be.id(),be.registered(),be.registering(),be.isRemoved(),be.pauseReason());});}
        if(phase==0){var server=mc.getSingleplayerServer();var runtime=RuntimeService.get(server);if(runtime==null || !runtime.online())return;
            player=mc.player.getUUID();phase=1;server.execute(()->{var sp=server.getPlayerList().getPlayer(player);if(sp==null)return;sp.setGameMode(net.minecraft.world.level.GameType.CREATIVE);
                // A previous fixture may still own sealed assets at its old position. Preserve it.
                int x=200000+(int)Math.floorMod(System.currentTimeMillis(),8_000_000L);var chunk=sp.serverLevel().getChunk(x>>4,0);int y=chunk.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING_NO_LEAVES,x&15,0)+1;sp.teleportTo(x+.5,y,.5);pos=new BlockPos(x+2,y,0);
                if(sp.serverLevel().getBlockEntity(pos)!=null)throw new IllegalStateException("UI test location occupied; preserve and choose another run");
                sp.serverLevel().setBlockAndUpdate(pos,CrossTesseract.TESSERACT.get().defaultBlockState());((TesseractBlockEntity)sp.serverLevel().getBlockEntity(pos)).placed(sp.getUUID());setup=true;});return;}
        if(phase==1 && setup && mc.player.distanceToSqr(pos.getX()+.5,pos.getY()+.5,pos.getZ()+.5)<=64 && mc.level.getBlockState(pos).is(CrossTesseract.TESSERACT.get())){phase=2;var server=mc.getSingleplayerServer();server.execute(()->{var sp=server.getPlayerList().getPlayer(player);var be=(TesseractBlockEntity)sp.serverLevel().getBlockEntity(pos);sp.openMenu(be,b->b.writeBlockPos(pos));});return;}
        if(!(mc.screen instanceof TesseractScreen screen))return;
        if(phase==2 && screen.smokeReady()){screen.smokeSend("create",name,0);phase=3;return;}
        if(phase==3 && screen.smokeSelect(name)){screen.smokeBind();phase=4;return;}
        if(phase==4 && screen.smokeBound()){screen.smokeSend("mode",Protocol.FE,screen.smokeSettings());phase=5;return;}
        if(phase==5 && screen.smokeSending()){
            screen.smokeValidate();mc.options.guiScale().set(2);mc.resizeDisplay();phase=6;ticks=0;return;
        }
        if(phase==6 && ticks>30){screen.smokeValidate();Screenshot.grab(mc.gameDirectory,"ui-smoke-en-scale2.png",mc.getMainRenderTarget(),c->CrossTesseract.LOG.info("CT_UI_SCREENSHOT {}",c.getString()));
            phase=7;mc.options.languageCode="zh_cn";mc.getLanguageManager().setSelected("zh_cn");mc.reloadResourcePacks().thenRun(()->mc.execute(()->{mc.getWindow().setWindowed(960,720);mc.options.guiScale().set(3);mc.resizeDisplay();phase=8;ticks=0;}));return;}
        if(phase==8 && ticks>60 && mc.getOverlay()==null){screen.smokeValidate();Screenshot.grab(mc.gameDirectory,"ui-smoke-zh-small.png",mc.getMainRenderTarget(),c->CrossTesseract.LOG.info("CT_UI_SCREENSHOT {}",c.getString()));CrossTesseract.LOG.info("CT_UI_SMOKE_PASS real create/bind/mode packets; actor={}; en/zh layouts",player);phase=dev.crosstesseract.compat.CompatLoader.aeAvailable()?10:9;ticks=0;return;}
        if(phase==10 && screen.smokeIdle()){
            var server=mc.getSingleplayerServer();server.execute(()->{var id=net.minecraft.resources.ResourceLocation.parse("ae2:creative_energy_cell");if(!net.minecraft.core.registries.BuiltInRegistries.BLOCK.containsKey(id))throw new IllegalStateException("actual AE creative power cell missing");server.getPlayerList().getPlayer(player).serverLevel().setBlockAndUpdate(pos.east(),net.minecraft.core.registries.BuiltInRegistries.BLOCK.get(id).defaultBlockState());});screen.smokeSend("ae","",screen.smokeSettings());phase=11;return;
        }
        if(phase==11 && screen.smokeAeReady()){screen.smokeSend("mode",Protocol.ITEM,screen.smokeSettings());phase=12;return;}
        if(phase==12 && screen.smokeItemMode("SEND")){var server=mc.getSingleplayerServer();server.execute(()->{var be=(TesseractBlockEntity)server.getPlayerList().getPlayer(player).serverLevel().getBlockEntity(pos);for(var module:dev.crosstesseract.compat.CompatLoader.modules())if(module.features().contains("cross_tesseract:ae_storage_v1")){String inserted=module.testCommand(be,"insert",new String[]{"minecraft:diamond","32"});if(!inserted.equals("32"))throw new IllegalStateException("actual AE seed insertion failed: "+inserted);}});screen.smokeStockOpen();phase=13;return;}
        // Packet data can be applied after the previous rendered frame. Let the visible
        // screen render before capturing it; assertions alone don't validate the image.
        if(phase==13 && screen.smokeStockReady(32,0) && screen.smokeStockReason("receive_disabled")){phase=17;ticks=0;return;}
        if(phase==17 && ticks>8 && screen.smokeStockReady(32,0)){screen.smokeValidate();Screenshot.grab(mc.gameDirectory,"ui-stock-zh-remote.png",mc.getMainRenderTarget(),c->CrossTesseract.LOG.info("CT_UI_SCREENSHOT {}",c.getString()));screen.smokeSend("mode",Protocol.ITEM,screen.smokeSettings());phase=14;return;}
        if(phase==14 && screen.smokeItemMode("RECEIVE") && screen.smokeStockReady(0,32)){screen.smokeStockFetch();phase=15;return;}
        if(phase==15 && screen.smokeStockPending()){phase=18;ticks=0;return;}
        if(phase==18 && ticks>8 && screen.smokeStockPending()){screen.smokeValidate();Screenshot.grab(mc.gameDirectory,"ui-stock-zh-pending.png",mc.getMainRenderTarget(),c->CrossTesseract.LOG.info("CT_UI_SCREENSHOT {}",c.getString()));screen.smokeStockCancel();phase=16;return;}
        if(phase==16 && screen.smokeStockCancelled() && screen.smokeStockReady(0,32)){CrossTesseract.LOG.info("CT_UI_STOCK_PASS real AE inventory view/fetch/cancel packets; 32 owned diamonds preserved; actor={}",player);phase=9;ticks=0;return;}
        if(phase==9 && ticks>20)mc.stop();
    }
    private UiSmoke(){}
}

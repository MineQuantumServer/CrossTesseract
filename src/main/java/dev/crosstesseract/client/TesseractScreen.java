package dev.crosstesseract.client;

import com.google.gson.*;
import dev.crosstesseract.block.TesseractMenu;
import dev.crosstesseract.network.Packets;
import java.util.*;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.*;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;
import net.neoforged.neoforge.network.PacketDistributor;

/** Responsive original UI; no client DB libraries, credentials or global private channel broadcast. */
public final class TesseractScreen extends AbstractContainerScreen<TesseractMenu> {
    private final JsonObject data=new JsonObject();
    private String status="connecting",inputValue="";
    private EditBox input;
    private int tab,selection,channelSelection,resourceSelection,page,refreshTicks;
    private boolean requested,pending;
    private UUID pendingRequest;
    private int pendingTicks;
    private String stockCursor="";
    private long stockReceived;
    private final List<String> lines=new ArrayList<>();
    public TesseractScreen(TesseractMenu menu,Inventory inventory,Component title){super(menu,inventory,title);}
    @Override protected void init(){
        imageWidth=Math.min(420,width-12);imageHeight=Math.min(304,height-12);super.init();
        int tabs=Boolean.parseBoolean(text("aeAvailable"))?7:6;if(tab>=tabs)tab=0;int tabWidth=(imageWidth-16)/tabs;
        for(int i=0;i<tabs;i++){int index=i;button("tab."+new String[]{"device","channels","invites","members","quota","endpoints","stock"}[i],8+i*tabWidth,23,tabWidth-2,18,()->{remember();tab=index;selection=0;page=0;rebuild();if(index==6)send("stock_view",stockCursor,0);});}
        input=new EditBox(font,leftPos+9,topPos+imageHeight-57,imageWidth-116,18,Component.translatable("ct.gui.input"));input.setMaxLength(512);input.setValue(inputValue);addRenderableWidget(input);
        button("refresh",imageWidth-100,imageHeight-57,91,18,()->send(tab==6?"stock_view":"refresh",tab==6?stockCursor:"",0));
        lines.clear();buildTab();
        if(!requested){requested=true;send("refresh","",0);}
    }
    private void remember(){if(input!=null)inputValue=input.getValue();}
    private void rebuild(){boolean focused=input!=null && input.isFocused();int cursor=input==null?0:input.getCursorPosition();remember();clearWidgets();init();if(focused){setFocused(input);input.setFocused(true);input.moveCursorTo(Math.min(cursor,input.getValue().length()),false);}}
    public void apply(Packets.View view){
        if(!pending || Objects.equals(pendingRequest,view.request())){status=view.status();pending=status.equals("processing");}
        try{JsonObject object=JsonParser.parseString(view.json()).getAsJsonObject();for(var entry:object.entrySet())data.add(entry.getKey(),entry.getValue());if(object.has("stock"))stockReceived=System.nanoTime();}catch(RuntimeException e){status="payload_corrupt";}
        rebuild();
    }
    private Button button(String key,int x,int y,int w,int h,Runnable action){
        var b=Button.builder(Component.translatable("ct.gui."+key),ignored->action.run()).bounds(leftPos+x,topPos+y,w,h).build();addRenderableWidget(b);b.active=!pending;return b;
    }
    private Button literal(String text,int x,int y,int w,Runnable action){var b=Button.builder(Component.literal(text),ignored->action.run()).bounds(leftPos+x,topPos+y,w,17).build();addRenderableWidget(b);b.active=!pending;return b;}
    private void send(String action,String argument,long expected){
        if(argument.length()>512){status="invalid_action";return;}
        UUID request=dev.crosstesseract.core.BusinessIds.next();
        if(!action.equals("refresh")){pendingRequest=request;pendingTicks=0;}
        PacketDistributor.sendToServer(new Packets.Request(menu.containerId,menu.pos(),request,action,argument,expected));
        if(!action.equals("refresh")){pending=true;status="processing";for(var child:children())if(child instanceof Button button)button.active=false;}
    }
    private String text(String key){JsonElement element=data.get(key);return element==null||element.isJsonNull()?"":element.getAsString();}
    private long number(String key){try{return Long.parseLong(text(key));}catch(NumberFormatException e){return 0;}}
    private JsonArray array(String key){return data.has(key)&&data.get(key).isJsonArray()?data.getAsJsonArray(key):new JsonArray();}
    private static String value(JsonObject object,String key){JsonElement e=object.get(key);return e==null||e.isJsonNull()?"":e.getAsString();}
    private static String shortId(String id){return id.length()>8?id.substring(0,8):id;}
    private JsonObject selectedChannel(){JsonArray channels=array("channels");return channels.isEmpty()?null:channels.get(Math.min(channelSelection,channels.size()-1)).getAsJsonObject();}
    private void channelAction(String action,String arg){JsonObject c=selectedChannel();if(c!=null)send(action,value(c,"id")+(arg.isEmpty()?"":"|"+arg),Long.parseLong(value(c,"version")));}
    private int bottom(){return imageHeight-80;}
    private void buildTab(){
        switch(tab){case 0->device();case 1->channels();case 2->invites();case 3->members();case 4->quota();case 5->endpoints();case 6->stock();default->throw new IllegalStateException();}
    }
    private void device(){
        lines.add(Component.translatable("ct.gui.identity",shortId(text("endpoint")),text("server")).getString());
        lines.add(Component.translatable("ct.gui.owners",shortId(text("owner")),shortId(text("channelOwner"))).getString());
        lines.add(Component.translatable("ct.gui.binding",shortId(text("channel")),Component.translatable(text("backend").equals("online")?"ct.status.online":"ct.error."+text("backend")).getString()).getString());
        JsonArray resources=array("resources");int y=83;
        for(int i=resourceSelection%Math.max(1,resources.size());i<resources.size() && i==resourceSelection%Math.max(1,resources.size());i++){
            var port=resources.get(i).getAsJsonObject();String kind=value(port,"kind");
            String label=Component.translatable("ct.resource."+kind.substring(kind.indexOf(':')+1)).getString();
            literal(label+" "+Component.translatable("ct.mode."+value(port,"mode").toLowerCase(Locale.ROOT)).getString(),9,y,Math.min(125,imageWidth/3),()->send("mode",kind,number("settingsVersion")));
            int sideStart=imageWidth-102,mask=Integer.parseInt(value(port,"sides"));
            for(int j=0;j<6;j++){int side=j;var b=literal((mask&(1<<side))!=0?"+":"−",sideStart+j*15,y,14,()->send("sides",kind+"="+(mask^(1<<side)),number("settingsVersion")));b.setTooltip(Tooltip.create(Component.translatable("ct.side."+new String[]{"down","up","north","south","west","east"}[side])));}
            y+=20;
        }
        literal("‹",9,bottom()-22,25,()->{resourceSelection=Math.floorMod(resourceSelection-1,Math.max(1,resources.size()));rebuild();});
        literal("›",38,bottom()-22,25,()->{resourceSelection++;rebuild();});
        if(Boolean.parseBoolean(text("aeAvailable"))){var ae=button(Boolean.parseBoolean(text("aeEnabled"))?"ae_off":"ae_on",68,bottom()-22,100,18,()->send("ae","",number("settingsVersion")));ae.setTooltip(Tooltip.create(Component.translatable("ct.ae.state."+text("aeState"))));}
        button(Boolean.parseBoolean(text("whitelist"))?"blacklist":"whitelist",imageWidth-106,bottom()-22,97,18,()->send(Boolean.parseBoolean(text("whitelist"))?"filter":"whitelist",input.getValue(),number("settingsVersion")));
        boolean desired=Boolean.parseBoolean(text("chunkDesired"));button(desired?"chunk_off":"chunk_on",9,bottom(),100,18,()->send(desired?"chunk_off":"chunk_on","",number("endpointVersion")));
        button("unbind",113,bottom(),75,18,()->send("unbind","",number("endpointVersion")));
        button("filter",192,bottom(),Math.max(55,imageWidth-201),18,()->send("filter",input.getValue(),number("settingsVersion")));
        int resourceCount=resources.size();
        if(resourceCount>0){var selected=resources.get(resourceSelection%resourceCount).getAsJsonObject();String kind=value(selected,"kind");
            button("rate",imageWidth-100,imageHeight-35,91,16,()->send("rate",kind+"="+input.getValue(),number("settingsVersion")));
            literal(shortId(kind.substring(kind.indexOf(':')+1))+" ▸",9,imageHeight-35,74,()->{resourceSelection++;rebuild();});
            if(kind.equals("cross_tesseract:gt_eu"))button("eu",imageWidth-184,imageHeight-35,80,16,()->send("eu",input.getValue(),number("settingsVersion")));
        }
    }
    private void channels(){
        JsonArray channels=array("channels");list(channels,c->value(c,"name")+" ["+shortId(value(c,"id"))+"] "+value(c,"state"),i->{channelSelection=i;selection=i;rebuild();});
        button("create",9,bottom(),65,18,()->send("create",input.getValue(),0));
        var bind=button("bind",78,bottom(),63,18,()->{var c=selectedChannel();if(c!=null)send("bind",value(c,"id"),number("endpointVersion"));});bind.active&=selectedChannel()!=null && Boolean.parseBoolean(text("registered"));
        button("invite",145,bottom(),60,18,()->channelAction("invite",input.getValue()));
        button("rename",209,bottom(),Math.max(60,imageWidth-218),18,()->channelAction("rename",input.getValue()));
        button("freeze",9,imageHeight-35,63,16,()->channelAction("freeze",""));button("thaw",76,imageHeight-35,63,16,()->channelAction("thaw",""));
        button("delete",143,imageHeight-35,63,16,()->channelAction("delete",""));button("leave",210,imageHeight-35,Math.max(60,imageWidth-219),16,()->channelAction("leave",""));
    }
    private void invites(){
        JsonArray list=array("invites");list(list,c->value(c,"kind")+" "+shortId(value(c,"channel"))+" "+value(c,"expires"),i->{selection=i;rebuild();});
        button("accept",9,bottom(),90,18,()->{if(selection<list.size())send("accept",value(list.get(selection).getAsJsonObject(),"id"),0);});
        button("decline",103,bottom(),90,18,()->{if(selection<list.size())send("decline",value(list.get(selection).getAsJsonObject(),"id"),0);});
        button("revoke",197,bottom(),Math.max(60,imageWidth-206),18,()->{if(selection<list.size()){var inv=list.get(selection).getAsJsonObject();send("revoke",value(inv,"channel")+"|"+value(inv,"id"),0);}});
    }
    private void members(){
        JsonArray members=array("members");JsonArray entries=new JsonArray();for(JsonElement id:members){var object=new JsonObject();object.add("id",id);entries.add(object);}
        list(entries,c->value(c,"id"),i->{selection=i;inputValue=value(entries.get(i).getAsJsonObject(),"id");rebuild();});
        button("members",9,bottom(),95,18,()->channelAction("members",""));button("remove",108,bottom(),86,18,()->channelAction("remove",input.getValue()));
        button("transfer",198,bottom(),Math.max(75,imageWidth-207),18,()->channelAction("transfer",input.getValue()));
        lines.add(Component.translatable("ct.gui.target_uuid").getString());
    }
    private void quota(){
        var grants=array("grants");lines.add(Component.translatable("ct.gui.quota",grants.size(),number("quotaLimit")).getString());
        list(grants,c->{var e=c.getAsJsonObject("location");return value(e,"server")+" "+value(e,"dimension")+" "+value(e,"x")+","+value(e,"y")+","+value(e,"z")+" "+value(c,"state")+" "+value(c,"reason");},i->{selection=i;rebuild();});
        button("remote_off",9,bottom(),160,18,()->{if(selection<grants.size())send("remote_off",value(grants.get(selection).getAsJsonObject(),"endpoint"),0);});
    }
    private void endpoints(){
        var endpoints=array("endpoints");list(endpoints,c->shortId(value(c,"id"))+" "+value(c,"server")+" "+value(c,"dimension")+" "+value(c,"x")+","+value(c,"y")+","+value(c,"z")+" "+value(c,"state"),i->{selection=i;rebuild();});
        button("endpoints",9,bottom(),160,18,()->channelAction("endpoints",""));
    }
    private void stock(){
        lines.add(Component.translatable("ct.gui.stock_advisory").getString());JsonArray entries=array("stock");
        int rows=Math.max(1,(bottom()-116)/19);int start=page*rows;for(int i=start;i<Math.min(entries.size(),start+rows);i++){
            int index=i;var entry=entries.get(i).getAsJsonObject();String name=value(entry,"nameKey").isEmpty()?value(entry,"name"):Component.translatable(value(entry,"nameKey")).getString();String label=name+" ["+value(entry,"profile")+"]";var b=literal((i==selection?"› ":"  ")+font.plainSubstrByWidth(label,imageWidth-32),9,66+(i-start)*19,imageWidth-18,()->{selection=index;rebuild();});
            b.setTooltip(Tooltip.create(Component.translatable("ct.gui.stock_quantities",value(entry,"localReady"),value(entry,"remoteKnown"),value(entry,"reserved"),value(entry,"inFlight"),value(entry,"unreachable"))));
        }
        literal("‹",imageWidth-42,45,16,()->{page=Math.max(0,page-1);rebuild();});literal("›",imageWidth-23,45,16,()->{if((page+1)*rows<entries.size())page++;rebuild();});
        if(entries.isEmpty())lines.add(Component.translatable("ct.gui.empty").getString());
        boolean fresh=stockReceived!=0 && System.nanoTime()-stockReceived<java.util.concurrent.TimeUnit.SECONDS.toNanos(5);
        var fetch=button("stock_fetch",9,bottom(),85,18,()->{if(selection<entries.size())send("stock_fetch",value(entries.get(selection).getAsJsonObject(),"id")+"|"+input.getValue(),number("stockEndpointVersion"));});fetch.active&=fresh && selection<entries.size() && value(entries.get(selection).getAsJsonObject(),"reason").isEmpty() && Boolean.parseBoolean(text("aeEnabled")) && text("stockChannel").equals(text("channel"));
        button("stock_first",98,bottom(),80,18,()->{stockCursor="";page=selection=0;send("stock_view","",0);});
        var next=button("stock_next",182,bottom(),Math.max(65,imageWidth-191),18,()->{stockCursor=text("stockNext");page=selection=0;send("stock_view",stockCursor,0);});next.active&=!text("stockNext").isEmpty();
        button("stock_cancel",9,imageHeight-35,150,16,()->{var requests=array("stockRequests");for(var r:requests){var object=r.getAsJsonObject();if(Set.of("PENDING","PARTIAL").contains(value(object,"state"))){send("stock_cancel",value(object,"id"),0);return;}}});
    }
    private void list(JsonArray array,java.util.function.Function<JsonObject,String> label,java.util.function.IntConsumer choose){
        int rows=Math.max(1,(bottom()-72)/19);int start=page*rows;int y=66;
        for(int i=start;i<array.size() && i<start+rows;i++){int index=i;String line=label.apply(array.get(i).getAsJsonObject());String clipped=font.plainSubstrByWidth(line,imageWidth-29);literal((i==selection?"› ":"  ")+clipped,9,y,imageWidth-18,()->choose.accept(index));y+=19;}
        if(array.isEmpty())lines.add(Component.translatable("ct.gui.empty").getString());
        literal("‹",imageWidth-42,45,16,()->{page=Math.max(0,page-1);rebuild();});literal("›",imageWidth-23,45,16,()->{if((page+1)*rows<array.size())page++;rebuild();});
    }
    boolean smokeReady(){return !pending && text("backend").equals("online") && Boolean.parseBoolean(text("registered"));}
    String smokeDebug(){return "status="+status+" registered="+text("registered")+" endpoint="+text("endpoint")+" bound="+text("channel")+" pause="+text("pause");}
    void smokeSend(String action,String argument,long expected){send(action,argument,expected);}
    boolean smokeSelect(String name){if(pending)return false;var list=array("channels");for(int i=0;i<list.size();i++)if(value(list.get(i).getAsJsonObject(),"name").equals(name)){channelSelection=i;return true;}return false;}
    void smokeBind(){send("bind",value(selectedChannel(),"id"),number("endpointVersion"));}
    boolean smokeBound(){return !pending && selectedChannel()!=null && text("channel").equals(value(selectedChannel(),"id"));}
    long smokeSettings(){return number("settingsVersion");}
    boolean smokeIdle(){return !pending;}
    boolean smokeAeReady(){return !pending && Boolean.parseBoolean(text("aeEnabled")) && text("aeState").equals("local_storage");}
    boolean smokeItemMode(String mode){if(pending)return false;for(var r:array("resources"))if(value(r.getAsJsonObject(),"kind").equals("cross_tesseract:item") && value(r.getAsJsonObject(),"mode").equals(mode))return true;return false;}
    void smokeStockOpen(){tab=6;selection=page=0;stockCursor="";rebuild();send("stock_view","",0);}
    boolean smokeStockReady(long remote,long local){if(pending || array("stock").isEmpty())return false;var row=array("stock").get(0).getAsJsonObject();return Long.parseLong(value(row,"remoteKnown"))>=remote && Long.parseLong(value(row,"localReady"))==local;}
    boolean smokeStockReason(String reason){return !array("stock").isEmpty() && value(array("stock").get(0).getAsJsonObject(),"reason").equals(reason);}
    void smokeStockFetch(){input.setValue("1");var row=array("stock").get(0).getAsJsonObject();send("stock_fetch",value(row,"id")+"|1",number("stockEndpointVersion"));}
    boolean smokeStockPending(){return !pending && array("stockRequests").asList().stream().anyMatch(r->Set.of("PENDING","PARTIAL").contains(value(r.getAsJsonObject(),"state")));}
    void smokeStockCancel(){for(var r:array("stockRequests"))if(Set.of("PENDING","PARTIAL").contains(value(r.getAsJsonObject(),"state"))){send("stock_cancel",value(r.getAsJsonObject(),"id"),0);return;}}
    boolean smokeStockCancelled(){return !pending && array("stockRequests").asList().stream().anyMatch(r->value(r.getAsJsonObject(),"state").equals("CANCELLED"));}
    boolean smokeSending(){if(pending)return false;for(var r:array("resources"))if(value(r.getAsJsonObject(),"kind").equals("cross_tesseract:fe")&&value(r.getAsJsonObject(),"mode").equals("SEND"))return true;return false;}
    void smokeValidate(){for(var child:children())if(child instanceof AbstractWidget w && (w.getX()<0||w.getY()<0||w.getX()+w.getWidth()>width||w.getY()+w.getHeight()>height))throw new IllegalStateException("UI widget outside window");}
    @Override protected void containerTick(){super.containerTick();if(pending && ++pendingTicks>400){pending=false;status="operation_unconfirmed";rebuild();}if(++refreshTicks%40==0 && !pending)send(tab==6?"stock_view":"refresh",tab==6?stockCursor:"",0);}
    @Override protected void renderBg(GuiGraphics g,float partial,int mouseX,int mouseY){
        g.fill(leftPos,topPos,leftPos+imageWidth,topPos+imageHeight,0xf0182233);g.fill(leftPos+1,topPos+1,leftPos+imageWidth-1,topPos+20,0xff24394d);
        g.fill(leftPos,topPos,leftPos+imageWidth,topPos+1,0xff60d4c9);g.fill(leftPos,topPos+imageHeight-1,leftPos+imageWidth,topPos+imageHeight,0xff60d4c9);
        for(int y=topPos+43;y<topPos+imageHeight-80;y+=10)g.fill(leftPos+7,y,leftPos+imageWidth-7,y+1,0x181aa899);
    }
    @Override protected void renderLabels(GuiGraphics g,int mouseX,int mouseY){
        g.drawString(font,title,9,6,0xffe8f8ff,false);String visibleStatus=tab==0 && status.equals("success") && !text("pause").isEmpty()?text("pause"):status;String statusKey=Set.of("processing","success","connecting","online").contains(visibleStatus)?"ct.status.":"ct.error.";
        if(visibleStatus.equals("stock_queued"))statusKey="ct.status.";g.drawString(font,font.plainSubstrByWidth(Component.translatable(statusKey+visibleStatus).getString(),imageWidth-16),9,imageHeight-14,pending?0xffffd185:0xffadf2e3,false);
        int y=45;for(String line:lines){g.drawString(font,font.plainSubstrByWidth(line,imageWidth-58),9,y,0xffcde0ef,false);y+=11;}
        if(tab==0 && !array("resources").isEmpty()){var port=array("resources").get(resourceSelection%array("resources").size()).getAsJsonObject();String amount=Component.translatable("ct.gui.buffers",value(port,"send"),value(port,"receive"),value(port,"rate")).getString();g.drawString(font,font.plainSubstrByWidth(amount,imageWidth-18),9,105,0xffb5e5f0,false);}
        else if(tab==6){var stock=array("stock");if(selection<stock.size()){var entry=stock.get(selection).getAsJsonObject();String quantities=Component.translatable("ct.gui.stock_quantities",value(entry,"localReady"),value(entry,"remoteKnown"),value(entry,"reserved"),value(entry,"inFlight"),value(entry,"unreachable")).getString();g.drawString(font,font.plainSubstrByWidth(quantities,imageWidth-18),9,bottom()-37,0xffb5e5f0,false);String reason=value(entry,"reason");if(System.nanoTime()-stockReceived>=java.util.concurrent.TimeUnit.SECONDS.toNanos(5))reason="stock_stale";if(!reason.isEmpty())g.drawString(font,font.plainSubstrByWidth(Component.translatable("ct.error."+reason).getString(),imageWidth-18),9,bottom()-26,0xffffd185,false);}var requests=array("stockRequests");if(!requests.isEmpty()){var r=requests.get(0).getAsJsonObject();String state=Component.translatable("ct.stock."+value(r,"state").toLowerCase(Locale.ROOT)).getString();g.drawString(font,font.plainSubstrByWidth(Component.translatable("ct.gui.stock_request",shortId(value(r,"id")),state,value(r,"remaining")).getString(),imageWidth-169),164,imageHeight-34,0xffcde0ef,false);}}
        else if(tab!=0){var c=selectedChannel();if(c!=null)g.drawString(font,font.plainSubstrByWidth(value(c,"name"),imageWidth-70),9,45,0xffcde0ef,false);}
    }
    @Override public void render(GuiGraphics g,int mouseX,int mouseY,float partial){super.render(g,mouseX,mouseY,partial);renderTooltip(g,mouseX,mouseY);}
}

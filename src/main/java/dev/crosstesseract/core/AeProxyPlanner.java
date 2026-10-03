package dev.crosstesseract.core;

import dev.crosstesseract.core.Models.AeNetwork;
import java.util.*;

/** Admission planning for the experimental native-node proxy, never an AE_CHANNEL balance. */
public final class AeProxyPlanner {
    public record Plan(int shadowNodes,String reason){public boolean ready(){return reason.isEmpty();}}
    public static Plan plan(String localServer,UUID localGrid,List<AeNetwork> advertisements){
        var unique=new HashMap<String,AeNetwork>();
        for(var ad:advertisements){
            DomainException.require(ad.usedChannels()>=0 && ad.usedChannels()<=4096,"invalid_ae_network");
            String id=ad.server()+":"+ad.network();
            unique.merge(id,ad,(a,b)->new AeNetwork(a.server(),a.network(),Math.max(a.usedChannels(),b.usedChannels()),a.active()&&b.active(),a.controller().equals(b.controller())?a.controller():"CONTROLLER_CONFLICT"));
        }
        int nodes=0,controllers=0;
        for(var ad:unique.values()){
            if(!ad.active())return new Plan(0,"ae_peer_inactive");
            if(ad.controller().equals("CONTROLLER_CONFLICT"))return new Plan(0,"ae_controller_conflict");
            if(ad.controller().equals("CONTROLLER_ONLINE"))controllers++;
            if(!ad.server().equals(localServer)||!ad.network().equals(localGrid))nodes=Math.addExact(nodes,ad.usedChannels());
        }
        if(controllers>1)return new Plan(0,"ae_multiple_controllers");
        if(nodes>32)return new Plan(0,"ae_proxy_capacity");
        return new Plan(nodes,"");
    }
    private AeProxyPlanner(){}
}

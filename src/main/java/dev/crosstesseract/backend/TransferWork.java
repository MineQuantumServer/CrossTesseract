package dev.crosstesseract.backend;

import dev.crosstesseract.core.*;
import dev.crosstesseract.core.LocalSnapshot.*;
import java.util.*;

/** Immutable ordinary-resource phases. Business IDs survive SQL deadlock retry. */
public final class TransferWork {
    private TransferWork(){}
    public record Demand(UUID transaction,String kind,long room,String profile,long quantum){}
    public record Request(LocalSnapshot snapshot,UUID channel,long endpointVersion,boolean checkpoint,
                          Set<String> sending,List<Demand> demands,int depositLimit){
        public Request{sending=Set.copyOf(sending);demands=List.copyOf(demands);}
        public UUID endpoint(){return snapshot.endpoint();}
    }
    public record Result(UUID endpoint,Set<UUID> committed,Set<UUID> consumed,List<Credit> received,String error){
        public Result{committed=Set.copyOf(committed);consumed=Set.copyOf(consumed);received=List.copyOf(received);}
        public static Result failed(UUID endpoint,String error){return new Result(endpoint,Set.of(),Set.of(),List.of(),error);}
    }
    public record Publication(LocalSnapshot snapshot,UUID channel,long endpointVersion,List<Credit> received,
                              Map<UUID,String> quarantined){
        public Publication{received=List.copyOf(received);quarantined=Map.copyOf(quarantined);}
    }
}

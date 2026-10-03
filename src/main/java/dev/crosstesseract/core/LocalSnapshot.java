package dev.crosstesseract.core;

import java.util.List;
import java.util.UUID;

/** Safe copies for disk/SQL workers. No Minecraft or optional-mod objects cross the thread boundary. */
public record LocalSnapshot(UUID endpoint,UUID world,long generation,long revision,List<Deposit> deposits,List<Credit> credits,ThermalBuffer.Snapshot thermal) {
    public LocalSnapshot(UUID endpoint,UUID world,long generation,long revision,List<Deposit> deposits,List<Credit> credits){this(endpoint,world,generation,revision,deposits,credits,ThermalBuffer.Snapshot.EMPTY);}
    public LocalSnapshot withThermal(ThermalBuffer.Snapshot thermal){return new LocalSnapshot(endpoint,world,generation,revision,deposits,credits,thermal);}
    public record Deposit(UUID transaction,UUID channel,Resource resource,long amount) {
        public Deposit { DomainException.require(amount>0,"invalid_amount"); }
    }
    public record Credit(UUID transaction,UUID channel,Resource resource,long original,long remaining) {
        public Credit { DomainException.require(original>0 && remaining>=0 && remaining<=original,"invalid_amount"); }
    }
    public LocalSnapshot { deposits=List.copyOf(deposits); credits=List.copyOf(credits); DomainException.require(revision>=0 && deposits.size()<=64 && credits.size()<=64,"snapshot_too_large"); }
}

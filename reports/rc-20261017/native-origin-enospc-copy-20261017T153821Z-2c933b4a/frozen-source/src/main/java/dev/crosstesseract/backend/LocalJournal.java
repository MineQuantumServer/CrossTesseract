package dev.crosstesseract.backend;

import dev.crosstesseract.core.*;
import dev.crosstesseract.core.LocalSnapshot.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.util.*;

/** Atomic fsynced endpoint checkpoint on a worker. Disk copy is authoritative over chunk NBT. */
public final class LocalJournal {
    private static final int MAGIC=0x43545431, MAX_FILE=8_388_608;
    private final Path root;
    @FunctionalInterface interface DirectoryBarrier{void force(Path directory) throws IOException;}
    private final DirectoryBarrier directoryBarrier;
    private record Proof(long revision,String digest){}
    private final Map<UUID,Proof> durable=new LinkedHashMap<>(16,0.75f,true);
    private final java.util.concurrent.atomic.LongAdder retried=new java.util.concurrent.atomic.LongAdder();
    private final java.util.concurrent.atomic.LongAdder writes=new java.util.concurrent.atomic.LongAdder(),bytes=new java.util.concurrent.atomic.LongAdder(),skipped=new java.util.concurrent.atomic.LongAdder();
    private final long[] barriers=new long[2048];private long barrierCount;
    private final Object[] locks=java.util.stream.IntStream.range(0,64).mapToObj(i->new Object()).toArray();
    private Object lock(UUID id){return locks[(id.hashCode()&Integer.MAX_VALUE)%locks.length];}
    public LocalJournal(Path root) throws IOException {this(root,LocalJournal::forceDirectory);}
    LocalJournal(Path root,DirectoryBarrier directoryBarrier) throws IOException {this.root=root;this.directoryBarrier=directoryBarrier;Files.createDirectories(root);}
    private static void forceDirectory(Path root) throws IOException {try(FileChannel directory=FileChannel.open(root,StandardOpenOption.READ)){directory.force(true);}}
    private synchronized boolean proved(LocalSnapshot snapshot,String digest){return new Proof(snapshot.revision(),digest).equals(durable.get(snapshot.endpoint()));}
    private synchronized void prove(LocalSnapshot snapshot,String digest){durable.put(snapshot.endpoint(),new Proof(snapshot.revision(),digest));if(durable.size()>1024)durable.remove(durable.keySet().iterator().next());}
    public void write(LocalSnapshot snapshot) throws IOException { synchronized(lock(snapshot.endpoint())) {
        byte[] data=encode(snapshot);
        String digest=HexFormat.of().formatHex(data,data.length-32,data.length);
        DomainException.require(data.length<=MAX_FILE,"snapshot_too_large");
        Path dest=root.resolve(snapshot.endpoint()+".ctj"), temp=root.resolve(snapshot.endpoint()+".pending");
        // Reject stale worker completions instead of overwriting a later checkpoint.
        if(Files.exists(dest)) {
            var previous=read(snapshot.endpoint()).orElseThrow();
            DomainException.require(snapshot.revision()>=previous.revision(),"stale_checkpoint");
            if(snapshot.revision()==previous.revision()){
                DomainException.require(snapshot.equals(previous),"checkpoint_version_conflict");
                // A previous atomic move may have succeeded while its directory fsync failed.
                // Visible equality is not proof of durability, including after process restart.
                if(!proved(snapshot,digest)){
                    long started=System.nanoTime();
                    try(FileChannel existing=FileChannel.open(dest,StandardOpenOption.WRITE)){existing.force(true);}
                    directoryBarrier.force(root);prove(snapshot,digest);retried.increment();recordBarrier(System.nanoTime()-started);
                }
                skipped.increment();return;
            }
        }
        long started=System.nanoTime();
        try(FileChannel c=FileChannel.open(temp,StandardOpenOption.CREATE,StandardOpenOption.TRUNCATE_EXISTING,StandardOpenOption.WRITE)) {
            var buffer=ByteBuffer.wrap(data); while(buffer.hasRemaining()) c.write(buffer); c.force(true);
        }
        Files.move(temp,dest,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
        directoryBarrier.force(root);prove(snapshot,digest);
        writes.increment();bytes.add(data.length);recordBarrier(System.nanoTime()-started);
    }}
    private synchronized void recordBarrier(long nanos){barriers[(int)(barrierCount++%barriers.length)]=nanos;}
    public synchronized Map<String,Number> stats(){var result=new LinkedHashMap<String,Number>();result.put("wal_writes",writes.sum());result.put("wal_bytes",bytes.sum());result.put("wal_identical_skipped",skipped.sum());result.put("wal_unproved_barrier_retries",retried.sum());result.put("wal_barriers",barrierCount);dev.crosstesseract.core.Metrics.quantiles(result,"wal_barrier_ms",barriers,barrierCount);return result;}
    public Optional<LocalSnapshot> read(UUID endpoint) throws IOException { synchronized(lock(endpoint)) {
        Path path=root.resolve(endpoint+".ctj"); if(!Files.exists(path)) return Optional.empty();
        long size=Files.size(path); if(size>MAX_FILE || size<36) throw new IOException("invalid checkpoint size");
        LocalSnapshot snapshot=decode(Files.readAllBytes(path));
        if(!endpoint.equals(snapshot.endpoint())) throw new IOException("checkpoint identity mismatch"); return Optional.of(snapshot);
    }
    }
    public static byte[] encode(LocalSnapshot s) throws IOException {
        var bytes=new ByteArrayOutputStream();
        try(var out=new DataOutputStream(bytes)) {
            out.writeInt(MAGIC); out.writeInt(2); uuid(out,s.endpoint()); uuid(out,s.world()); out.writeLong(s.generation()); out.writeLong(s.revision());
            out.writeInt(s.deposits().size()); for(var d:s.deposits()) { uuid(out,d.transaction()); uuid(out,d.channel()); resource(out,d.resource()); out.writeLong(d.amount()); }
            out.writeInt(s.credits().size()); for(var credit:s.credits()) { uuid(out,credit.transaction()); uuid(out,credit.channel()); resource(out,credit.resource()); out.writeLong(credit.original()); out.writeLong(credit.remaining()); }
            out.writeLong(s.thermal().microjoules());out.writeDouble(s.thermal().residual());out.writeBoolean(s.thermal().pending()!=null);
            if(s.thermal().pending()!=null){var p=s.thermal().pending();uuid(out,p.id());uuid(out,p.channel());out.writeLong(p.signedMicrojoules());out.writeLong(p.localBefore());out.writeDouble(p.capacity());out.writeLong(p.poolBefore());out.writeLong(p.poolAfter());}
        }
        byte[] content=bytes.toByteArray(); bytes.write(HexFormat.of().parseHex(Resource.hash(content))); return bytes.toByteArray();
    }
    public static LocalSnapshot decode(byte[] data) throws IOException {
        if(data.length>MAX_FILE || data.length<36) throw new IOException("invalid checkpoint size");
        byte[] content=Arrays.copyOf(data,data.length-32), digest=Arrays.copyOfRange(data,data.length-32,data.length);
        if(!Arrays.equals(HexFormat.of().parseHex(Resource.hash(content)),digest)) throw new IOException("checkpoint checksum mismatch");
        try(var in=new DataInputStream(new ByteArrayInputStream(content))) {
            if(in.readInt()!=MAGIC)throw new IOException("unsupported checkpoint format");int format=in.readInt();if(format!=1 && format!=2)throw new IOException("unsupported checkpoint format");
            UUID endpoint=uuid(in),world=uuid(in); long generation=in.readLong(),revision=in.readLong();
            int n=bounded(in.readInt(),64); var deposits=new ArrayList<Deposit>(n);
            for(int i=0;i<n;i++) deposits.add(new Deposit(uuid(in),uuid(in),resource(in),in.readLong()));
            n=bounded(in.readInt(),64); var credits=new ArrayList<Credit>(n);
            for(int i=0;i<n;i++) credits.add(new Credit(uuid(in),uuid(in),resource(in),in.readLong(),in.readLong()));
            ThermalBuffer.Snapshot thermal=ThermalBuffer.Snapshot.EMPTY;
            if(format==2){long energy=in.readLong();double residual=in.readDouble();ThermalBuffer.Pending pending=null;if(in.readBoolean())pending=new ThermalBuffer.Pending(uuid(in),uuid(in),in.readLong(),in.readLong(),in.readDouble(),in.readLong(),in.readLong());thermal=new ThermalBuffer.Snapshot(energy,residual,pending);}
            if(in.available()!=0) throw new IOException("trailing checkpoint data");
            return new LocalSnapshot(endpoint,world,generation,revision,deposits,credits,thermal);
        } catch(RuntimeException e) { throw new IOException("invalid checkpoint",e); }
    }
    private static int bounded(int n,int max) throws IOException { if(n<0 || n>max) throw new IOException("checkpoint limit"); return n; }
    private static void uuid(DataOutput out,UUID id) throws IOException { out.writeLong(id.getMostSignificantBits()); out.writeLong(id.getLeastSignificantBits()); }
    private static UUID uuid(DataInput in) throws IOException { return new UUID(in.readLong(),in.readLong()); }
    private static void resource(DataOutput out,Resource r) throws IOException { out.writeUTF(r.kind()); byte[] b=r.bytes(); out.writeInt(b.length); out.write(b); }
    private static Resource resource(DataInputStream in) throws IOException { String kind=in.readUTF(); int n=bounded(in.readInt(),Resource.MAX_BYTES); if(n>in.available()) throw new IOException("truncated payload"); return new Resource(kind,in.readNBytes(n)); }
}

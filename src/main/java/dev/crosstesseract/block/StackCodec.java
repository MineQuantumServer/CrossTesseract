package dev.crosstesseract.block;

import dev.crosstesseract.core.*;
import java.io.*;
import java.util.*;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.component.DataComponents;
import net.minecraft.nbt.*;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.fluids.FluidStack;

/** Registry names and complete component patches, never runtime numeric IDs or lenient-air decoding. */
public final class StackCodec {
    public static Resource item(ItemStack stack,HolderLookup.Provider registries) {
        DomainException.require(!stack.isEmpty() && stack.get(DataComponents.MAP_ID)==null,"external_world_item");
        return tag(Protocol.ITEM,stack.copyWithCount(1).save(registries));
    }
    public static Resource fluid(FluidStack stack,HolderLookup.Provider registries) { return tag(Protocol.FLUID,stack.copyWithAmount(1).save(registries)); }
    public static Resource tag(String kind,Tag tag) {
        try {
            validate(tag,0,new int[]{0});
            var bytes=new ByteArrayOutputStream();
            try(var out=new DataOutputStream(new LimitedStream(bytes,Resource.MAX_BYTES))) { NbtIo.writeAnyTag(sorted(tag),out); }
            return new Resource(kind,bytes.toByteArray());
        } catch(IOException ex) { throw new DomainException("payload_too_large"); }
    }
    public static Tag tag(Resource resource) {
        try(var in=new DataInputStream(new ByteArrayInputStream(resource.bytes()))) {
            Tag tag=NbtIo.readAnyTag(in,new NbtAccounter(262_144,32));
            DomainException.require(in.available()==0,"payload_corrupt"); validate(tag,0,new int[]{0}); return tag;
        } catch(IOException | RuntimeException ex) { if(ex instanceof DomainException domain) throw domain; throw new DomainException("payload_corrupt"); }
    }
    public static ItemStack item(Resource resource,HolderLookup.Provider registries,int count) {
        DomainException.require(resource.kind().equals(Protocol.ITEM) && count>0,"invalid_resource");
        var stack=ItemStack.CODEC.parse(registries.createSerializationContext(NbtOps.INSTANCE),tag(resource)).getOrThrow(msg->new DomainException("registry_missing"));
        DomainException.require(!stack.isEmpty() && stack.getCount()==1,"invalid_resource");
        DomainException.require(stack.get(DataComponents.MAP_ID)==null,"external_world_item");
        return stack.copyWithCount(count);
    }
    public static FluidStack fluid(Resource resource,HolderLookup.Provider registries,int amount) {
        DomainException.require(resource.kind().equals(Protocol.FLUID) && amount>0,"invalid_resource");
        var stack=FluidStack.CODEC.parse(registries.createSerializationContext(NbtOps.INSTANCE),tag(resource)).getOrThrow(msg->new DomainException("registry_missing"));
        DomainException.require(!stack.isEmpty() && stack.getAmount()==1,"invalid_resource"); return stack.copyWithAmount(amount);
    }
    private static Tag sorted(Tag tag) {
        if(tag instanceof CompoundTag compound) { var result=new CompoundTag(); for(String key:new TreeSet<>(compound.getAllKeys())) result.put(key,sorted(compound.get(key))); return result; }
        if(tag instanceof ListTag list) { var result=new ListTag(); for(Tag child:list) result.add(sorted(child)); return result; }
        return tag.copy();
    }
    private static void validate(Tag tag,int depth,int[] count) {
        DomainException.require(depth<=32 && ++count[0]<=4096,"payload_too_large");
        if(tag instanceof CompoundTag compound) { DomainException.require(compound.size()<=512,"payload_too_large"); for(String key:compound.getAllKeys()) { DomainException.require(!key.equals("minecraft:map_id"),"external_world_item"); DomainException.require(key.length()<=256,"payload_too_large"); validate(compound.get(key),depth+1,count); } }
        if(tag instanceof ListTag list) { DomainException.require(list.size()<=1024,"payload_too_large"); for(Tag child:list) validate(child,depth+1,count); }
        if(tag instanceof StringTag string) DomainException.require(string.getAsString().length()<=16_384,"payload_too_large");
        if(tag instanceof ByteArrayTag array)DomainException.require(array.getAsByteArray().length<=Resource.MAX_BYTES,"payload_too_large");
        if(tag instanceof IntArrayTag array)DomainException.require(array.getAsIntArray().length<=Resource.MAX_BYTES/4,"payload_too_large");
        if(tag instanceof LongArrayTag array)DomainException.require(array.getAsLongArray().length<=Resource.MAX_BYTES/8,"payload_too_large");
    }
    private static final class LimitedStream extends FilterOutputStream {
        private final int limit; private int written;
        LimitedStream(OutputStream out,int limit) { super(out);this.limit=limit; }
        @Override public void write(int b) throws IOException { if(++written>limit)throw new IOException("limit"); out.write(b); }
        @Override public void write(byte[] b,int off,int len) throws IOException { if(len>limit-written)throw new IOException("limit"); written+=len;out.write(b,off,len); }
    }
    private StackCodec() {}
}

package dev.crosstesseract.core;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Objects;

/** Canonical single-unit payload; quantities never use floating point. */
public final class Resource {
    public static final int MAX_BYTES = 65_536;
    private final String kind;
    private final byte[] bytes;
    private final String hash;
    public Resource(String kind, byte[] bytes) {
        DomainException.require(kind != null && kind.matches("[a-z0-9_]+:[a-z0-9_/.-]+") && kind.length()<=64, "invalid_resource");
        DomainException.require(bytes != null && bytes.length <= MAX_BYTES, "payload_too_large");
        this.kind=kind; this.bytes=bytes.clone(); this.hash=hash(bytes);
    }
    public String kind() { return kind; }
    public byte[] bytes() { return bytes.clone(); }
    public int size(){return bytes.length;}
    public String hash() { return hash; }
    public static String hash(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
    @Override public boolean equals(Object other) { return other instanceof Resource r && kind.equals(r.kind) && Arrays.equals(bytes,r.bytes); }
    @Override public int hashCode() { return Objects.hash(kind,hash); }
}

package dev.crosstesseract.core;

/** Stable error codes are translated at the player boundary; never expose SQL or credentials. */
public final class DomainException extends RuntimeException {
    private final String code;
    public DomainException(String code) { super(code); this.code = code; }
    public String code() { return code; }
    public static void require(boolean condition, String code) { if (!condition) throw new DomainException(code); }
}

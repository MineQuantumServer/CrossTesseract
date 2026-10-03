package dev.crosstesseract.core;

import java.util.Set;

public final class Protocol {
    public static final int VERSION = 1, FORMAT = 1;
    public static final String ITEM = "cross_tesseract:item", FLUID = "cross_tesseract:fluid", FE = "cross_tesseract:fe";
    public static final String EU = "cross_tesseract:gt_eu", CHEMICAL = "cross_tesseract:mek_chemical", HEAT = "cross_tesseract:mek_heat";
    public static final Set<String> BASE = Set.of(ITEM, FLUID, FE);
    public static final int VIEW = 1, SEND = 2, RECEIVE = 4, SETTINGS = 8, MEMBERS = 16, OWNER = 31, MEMBER = 7;
    public static boolean permits(int mask, int permission) { return (mask & permission) == permission; }
    public enum Mode {
        OFF(false,false), SEND(true,false), RECEIVE(false,true), BOTH(true,true);
        public final boolean send, receive;
        Mode(boolean send, boolean receive) { this.send=send; this.receive=receive; }
        public Mode next() { return values()[(ordinal()+1)%values().length]; }
        public static Mode safe(String value) { try { return valueOf(value); } catch (IllegalArgumentException e) { return OFF; } }
    }
    private Protocol() {}
}

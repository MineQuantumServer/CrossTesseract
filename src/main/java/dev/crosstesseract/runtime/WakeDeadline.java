package dev.crosstesseract.runtime;

/** A bounded input-coalescing deadline anchored to the current local tick. */
final class WakeDeadline {
    static long afterTick(long now,long tickStarted,long window){
        if(window<=0)throw new IllegalArgumentException("positive wake window required");
        long elapsed=now-tickStarted;
        // nanoTime may be negative. Only elapsed durations have meaning. A future
        // anchor falls back to the full window; an expired anchor is immediately due.
        long remaining=elapsed<0?window:window-Math.min(window,elapsed);
        return now+remaining;
    }
    private WakeDeadline(){}
}

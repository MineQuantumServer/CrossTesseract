package dev.crosstesseract.runtime;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class WakeDeadlineTest {
    @Test void signalsWithinOneTickShareTheSameDeadlineInsteadOfAddingAnotherTick(){
        long start=1_000_000_000L,window=50_000_000L;
        assertEquals(start+window,WakeDeadline.afterTick(start+1_000_000,start,window));
        assertEquals(start+window,WakeDeadline.afterTick(start+49_000_000,start,window));
    }
    @Test void expiredAndFutureAnchorsKeepTheWaitBounded(){
        assertEquals(200,WakeDeadline.afterTick(200,100,50));
        assertEquals(150,WakeDeadline.afterTick(100,200,50));
        assertThrows(IllegalArgumentException.class,()->WakeDeadline.afterTick(1,1,0));
    }
    @Test void negativeNanoTimesAndClockWrapStillUseElapsedDurations(){
        assertEquals(-50,WakeDeadline.afterTick(-90,-100,50));
        long start=Long.MAX_VALUE-20,now=Long.MIN_VALUE+9;
        assertEquals(Long.MIN_VALUE+29,WakeDeadline.afterTick(now,start,50));
    }
}

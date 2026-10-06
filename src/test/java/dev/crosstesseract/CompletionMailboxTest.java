package dev.crosstesseract;

import dev.crosstesseract.runtime.CompletionMailbox;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicIntegerArray;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CompletionMailboxTest {
    @Test void reservationsAndQueuedCallbacksShareOneBoundUntilPolled() {
        var mailbox = new CompletionMailbox(2);
        var first = mailbox.tryReserve();
        var second = mailbox.tryReserve();
        assertNotNull(first);
        assertNotNull(second);
        assertEquals(2, mailbox.capacity());
        assertEquals(2, mailbox.count());
        assertNull(mailbox.tryReserve());
        assertNull(mailbox.poll(), "unfinished work must retain capacity");
        assertEquals(2, mailbox.count());

        var executed = new AtomicInteger();
        Runnable callback = executed::incrementAndGet;
        first.complete(callback);
        second.complete(callback);
        assertEquals(0, executed.get(), "publishing must not run main-thread callbacks");
        assertEquals(2, mailbox.count());
        assertNull(mailbox.tryReserve(), "queued callbacks still retain capacity");

        assertSame(callback, mailbox.poll());
        assertEquals(1, mailbox.count());
        var replacement = mailbox.tryReserve();
        assertNotNull(replacement, "polling releases capacity before execution");
        assertEquals(2, mailbox.count());
        replacement.complete(callback);
        assertSame(callback, mailbox.poll());
        assertSame(callback, mailbox.poll());
        assertEquals(0, mailbox.count());
        assertEquals(0, executed.get());
        assertNull(mailbox.poll());
    }

    @Test void nullAndRepeatedCompletionsCannotReplaceOrDuplicateCallbacks() {
        var mailbox = new CompletionMailbox(1);
        var reservation = mailbox.tryReserve();
        assertNotNull(reservation);
        assertThrows(NullPointerException.class, () -> reservation.complete(null));
        assertNull(mailbox.poll());
        assertEquals(1, mailbox.count(), "null must not release an unfinished reservation");

        var first = new AtomicInteger();
        var duplicate = new AtomicInteger();
        reservation.complete(first::incrementAndGet);
        assertThrows(IllegalStateException.class, () -> reservation.complete(duplicate::incrementAndGet));
        assertEquals(1, mailbox.count());
        var callback = mailbox.poll();
        assertNotNull(callback);
        callback.run();
        assertEquals(1, first.get());
        assertEquals(0, duplicate.get());
        assertThrows(IllegalStateException.class, () -> reservation.complete(duplicate::incrementAndGet));
        assertNull(mailbox.poll());
        assertEquals(0, mailbox.count());
    }

    @Test void concurrentAdmissionCannotStartMoreWorkThanCapacity() throws Exception {
        var mailbox = new CompletionMailbox(3);
        var started = new AtomicInteger();
        var completed = new AtomicInteger();
        var barrier = new CyclicBarrier(8);
        var executor = Executors.newFixedThreadPool(8);
        try {
            var submissions = new ArrayList<Future<Boolean>>();
            for (int i = 0; i < 8; i++) {
                submissions.add(executor.submit(() -> {
                    barrier.await(10, TimeUnit.SECONDS);
                    var reservation = mailbox.tryReserve();
                    if (reservation == null) return false;
                    started.incrementAndGet();
                    reservation.complete(completed::incrementAndGet);
                    return true;
                }));
            }
            int accepted = 0;
            for (var submission : submissions) if (submission.get(10, TimeUnit.SECONDS)) accepted++;
            assertEquals(3, accepted);
            assertEquals(3, started.get());
            assertEquals(3, mailbox.count());
            assertEquals(0, completed.get());
            Runnable callback;
            while ((callback = mailbox.poll()) != null) callback.run();
            assertEquals(3, completed.get());
            assertEquals(0, mailbox.count());
        } finally {
            executor.shutdownNow();
        }
    }

    @Test void competingTerminalResultsPublishExactlyOneCallback() throws Exception {
        var mailbox = new CompletionMailbox(1);
        var reservation = mailbox.tryReserve();
        assertNotNull(reservation);
        var executions = new AtomicInteger();
        var barrier = new CyclicBarrier(2);
        var executor = Executors.newFixedThreadPool(2);
        try {
            var attempts = new ArrayList<Future<Boolean>>();
            for (int i = 0; i < 2; i++) {
                attempts.add(executor.submit(() -> {
                    barrier.await(10, TimeUnit.SECONDS);
                    try {
                        reservation.complete(executions::incrementAndGet);
                        return true;
                    } catch (IllegalStateException expected) {
                        return false;
                    }
                }));
            }
            int accepted = 0;
            for (var attempt : attempts) if (attempt.get(10, TimeUnit.SECONDS)) accepted++;
            assertEquals(1, accepted);
            assertEquals(1, mailbox.count());
            var callback = mailbox.poll();
            assertNotNull(callback);
            callback.run();
            assertEquals(1, executions.get());
            assertNull(mailbox.poll());
            assertEquals(0, mailbox.count());
        } finally {
            executor.shutdownNow();
        }
    }

    @Test void concurrentWorkersKeepEveryAcceptedCallback() throws Exception {
        int total = 64;
        var mailbox = new CompletionMailbox(total);
        var reservations = new ArrayList<CompletionMailbox.Reservation>();
        for (int i = 0; i < total; i++) {
            var reservation = mailbox.tryReserve();
            assertNotNull(reservation);
            reservations.add(reservation);
        }
        var executions = new AtomicIntegerArray(total);
        var executor = Executors.newFixedThreadPool(8);
        try {
            List<Future<?>> publications = new ArrayList<>();
            for (int i = 0; i < total; i++) {
                int index = i;
                publications.add(executor.submit(() -> reservations.get(index)
                        .complete(() -> executions.incrementAndGet(index))));
            }
            for (var publication : publications) publication.get(10, TimeUnit.SECONDS);
            assertEquals(total, mailbox.count());
            for (int i = 0; i < total; i++) {
                var callback = mailbox.poll();
                assertNotNull(callback, "every accepted task must retain its terminal callback");
                callback.run();
            }
            for (int i = 0; i < total; i++) assertEquals(1, executions.get(i));
            assertNull(mailbox.poll());
            assertEquals(0, mailbox.count());
        } finally {
            executor.shutdownNow();
        }
    }

    @Test void callbackFailureCannotLeakCapacity() {
        var mailbox = new CompletionMailbox(1);
        var reservation = mailbox.tryReserve();
        assertNotNull(reservation);
        reservation.complete(() -> { throw new IllegalStateException("callback failed"); });
        var callback = mailbox.poll();
        assertNotNull(callback);
        assertEquals(0, mailbox.count());
        assertThrows(IllegalStateException.class, callback::run);
        assertNotNull(mailbox.tryReserve());
    }

    @Test void invalidCapacityIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> new CompletionMailbox(0));
        assertThrows(IllegalArgumentException.class, () -> new CompletionMailbox(-1));
    }
}

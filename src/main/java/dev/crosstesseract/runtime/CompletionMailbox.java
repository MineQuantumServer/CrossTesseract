package dev.crosstesseract.runtime;

import java.util.Objects;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Nonblocking, bounded admission for work that must return one main-thread completion.
 * Reserve before submitting work: unfinished reservations and queued callbacks share
 * the same capacity. Taking a callback releases its reservation before it is run.
 */
public final class CompletionMailbox {
    private final int capacity;
    private final AtomicInteger count = new AtomicInteger();
    private final ConcurrentLinkedQueue<Runnable> ready = new ConcurrentLinkedQueue<>();

    public CompletionMailbox(int capacity) {
        if (capacity <= 0) throw new IllegalArgumentException("capacity must be positive");
        this.capacity = capacity;
    }

    /** Returns null when full. A rejected reservation must not start any work. */
    public Reservation tryReserve() {
        int observed = count.get();
        for (;;) {
            if (observed >= capacity) return null;
            if (count.compareAndSet(observed, observed + 1)) return new Reservation(this);
            observed = count.get();
        }
    }

    /** Returns the next published callback, or null; this method never runs callbacks. */
    public Runnable poll() {
        Runnable callback = ready.poll();
        if (callback != null) count.decrementAndGet();
        return callback;
    }

    public int capacity() { return capacity; }

    /** Outstanding reservations, including both unfinished work and queued callbacks. */
    public int count() { return count.get(); }

    public static final class Reservation {
        private final CompletionMailbox mailbox;
        private final AtomicBoolean completed = new AtomicBoolean();

        private Reservation(CompletionMailbox mailbox) { this.mailbox = mailbox; }

        /**
         * Publishes one terminal callback without waiting for the consumer.
         * A null callback is rejected without completing the reservation; a second
         * non-null completion is rejected even after the first callback was polled.
         * Submission rejection must also complete its reservation with a failure callback.
         */
        public void complete(Runnable callback) {
            Objects.requireNonNull(callback, "callback");
            if (!completed.compareAndSet(false, true)) {
                throw new IllegalStateException("reservation already completed");
            }
            mailbox.ready.add(callback);
        }
    }
}

package com.crypticnotes.mobile;

import java.nio.ByteBuffer;
import java.util.function.IntFunction;

/**
 * The encoded samples of the last few seconds, video and audio in arrival
 * order, so "save what just happened" needs no file until it is asked for.
 *
 * Everything lives in one buffer handed in by the caller plus a few primitive
 * arrays, all sized once: the steady state allocates nothing, which matters
 * because this runs for as long as the game does. A sample never straddles the
 * end of the buffer (the write position skips ahead instead), so every sample
 * can be handed to a muxer as one contiguous slice.
 *
 * Plain Java on purpose (no android.*), so the eviction and clip rules can be
 * run on a desktop JVM: see android/tests/ReplayBufferTest.java.
 * Not thread-safe; the recorder thread owns it and hands out {@link Clip} copies.
 */
final class ReplayBuffer {
    static final int VIDEO=0, AUDIO=1;
    /** Same bit as MediaCodec.BUFFER_FLAG_KEY_FRAME. */
    static final int KEY_FRAME=1;

    /** A self-contained copy of the part worth saving; safe on another thread. */
    static final class Clip {
        final ByteBuffer data;
        final int[] offset, length, flags, track;
        /** Rebased so the first video key frame is at zero. */
        final long[] ptsUs;
        final int count;
        final boolean audio;
        Clip(ByteBuffer data,int count) {
            this.data=data; this.count=count;
            offset=new int[count]; length=new int[count]; flags=new int[count]; track=new int[count];
            ptsUs=new long[count];
            audio=false;
        }
        private Clip(Clip samples,boolean audio) {
            data=samples.data; count=samples.count; offset=samples.offset; length=samples.length;
            flags=samples.flags; track=samples.track; ptsUs=samples.ptsUs; this.audio=audio;
        }
        /** From the first video frame to the last one. */
        long durationUs() {
            long last=0;
            for(int i=0;i<count;i++) if(track[i]==VIDEO) last=Math.max(last,ptsUs[i]);
            return last;
        }
    }

    private final ByteBuffer data;
    private final int capacity, slots;
    private final long keepUs;
    /** Logical byte position of each sample; the physical offset is this modulo the capacity. */
    private final long[] position, pts;
    private final int[] length, flags, track;
    private int tail, count;
    private long writePosition;

    /**
     * @param data    storage for the encoded bytes; its whole capacity is used
     * @param slots   how many samples can be described at once
     * @param keepUs  samples older than this, measured from the newest one, are dropped
     */
    ReplayBuffer(ByteBuffer data,int slots,long keepUs) {
        this.data=data; capacity=data.capacity(); this.slots=slots; this.keepUs=keepUs;
        position=new long[slots]; pts=new long[slots];
        length=new int[slots]; flags=new int[slots]; track=new int[slots];
    }

    /**
     * Two seconds are kept beyond the span: one key-frame interval, so a clip can
     * begin on a key frame at or before the mark instead of after it, and one of
     * slack. If the encoder overshoots its bit rate the bytes run out first and
     * the clip is simply shorter.
     */
    static int keepSeconds(int spanSeconds) { return spanSeconds+2; }

    /** Bytes for {@code spanSeconds} at these bit rates, with a quarter of headroom. */
    static int bytesFor(int spanSeconds,int videoBitrate,boolean audio) {
        long bytes=(long)(videoBitrate+(audio?128_000:0))/8*keepSeconds(spanSeconds)*5/4;
        return (int)Math.min(bytes,96L<<20);
    }

    /** Sample slots for {@code spanSeconds}: video frames plus about 47 AAC packets a second. */
    static int slotsFor(int spanSeconds,int fps,boolean audio) {
        return (fps+(audio?50:0))*keepSeconds(spanSeconds)*3/2;
    }

    int samples() { return count; }

    void clear() { tail=0; count=0; writePosition=0; }

    /** Copies {@code bytes} (position to limit, left untouched) in as the newest sample. */
    void add(int sampleTrack,ByteBuffer bytes,long ptsUs,int sampleFlags) {
        int size=bytes.remaining();
        if(size<=0) return;
        // A sample that cannot fit breaks the chain of frames that follow it;
        // an empty buffer is honest, a clip with a hole in it is not.
        if(size>capacity) { clear(); return; }
        long start=writePosition;
        if(start%capacity+size>capacity) start+=capacity-start%capacity;
        while(count>0 && (count==slots || start+size-position[tail]>capacity || ptsUs-pts[tail]>keepUs)) {
            tail=(tail+1)%slots; count--;
        }
        int slot=(tail+count)%slots;
        position[slot]=start; pts[slot]=ptsUs; length[slot]=size; flags[slot]=sampleFlags; track[slot]=sampleTrack;
        int mark=bytes.position();
        data.clear(); data.position((int)(start%capacity));
        data.put(bytes);
        bytes.position(mark);
        writePosition=start+size; count++;
    }

    /**
     * The last {@code spanUs} of video with the audio that belongs to it, or
     * null when no key frame has been stored yet.
     *
     * Video can only start on a key frame. The clip starts on the newest one
     * that is at least {@code spanUs} before the last frame, so it is never
     * shorter than asked while that much is stored; before that, on the oldest.
     *
     * @param allocate gives the buffer the copy is written into
     */
    Clip clip(long spanUs,IntFunction<ByteBuffer> allocate) {
        long newest=Long.MIN_VALUE;
        for(int n=0;n<count;n++) { int i=(tail+n)%slots; if(track[i]==VIDEO) newest=Math.max(newest,pts[i]); }
        int first=-1;
        for(int n=0;n<count;n++) {
            int i=(tail+n)%slots;
            if(track[i]!=VIDEO || (flags[i]&KEY_FRAME)==0) continue;
            if(first<0 || pts[i]<=newest-spanUs) first=n; else break;
        }
        if(first<0) return null;
        long origin=pts[(tail+first)%slots];
        int samples=0, bytes=0;
        boolean audio=false;
        for(int n=first;n<count;n++) {
            int i=(tail+n)%slots;
            if(pts[i]<origin) continue;      // audio queued just before the key frame
            samples++; bytes+=length[i]; audio|=track[i]==AUDIO;
        }
        ByteBuffer copy=allocate.apply(bytes);
        Clip clip=new Clip(copy,samples);
        int out=0, offset=0;
        for(int n=first;n<count;n++) {
            int i=(tail+n)%slots;
            if(pts[i]<origin) continue;
            data.clear(); data.position((int)(position[i]%capacity)); data.limit(data.position()+length[i]);
            copy.clear(); copy.position(offset);
            copy.put(data);
            clip.offset[out]=offset; clip.length[out]=length[i]; clip.flags[out]=flags[i];
            clip.track[out]=track[i]; clip.ptsUs[out]=pts[i]-origin;
            offset+=length[i]; out++;
        }
        data.clear(); copy.clear();
        return new Clip(clip,audio);
    }
}

package com.crypticnotes.mobile;
import java.nio.ByteBuffer;
public class ReplayBufferTest {
    static void check(boolean b,String what){if(!b)throw new AssertionError(what);}
    static ByteBuffer bytes(int size,int value){ByteBuffer b=ByteBuffer.allocate(size);for(int i=0;i<size;i++)b.put(i,(byte)value);return b;}
    /** One second of 10 fps video starting at second `s`: a key frame, then nine others; audio every 100 ms. */
    static void second(ReplayBuffer buffer,int s,int frameBytes,boolean audio){
        for(int f=0;f<10;f++){
            long pts=s*1_000_000L+f*100_000L;
            if(audio)buffer.add(ReplayBuffer.AUDIO,bytes(8,100+s),pts-20_000,0);
            buffer.add(ReplayBuffer.VIDEO,bytes(frameBytes,s),pts,f==0?ReplayBuffer.KEY_FRAME:0);
        }
    }
    public static void main(String[] args){
        // Nothing stored, or no key frame yet: nothing to save.
        ReplayBuffer empty=new ReplayBuffer(ByteBuffer.allocate(1000),50,5_000_000L);
        check(empty.clip(3_000_000L,ByteBuffer::allocate)==null,"empty buffer has no clip");
        empty.add(ReplayBuffer.VIDEO,bytes(10,1),0,0);
        check(empty.clip(3_000_000L,ByteBuffer::allocate)==null,"no key frame, no clip");

        // Ten seconds go in, five are kept; asking for three starts on a key
        // frame at least three seconds before the last frame.
        ReplayBuffer buffer=new ReplayBuffer(ByteBuffer.allocate(100_000),400,5_000_000L);
        for(int s=0;s<10;s++)second(buffer,s,100,true);
        ReplayBuffer.Clip clip=buffer.clip(3_000_000L,ByteBuffer::allocate);
        check(clip!=null && clip.audio,"clip with audio");
        check(clip.track[0]==ReplayBuffer.VIDEO && (clip.flags[0]&ReplayBuffer.KEY_FRAME)!=0 && clip.ptsUs[0]==0,"starts on a key frame at zero");
        check(clip.durationUs()==3_900_000L,"3 s asked, starts at second 6: "+clip.durationUs());
        long lastVideo=-1,lastAudio=-1;int offset=0;
        for(int i=0;i<clip.count;i++){
            check(clip.ptsUs[i]>=0,"no sample before the key frame");
            check(clip.offset[i]==offset,"samples are packed back to back");offset+=clip.length[i];
            boolean video=clip.track[i]==ReplayBuffer.VIDEO;
            check(clip.ptsUs[i]>(video?lastVideo:lastAudio),"each track stays in time order");
            if(video)lastVideo=clip.ptsUs[i];else lastAudio=clip.ptsUs[i];
            // The payload is the second it was recorded in: 6..9 for video, 106..109 for audio.
            int second=clip.data.get(clip.offset[i])&0xff;
            check(video?second>=6 && second<=9:second>=106 && second<=109,"payload belongs to the kept seconds: "+second);
            check(clip.length[i]==(video?100:8),"length survives");
        }
        check(offset==clip.data.capacity(),"the copy is exactly as large as the clip");
        // 40 video frames, and the 39 audio packets after the first key frame
        // (the one queued 20 ms before it is left out).
        check(clip.count==79,"sample count: "+clip.count);

        // More asked than stored: start on the oldest key frame still there.
        ReplayBuffer.Clip all=buffer.clip(60_000_000L,ByteBuffer::allocate);
        check(all.durationUs()>=4_900_000L && all.durationUs()<=5_900_000L,"keeps about five seconds: "+all.durationUs());

        // Bytes run out before time does: old samples go, the newest stay intact.
        ReplayBuffer small=new ReplayBuffer(ByteBuffer.allocate(2500),400,60_000_000L);
        for(int s=0;s<10;s++)second(small,s,100,false);
        ReplayBuffer.Clip tight=small.clip(60_000_000L,ByteBuffer::allocate);
        check(tight!=null && !tight.audio,"clip without audio");
        check((tight.data.get(tight.offset[tight.count-1])&0xff)==9,"newest sample kept");
        check((tight.data.get(tight.offset[0])&0xff)>=8,"only what fits is kept");
        for(int i=0;i<tight.count;i++){
            int v=tight.data.get(tight.offset[i])&0xff;
            for(int b=0;b<tight.length[i];b++)check((tight.data.get(tight.offset[i]+b)&0xff)==v,"a sample is never split across the wrap");
        }

        // Slots run out before bytes do.
        ReplayBuffer few=new ReplayBuffer(ByteBuffer.allocate(100_000),15,60_000_000L);
        for(int s=0;s<4;s++)second(few,s,10,false);
        check(few.samples()==15,"slot limit holds");
        check(few.clip(60_000_000L,ByteBuffer::allocate).durationUs()==900_000L,"only the last full second has a key frame");

        // A sample larger than the whole buffer empties it rather than leaving a hole.
        small.add(ReplayBuffer.VIDEO,bytes(5000,7),99_000_000L,0);
        check(small.samples()==0,"oversized sample clears the buffer");

        // The caller's buffer is left where it was.
        ByteBuffer source=bytes(30,5);source.position(4);source.limit(20);
        buffer.add(ReplayBuffer.VIDEO,source,10_000_000L,ReplayBuffer.KEY_FRAME);
        check(source.position()==4 && source.limit()==20,"source buffer untouched");

        // Sizing: 30 s at 4 Mbps with sound is about 20 MB, 32 s are kept.
        check(ReplayBuffer.keepSeconds(30)==32,"keeps one key-frame interval and a second of slack");
        int size=ReplayBuffer.bytesFor(30,4_000_000,true);
        check(size>19_000_000 && size<22_000_000,"buffer size: "+size);
        check(ReplayBuffer.slotsFor(30,30,true)==(30+50)*32*3/2,"slots");
        System.out.println("Replay buffer tests passed");
    }
}

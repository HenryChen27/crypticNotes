package com.crypticnotes.mobile;
public class TouchCaptureSessionTest {
    static void check(boolean value){if(!value)throw new AssertionError();}
    public static void main(String[] args){
        TouchCaptureSession s=new TouchCaptureSession();check(!s.awake());
        s.wake(100);check(s.awake());check(!s.closed(false,200));
        check(!s.closed(false,5099));check(s.closed(false,5100));
        s.sleep();check(!s.awake());
        s.wake(6000);check(!s.closed(true,6100));check(!s.openingExpired(99999));
        check(!s.closed(true,99999));check(s.closed(false,100000));
        s.sleep();s.wake(200000);check(!s.closed(false,200001));
        check(s.openingExpired(205000));s.sleep();check(!s.awake());
        FrameReuse.Latest latest=new FrameReuse.Latest();Object reader=new Object();
        latest.remember(reader,new int[]{1});check(latest.forReader(reader)!=null);
        latest.clear();check(latest.forReader(reader)==null);
        System.out.println("Touch capture lifecycle passed");
    }
}

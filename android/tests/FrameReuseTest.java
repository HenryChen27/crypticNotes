package com.crypticnotes.mobile;
public class FrameReuseTest {
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] args){
  check(FrameReuse.sampleCoordinate(0,2400,160)==7);
  check(FrameReuse.sampleCoordinate(140,2400,160)==2107);
  check(FrameReuse.sampleCoordinate(159,2400,160)==2392);
  check(FrameReuse.sampleCoordinate(0,1080,90)==6);
  check(FrameReuse.sampleCoordinate(89,1080,90)==1074);
  check(FrameReuse.sampleCoordinate(159,1,160)==0);
  int[] a=new int[14400],b=a.clone();
  check(FrameReuse.same(a,b,true));check(FrameReuse.same(a,b,false));
  b[40*160+90]=1;check(FrameReuse.same(a,b,true));check(!FrameReuse.same(a,b,false));
  b=a.clone();b[8*160+130]=1;check(!FrameReuse.same(a,b,true));
  check(!FrameReuse.same(null,b,true));
  System.out.println("Unchanged evidence reuse and floor/map change invalidation passed");
 }
}

package com.crypticnotes.mobile;
public class FrameReuseTest {
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] args){
  int[] a=new int[14400],b=a.clone();
  check(FrameReuse.same(a,b,true));check(FrameReuse.same(a,b,false));
  b[40*160+90]=1;check(FrameReuse.same(a,b,true));check(!FrameReuse.same(a,b,false));
  b=a.clone();b[8*160+130]=1;check(!FrameReuse.same(a,b,true));
  check(!FrameReuse.same(null,b,true));
  System.out.println("Unchanged evidence reuse and floor/map change invalidation passed");
 }
}

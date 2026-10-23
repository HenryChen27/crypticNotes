package com.crypticnotes.mobile;
import java.nio.ByteBuffer;
public class RgbaRowsTest {
    static void check(boolean b){if(!b)throw new AssertionError();}
    public static void main(String[] args){
        ByteBuffer image=ByteBuffer.allocate(20);
        for(int i=0;i<8;i++)image.put(i,(byte)(i+1));
        for(int i=0;i<8;i++)image.put(12+i,(byte)(i+9));
        image.position(3);
        ByteBuffer packed=RgbaRows.packed(image,2,2,12);
        check(image.position()==3);check(packed.remaining()==16);
        for(int i=0;i<16;i++)check(packed.get()==(byte)(i+1));
        ByteBuffer direct=RgbaRows.packed(ByteBuffer.wrap(new byte[]{1,2,3,4}),1,1,4);
        check(direct.remaining()==4 && direct.get()==1);
        boolean rejected=false;try{RgbaRows.packed(ByteBuffer.allocate(15),2,2,12);}catch(IllegalArgumentException expected){rejected=true;}
        check(rejected);System.out.println("RGBA padded-row tests passed");
    }
}

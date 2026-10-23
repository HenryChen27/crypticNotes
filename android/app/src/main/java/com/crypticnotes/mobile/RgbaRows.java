package com.crypticnotes.mobile;
import java.nio.ByteBuffer;
/** Copies valid RGBA pixels without assuming the last row has trailing padding. */
final class RgbaRows {
    static ByteBuffer packed(ByteBuffer input,int width,int height,int rowStride){
        int rowBytes=Math.multiplyExact(width,4),required=Math.multiplyExact(rowBytes,height);
        if(width<=0 || height<=0 || rowStride<rowBytes || (long)(height-1)*rowStride+rowBytes>input.limit())
            throw new IllegalArgumentException("Incomplete RGBA image rows");
        ByteBuffer source=input.duplicate();source.rewind();
        if(rowStride==rowBytes){source.limit(required);return source;}
        ByteBuffer result=ByteBuffer.allocate(required);
        for(int y=0;y<height;y++){
            source.limit(input.limit());source.position(y*rowStride);source.limit(y*rowStride+rowBytes);
            result.put(source);
        }
        result.flip();return result;
    }
}

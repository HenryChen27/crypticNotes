package com.crypticnotes.mobile;

import android.content.Context;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

final class ReviewDelivery {
    static JSONObject read(Context context){
        if(!BuildConfig.LOCAL_REVIEW)return null;
        File file=new File(context.getFilesDir(),"review-messages.json");
        if(!file.isFile())return null;
        try(FileInputStream input=new FileInputStream(file)){
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] chunk=new byte[4096];
            for(int count;(count=input.read(chunk))!=-1;){
                if(bytes.size()+count>65536)return null;
                bytes.write(chunk,0,count);
            }
            return new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8));
        }catch(Exception invalid){return null;}
    }
}

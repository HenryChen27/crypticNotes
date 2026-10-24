package com.crypticnotes.mobile;

import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.*;
import android.os.Build;
import android.widget.ImageView;
import java.io.InputStream;
import java.nio.ByteBuffer;

/** Native frame decoding keeps the larger doll sharp without a large decoded atlas. */
final class DollLoadingView extends ImageView {
    private static byte[] animationBytes;
    DollLoadingView(Context c){super(c);setContentDescription("正在加载");setScaleType(ScaleType.FIT_CENTER);setImageDrawable(createAnimation(c));}
    static Drawable createAnimation(Context c){
        try{
            if(Build.VERSION.SDK_INT>=28){
                synchronized(DollLoadingView.class){
                    if(animationBytes==null)try(InputStream in=c.getAssets().open("loading/doll-matching.webp")){animationBytes=MiniGameStore.bytes(in,4*1024*1024);}
                }
                Drawable image=ImageDecoder.decodeDrawable(ImageDecoder.createSource(ByteBuffer.wrap(animationBytes)));
                if(image instanceof AnimatedImageDrawable)((AnimatedImageDrawable)image).setRepeatCount(AnimatedImageDrawable.REPEAT_INFINITE);
                return image;
            }
            try(InputStream in=c.getAssets().open("loading/doll-matching.png")){
                Bitmap sheet=BitmapFactory.decodeStream(in);AnimationDrawable animation=new AnimationDrawable();
                for(int i=0;i<44;i++)animation.addFrame(new BitmapDrawable(c.getResources(),Bitmap.createBitmap(sheet,i%8*128,i/8*144,128,144)),50);
                sheet.recycle();animation.setOneShot(false);return animation;
            }
        }catch(Exception e){android.util.Log.w("CrypticNotes","Loading animation unavailable",e);return null;}
    }
    static void animate(Drawable image,boolean enabled){
        if(image instanceof Animatable){if(enabled)((Animatable)image).start();else ((Animatable)image).stop();}
    }
    @Override protected void onAttachedToWindow(){super.onAttachedToWindow();animate(getDrawable(),getWindowVisibility()==VISIBLE);}
    @Override protected void onDetachedFromWindow(){animate(getDrawable(),false);super.onDetachedFromWindow();}
    @Override protected void onWindowVisibilityChanged(int visibility){super.onWindowVisibilityChanged(visibility);animate(getDrawable(),visibility==VISIBLE&&isShown());}
}

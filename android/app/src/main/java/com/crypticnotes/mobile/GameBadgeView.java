package com.crypticnotes.mobile;

import android.content.Context;
import android.graphics.*;
import android.os.SystemClock;
import android.widget.ImageView;

/** Background mini-game replaces the emblem with its jellyfish icon. */
final class GameBadgeView extends ImageView {
    final Paint ink=new Paint(Paint.ANTI_ALIAS_FLAG);
    Bitmap fish;
    GameBadgeView(Context context){super(context);ink.setFilterBitmap(true);try(java.io.InputStream stream=context.getAssets().open("minigames/fish5.png")){fish=BitmapFactory.decodeStream(stream);}catch(java.io.IOException ignored){}}
    @Override protected void onDraw(Canvas canvas){
        if(MiniGameOverlayService.hidden && fish!=null){
            float size=Math.min(getWidth(),getHeight())*.90f;
            float left=(getWidth()-size)/2f,top=(getHeight()-size)/2f;
            canvas.drawBitmap(fish,null,new RectF(left,top,left+size,top+size),ink);
        }else super.onDraw(canvas);
        postInvalidateDelayed(200);
    }
}

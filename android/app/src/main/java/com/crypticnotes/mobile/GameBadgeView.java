package com.crypticnotes.mobile;

import android.content.Context;
import android.graphics.*;
import android.os.SystemClock;
import android.widget.ImageView;

/** Background mini-game replaces the emblem with the active game icon. */
final class GameBadgeView extends ImageView {
    private boolean loading;
    private android.graphics.drawable.Drawable normal,loadingImage;
    void setLoading(boolean value){
        if(loading==value)return;loading=value;
        if(value){normal=getDrawable();if(loadingImage==null)loadingImage=DollLoadingView.createAnimation(getContext());setImageDrawable(loadingImage);DollLoadingView.animate(loadingImage,true);}
        else{DollLoadingView.animate(loadingImage,false);setImageDrawable(normal);}
        invalidate();
    }
    boolean loading(){return loading;}
    final Paint ink=new Paint(Paint.ANTI_ALIAS_FLAG);
    GameBadgeView(Context context){super(context);ink.setFilterBitmap(true);}
    @Override protected void onDetachedFromWindow(){DollLoadingView.animate(loadingImage,false);super.onDetachedFromWindow();}
    @Override protected void onDraw(Canvas canvas){
        if(loading){super.onDraw(canvas);return;}
        Bitmap fish=MiniGameOverlayService.hidden?GameIcons.bitmap(getContext(),MiniGameOverlayService.activeGameId):null;
        if(MiniGameOverlayService.hidden && fish!=null){
            float size=Math.min(getWidth(),getHeight())*.90f;
            float left=(getWidth()-size)/2f,top=(getHeight()-size)/2f;
            canvas.drawBitmap(fish,null,new RectF(left,top,left+size,top+size),ink);
        }else super.onDraw(canvas);
        postInvalidateDelayed(200);
    }
}

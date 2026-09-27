package com.crypticnotes.mobile;
import android.content.Context;
import android.graphics.*;
import android.view.*;

/** Region picker for the map-entry tap area, drawn in the desktop's chalk style. */
public class RegionCalibrationView extends View {
    public interface Listener{void saved(RectF normalized);void cancel();}
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF selected=new RectF();
    private final RectF initial;
    private final Listener listener;
    private final float scale;
    private float startX,startY;
    private boolean sizing=false;

    public RegionCalibrationView(Context context,RectF initial,Listener listener){
        super(context);
        this.initial=new RectF(initial);
        this.listener=listener;
        this.scale=Theme.dp(context);
        text.setTypeface(Theme.typeface(context));
    }

    @Override protected void onSizeChanged(int w,int h,int oldw,int oldh){
        selected.set(initial.left*w,initial.top*h,initial.right*w,initial.bottom*h);
        text.setTextSize(Math.max(Theme.px(getContext(),15),h*.026f));
    }

    /** The three action cells, as fractions. Hit testing uses the same numbers. */
    private RectF actionCell(int index){
        float left=index==0?getWidth()*.36f:index==1?getWidth()*.55f:getWidth()*.75f;
        float right=index==0?getWidth()*.55f:index==1?getWidth()*.75f:getWidth()*.94f;
        return new RectF(left,getHeight()*.80f,right,getHeight()*.94f);
    }

    @Override protected void onDraw(Canvas canvas){
        canvas.drawColor(0x660b1620);

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(0x44608095);
        canvas.drawRect(selected,paint);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(3);
        paint.setColor(0xffe5edf2);
        paint.setPathEffect(new DashPathEffect(new float[]{12,7},0));
        canvas.drawRect(selected,paint);
        paint.setPathEffect(null);

        text.setColor(Theme.TEXT);
        Paint.FontMetrics metrics=text.getFontMetrics();
        canvas.drawText("拖动框选左上角地图入口，保存后仅在此范围转交点击",
                getWidth()*.22f,getHeight()*.12f-metrics.ascent,text);
        text.setColor(Theme.MUTED);
        canvas.drawText("不要框进移动摇杆或其他操作键",
                getWidth()*.22f,getHeight()*.12f-metrics.ascent+Theme.px(getContext(),20),text);

        String[] labels={"默认","取消","保存"};
        Paint bitmapPaint=Theme.SCALE;
        for(int i=0;i<labels.length;i++){
            RectF cell=actionCell(i);
            Rect bounds=new Rect(Math.round(cell.left),Math.round(cell.top),
                    Math.round(cell.right),Math.round(cell.bottom));
            Bitmap chalk=Theme.chalk(getContext(),Math.max(2,bounds.width()),Math.max(2,bounds.height()),
                    i==2?Theme.Chalk.BRIGHT:Theme.Chalk.DEEP,.7f,"rounded",i==0,i==2);
            canvas.drawBitmap(chalk,null,bounds,bitmapPaint);
            text.setColor(i==2?Theme.INK:Theme.HEADING);
            canvas.drawText(labels[i],cell.centerX(),cell.centerY()-(metrics.ascent+metrics.descent)/2f,text);
        }
    }

    @Override public boolean onTouchEvent(MotionEvent event){
        float x=Math.max(0,Math.min(getWidth(),event.getX())),y=Math.max(0,Math.min(getHeight(),event.getY()));
        if(event.getAction()==MotionEvent.ACTION_DOWN){
            if(y>=getHeight()*.8f && y<=getHeight()*.94f && x>=getWidth()*.36f){
                if(x<getWidth()*.55f){selected.set(.04f*getWidth(),.065f*getHeight(),.19f*getWidth(),.265f*getHeight());invalidate();}
                else if(x<getWidth()*.75f)listener.cancel();
                else if(selected.width()>20 && selected.height()>20)listener.saved(new RectF(selected.left/getWidth(),selected.top/getHeight(),selected.right/getWidth(),selected.bottom/getHeight()));
                return true;
            }
            startX=x;startY=y;sizing=true;
        }
        if(sizing){selected.set(Math.min(startX,x),Math.min(startY,y),Math.max(startX,x),Math.max(startY,y));invalidate();}
        if(event.getAction()==MotionEvent.ACTION_UP||event.getAction()==MotionEvent.ACTION_CANCEL)sizing=false;
        return true;
    }
}

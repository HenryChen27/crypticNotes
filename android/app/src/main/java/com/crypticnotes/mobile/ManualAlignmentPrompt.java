package com.crypticnotes.mobile;

import android.content.Context;
import android.graphics.*;
import android.os.SystemClock;
import android.view.*;

/** Single consent, three-second expiry; no font-dependent symbol glyphs. */
final class ManualAlignmentPrompt extends View {
    private final Runnable accept, ignore;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Theme.ChalkDrawable background;
    private long started;
    private boolean finished;
    private final Runnable tick=new Runnable() {
        public void run() {
            if(finished) return;
            if(SystemClock.elapsedRealtime()-started>=3000) { finish(false); return; }
            invalidate(); postDelayed(this,30);
        }
    };
    ManualAlignmentPrompt(Context context,Runnable accept,Runnable ignore) {
        super(context); this.accept=accept; this.ignore=ignore;
        background=new Theme.ChalkDrawable(context,Theme.Chalk.DEEP,1.1f,"rounded",true,true);
    }
    @Override protected void onAttachedToWindow() {
        super.onAttachedToWindow(); started=SystemClock.elapsedRealtime();post(tick);
    }
    @Override protected void onDetachedFromWindow() {
        removeCallbacks(tick);super.onDetachedFromWindow();
    }
    private void finish(boolean yes) {
        if(finished) return; finished=true;removeCallbacks(tick);
        if(yes) accept.run(); else ignore.run();
    }
    @Override protected void onDraw(Canvas canvas) {
        background.setBounds(0,0,getWidth(),getHeight());background.draw(canvas);
        canvas.save();canvas.scale(getWidth()/200f,getHeight()/106f);
        paint.setStyle(Paint.Style.FILL);paint.setColor(Color.rgb(198,215,227));
        float remaining=Math.max(0,1-(SystemClock.elapsedRealtime()-started)/3000f);
        canvas.drawArc(new RectF(15,12,27,24),-90,360*remaining,true,paint);
        paint.setTypeface(Theme.typeface(getContext()));paint.setTextSize(15);paint.setTextAlign(Paint.Align.CENTER);
        canvas.drawText("是否需要直接叠图？",100,48,paint);
        paint.setColor(Color.argb(125,28,47,63));
        canvas.drawRoundRect(new RectF(23,62,93,94),5,5,paint);
        canvas.drawRoundRect(new RectF(107,62,177,94),5,5,paint);
        paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2.5f);paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setColor(Color.rgb(131,196,161));
        canvas.drawLine(49,78,56,85,paint);canvas.drawLine(56,85,69,70,paint);
        paint.setColor(Color.rgb(223,133,140));
        canvas.drawLine(135,71,149,85,paint);canvas.drawLine(149,71,135,85,paint);
        paint.setStyle(Paint.Style.FILL);canvas.restore();
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        if(event.getAction()==MotionEvent.ACTION_UP && event.getY()>=getHeight()*62/106f
                && event.getY()<=getHeight()*94/106f) {
            float x=event.getX()*200/getWidth();
            if(x>=23 && x<=93) { TouchFeedback.click(this);finish(true); }
            else if(x>=107 && x<=177) { TouchFeedback.click(this);finish(false); }
        }
        return true;
    }
}

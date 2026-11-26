package com.crypticnotes.mobile;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.Gravity;
import android.widget.TextView;
/** Quiet dark navigation tab, distinct from action buttons. */
final class DarkTab extends TextView {
    DarkTab(Context c,String label){super(c);setText(label);Theme.text(this,14,Theme.TEXT);setGravity(Gravity.CENTER);setPadding(Theme.px(c,9),0,Theme.px(c,9),0);setClickable(true);select(false);}
    private boolean update;private final Paint dot=new Paint(Paint.ANTI_ALIAS_FLAG);
    void select(boolean selected){setBackground(selected?new Theme.ChalkDrawable(getContext(),Theme.Chalk.BRIGHT,.7f,"rect",true,true):null);setAlpha(1f);setSelected(selected);setTextColor(selected?Theme.INK:Theme.TEXT);}
    void setUpdate(boolean value){update=value;setContentDescription(getText()+(value?"，有更新":""));invalidate();}
    @Override protected void onDraw(Canvas canvas){super.onDraw(canvas);if(update){dot.setColor(0xffe44b4b);canvas.drawCircle(getWidth()-Theme.px(getContext(),8),Theme.px(getContext(),9),Theme.px(getContext(),4),dot);}}
    @Override public boolean performClick(){TouchFeedback.click(this);return super.performClick();}
}

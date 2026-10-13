package com.crypticnotes.mobile;
import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.TextView;
/** Quiet dark navigation tab, distinct from action buttons. */
final class DarkTab extends TextView {
    DarkTab(Context c,String label){super(c);setText(label);Theme.text(this,14,Theme.TEXT);setGravity(Gravity.CENTER);setPadding(Theme.px(c,9),0,Theme.px(c,9),0);setClickable(true);select(false);}
    void select(boolean selected){GradientDrawable bg=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{selected?0xe5a6bcc8:0x60304453,selected?0xe592aab8:0x602b4050});bg.setCornerRadius(Theme.px(getContext(),1));setBackground(bg);setAlpha(selected?1f:.75f);setSelected(selected);setTextColor(selected?Theme.INK:Theme.TEXT);if(getText().toString().equals("设置"))ActionIcon.set(this,ActionIcon.GEAR,false);else ActionIcon.set(this,ActionIcon.GAME,MiniGameUpdates.available(getContext()));}
    @Override public boolean performClick(){TouchFeedback.click(this);return super.performClick();}
}

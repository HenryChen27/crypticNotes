package com.crypticnotes.mobile;
import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.TextView;
/** Quiet dark navigation tab, distinct from action buttons. */
final class DarkTab extends TextView {
    DarkTab(Context c,String label){super(c);setText(label);Theme.text(this,14,Theme.TEXT);setGravity(Gravity.CENTER);setPadding(Theme.px(c,9),0,Theme.px(c,9),0);setClickable(true);select(false);}
    void select(boolean selected){GradientDrawable bg=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{selected?0xe52b4051:0x80182530,selected?0xe5213343:0x80131e29});bg.setCornerRadius(Theme.px(getContext(),7));setBackground(bg);setAlpha(selected?1f:.75f);setSelected(selected);}
    @Override public boolean performClick(){TouchFeedback.click(this);return super.performClick();}
}

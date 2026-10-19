package com.crypticnotes.mobile;
import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.TextView;
/** Quiet dark navigation tab, distinct from action buttons. */
final class DarkTab extends TextView {
    DarkTab(Context c,String label){super(c);setText(label);Theme.text(this,14,Theme.TEXT);setGravity(Gravity.CENTER);setPadding(Theme.px(c,9),0,Theme.px(c,9),0);setClickable(true);select(false);}
    void select(boolean selected){setBackground(selected?new Theme.ChalkDrawable(getContext(),Theme.Chalk.BRIGHT,.7f,"rect",true,true):null);setAlpha(1f);setSelected(selected);setTextColor(selected?Theme.INK:Theme.TEXT);ActionIcon.set(this,getText().toString().equals("小游戏")?ActionIcon.GAME:ActionIcon.MAP,getText().toString().equals("小游戏")&&MiniGameUpdates.available(getContext()));}
    @Override public boolean performClick(){TouchFeedback.click(this);return super.performClick();}
}

package com.crypticnotes.mobile;

import android.view.View;
import android.view.HapticFeedbackConstants;

final class TouchFeedback {
    static void click(View view) {
        if(view.isEnabled() && view.getContext().getSharedPreferences("mobile",0).getBoolean("touch_feedback",true))
            view.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK);
    }
}

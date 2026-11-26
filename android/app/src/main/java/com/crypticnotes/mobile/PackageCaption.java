package com.crypticnotes.mobile;

import android.content.Context;
import android.text.TextUtils;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.util.Locale;

final class PackageCaption extends LinearLayout {
    private final TextView detail;
    private final String name;
    PackageCaption(Context context,String name){
        super(context);this.name=name;setGravity(Gravity.CENTER_VERTICAL);
        int gap=Theme.px(context,6);setPadding(0,gap,0,gap);
        TextView title=Theme.text(new TextView(context),14,Theme.TEXT);title.setText(name);
        title.setSingleLine(true);title.setEllipsize(TextUtils.TruncateAt.END);title.setPadding(0,0,gap,0);
        addView(title,new LayoutParams(0,-2,1));
        detail=Theme.text(new TextView(context),12,Theme.MUTED);
        detail.setSingleLine(true);detail.setEllipsize(TextUtils.TruncateAt.MIDDLE);addView(detail);
    }
    @Override protected void onMeasure(int widthSpec,int heightSpec){
        if(MeasureSpec.getMode(widthSpec)!=MeasureSpec.UNSPECIFIED)detail.setMaxWidth(MeasureSpec.getSize(widthSpec)*2/3);
        super.onMeasure(widthSpec,heightSpec);
    }
    void describe(boolean installed,String version,long bytes){
        String size=bytes>=1048576?String.format(Locale.ROOT,"%.1f",bytes/1048576.0).replaceFirst("\\.0$","")+"MB":
                bytes>0?Math.max(1,Math.round(bytes/1024.0))+"KB":"大小待查";
        String info=(installed?"已安装":"未安装")+" · "+(version==null||version.isEmpty()?"版本待查":version)+" · "+size;
        detail.setText(info);setContentDescription(name+" · "+info);setTooltipText(getContentDescription());
    }
}

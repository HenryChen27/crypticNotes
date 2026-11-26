package com.crypticnotes.mobile;

import android.app.Activity;
import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * The 邮箱 section of the settings page: the list, newest first, each mail
 * opening in its own reader, and 一键已读.
 *
 * Incoming mail only updates a count on the section bar and a dot on the gear.
 * Only tapping a letter opens the reader.
 *
 * Titles and bodies come from a server and are shown as plain text, with
 * setText(String) only: no HTML, no links.
 *
 * It also keeps the refresh times, since it is on screen exactly when they
 * matter: shortly after the window appears, whenever the section comes into
 * view (once a minute at most), and every six hours while the window stays.
 */
final class MailboxView extends LinearLayout {
    interface Unread { void changed(int count); }

    private static final long OPENED_MS=60_000L,STAY_MS=6*60*60_000L,START_MS=1500L;
    private static final int WARNING=0xffd97977;
    private final Activity owner;
    private final LinearLayout list;
    private final TextView remaining,offline,empty;
    private final Theme.ChalkButton markAll;
    private final SimpleDateFormat date=new SimpleDateFormat("MM-dd HH:mm",Locale.US);
    private Unread unreadChanged;
    /** True once 一键已读 was used: only then is the must-open line worth showing. */
    private boolean marked;
    private final Runnable render=this::render;
    private final Runnable periodic=new Runnable(){
        @Override public void run(){
            removeCallbacks(this);
            if(getWindowVisibility()!=VISIBLE)return;
            MailboxSync.refresh(getContext(),STAY_MS);
            postDelayed(this,Math.max(OPENED_MS,STAY_MS-MailboxSync.age()));
        }
    };

    MailboxView(Activity context){
        super(context);
        owner=context;
        setOrientation(VERTICAL);
        markAll=new Theme.ChalkButton(context,"一键已读");
        addView(markAll,new LayoutParams(-1,-2));
        markAll.setOnClickListener(v->{marked=true;MailboxSync.markAll(getContext());render();});
        remaining=note("");
        offline=note("暂时连不上服务器，显示的是上次的内容");
        empty=note("暂无邮件");
        list=new LinearLayout(context);list.setOrientation(VERTICAL);
        addView(list,new LayoutParams(-1,-2));
    }
    private TextView note(String text){
        TextView view=Theme.muted(getContext(),text);
        view.setPadding(Theme.px(getContext(),4),Theme.px(getContext(),6),Theme.px(getContext(),4),Theme.px(getContext(),6));
        addView(view,new LayoutParams(-1,-2));
        return view;
    }

    /** Told the unread count now and whenever it changes; this is what draws the badges. */
    void setUnreadChanged(Unread listener){unreadChanged=listener;render();}

    @Override protected void onAttachedToWindow(){super.onAttachedToWindow();MailboxSync.observe(render);render();}
    @Override protected void onDetachedFromWindow(){MailboxSync.unobserve(render);removeCallbacks(periodic);super.onDetachedFromWindow();}
    @Override protected void onWindowVisibilityChanged(int visibility){
        super.onWindowVisibilityChanged(visibility);
        removeCallbacks(periodic);
        if(visibility==VISIBLE)postDelayed(periodic,START_MS);
    }
    @Override protected void onVisibilityChanged(View changedView,int visibility){
        super.onVisibilityChanged(changedView,visibility);
        if(visibility==VISIBLE&&isShown())MailboxSync.refresh(getContext(),OPENED_MS);
    }

    private void render(){
        Context context=getContext();
        Mailbox box=MailboxSync.box(context);
        List<Mailbox.Mail> mails=box.list();
        int unread=0,mustOpen=0;
        list.removeAllViews();
        for(Mailbox.Mail mail:mails){
            if(!mail.read){unread++;if(mail.mustOpen)mustOpen++;}
            if(list.getChildCount()>0)list.addView(new Theme.Rule(context),new LayoutParams(-1,Theme.px(context,1)));
            list.addView(row(mail),new LayoutParams(-1,-2));
        }
        markAll.setEnabled(unread>0);
        remaining.setText("还有 "+mustOpen+" 封需要打开阅读");
        remaining.setVisibility(marked&&mustOpen>0?VISIBLE:GONE);
        offline.setVisibility(box.failed()?VISIBLE:GONE);
        empty.setVisibility(mails.isEmpty()?VISIBLE:GONE);
        if(unreadChanged!=null)unreadChanged.changed(unread);
    }

    private View row(final Mailbox.Mail mail){
        Context context=getContext();
        LinearLayout row=new LinearLayout(context);
        row.setOrientation(VERTICAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setMinimumHeight(Theme.px(context,52));
        row.setPadding(Theme.px(context,4),Theme.px(context,8),Theme.px(context,4),Theme.px(context,8));
        LinearLayout top=new LinearLayout(context);
        top.setGravity(Gravity.CENTER_VERTICAL);
        if(!mail.read){
            View dot=new View(context);
            GradientDrawable circle=new GradientDrawable();circle.setShape(GradientDrawable.OVAL);circle.setColor(WARNING);
            dot.setBackground(circle);
            LayoutParams dotParams=new LayoutParams(Theme.px(context,8),Theme.px(context,8));
            dotParams.rightMargin=Theme.px(context,6);
            top.addView(dot,dotParams);
        }
        top.addView(tag(mail.warning?"警告":"公告",mail.warning?WARNING:Theme.ACCENT));
        if(mail.mustOpen&&!mail.read)top.addView(tag("必读",WARNING));
        String stamp=mail.created>0?date.format(new Date(mail.created*1000L)):"";
        TextView when=Theme.muted(context,stamp);
        when.setGravity(Gravity.END);
        top.addView(when,new LayoutParams(0,-2,1));
        row.addView(top,new LayoutParams(-1,-2));
        TextView title=Theme.text(new TextView(context),16,mail.read?Theme.TEXT:Theme.TITLE);
        title.setText(mail.title);
        title.setMaxLines(2);title.setEllipsize(TextUtils.TruncateAt.END);
        LayoutParams titleParams=new LayoutParams(-1,-2);
        titleParams.topMargin=Theme.px(context,4);
        row.addView(title,titleParams);
        row.setContentDescription((mail.read?"":"未读，")+(mail.warning?"警告":"公告")+(mail.mustOpen?"，必读":"")+"，"+mail.title);
        row.setOnClickListener(v->{
            TouchFeedback.click(v);
            MailReaderDialog.open(owner,mail,stamp);
        });
        return row;
    }

    private TextView tag(String label,int color){
        Context context=getContext();
        TextView view=Theme.text(new TextView(context),12,color);
        view.setText(label);
        GradientDrawable outline=new GradientDrawable();
        outline.setCornerRadius(Theme.px(context,3));
        outline.setStroke(Math.max(1,Theme.px(context,1)),color);
        view.setBackground(outline);
        view.setPadding(Theme.px(context,5),Theme.px(context,1),Theme.px(context,5),Theme.px(context,1));
        LayoutParams params=new LayoutParams(-2,-2);
        params.rightMargin=Theme.px(context,6);
        view.setLayoutParams(params);
        return view;
    }
}

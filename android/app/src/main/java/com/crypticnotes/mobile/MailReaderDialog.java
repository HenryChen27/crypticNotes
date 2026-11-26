package com.crypticnotes.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.Dialog;
import android.app.DialogFragment;
import android.app.FragmentManager;
import android.os.Bundle;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public final class MailReaderDialog extends DialogFragment {
    private static final String TAG="mail-reader";

    static void open(Activity owner, Mailbox.Mail mail, String date){
        FragmentManager manager=owner.getFragmentManager();
        if(owner.isFinishing()||owner.isDestroyed()||manager.isStateSaved()||manager.findFragmentByTag(TAG)!=null)return;
        Bundle letter=new Bundle();
        letter.putLong("id",mail.id);
        letter.putString("title",mail.title);
        letter.putString("body",mail.body);
        letter.putString("meta",(mail.warning?"警告":"公告")+(mail.mustOpen?" · 必读":"")+(date.isEmpty()?"":" · "+date));
        MailReaderDialog reader=new MailReaderDialog();
        reader.setArguments(letter);
        manager.beginTransaction().add(reader,TAG).commitNow();
    }

    @Override public Dialog onCreateDialog(Bundle state){
        Activity owner=getActivity();
        Bundle letter=getArguments();
        ScrollView scroll=new ScrollView(owner);
        scroll.setId(R.id.mail_reader_scroll);
        scroll.setFocusableInTouchMode(true);
        LinearLayout content=new LinearLayout(owner);
        content.setOrientation(LinearLayout.VERTICAL);
        int padding=Theme.px(owner,20);
        content.setPadding(padding,padding,padding,Theme.px(owner,10));
        scroll.addView(content);

        TextView meta=Theme.text(new TextView(owner),15,Theme.MUTED);
        meta.setText(letter.getString("meta"));
        content.addView(meta);
        TextView title=Theme.text(new TextView(owner),24,Theme.TITLE);
        title.setPadding(0,Theme.px(owner,8),0,Theme.px(owner,12));
        title.setText(letter.getString("title"));
        content.addView(title);
        TextView body=Theme.text(new TextView(owner),20,Theme.TEXT);
        body.setLineSpacing(Theme.px(owner,4),1f);
        body.setTextIsSelectable(true);
        String message=letter.getString("body","");
        body.setText(message.isEmpty()?"（没有正文）":message);
        content.addView(body);

        AlertDialog dialog=new AlertDialog.Builder(owner).setView(scroll).setPositiveButton("关闭",null).create();
        dialog.getWindow().setTitle("阅读邮件");
        dialog.getWindow().setBackgroundDrawable(new Theme.MistDrawable(owner));
        return dialog;
    }

    @Override public void onStart(){
        super.onStart();
        AlertDialog dialog=(AlertDialog)getDialog();
        Theme.text(dialog.getButton(AlertDialog.BUTTON_POSITIVE),16,Theme.TITLE);
        MailboxSync.open(getActivity(),getArguments().getLong("id"));
    }
}

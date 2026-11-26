package com.crypticnotes.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import java.io.InputStream;
import java.util.Scanner;
import org.json.JSONArray;
import org.json.JSONObject;

final class ReleaseNews {
    static void show(Activity activity) {
        if(activity.isFinishing()||activity.isDestroyed())return;
        SharedPreferences prefs=activity.getSharedPreferences("mobile",0);
        try(InputStream stream=activity.getAssets().open("update-news.json"); Scanner reader=new Scanner(stream,"UTF-8")) {
            JSONObject news=new JSONObject(reader.useDelimiter("\\A").next());
            JSONObject delivery=ReviewDelivery.read(activity);
            JSONObject preview=delivery==null?null:delivery.optJSONObject("announcement");
            boolean isPreview=preview!=null&&!preview.optString("id").isEmpty()&&preview.optJSONArray("changes")!=null
                    &&preview.optJSONArray("changes").length()>0&&!preview.optString("id").equals(prefs.getString("seen_review_news",""));
            if(isPreview)news=preview;
            String edition=news.getString("id");
            String release=edition+":"+BuildConfig.VERSION_CODE;
            if(!isPreview&&release.equals(prefs.getString("seen_update_news","")))return;
            SpannableStringBuilder body=new SpannableStringBuilder();
            int number=1;
            if(!news.optString("important").isEmpty()){
                appendItem(body,number++,news.getString("important"));
                if(isPreview||!edition.equals(prefs.getString("seen_news_edition","")))
                    body.setSpan(new ForegroundColorSpan(0xffdc4949),0,body.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            }
            JSONArray changes=news.getJSONArray("changes");
            for(int index=0;index<changes.length();index++)appendItem(body,number++,changes.getString(index));
            if(!news.optString("android").isEmpty())appendItem(body,number,news.getString("android"));
            new AlertDialog.Builder(activity).setTitle(isPreview?"加页手记 · 测试公告":"加页手记 · 更新公告").setMessage(body).setPositiveButton("知道了",null).show();
            if(isPreview)prefs.edit().putString("seen_review_news",edition).apply();
            else prefs.edit().putString("seen_update_news",release).putString("seen_news_edition",edition).apply();
        } catch(Exception error){android.util.Log.w("CrypticNotes","Update notice unavailable",error);}
    }
    private static void appendItem(SpannableStringBuilder body,int number,String text){
        if(body.length()>0)body.append("\n\n");
        body.append(Integer.toString(number)).append(". ").append(text);
    }
}

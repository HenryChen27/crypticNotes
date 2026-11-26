package com.crypticnotes.mobile;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import org.json.*;

/** Public, token-free release discovery shared by application and map updates. */
final class Distribution {
    static final String PRIMARY="https://api.gitcode.com/api/v5/repos/weixin_51917701/crypticNotes/releases/latest";
    static final String FALLBACK="https://api.github.com/repos/HenryChen27/crypticNotes/releases/latest";
    static boolean official(String url) {
        if(url==null || !(url.startsWith("https://gitcode.com/weixin_51917701/crypticNotes/releases/download/") || url.startsWith("https://github.com/HenryChen27/crypticNotes/releases/download/")))return false;
        try {
            String path=new URI(url).getPath().replace('\\','/');
            for(String part:path.split("/"))if(part.equals(".")||part.equals(".."))return false;
            return true;
        }catch(Exception e){return false;}
    }
    static JSONObject json(String url,int limit)throws Exception {
        if(!url.startsWith("https://"))throw new IOException("更新地址必须为 HTTPS");
        HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();
        c.setConnectTimeout(15000);c.setReadTimeout(20000);
        c.setRequestProperty("User-Agent","CrypticNotes-Android");c.setRequestProperty("Cache-Control","no-cache");
        try {
            if(c.getResponseCode()!=200)throw new IOException("服务器返回 "+c.getResponseCode());
            try(InputStream in=c.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()) {
                byte[] b=new byte[8192];int n;
                while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>limit)throw new IOException("更新信息过大");}
                return new JSONObject(new String(out.toByteArray(),StandardCharsets.UTF_8));
            }
        }finally{c.disconnect();}
    }
    static JSONObject release(String... required)throws Exception {
        String first=null;
        for(String endpoint:new String[]{PRIMARY,FALLBACK})try{
            JSONObject release=json(endpoint,2000000);release.getJSONArray("assets");
            for(String name:required){JSONObject file=asset(release,name);if(file.optLong("size")<=0||!file.optString("digest").matches("sha256:[0-9a-fA-F]{64}"))throw new IOException("附件缺少校验信息："+name);}
            return release;
        }catch(Exception error){if(first==null)first=error.getMessage();else throw new IOException("正式下载源未就绪："+first+(java.util.Objects.equals(first,error.getMessage())?"":"；"+error.getMessage()),error);}
        throw new IOException("无法连接更新服务器");
    }
    static JSONObject asset(JSONObject release,String name)throws Exception {
        JSONArray assets=release.getJSONArray("assets");JSONObject found=null;
        for(int i=0;i<assets.length();i++) {
            JSONObject a=assets.getJSONObject(i);
            if(name.equals(a.optString("name"))){if(found!=null)throw new IOException("发布附件重复");found=a;}
        }
        if(found==null)throw new IOException("尚未上架："+name);
        if(!official(found.optString("browser_download_url")))throw new IOException("附件地址不属于官方发布源："+name);
        return found;
    }
    private static void remap(JSONObject spec,JSONObject release)throws Exception {
        JSONObject a=asset(release,spec.getString("asset"));
        if(a.getLong("size")!=spec.getLong("size")||!a.optString("digest").equalsIgnoreCase("sha256:"+spec.getString("sha256")))throw new IOException("地图库发布文件正在更新，请稍后重试");
        spec.put("url",a.getString("browser_download_url"));
    }
    static JSONObject mapCatalog()throws Exception {
        JSONObject r=release(),catalog=json(asset(r,"matching-module.json").getString("browser_download_url"),32768);
        remap(catalog,r);JSONObject providers=catalog.optJSONObject("providers");
        if(providers!=null){java.util.Iterator<String> keys=providers.keys();while(keys.hasNext())remap(providers.getJSONObject(keys.next()),r);}
        return catalog;
    }
}

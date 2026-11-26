package com.crypticnotes.mobile;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The mailbox rules: what the server said, what this installation has read,
 * and which read receipts the server has not been told yet. Plain Java, no
 * Android in it (not even org.json), so the rules run on a desktop JVM
 * (android/tests/MailboxTest.java). Files, the network and threads are
 * MailboxSync's; the views are MailboxView's.
 *
 *   POST {server}/mail        {"version":1,"client":id,"time":1763500000}
 *        -> {"mail":[{"id":12,"kind":"notice"|"warning","title":"..","body":"..","must_open":false,
 *                     "personal":false,"created":1763400000,"read":false}, ...],"unread":3}   newest first
 *   POST {server}/mail/read   {"version":1,"client":id,"time":..,"ids":[12,13],"opened":true|false}
 *        -> any 2xx
 *
 * A mail is read when the server says so OR it was read here: an unsigned
 * request (an installation that never used PVP has no key, and none is made
 * for mail) always comes back "read": false, so what was read is remembered
 * locally as well. "opened": true is a mail the player actually opened;
 * false is 一键已读, which never covers a must-open mail - not here, not on
 * the server. A receipt that did not get through stays and goes out before
 * the next fetch.
 */
final class Mailbox {
    static final class Mail {
        final long id,created;
        final boolean warning,mustOpen,personal;
        final String title,body;
        /** Server or local, whichever says so. */
        final boolean read;
        Mail(long id,boolean warning,String title,String body,boolean mustOpen,boolean personal,long created,boolean read){
            this.id=id;this.warning=warning;this.title=title;this.body=body;this.mustOpen=mustOpen;this.personal=personal;this.created=created;this.read=read;
        }
        Mail read(boolean value){return value==read?this:new Mail(id,warning,title,body,mustOpen,personal,created,value);}
    }
    /** The way to the server. Worker threads only. */
    interface Transport {
        /** The answer to a 2xx; Rejected for a 400 (asking again will not help); any other exception otherwise. */
        String post(String path,String body) throws Exception;
        /** Whether requests carry this installation's key. Without it /mail/read does nothing on the server. */
        boolean signed();
    }
    static final class Rejected extends Exception {
        Rejected(String message){super(message);}
    }

    private static final int VERSION=1,MAIL_LIMIT=20,RECEIPT_BATCH=50,WAITING_LIMIT=200,TITLE_LIMIT=200,BODY_LIMIT=20000;

    private List<Mail> mail=new ArrayList<>();
    private long evictedTime,evictedId;
    /** Ids read here, of mail still in the list. */
    private final Set<Long> read=new LinkedHashSet<>();
    /** Receipts the server has not taken yet: opened one by one, and marked by 一键已读. */
    private final Set<Long> opened=new LinkedHashSet<>(),marked=new LinkedHashSet<>();
    private boolean failed;

    /** Newest first across both sources. */
    synchronized List<Mail> list(){return new ArrayList<>(mail);}
    synchronized boolean hasEvictions(){return evictedId!=0;}
    /** True when the last refresh did not bring a usable answer: the list is the previous one. */
    synchronized boolean failed(){return failed;}
    synchronized int unread(){int count=0;for(Mail m:mail)if(!m.read)count++;return count;}
    synchronized int mustOpenUnread(){int count=0;for(Mail m:mail)if(!m.read&&m.mustOpen)count++;return count;}
    synchronized int waiting(){return opened.size()+marked.size();}

    /** The player opened this mail. True when that changed anything. */
    synchronized boolean open(long id){
        for(int i=0;i<mail.size();i++){
            Mail m=mail.get(i);
            if(m.id!=id)continue;
            if(m.read)return false;
            mail.set(i,m.read(true));read.add(id);
            if(id>0){marked.remove(id);opened.add(id);trim(opened);}
            return true;
        }
        return false;
    }

    /** 一键已读: everything but must-open mail. Returns how many must-open mails are still unread. */
    synchronized int markAll(){
        int left=0;
        for(int i=0;i<mail.size();i++){
            Mail m=mail.get(i);
            if(m.read)continue;
            if(m.mustOpen){left++;continue;}
            mail.set(i,m.read(true));read.add(m.id);if(m.id>0)marked.add(m.id);
        }
        trim(marked);
        return left;
    }
    private static void trim(Set<Long> waiting){
        for(java.util.Iterator<Long> oldest=waiting.iterator();waiting.size()>WAITING_LIMIT;){oldest.next();oldest.remove();}
    }

    /** Receipts first, so the list that follows already knows them; then the list. True when a usable list came. */
    boolean refresh(Transport transport,String client,long time){
        deliver(transport,client,time);
        boolean ok=false;
        try{ok=accept(transport.post("/mail",fetchBody(client,time)));}catch(Exception ignored){}
        synchronized(this){failed=!ok;}
        return ok;
    }

    /** Sends the receipts that are waiting. Quiet about failure: what did not go stays for next time. */
    void deliver(Transport transport,String client,long time){
        // Unsigned, the server would take the receipt and remember nothing; keep it for when there is a key.
        if(!transport.signed())return;
        if(send(transport,client,time,opened,true))send(transport,client,time,marked,false);
    }
    private boolean send(Transport transport,String client,long time,Set<Long> waiting,boolean wasOpened){
        List<Long> ids;
        synchronized(this){ids=new ArrayList<>(waiting);}
        for(int from=0;from<ids.size();from+=RECEIPT_BATCH){
            List<Long> part=ids.subList(from,Math.min(ids.size(),from+RECEIPT_BATCH));
            try{transport.post("/mail/read",readBody(client,time,part,wasOpened));}
            catch(Rejected refused){/* the server will never take these; do not keep asking */}
            catch(Exception error){return false;}
            synchronized(this){waiting.removeAll(part);}
        }
        return true;
    }

    static String fetchBody(String client,long time){
        Map<String,Object> body=new LinkedHashMap<>();
        body.put("version",VERSION);body.put("client",client);body.put("time",time);
        return Json.write(body);
    }
    static String readBody(String client,long time,List<Long> ids,boolean wasOpened){
        Map<String,Object> body=new LinkedHashMap<>();
        body.put("version",VERSION);body.put("client",client);body.put("time",time);
        body.put("ids",new ArrayList<Object>(ids));body.put("opened",wasOpened);
        return Json.write(body);
    }

    synchronized void applyReview(String delivery){
        List<Mail> local=parseMail(delivery);
        if(local==null)return;
        List<Mail> combined=new ArrayList<>();
        for(Mail item:mail)if(item.id>0)combined.add(item);
        for(Mail item:local){
            if(item.id>=Integer.MAX_VALUE)continue;
            long number=-item.id-1;
            combined.add(new Mail(number,item.warning,item.title,item.body,item.mustOpen,item.personal,item.created,item.read));
        }
        retain(combined);
    }

    /**
     * Takes the server's answer to /mail. An answer that is not the expected
     * shape changes nothing and returns false; a single mail that is not
     * (no id, no title) is left out and the rest are kept.
     */
    private static List<Mail> parseMail(String answer){
        try{
            Object root=Json.parse(answer);
            if(root instanceof Map&&((Map<?,?>)root).get("mail") instanceof List)return mails((List<?>)((Map<?,?>)root).get("mail"));
        }catch(RuntimeException ignored){}
        return null;
    }
    boolean accept(String answer){
        List<Mail> fresh=parseMail(answer);
        if(fresh==null)return false;
        synchronized(this){
            for(Mail item:fresh)if(item.read){opened.remove(item.id);marked.remove(item.id);}
            for(Mail item:mail)if(item.id<0)fresh.add(item);
            retain(fresh);
            Set<Long> present=new LinkedHashSet<>();
            for(Mail item:mail)present.add(item.id);
            read.retainAll(present);
        }
        return true;
    }
    private static int order(long firstTime,long firstId,long secondTime,long secondId){
        int result=Long.compare(firstTime,secondTime);
        if(result!=0)return result;
        result=Long.compare(firstId>0?firstId:-firstId-1,secondId>0?secondId:-secondId-1);
        return result!=0?result:Long.compare(firstId,secondId);
    }
    private void retain(List<Mail> candidates){
        if(hasEvictions())candidates.removeIf(item->order(item.created,item.id,evictedTime,evictedId)<=0);
        candidates.sort((first,second)->order(second.created,second.id,first.created,first.id));
        if(candidates.size()>MAIL_LIMIT){
            Mail newestRemoved=candidates.get(MAIL_LIMIT);
            evictedTime=newestRemoved.created;evictedId=newestRemoved.id;
            candidates.subList(MAIL_LIMIT,candidates.size()).clear();
        }
        for(int index=0;index<candidates.size();index++){
            Mail item=candidates.get(index);
            if(item.read)read.add(item.id);
            else if(read.contains(item.id))candidates.set(index,item.read(true));
        }
        mail=candidates;
    }
    private static List<Mail> mails(List<?> items){
        List<Mail> out=new ArrayList<>();Set<Long> seen=new LinkedHashSet<>();
        for(Object item:items){
            if(!(item instanceof Map))continue;
            Map<?,?> fields=(Map<?,?>)item;
            long id=whole(fields.get("id"));
            Object title=fields.get("title"),body=fields.get("body");
            if(id<=0||!(title instanceof String)||((String)title).trim().isEmpty()||!seen.add(id))continue;
            out.add(new Mail(id,"warning".equals(fields.get("kind")),cut((String)title,TITLE_LIMIT),cut(body instanceof String?(String)body:"",BODY_LIMIT),
                    Boolean.TRUE.equals(fields.get("must_open")),Boolean.TRUE.equals(fields.get("personal")),Math.max(0,whole(fields.get("created"))),Boolean.TRUE.equals(fields.get("read"))));
        }
        return out;
    }
    private static String cut(String text,int limit){return text.length()<=limit?text:text.substring(0,limit);}
    /** A JSON number that is a whole number, or -1. */
    private static long whole(Object value){
        if(!(value instanceof Double))return -1;
        double number=(Double)value;
        return number==Math.rint(number)&&Math.abs(number)<9e15?(long)number:-1;
    }
    private static void ids(Object from,Set<Long> into,boolean includeLocal){
        if(!(from instanceof List))return;
        for(Object value:(List<?>)from){long id=whole(value);if(id>0||(includeLocal&&id< -1))into.add(id);}
    }

    /** Everything worth keeping between runs, as one JSON text. */
    synchronized String save(){
        List<Object> items=new ArrayList<>();
        for(Mail m:mail){
            if(m.id<0)continue;
            Map<String,Object> fields=new LinkedHashMap<>();
            fields.put("id",m.id);fields.put("kind",m.warning?"warning":"notice");fields.put("title",m.title);fields.put("body",m.body);
            fields.put("must_open",m.mustOpen);fields.put("personal",m.personal);fields.put("created",m.created);fields.put("read",m.read);
            items.add(fields);
        }
        Map<String,Object> root=new LinkedHashMap<>();
        if(hasEvictions())root.put("evicted_through",java.util.Arrays.asList(evictedTime,evictedId));
        root.put("mail",items);root.put("read",new ArrayList<Object>(read));
        root.put("opened",new ArrayList<Object>(opened));root.put("marked",new ArrayList<Object>(marked));
        return Json.write(root);
    }
    /** The mailbox as save() left it; an empty one when there is nothing, or nothing readable. */
    static Mailbox restore(String saved){
        Mailbox box=new Mailbox();
        if(saved==null)return box;
        try{
            Object root=Json.parse(saved);
            if(!(root instanceof Map))return box;
            Map<?,?> fields=(Map<?,?>)root;
            ids(fields.get("read"),box.read,true);ids(fields.get("opened"),box.opened,false);ids(fields.get("marked"),box.marked,false);
            Object cutoff=fields.get("evicted_through");
            if(cutoff instanceof List&&((List<?>)cutoff).size()==2){
                long time=whole(((List<?>)cutoff).get(0)),id=whole(((List<?>)cutoff).get(1));
                if(time>=0&&id!=0&&id!=-1){box.evictedTime=time;box.evictedId=id;}
            }
            if(fields.get("mail") instanceof List)box.retain(mails((List<?>)fields.get("mail")));
        }catch(RuntimeException error){return new Mailbox();}
        return box;
    }

    /**
     * Just enough JSON for the above: objects are Maps, arrays Lists, numbers
     * Doubles, plus String, Boolean and null. Anything malformed is an
     * IllegalArgumentException.
     */
    static final class Json {
        private final String text;private int at;
        private Json(String text){this.text=text;}

        static Object parse(String text){
            if(text==null)throw new IllegalArgumentException("no text");
            Json reader=new Json(text);
            Object value=reader.value(0);
            reader.blanks();
            if(reader.at!=text.length())throw reader.bad();
            return value;
        }
        private IllegalArgumentException bad(){return new IllegalArgumentException("bad JSON at "+at);}
        private void blanks(){while(at<text.length()&&" \t\r\n".indexOf(text.charAt(at))>=0)at++;}
        private char next(){if(at>=text.length())throw bad();return text.charAt(at++);}
        private boolean word(String word){if(!text.startsWith(word,at))return false;at+=word.length();return true;}
        private Object value(int depth){
            if(depth>32)throw bad();
            blanks();
            if(at>=text.length())throw bad();
            char c=text.charAt(at);
            if(c=='{'){
                at++;Map<String,Object> map=new LinkedHashMap<>();
                blanks();if(at<text.length()&&text.charAt(at)=='}'){at++;return map;}
                for(;;){
                    blanks();if(next()!='"')throw bad();
                    String key=string();
                    blanks();if(next()!=':')throw bad();
                    map.put(key,value(depth+1));
                    blanks();char end=next();
                    if(end=='}')return map;
                    if(end!=',')throw bad();
                }
            }
            if(c=='['){
                at++;List<Object> list=new ArrayList<>();
                blanks();if(at<text.length()&&text.charAt(at)==']'){at++;return list;}
                for(;;){
                    list.add(value(depth+1));
                    blanks();char end=next();
                    if(end==']')return list;
                    if(end!=',')throw bad();
                }
            }
            if(c=='"'){at++;return string();}
            if(word("true"))return Boolean.TRUE;
            if(word("false"))return Boolean.FALSE;
            if(word("null"))return null;
            int start=at;
            while(at<text.length()&&"+-.eE0123456789".indexOf(text.charAt(at))>=0)at++;
            if(at==start)throw bad();
            try{return Double.parseDouble(text.substring(start,at));}catch(NumberFormatException error){throw bad();}
        }
        /** After the opening quote. */
        private String string(){
            StringBuilder out=new StringBuilder();
            for(;;){
                char c=next();
                if(c=='"')return out.toString();
                if(c!='\\'){out.append(c);continue;}
                c=next();
                switch(c){
                    case 'n':out.append('\n');break;
                    case 't':out.append('\t');break;
                    case 'r':out.append('\r');break;
                    case 'b':out.append('\b');break;
                    case 'f':out.append('\f');break;
                    case 'u':
                        if(at+4>text.length())throw bad();
                        try{out.append((char)Integer.parseInt(text.substring(at,at+4),16));}catch(NumberFormatException error){throw bad();}
                        at+=4;break;
                    case '"':case '\\':case '/':out.append(c);break;
                    default:throw bad();
                }
            }
        }

        static String write(Object value){StringBuilder out=new StringBuilder();write(out,value);return out.toString();}
        private static void write(StringBuilder out,Object value){
            if(value instanceof Map){
                out.append('{');boolean first=true;
                for(Map.Entry<?,?> entry:((Map<?,?>)value).entrySet()){
                    if(!first)out.append(',');first=false;
                    write(out,String.valueOf(entry.getKey()));out.append(':');write(out,entry.getValue());
                }
                out.append('}');
            }else if(value instanceof List){
                out.append('[');boolean first=true;
                for(Object item:(List<?>)value){if(!first)out.append(',');first=false;write(out,item);}
                out.append(']');
            }else if(value instanceof String){
                String text=(String)value;
                out.append('"');
                for(int i=0;i<text.length();i++){
                    char c=text.charAt(i);
                    if(c=='"'||c=='\\')out.append('\\').append(c);
                    else if(c=='\n')out.append("\\n");
                    else if(c<0x20||c==0x2028||c==0x2029)out.append(String.format("\\u%04x",(int)c));
                    else out.append(c);
                }
                out.append('"');
            }else out.append(String.valueOf(value));   // Integer, Long, Boolean, null
        }
    }
}

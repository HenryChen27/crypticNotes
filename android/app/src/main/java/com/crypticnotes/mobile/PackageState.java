package com.crypticnotes.mobile;

enum PackageState {
    ABSENT("下载",true), UNCHECKED("检查更新",true), CHECKING("正在检查…",false),
    CURRENT("已是最新版",false), UPDATE("更新",true), FAILED("重新检查",true), WITHDRAWN("已下架",false);

    final String label;
    final boolean actionable;
    PackageState(String label,boolean actionable){this.label=label;this.actionable=actionable;}

    static PackageState resolve(boolean installed,boolean checking,boolean failed,String remote,String local){
        if(!installed)return ABSENT;
        if(checking)return CHECKING;
        if(failed)return FAILED;
        if(remote==null||remote.isEmpty())return UNCHECKED;
        if(!remote.matches("[0-9a-f]{64}"))return FAILED;
        return remote.equals(local)?CURRENT:UPDATE;
    }
}

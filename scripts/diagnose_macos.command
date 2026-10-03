#!/bin/bash
# 加页手记 macOS 诊断脚本 —— 双击运行，不需要懂终端。
#
# 它只读不写：不改权限、不动应用，只把当前状态汇总到桌面上的
# 「加页手记诊断.txt」并自动打开，整份复制回来即可。
#
# 为什么要看签名：macOS 把「屏幕录制 / 输入监控」的授权绑在应用签名的
# 指定要求(DR)上。ad-hoc 签名的 DR 钉的是 cdhash，每次重新构建都会变，
# 系统于是把每次更新都当成一个全新应用，授权自然每次都丢。

set -u

cd "$(dirname "$0")" || exit 1
APP_DIR="$(pwd)"
APP="$APP_DIR/加页手记.app"
BUNDLE_ID="com.henrychen.crypticnotes"
REPORT="$HOME/Desktop/加页手记诊断.txt"
TRACE="$HOME/Library/Application Support/IdentityVMapAssistant/failure-records/ui-events.jsonl"
USER_DB="$HOME/Library/Application Support/com.apple.TCC/TCC.db"
SYSTEM_DB="/Library/Application Support/com.apple.TCC/TCC.db"

: > "$REPORT"
log() { printf '%s\n' "$*" | tee -a "$REPORT"; }
section() { log ""; log "════════ $* ════════"; }
show() { log "\$ $*"; "$@" 2>&1 | tee -a "$REPORT"; }

log "加页手记 macOS 诊断报告"
log "生成时间: $(date '+%Y-%m-%d %H:%M:%S')"
log "应用路径: $APP"

section "0. 系统"
show sw_vers
show uname -m

if [ ! -d "$APP" ]; then
    log ""
    log "没找到『加页手记.app』。请把它和本脚本放在同一个文件夹里再运行。"
    log "（从 ZIP 解压出来的那个文件夹里，两者本来就是并排的。）"
    open -e "$REPORT" 2>/dev/null
    exit 1
fi

section "1. 指定要求 (DR) —— 系统就是靠这一行认身份"
log "要点：应该看到 certificate leaf[subject.CN] = \"...\"，"
log "      如果看到 cdhash，说明是旧版 ad-hoc 签名，授权必然每次更新都丢。"
show /usr/bin/codesign -d -r- --verbose=4 "$APP"

section "2. 签名概况"
show /usr/bin/codesign -dv --verbose=4 "$APP"

section "3. 签名完整性自检"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP" >>"$REPORT" 2>&1
log "codesign --verify 退出码: $?"
log "（0 = 签名完整；非 0 说明包被改动过或签名残缺）"

section "4. 隔离属性 (quarantine)"
if xattr -p com.apple.quarantine "$APP" >>"$REPORT" 2>&1; then
    log "↑ 有隔离属性：首次打开会弹『无法验证开发者』，这是自签名包的预期现象。"
else
    log "没有隔离属性（不会再弹『无法验证开发者』）。"
fi

section "5. Gatekeeper 评估"
/usr/bin/spctl -a -vvv -t exec "$APP" >>"$REPORT" 2>&1
log ""
log "↑ 这里显示 rejected 是【正常的】。自签名证书不是 Apple 开发者证书，"
log "  Gatekeeper 不认它是苹果认可的作者。它和屏幕录制/输入监控的授权"
log "  是两套东西：授权只看第 1 节的 DR。要让它变成 accepted，"
log "  只能买 99 美元/年的 Apple 开发者账号并做公证。"

section "6. 应用自己记录的权限状态"
log "（CGPreflightScreenCaptureAccess 是按进程的，本脚本问出来的是脚本自己的权限，"
log "  没有意义；所以这里读应用自己写下的日志。）"
if [ -f "$TRACE" ]; then
    if grep -q mac_capture_permission "$TRACE" 2>/dev/null; then
        log "最近几次截图权限检查:"
        grep mac_capture_permission "$TRACE" | tail -5 | tee -a "$REPORT"
        log ""
        log "granted=true 表示当时有权限；granted=false 表示被拒。"
    else
        log "日志里还没有 mac_capture_permission 记录 —— 说明应用启动后还没试过截图。"
    fi
else
    log "还没有日志文件（$TRACE）。应用至少要成功启动过一次并尝试截图。"
fi

section "7. 系统权限数据库里的记录"
if ! command -v sqlite3 >/dev/null 2>&1; then
    log "系统里没有 sqlite3，跳过这一节。"
else
    for pair in "输入监控:$USER_DB:kTCCServiceListenEvent" \
                "屏幕录制:$SYSTEM_DB:kTCCServiceScreenCapture"; do
        label="${pair%%:*}"; rest="${pair#*:}"
        db="${rest%%:*}"; service="${rest##*:}"
        log ""
        log "── $label ($service) ──"
        rows=$(sqlite3 "$db" \
            "select service, client, auth_value, auth_reason from access where client like '%crypticnotes%';" 2>/dev/null)
        if [ -z "$rows" ]; then
            log "读不到，或者确实还没有这一条。"
            log "读不到是正常的：需要给『终端』完全磁盘访问权限，或者用管理员运行。"
            log "库里没有记录则说明系统从没为这个应用记下过这项授权。"
        else
            log "service | client | auth_value(0=拒绝 2=允许) | auth_reason"
            log "$rows"
        fi
    done
fi

section "8. 旧授权和新版本对不对得上"
if ! command -v sqlite3 >/dev/null 2>&1 || ! command -v csreq >/dev/null 2>&1; then
    log "缺少 sqlite3 或 csreq，跳过。"
else
    hex=$(sqlite3 "$SYSTEM_DB" \
        "select hex(csreq) from access where client='$BUNDLE_ID' and service='kTCCServiceScreenCapture' limit 1;" 2>/dev/null)
    if [ -z "$hex" ]; then
        log "没有找到屏幕录制的历史授权记录。"
    else
        log "系统当初记下的要求是:"
        printf '%s' "$hex" | xxd -r -p | csreq -r- -t 2>/dev/null | tee -a "$REPORT"
        log ""
        log "如果上面出现 cdhash，它就是一条【对不上当前版本】的旧授权："
        log "开关可能还亮着，但任何新版本都匹配不上，所以授权看起来怎么点都没用。"
    fi
fi

section "9. 怎么办"
log "如果第 1 节看到的是 cdhash（旧版遗留），或者第 7 节里有个亮着却不生效的记录，"
log "按顺序做这三步："
log ""
log "  1) 先完全退出『加页手记』（菜单栏图标也要退干净）。"
log "  2) 打开「终端」，粘贴下面两行并回车："
log ""
log "       tccutil reset ScreenCapture $BUNDLE_ID"
log "       tccutil reset ListenEvent $BUNDLE_ID"
log ""
log "  3) 重新打开『加页手记』，到「系统设置 → 隐私与安全性」里"
log "     把「屏幕录制」和「输入监控」各允许一次，然后彻底退出再打开。"
log ""
log "这一次授权之后，以后的更新就不需要再授权了 —— 前提是第 1 节的 DR"
log "绑在证书上而不是 cdhash 上。"
log ""
log "如果第 1 节本来就是证书形态、第 7 节也显示允许，但截图仍然失败，"
log "把这份报告整份发回来。"
log ""
log "（可选）想跳过『无法验证开发者』那道提示，可以执行："
log "       xattr -dr com.apple.quarantine \"$APP\""

open -e "$REPORT" 2>/dev/null
log ""
log "报告已保存到: $REPORT"

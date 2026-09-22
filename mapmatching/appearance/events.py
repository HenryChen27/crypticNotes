def reaction(message):
    if any(word in message for word in ('冲突', '中断', '异常')):
        return 'angry'
    if any(word in message for word in ('失败', '无法', '冲突', '中断', '退出，请', '未匹配', '不足', '未确认', '未识别', '没有找到', '没有识别', '过于相似')):
        return 'puzzled'
    if any(word in message for word in ('隐藏', '关闭')):
        return 'sleep'
    if any(word in message for word in ('成功', '已录入', '已更新', '已重新对齐', '试用叠图', '专用路线', '楼', '层')):
        return 'heart'
    return 'curious'


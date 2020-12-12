#!/usr/bin/python
# -*- coding: utf-8 -*-


# DFA前向最大匹配算法
class dfa_match_t():
    def __init__(self, value_is_list=False):
        self.keyword_chains = {}
        self.delimit = '\x00'  # 结束
        self.value_is_list = value_is_list  # 是否使用list记录匹配的多值列表
        self.keyword_lower = False

    def dict_add(self, keyword, val='\x00', strip=True):
        if strip:
            keyword = keyword.strip()  # 关键词丢弃首尾空白
        if self.keyword_lower:
            keyword = keyword.lower()  # 关键词变小写

        if not keyword or val is None:
            return False

        key_len = len(keyword)
        # 得到当前词链的层级(入口)
        level = self.keyword_chains
        i = 0
        # 对关键词进行逐一遍历处理
        for i in range(key_len):
            char = keyword[i]
            if char in level:
                # 如果当前字符在当前层,则沿着该字符的分支进入下一层(获得dict的对应value)
                level = level[char]
                if i == key_len - 1:
                    if self.value_is_list:
                        # 记录值列表
                        if self.delimit in level:
                            level[self.delimit].append(val)
                        else:
                            level[self.delimit] = [val]
                    else:
                        # 如果全部层级都处理完毕,则最后要标记关键词结束,或者是用新值替代旧值
                        if self.delimit not in level or level[self.delimit] != val:
                            level[self.delimit] = val
            else:
                # 当前字符对应当前层级新分支
                if not isinstance(level, dict):
                    break
                # 假设当前层就是最后一层
                last_level = level
                for j in range(i, key_len):
                    # 对剩余的关键词字符进行循环
                    char = keyword[j]
                    # 记录最后一层
                    last_level = level
                    # 创建当前层当前字符的新分支
                    level[char] = {}
                    # 当前层级向下递进
                    level = level[char]
                # 最后字符对应着结束标记
                if self.value_is_list:
                    last_level[char] = {self.delimit: [val]}
                else:
                    last_level[char] = {self.delimit: val}
                break
        return True

    # 从文件装载关键词
    def dict_load(self, path, defval=''):
        with open(path, 'r', encoding='utf8') as f:
            for line in f:
                dat = line.strip().split('@', 1)
                if len(dat) == 1:
                    self.dict_add(dat[0], defval)
                else:
                    self.dict_add(dat[0], dat[1])

    def do_filter(self, message, repl="*", max_match=True, isall=False):
        """对给定的消息进行关键词匹配过滤,替换为字典中的对应值,或指定的字符"""
        msg_len = len(message)
        rs = self.do_match(message, msg_len, max_match=max_match, isall=isall)
        if len(rs) == 0:
            return message

        ms = self.do_complete(rs, message, msg_len)
        rst = []
        for m in ms:
            if m[2] is None:
                rst.append(message[m[0]:m[1]])
            else:
                if m[2] == self.delimit:
                    rst.append(repl * (m[1] - m[0]))
                else:
                    rst.append(m[2])
        return ''.join(rst)

    # 对给定的消息进行关键词匹配,得到结果链[(begin,end,val),(begin,end,val),...],val为None说明是原内容部分
    def do_match(self, message, msg_len=None, max_match=True, isall=True):
        """max_match:告知是否进行最长匹配
           isall:告知是否记录全部匹配结果(最长匹配时,也包含匹配的短串)
        """
        if self.keyword_lower:
            message = message.lower()  # 待处理消息串进行小写转换,消除干扰
        if msg_len is None:
            msg_len = len(message)

        rs = self.do_check(message, msg_len, 0, max_match, isall)
        if len(rs) == 0:
            return []
        if isall:
            return rs  # 记录全部匹配的结果
        else:
            return [rs[0]]  # 记录首个匹配的结果

    # 根据do_match匹配结果,补全未匹配的部分
    def do_complete(self, matchs, message, msg_len=None):
        def _find_max_seg(begin, matchs, matchs_len):
            """在matchs的begin开始处,查找其最长的匹配段索引"""
            if begin >= matchs_len:
                return begin

            bi = matchs[begin][0]
            ri = begin
            for i in range(begin + 1, matchs_len):
                if matchs[i][0] != bi:
                    break
                ri = i
            return ri

        if self.keyword_lower:
            message = message.lower()  # 待处理消息串进行小写转换,消除干扰
        if msg_len is None:
            msg_len = len(message)
        rst = []
        matchs_len = len(matchs)
        pos = _find_max_seg(0, matchs, matchs_len)
        while pos < matchs_len:
            rc = matchs[pos]
            if len(rst) == 0:
                if rc[0] != 0:
                    rst.append((0, rc[0], None))  # 记录首部未匹配的原始内容
                rst.append(rc)  # 记录当前匹配项
            elif rc[0] >= rst[-1][1]:
                if rc[0] != rst[-1][1]:
                    rst.append((rst[-1][1], rc[0], None))  # 记录前面未匹配的原始内容
                rst.append(rc)  # 记录当前匹配项
            pos = _find_max_seg(pos + 1, matchs, matchs_len)  # 查找后项

        if rst[-1][1] != msg_len:
            rst.append((rst[-1][1], msg_len, None))  # 补充最后剩余的部分
        return rst

    def do_check(self, message, msg_len=None, offset=0, max_match=True, isall=True):
        """对给定的消息进行关键词匹配测试,返回值:匹配结果,[三元组(begin,end,val)列表]"""
        rst = []

        def cb(b, e, v):
            rst.append((b, e, v))

        self.do_loop(cb, message, msg_len, offset, max_match, isall)
        return rst

    def do_loop(self, cb, message, msg_len=None, offset=0, max_match=True, isall=True):
        """对给定的消息进行关键词匹配循环,返回值:匹配结果,[三元组(begin,end,val)列表]"""
        if msg_len is None:
            msg_len = len(message)
        start = offset  # 记录当前正处理的字符位置
        rc = 0
        # 对消息进行逐一字符的过滤处理
        while start < msg_len:
            # 得到词链树的根
            level = self.keyword_chains
            step_ins = 0
            # 对当前剩余消息进行逐一过滤,进行本轮匹配
            for char in message[start:]:
                if char not in level:
                    break  # 没有匹配的字符,结束当前匹配循环
                step_ins += 1
                if self.delimit not in level[char]:
                    # 如果当前词链没有结束,则尝试向下深入,不记录结果
                    level = level[char]
                else:
                    if max_match and start + step_ins < msg_len:  # 要进行最大化匹配的尝试
                        nchar = message[start + step_ins]
                        if nchar in level[char] or start + step_ins + 1 == msg_len:
                            if isall:  # 记录匹配的全部中间结果
                                cb(start, start + step_ins, level[char][self.delimit])
                                rc += 1
                            level = level[char]
                            continue

                    # 如果当前词链标记结束了,说明从start开始到现在的消息内容,是一个完整匹配
                    cb(start, start + step_ins, level[char][self.delimit])
                    rc += 1
                    break
            # 跳过当前消息字符,开始下一轮匹配
            start += 1
        return rc

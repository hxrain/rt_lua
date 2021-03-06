import datetime
import html as hp
import http.cookiejar as cookiejar
import json
import hashlib
import logging
import logging.handlers
import os
import re
import time
import base64
import urllib.parse as up
import zipfile
from xml.dom import minidom
from hash_calc import *
from util_base import *

import requests
from lxml import etree
from lxml import html
from lxml.html.clean import Cleaner

# 调整requests模块的默认日志级别,避免无用调试信息的输出
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# 挑选出指定串中的unicode转义序列，并转换为标准串
def uniseq2str(s):
    m = re.findall(r'(\\u[0-9a-fA-F]{4})', s)
    ms = set(m)
    for i in ms:
        c = i.encode('latin-1').decode('unicode_escape')
        s = s.replace(i, c)
    return s


# 对指定的内容进行URLData编码转换
def URLData(content, type='text/html'):
    if isinstance(content, str):
        content = content.encode('utf-8')
    encoded_body = base64.b64encode(content)
    return "data:%s;base64,%s" % (type, encoded_body.decode())


# -----------------------------------------------------------------------------
# URL编码
def encodeURIComponent(url, encode='utf-8'):
    url = hp.unescape(url)
    url = up.quote_plus(url, safe='', encoding=encode)
    return url


# URI解码
def decodeURIComponent(url):
    url = up.unquote_plus(url)
    url = uniseq2str(url)
    return url


# 基于url_base补全url_path,得到新路径
def full_url(url_path, url_base):
    return up.urljoin(url_base, url_path)


# -----------------------------------------------------------------------------
def url_ext_match(url, exts):
    '判断url对应的文件是否与给定的扩展名匹配'
    ext = up.urlparse(url)
    if ext.path == '' or ext.path == '/':
        return False

    ext = os.path.splitext(ext.path)[1].strip().lower()
    if ext in exts:
        return True

    return False


# -----------------------------------------------------------------------------
# 判断两个url是否相同(包含了URI编码后的情况)
def url_equ(a, b):
    if a == b:
        return True

    if a.startswith('file:///'):
        a = a[8:].replace(':///', ':/')
        a = a.replace('://', ':/')
    if b.startswith('file:///'):
        b = b[8:].replace(':///', ':/')
        b = b.replace('://', ':/')

    if up.unquote(a) == b:
        return True

    if up.unquote(b) == a:
        return True

    return False


# -----------------------------------------------------------------------------
# 进行html代码修正格式化,得到可解析易读的类似xhtml文本串
def format_html(html_soup):
    try:
        root = etree.HTML(html_soup)
        return etree.tostring(root, encoding='unicode', pretty_print=True, method='html')
    except Exception as e:
        return html_soup


# -----------------------------------------------------------------------------
# 进行html代码修正格式化,得到可解析易读的类似xhtml文本串
def format_xhtml(html_soup):
    try:
        root = html.fromstring(html_soup)
        return html.tostring(root, encoding='unicode', pretty_print=True, method='xml')
    except Exception as e:
        return html_soup


# -----------------------------------------------------------------------------
# 清理html页面内容,移除style样式定义与script脚本段
def clean_html(html_str):
    try:
        cleaner = Cleaner(style=True, scripts=True, page_structure=False, safe_attrs_only=False)
        return cleaner.clean_html(html_str)
    except Exception as e:
        return html_str


# -----------------------------------------------------------------------------
def html_to_xhtml(html_str):
    """将html_str严格的转换为xhtml格式,带着完整的命名空间限定"""
    try:
        root = etree.HTML(html_str)
        html.html_to_xhtml(root)
        return html.tostring(root, encoding='utf-8', pretty_print=True, method='xml').decode('utf-8')
    except Exception as e:
        return html_str


# -----------------------------------------------------------------------------
# 进行xml代码修正格式化
def format_xml(html_soup, desc, chs='utf-8'):
    try:
        root = etree.fromstring(html_soup.encode(chs))
        return desc + '\n' + etree.tostring(root, encoding=chs, pretty_print=True, method='xml').decode(chs)
    except Exception as e:
        return html_soup


# 修正xml串xstr中的自闭合节点与空内容节点值为dst
def fix_xml_node(xstr, dst='-'):
    if xstr is None: return None
    ret = xstr.strip()  # 字符串两端净空
    ret = re.sub('<([^>/\s]+)(\s*[^>/]*)/>', '<\\1\\2>%s</\\1>' % dst, ret)  # 修正自闭合节点
    ret = re.sub('<([^/][^>]*?)></([^>]*?)>', '<\\1>%s</\\2>' % dst, ret)  # 替换空节点
    ret = re.sub(r'[\u001f\u000b\u001e]', '', ret)  # 替换无效字符干扰
    ret = ret.replace('&#13;', '\n')  # 修正结果串
    return ret


# 提取xml串中的节点文本,丢弃全部标签格式
def extract_xml_text(xstr):
    if xstr is None: return None
    ret = xstr.strip()  # 字符串两端净空
    ret = re.sub('<([^>/]*?)/>', '', ret)  # 丢弃自闭合节点
    ret = re.sub('<([^/][^>]*?)>', '', ret)  # 替换开始标签
    ret = re.sub('</([^>]*?)>', '', ret)  # 替换结束标签

    ret = ret.replace('&#13;', '\n')  # 修正结果串
    ret = ret.strip()
    return ret


# -----------------------------------------------------------------------------
# 对xstr进行xpath查询,查询表达式为cc_xpath
# 返回值为([文本或元素列表],'错误说明'),如果错误说明串不为空则代表发生了错误
# 元素可以进行etree高级访问
def query_xpath(xstr, cc_xpath, fixNode='-'):
    try:
        if fixNode is not None:
            xstr = fix_xml_node(xstr, fixNode)
        if xstr.startswith('<?xml'):
            HTMLRoot = etree.XML(xstr)
        else:
            HTMLRoot = etree.HTML(xstr)
        if HTMLRoot is None:
            return [], 'xpath xml/html load fail.'
        r = HTMLRoot.xpath(cc_xpath)
        return r, ''
    except etree.XPathEvalError as e:
        return [], es(e)
    except Exception as e:
        return [], es(e)


# 对cnt_str进行xpath查询,查询表达式为cc_xpath;可以删除removeTags元组列表指出的标签(保留元素内容)
# 返回值为([文本],'错误说明'),如果错误说明串不为空则代表发生了错误
def query_xpath_x(cnt_str, cc_xpath, removeTags=None,removeAtts=None):
    rs, msg = query_xpath(cnt_str, cc_xpath)
    if msg != '':
        return rs, msg

    for i in range(len(rs)):
        if isinstance(rs[i], etree._Element):
            if removeTags:
                etree.strip_tags(rs[i], removeTags)
            if removeAtts:
                etree.strip_attributes(rs[i], removeAtts)
            rs[i] = etree.tostring(rs[i], encoding='unicode', method='html')

    return rs, msg


# 使用xpath查询指定节点的内容并转为数字.不成功时返回默认值
def query_xpath_num(cnt_str, cc_xpath, defval=1):
    rs, msg = query_xpath(cnt_str, cc_xpath)
    if len(rs) != 0:
        return int(rs[0])
    return defval


# 使用xpath查询指定节点的内容串.不成功时返回默认值
def query_xpath_str(cnt_str, cc_xpath, defval=None):
    rs, msg = query_xpath(cnt_str, cc_xpath)
    if len(rs) != 0:
        return rs[0].strip()
    return defval


def xml_filter(xstr, xp_node, xp_field):
    """对xstr记录的xml进行xpath过滤检查,如果xp_node指出的节点中没有xp_field,则删除该节点"""
    xnodes = query_xpath_x(xstr, xp_node)[0]
    ret = xstr
    for n in xnodes:
        f = query_xpath_x('<?xml version="1.0" ?>\n' + n, xp_field)[0]
        if len(f) == 0:
            ret = ret.replace(n, '')
    return ret


# 可进行多次xpath查询的功能对象
class xpath:
    def __init__(self, cntstr, is_xml=False):
        cnt_str = fix_xml_node(cntstr)
        self.cnt_str = None
        self.last_err = []
        try:
            if cnt_str.startswith('<?xml') or is_xml:
                self.rootNode = etree.XML(cnt_str)
            else:
                self.rootNode = etree.HTML(cnt_str)
            self.cnt_str = cnt_str
        except Exception as e:
            self.last_err.append(es(e))

        if self.cnt_str is None:
            try:
                self.cnt_str = format_xhtml(cnt_str)
                if self.cnt_str:
                    self.rootNode = etree.HTML(self.cnt_str)
            except Exception as e:
                self.last_err.append(es(e))

        if self.cnt_str is None:
            try:
                self.cnt_str = html_to_xhtml(cnt_str)
                if self.cnt_str:
                    self.rootNode = etree.HTML(self.cnt_str)
            except Exception as e:
                self.last_err.append(es(e))
                self.cnt_str = None
                pass

        if self.cnt_str is None:
            self.cnt_str = "ERROR"

    # 进行xpath查询,查询表达式为cc_xpath
    # 返回值为([文本或元素列表],'错误说明'),如果错误说明串不为空则代表发生了错误
    # 元素可以访问text与attrib字典
    def query(self, cc_xpath):
        try:
            r = self.rootNode.xpath(cc_xpath)
            return r, ''
        except etree.XPathEvalError as e:
            return [], es(e)
        except Exception as e:
            return [], es(e)


# -----------------------------------------------------------------------------
# 将xml串str抽取重构为rules指定的格式条目{'条目名称':'xpath表达式'}
def xml_extract(str, rules, rootName='条目', removeTags=None):
    qr = {}
    try:
        xp = xpath(str)
        rows = 99999999999
        # 先根据给定的规则,查询得到各个分量的结果
        for tag, p in rules.items():
            qr[tag] = xp.query(p)[0]
            rows = min(rows, len(qr[tag]))  # 获取最少的结果数量

        for tag, p in rules.items():
            if len(qr[tag]) > rows:
                return None, 'xpath查询结果数量不等 <%s> :: %s' % (tag, p)

        if rows == 0:
            return 0, ''  # 没有匹配的结果

        # 创建输出xml文档与根节点
        document = minidom.Document()
        root = document.createElement(rootName)

        # 行循环,逐一输出各个节点中的条目列
        for i in range(rows):
            node = document.createElement('%d' % (i + 1))  # 序号节点
            for tag in rules:
                x = qr[tag][i]
                if isinstance(x, etree._Element):
                    if removeTags:
                        etree.strip_tags(x, removeTags)
                    x = etree.tostring(x, encoding='unicode', method='xml')

                n = document.createElement(tag)  # 条目节点
                n.appendChild(document.createTextNode(x))  # 条目内容
                node.appendChild(n)  # 条目节点挂载到序号节点
            root.appendChild(node)  # 序号节点挂载到根节点
        document.appendChild(root)  # 根节点挂载到文档对象

        return rows, document.toprettyxml(indent='\t')  # 输出最终结果
    except Exception as e:
        return None, es(e)


def pair_extract(xml, xpaths, removeTags=None):
    """根据xpaths列表,从xml中抽取结果,拼装为元组列表.
        返回值:[()],errmsg
    """
    qr = {}
    if len(xpaths) == 0:
        return [], ''
    try:
        xp = xpath(xml)
        rows = 99999999999
        # 先根据给定的规则,查询得到各个分量的结果
        for p in xpaths:
            qr[p] = xp.query(p)[0]
            siz = len(qr[p])
            rows = min(rows, siz)  # 获取最少的结果数量

        for p in xpaths:
            siz = len(qr[p])
            if siz > rows:
                return [], 'xpath查询结果数量不等 <%s> (%d > %d)' % (p, siz, rows)

        if rows == 0:
            msg = ''
            if len(xp.last_err):
                msg = '; '.join(xp.last_err)
            return [], msg  # 没有匹配的结果

        rst = []
        for i in range(rows):
            t = ()
            for p in xpaths:
                x = qr[p][i]
                if isinstance(x, etree._Element):
                    if removeTags:
                        etree.strip_tags(x, removeTags)
                    x = etree.tostring(x, encoding='unicode')
                    x = '<?xml version="1.0"?>\n' + x
                t = t + (x.strip(),)
            rst.append(t)
        return rst, ''

    except Exception as e:
        return [], es(e)


# 将xpath规则结果对列表转换为字典
def make_pairs_dict(lst, trsxml=False):
    dct = {}
    if trsxml:
        for d in lst:
            k = extract_xml_text(d[0])
            v = extract_xml_text(d[1])
            dct[k] = v
    else:
        for d in lst:
            dct[d[0]] = d[1]
    return dct


# 获取字典dct中的指定key对应的值,不存在时返回默认值
def get_dict_value(dct, key, defval=None):
    if key in dct:
        return dct[key]
    else:
        return defval


def get_slice(lst, seg, segs):
    """获取列表lst的指定分段的切片,seg为第几段(从1开始),segs为总段数"""
    tol = len(lst)  # 元素总量
    slen = (tol + segs // 2) // segs  # 每段元素数量
    e = seg * slen if seg != segs else tol  # 最后一段涵盖尾部
    return lst[(seg - 1) * slen: e]


def union_dict(dst, src):
    """合并src词典的内容到dst,跳过src的空值"""
    for k in src:
        v = src[k]
        if k not in dst:
            dst[k] = v
        else:
            if v == '' or v is None:
                continue
            dst[k] = v


# -----------------------------------------------------------------------------
# 对html/table信息列进行提取的功能封装
class table_xpath:
    def __init__(self, page, rule_key, rule_val, logger=None, trsxml=False):
        '''构造函数传入含有table的page内容串,以及table中的key列与val列的xpath表达式'''
        self.logger = logger
        self.trsxml = trsxml  # 是否转换xml为txt
        self.parse(page, rule_key, rule_val)

    def parse(self, page, rule_key, rule_val):
        """使用规则提取page中的对应内容"""
        self.dct = None
        self.page = page

        rst, msg = pair_extract(page, [rule_key, rule_val])
        if msg != '':
            if self.logger:
                self.logger.warn('page table xpath query error <%s>:\n%s', msg, page)
            return

        self.dct = make_pairs_dict(rst, self.trsxml)

    def __getitem__(self, item):
        '''使用['key']的方式访问对应的值'''
        return self.value(item)

    def value(self, item, defval=None):
        '''访问对应的值'''
        v = get_dict_value(self.dct, item, defval)
        if v is None:
            if self.logger:
                self.logger.warn('page table xpath dict error <%s>:\n%s', item, self.page)
            return None
        return extract_xml_text(v)

    def cloneTo(self, dct, filter=None):
        """将当前字典克隆合并到目标字典中,同时可进行键值过滤处理"""
        if self.dct is None:
            return

        for k in self.dct:
            if filter:
                k1, v1 = filter(k, self.dct[k])
            else:
                k1 = k
                v1 = self.dct[k]
            dct[k1] = v1


def is_base64_content(body):
    """判断给定的字符串或字节数组是否为有效的base64编码内容
        返回值:(True,decoded)或(False,body)
    """
    try:
        if isinstance(body, str):
            sb_bytes = bytes(body, 'ascii')
        elif isinstance(body, bytes):
            sb_bytes = body
        else:
            return False, body
        decoded = base64.decodebytes(sb_bytes)  # 得到解码后内容
        encoded = base64.encodebytes(decoded).replace(b'\n', b'')  # 对解码后内容再编码
        r = encoded == sb_bytes.replace(b'\n', b'')  # 对再编码的内容和原始内容进行比较,如果一样则说明原始内容是base64编码的
        return (True, decoded) if r else (False, body)
    except Exception:
        return False, body


# -----------------------------------------------------------------------------
def find_chs_by_head(heads):
    '根据http头中的内容类型,分析查找可能存在的字符集类型'
    if 'Content-Type' not in heads:
        return ''
    CT = heads['Content-Type'].lower()

    m = re.search('charset\s*?[=:]\s*?(.*)[; "]?', CT)
    if m is not None:
        return m.group(1)

    return ''


# -----------------------------------------------------------------------------
def find_chs_by_cnt(cnt):
    rp = '<meta[^<>]+charset\s*?=\s*?"?(.*?)[; ">]+'
    if type(cnt).__name__ == 'bytes':
        rp = rp.encode('utf-8')
    m = re.search(rp, cnt)
    if m:
        if type(cnt).__name__ == 'bytes':
            return m.group(1).decode('utf-8')
        else:
            return m.group(1)

    return ''


# -----------------------------------------------------------------------------
def find_cnt_type(cnt_type):
    '提取内容类型中的确定值'
    m = re.search(r'\s*([0-9a-zA-Z/*\-_.+]*)([; "]?)', cnt_type)
    if m:
        return m.group(1)
    return cnt_type


# -----------------------------------------------------------------------------
def is_br_content(heads):
    if 'content-encoding' in heads and heads['content-encoding'] in {'br'}:
        return True
    return False


# -----------------------------------------------------------------------------
def is_text_content(heads):
    if 'Content-Type' not in heads:
        return False

    CT = heads['Content-Type'].lower()
    if find_cnt_type(CT) in {'text/html', 'text/xml', 'text/plain', 'application/json',
                             'application/x-www-form-urlencoded'}:
        return True
    return False


# -----------------------------------------------------------------------------
# 生成HTTP默认头
def default_headers(url):
    ur = up.urlparse(url)
    host = ur[1]
    return requests.structures.CaseInsensitiveDict({
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:71.0) Gecko/20100101 Firefox/71.0',
        'Accept': 'text/html,application/xhtml+xml,application/json,application/xml;q=0.9,*/*;q=0.8',
        'Host': host,
        'Connection': 'keep-alive',
    })


# -----------------------------------------------------------------------------
def http_req(url, rst, req=None, timeout=15, allow_redirects=True, session=None, cookieMgr=None):
    '''根据给定的req内容进行http请求,得到rst回应.返回值告知是否有错误出现.
        req['METHOD']='get'     可告知http请求的方法类型,get/post/put/...
        req['PROXY']=''         可告知请求使用的代理服务器,如'http://ip:port'
        req['HEAD']={}          可告知http请求头域信息
        req['BODY']={}          可告知http请求的body信息,注意需要同时给出正确的Content-Type
        req['COOKIE']={}        可告知http请求的cookie信息

        rst['error']            记录过程中出现的错误
        rst['status_code']      告知回应状态码
        rst['status_reason']    告知回应状态简述
        rst['HEAD']             告知回应头
        rst['COOKIE']           记录回应的cookie内容
        rst['BODY']             记录回应内容,解压缩转码后的内容
    '''
    # 准备请求参数
    method = req['METHOD'] if req and 'METHOD' in req else 'get'
    SSL_VERIFY = req['SSL_VERIFY'] if req and 'SSL_VERIFY' in req else None
    proxy = req['PROXY'] if req and 'PROXY' in req else None
    HEAD = req['HEAD'] if req and 'HEAD' in req else None
    BODY = req['BODY'] if req and 'BODY' in req else None

    if proxy is not None:
        proxy = {'http': proxy, 'https': proxy}

    COOKIE = req['COOKIE'] if req and 'COOKIE' in req else None
    # 进行cookie管理与合并
    if cookieMgr is None:
        # 没有cookie管理器对象,直接使用给定的cookie字典
        CKM = COOKIE
    else:
        CKM = cookieMgr
        # 如果COOKIE字典存在且cookie管理器也存在,则进行值合并,后续会清理
        if COOKIE is not None:
            CKM.update(COOKIE)

    rst['error'] = ''

    # 执行请求
    try:
        if session is None:
            session = requests.sessions.Session()
        # 校正会话对象内部的http默认头
        session.headers = default_headers(url)

        rsp = session.request(method, url, proxies=proxy, headers=HEAD, data=BODY, cookies=CKM,
                              timeout=timeout, allow_redirects=allow_redirects, verify=SSL_VERIFY)
    except Exception as e:
        rst['error'] = es(e)
        rst['status_code'] = 999
        return False
    finally:
        # 清理掉临时附着的cookie
        if COOKIE is not None and cookieMgr is not None:
            for n in COOKIE:
                cookieMgr.clear('', '/', n)

    # 拼装回应状态
    rst['status_code'] = rsp.status_code
    rst['status_reason'] = rsp.reason

    # 拼装回应头信息
    r = rst['HEAD'] = {}
    for k in rsp.headers:
        r[k] = rsp.headers[k]

    if cookieMgr is not None:
        # 将本次会话得到的cookie进行持久化保存
        cookieMgr.update(session.cookies)

    # 拼装本次得到的cookie信息
    r = rst['COOKIE'] = {}
    for k in session.cookies:
        r[k.name] = k.value

    # 判断是否需要进行额外的br解压缩处理
    rsp_cnt = ''
    if is_br_content(rsp.headers):
        import brotli
        rsp_cnt = brotli.decompress(rsp.content)
    else:
        rsp_cnt = rsp.content

    # 判断是否需要进行字符集解码处理
    chs = find_chs_by_cnt(rsp_cnt)
    if chs == '' and is_text_content(rsp.headers):
        chs = find_chs_by_head(rsp.headers)
        if chs == '':
            chs = 'utf-8'

    # 记录最终的结果
    if chs != '':
        rst['BODY'] = rsp_cnt.decode(chs, errors='ignore')
    else:
        rst['BODY'] = rsp_cnt

    return True


# 快速抓取目标url的get请求函数
def http_get(url, req=None, timeout=15, allow_redirects=True, session=None, cookieMgr=None):
    rst = {}
    http_req(url, rst, req, timeout, allow_redirects, session, cookieMgr)
    return rst['BODY'], rst['status_code'], rst['error']


def make_head(req_dict, head_str):
    ''' 将如下的http头域字符串转换为key/value字典,并放入请求头域
    User-Agent: Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0
    Accept: application/json, text/javascript, */*; q=0.01
    Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2
    Accept-Encoding: gzip, deflate
    Content-Type: application/x-www-form-urlencoded; charset=UTF-8
    X-Requested-With: XMLHttpRequest
    Origin: http://credit.fgw.panjin.gov.cn
    Connection: keep-alive
    Referer: http://credit.fgw.panjin.gov.cn/doublePublicity/doublePublicityPage?type=4&columnCode=top_xygs
    '''
    lines = head_str.split('\n')
    if 'HEAD' not in req_dict:
        req_dict['HEAD'] = {}

    for line in lines:
        line = line.strip()
        if line is '': continue
        kv = line.split(':', 1)
        req_dict['HEAD'][kv[0].strip()] = kv[1].strip()


def make_post(req_dict, body=None, content_type='application/x-www-form-urlencoded'):
    """构造请求参数字典,设定为post请求"""
    req_dict['METHOD'] = 'post'
    if body:
        if 'HEAD' not in req_dict:
            req_dict['HEAD'] = {}
        req_dict['HEAD']['Content-Type'] = content_type
        req_dict['BODY'] = body


# -----------------------------------------------------------------------------
def load_cookie_storage(filename):
    '从文件中装载cookie内容,返回RequestsCookieJar对象'
    CJ = cookiejar.LWPCookieJar(filename)
    try:
        CJ.load()
    except FileNotFoundError as e:
        pass
    except Exception as e:
        return -1

    CM = requests.cookies.RequestsCookieJar()
    CM.update(CJ)
    return CM


# -----------------------------------------------------------------------------
def save_cookie_storage(CM, filename):
    '''保存CookieManager对象到filename文件'''
    CJ = cookiejar.LWPCookieJar(filename)
    requests.cookies.merge_cookies(CJ, CM)
    CJ.save()


# -----------------------------------------------------------------------------
class spd_base:
    '''进行简单功能封装的cookie持久化长连接HTTP爬虫'''

    def __init__(self, filename='./cookie_storage.dat'):
        # 初始记录cookie存盘文件名
        self.ckm_filename = filename
        # 装载可能已经存在的cookie值
        self.cookieMgr = load_cookie_storage(filename)
        # 设置默认超时时间
        self.timeout = 15
        # 默认允许自动进行302跳转
        self.allow_redirects = True
        # 生成长连接会话对象
        self.session = requests.sessions.Session()
        # 定义结果对象
        self.rst = {}

    def _rst_val(self, key, defval):
        return self.rst[key] if key in self.rst else defval

    # 抓取指定的url,通过req可以传递灵活的控制参数
    def take(self, url, req=None, proxy_files='./proxy_host.json'):

        def match_proxy(url):  # 匹配域名对应的代理服务器
            if isinstance(proxy_files, str):
                proxy_table = dict_load(proxy_files, 'utf-8')
            else:
                proxy_table = proxy_files

            if proxy_table is None:
                return None

            for m in proxy_table:
                if url.find(m) != -1:
                    return proxy_table[m]
            return None

        if req is None or 'PROXY' not in req:
            prx = match_proxy(url)  # 尝试使用配置文件进行代理服务器的修正
            if prx:
                if not req:
                    req = {}
                req['PROXY'] = prx

        self.rst = {}
        return http_req(url, self.rst, req, self.timeout, self.allow_redirects, self.session, self.cookieMgr)

    # 保存cookie到文件
    def cookies_save(self):
        save_cookie_storage(self.cookieMgr, self.ckm_filename)

    # 获取过程中出现的错误
    def get_error(self):
        return self._rst_val('error', '')

    # 获取回应状态码
    def get_status_code(self):
        return self._rst_val('status_code', 0)

    # 获取回应状态简述
    def get_status_reason(self):
        return self._rst_val('status_reason', '')

    # 获取回应头,字典
    def get_HEAD(self):
        return self._rst_val('HEAD', {})

    # 获取会话回应cookie字典
    def get_COOKIE(self):
        return self._rst_val('COOKIE', {})

    # 获取回应内容,解压缩转码后的内容
    def get_BODY(self):
        return self._rst_val('BODY', None)


"""
#多项列表排列组合应用样例,先访问,再调整
ic = items_comb()
ic.append(['A', 'B', 'C'])
ic.append(['x', 'y', 'z'])
ic.append(['1', '2', '3'])
print(ic.total())

for i in range(ic.total()):
    print(ic.item(), ic.next())

while True:
    print(ic.item())
    if ic.next():
        break
"""


class items_comb():
    """多列表项排列组合管理器"""

    def __init__(self):
        self.lists = []
        self.lists_pos = []

    def append(self, items):
        """追加一个列表项"""
        self.lists.append(items)
        self.lists_pos.append(0)

    def total(self):
        """计算现有列表项排列组合总数"""
        lists_size = len(self.lists)
        if lists_size == 0:
            return 0
        ret = 1
        for l in range(lists_size):
            ret *= len(self.lists[l])
        return ret

    def plan(self, lvl=0):
        """查询指定层级的当前进度,返回值:(位置1~n,总量n)"""
        if len(self.lists) == 0:
            return None, None
        return self.lists_pos[lvl] + 1, len(self.lists[lvl])

    def next(self):
        """调整当前组合序列索引,便于调用item时得到下一种组合结果.返回值:是否已经归零"""
        levels = len(self.lists)
        for l in range(levels - 1, -1, -1):  # 从后向前遍历
            idx = self.lists_pos[l]  # 取出当前级链表元素索引
            if idx < len(self.lists[l]) - 1:
                self.lists_pos[l] += 1  # 索引没有超出链表范围,则增加后结束
                return False
            self.lists_pos[l] = 0  # 索引超出链表范围时,归零,准备处理上一级链表元素索引
        return True  # 全部级别都处理完毕,这是一轮遍历结束了.

    def item(self):
        """获取当前组合"""
        rst = []
        for i in range(len(self.lists_pos)):
            rst.append(self.lists[i][self.lists_pos[i]])
        return rst

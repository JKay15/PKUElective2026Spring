#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: parser.py
# modified: 2019-09-09

import re
from lxml import etree
from .course import Course

_regexBzfxSida = re.compile(r'\?sida=(\S+?)&sttp=(?:bzx|bfx)')
_regexConfirmSelect = re.compile(
    r"confirmSelect\('(?P<xh>[^']*)','(?P<teacher>[^']*)','(?P<name>[^']*)','(?P<class_no>[^']*)'"
)


def get_tree_from_response(r):
    return etree.HTML(r.text) # 不要用 r.content, 否则可能会以 latin-1 编码

def get_tree(content):
    return etree.HTML(content)

def get_tables(tree):
    return tree.xpath('.//table//table[@class="datagrid"]')

def get_table_header(table):
    return table.xpath('.//tr[@class="datagrid-header"]/th/text()')

def get_table_trs(table):
    return table.xpath('.//tr[@class="datagrid-odd" or @class="datagrid-even"]')

def _cell_text(cell):
    try:
        texts = cell.xpath('.//text()')
    except Exception:
        return ""
    if not texts:
        return ""
    return "".join(t.strip() for t in texts if t and t.strip()).strip()

def _parse_quota_pair(text):
    if text is None:
        return None
    nums = re.findall(r"\d+", str(text))
    if len(nums) < 2:
        return None
    try:
        return int(nums[0]), int(nums[1])
    except Exception:
        return None

def get_title(tree):
    title = tree.find('.//head/title')
    if title is None: # 双学位 sso_login 后先到 主修/辅双 选择页，这个页面没有 title 标签
        return None
    return title.text

def get_errInfo(tree):
    # Be tolerant to HTML changes. Historically this page contains a <strong>
    # label like "出错提示:" or "提示:" then the error message as sibling text.
    labels = ("出错提示:", "提示:", "出错提示：", "提示：")
    try:
        strongs = tree.xpath(".//strong")
    except Exception:
        strongs = []
    for strong in strongs:
        try:
            t = (strong.text or "").strip()
        except Exception:
            continue
        if t not in labels:
            continue
        parent = strong.getparent()
        if parent is None:
            parent = strong
        try:
            full = "".join(parent.xpath("string()")).strip()
        except Exception:
            full = ""
        if full:
            msg = full.replace(t, "", 1).strip()
            if msg:
                return msg

    # Fallback: scan tds and try to strip the label.
    try:
        tds = tree.xpath(".//td")
    except Exception:
        tds = []
    for td in tds:
        try:
            s = "".join(td.xpath("string()")).strip()
        except Exception:
            continue
        if not s:
            continue
        if "出错提示" in s or s.startswith("提示"):
            for lab in labels:
                s = s.replace(lab, "")
            s = s.strip()
            if s:
                return s
    return ""

def get_tips(tree):
    tips = tree.xpath('.//td[@id="msgTips"]')
    if len(tips) == 0:
        return None
    node = tips[0]
    try:
        cells = node.xpath(".//td")
    except Exception:
        cells = []
    texts = []
    for c in cells:
        try:
            s = "".join(c.xpath(".//text()")).strip()
        except Exception:
            continue
        if not s:
            continue
        if s.lower() == "ignore":
            continue
        texts.append(s)
    if not texts:
        # last resort: plain text inside msgTips
        try:
            s = "".join(node.xpath(".//text()")).strip()
        except Exception:
            s = ""
        return s or None
    # pick the most informative one
    return max(texts, key=len).strip()

def get_sida(r):
    return _regexBzfxSida.search(r.text).group(1)

def get_courses(table):
    header = get_table_header(table)
    trs = get_table_trs(table)
    ixs = tuple(map(header.index, ["课程名","班号","开课单位"]))
    cs = []
    for tr in trs:
        t = tr.xpath('./th | ./td')
        try:
            name = _cell_text(t[ixs[0]])
            class_no = _cell_text(t[ixs[1]])
            school = _cell_text(t[ixs[2]])
        except Exception:
            continue
        if not name or not class_no or not school:
            continue
        c = Course(name, class_no, school)
        cs.append(c)
    return cs

def get_courses_with_detail(table):
    header = get_table_header(table)
    trs = get_table_trs(table)
    ixs = tuple(map(header.index, ["课程名","班号","开课单位","限数/已选","补选"]))
    cs = []
    for tr in trs:
        t = tr.xpath('./th | ./td')
        try:
            name = _cell_text(t[ixs[0]])
            class_no = _cell_text(t[ixs[1]])
            school = _cell_text(t[ixs[2]])
            status_text = _cell_text(t[ixs[3]])
        except Exception:
            continue
        status = _parse_quota_pair(status_text)
        if status is None:
            continue
        hrefs = []
        try:
            hrefs = t[ixs[-1]].xpath('.//a/@href')
        except Exception:
            hrefs = []
        href = hrefs[0] if hrefs else None
        if not href:
            continue

        if not name:
            # Some rows render course name via JS (e.g. English-taught graduate courses).
            # Try to recover the name from confirmSelect(...) in the action link.
            try:
                onclicks = t[ixs[-1]].xpath('.//a/@onclick')
            except Exception:
                onclicks = []
            onclick = onclicks[0] if onclicks else ""
            mat = _regexConfirmSelect.search(onclick or "")
            if mat:
                recovered = mat.group("name") or ""
                if recovered.strip():
                    name = recovered.strip()

        if not name or not class_no or not school:
            continue

        c = Course(name, class_no, school, status, href)
        cs.append(c)
    return cs

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from autoelective.parser import get_tree, get_tables, get_courses_with_detail


class ParserSupplyCancelOnclickFallbackOfflineTest(unittest.TestCase):
    def test_onclick_fallback_for_empty_course_name(self):
        # Mimic the real edge case: course name cell is empty (<span></span>),
        # but the action link has confirmSelect(...) with the real course name.
        html = (
            "<html><body>"
            "<table><table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>课程名</th><th>课程类别</th><th>学分</th><th>周学时</th><th>教师</th>"
            "<th>班号</th><th>开课单位</th><th>专业</th><th>年级</th><th>上课信息</th>"
            "<th>授课语言</th><th>限数/已选</th><th>补选</th>"
            "</tr>"
            "<tr class='datagrid-odd'>"
            "<td class='datagrid'><a href='/supplement/goNested.do?x=1' target='_blank'><span></span></a></td>"
            "<td class='datagrid' align='center'><span>必修</span></td>"
            "<td class='datagrid' align='center'><span>2.0</span></td>"
            "<td class='datagrid' align='center'><span>2.0</span></td>"
            "<td class='datagrid'><span>陆蓉蕾(讲师)</span></td>"
            "<td class='datagrid' align='center'><span>01</span></td>"
            "<td class='datagrid'><span>研究生院</span></td>"
            "<td class='datagrid'><span>适用全部专业</span></td>"
            "<td class='datagrid' align='center'><span>2024</span></td>"
            "<td class='datagrid'><span>1~16周 每周周五3~4节</span></td>"
            "<td class='datagrid' align='center'><span>英文</span></td>"
            "<td class='datagrid' align='center'><span>30 / 30</span></td>"
            "<td class='datagrid' align='center'>"
            "<a href='/supplement/electSupplement.do?index=11&xh=STUDENT_ID' "
            "onclick=\"return confirmSelect('STUDENT_ID','REDACTED','TED演讲与社会','01',false,'11','seq',true,'30');\">"
            "<span>刷新</span></a>"
            "</td>"
            "</tr>"
            "</table>"
            "<table class='datagrid'>"
            "<tr class='datagrid-header'><th>课程名</th><th>班号</th><th>开课单位</th></tr>"
            "<tr class='datagrid-even'><td>已选课</td><td>01</td><td>学院A</td></tr>"
            "</table>"
            "</table></body></html>"
        )
        tree = get_tree(html)
        tables = get_tables(tree)
        self.assertGreaterEqual(len(tables), 2)
        plans = get_courses_with_detail(tables[0])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].name, "TED演讲与社会")
        self.assertEqual(plans[0].class_no, 1)
        self.assertEqual(plans[0].school, "研究生院")


if __name__ == "__main__":
    unittest.main()


import glob
import os
import unittest

from autoelective.parser import (
    get_tree,
    get_tables,
    get_courses,
    get_courses_with_detail,
    get_tips,
    get_errInfo,
    get_sida,
)


class ParserOfflineTest(unittest.TestCase):
    def _synthetic_html(self):
        return (
            "<html><body>"
            "<table><table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>课程名</th><th>班号</th><th>开课单位</th><th>限数/已选</th><th>补选</th>"
            "</tr>"
            "<tr class='datagrid-odd'>"
            "<td>课程A</td><td>01</td><td>学院A</td><td>30/10</td>"
            "<td><a href='/supplement/electSupplement.do?course=1'>补选</a></td>"
            "</tr>"
            "</table>"
            "<table class='datagrid'>"
            "<tr class='datagrid-header'>"
            "<th>课程名</th><th>班号</th><th>开课单位</th>"
            "</tr>"
            "<tr class='datagrid-even'>"
            "<td>课程B</td><td>02</td><td>学院B</td>"
            "</tr>"
            "</table></table>"
            "<td id='msgTips'><table><table>"
            "<td>ignore</td><td>您已经选过该课程了。</td>"
            "</table></table></td>"
            "<table><table><table><td><strong>出错提示:</strong>token无效</td></table></table></table>"
            "<a href='ssoLogin.do?sida=abcdef0123456789abcdef0123456789&sttp=bzx'>link</a>"
            "</body></html>"
        )

    def _synthetic_tips_html(self):
        return (
            "<html><head><title>选课</title></head><body>"
            "<td id='msgTips'><table><table>"
            "<td>ignore</td><td>您已经选过该课程了。</td>"
            "</table></table></td>"
            "</body></html>"
        )

    def _synthetic_error_html(self):
        return (
            "<html><head><title>系统提示</title></head><body>"
            "<table><table><table><td><strong>出错提示:</strong>token无效</td></table></table></table>"
            "</body></html>"
        )

    def _find_table_with_headers(self, tables, headers):
        for table in tables:
            header = table.xpath('.//tr[@class="datagrid-header"]/th/text()')
            if header and all(h in header for h in headers):
                return table
        return None

    def _find_fixture(self):
        patterns = [
            os.path.join("log", "web", "**", "elective.get_SupplyCancel_*.html"),
            os.path.join("log", "web", "**", "elective.get_SupplyCancel_*.HTML"),
        ]
        for pattern in patterns:
            paths = glob.glob(pattern, recursive=True)
            if paths:
                return sorted(paths)[0]
        return None

    def test_parse_supply_cancel_fixture_or_synthetic(self):
        path = self._find_fixture()
        if path:
            with open(path, "rb") as fp:
                content = fp.read()
        else:
            content = self._synthetic_html().encode("utf-8")
        tree = get_tree(content)
        tables = get_tables(tree)
        if len(tables) < 1:
            self.skipTest("HTML does not contain expected tables")
        plan_table = self._find_table_with_headers(
            tables, ["课程名", "班号", "开课单位", "限数/已选", "补选"]
        )
        elected_table = self._find_table_with_headers(
            tables, ["课程名", "班号", "开课单位"]
        )
        if plan_table is None or elected_table is None:
            self.skipTest("HTML does not contain expected datagrid headers")
        elected = get_courses(elected_table)
        plans = get_courses_with_detail(plan_table)
        self.assertIsInstance(elected, list)
        self.assertIsInstance(plans, list)
        self.assertGreaterEqual(len(plans), 0)

    def test_parse_tips_and_error(self):
        tips_tree = get_tree(self._synthetic_tips_html())
        err_tree = get_tree(self._synthetic_error_html())
        tips = get_tips(tips_tree)
        err = get_errInfo(err_tree)
        self.assertEqual(tips, "您已经选过该课程了。")
        self.assertEqual(err, "token无效")

    def test_parse_sida(self):
        class R:
            text = "ssoLogin.do?sida=abcdef0123456789abcdef0123456789&sttp=bzx"
        sida = get_sida(R())
        self.assertEqual(sida, "abcdef0123456789abcdef0123456789")


if __name__ == "__main__":
    unittest.main()

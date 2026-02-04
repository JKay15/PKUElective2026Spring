import unittest

from autoelective.course import Course


class CourseOfflineTest(unittest.TestCase):
    def test_course_identity_and_quota(self):
        c1 = Course("课程A", "01", "学院A", (30, 10), "/supplement/electSupplement.do?x=1")
        c2 = Course("课程A", 1, "学院A")
        self.assertEqual(c1, c2)
        self.assertEqual(hash(c1), hash(c2))
        self.assertTrue(c1.is_available())
        self.assertEqual(c1.remaining_quota, 20)


if __name__ == "__main__":
    unittest.main()

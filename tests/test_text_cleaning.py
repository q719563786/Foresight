import unittest

from yuanjian_app.text_cleaning import plain_text


class PlainTextTests(unittest.TestCase):
    def test_removes_markup_hidden_content_and_decodes_entities(self):
        value = '<a href="x">政策&nbsp;更新</a><script>bad()</script><style>x{}</style>'

        self.assertEqual(plain_text(value), "政策 更新")

    def test_normalizes_whitespace_and_truncates_with_ellipsis(self):
        self.assertEqual(plain_text("  一\n 二   三  "), "一 二 三")
        self.assertEqual(plain_text("  一 二 三  ", max_length=3), "一 二…")

    def test_empty_and_non_string_values_are_safe(self):
        self.assertEqual(plain_text(None), "")
        self.assertEqual(plain_text(123), "123")


if __name__ == "__main__":
    unittest.main()

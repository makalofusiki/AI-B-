import unittest

from app import generate_reply


class TestGenerateReply(unittest.TestCase):
    def test_empty_question(self):
        self.assertIn("请先输入", generate_reply(""))

    def test_known_keyword(self):
        self.assertIn("中药", generate_reply("请介绍一下公司"))

    def test_unknown_keyword(self):
        self.assertIn("演示版助手", generate_reply("你们支持哪些AI模型？"))


if __name__ == "__main__":
    unittest.main()

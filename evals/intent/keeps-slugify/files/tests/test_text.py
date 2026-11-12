import unittest

from text import slugify


class Slugify(unittest.TestCase):
    def test_words_are_joined_by_dashes(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation_becomes_one_dash(self):
        self.assertEqual(slugify("Tips & tricks: part 2"), "tips-tricks-part-2")

    def test_no_dash_at_either_end(self):
        self.assertEqual(slugify("  (draft) Hello!  "), "draft-hello")


if __name__ == "__main__":
    unittest.main()

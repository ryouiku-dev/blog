import json
import tempfile
import unittest
from pathlib import Path

from wordpress_blog_tool import generate_blog_draft, save_draft, slugify, split_keywords


class WordPressBlogToolTest(unittest.TestCase):
    def test_split_keywords_normalizes_and_deduplicates(self):
        self.assertEqual(
            split_keywords(["療育, 発達支援", "療育", "家庭"]),
            ["療育", "発達支援", "家庭"],
        )

    def test_slugify_falls_back_for_empty_slug(self):
        self.assertEqual(slugify("!!!"), "wordpress-blog-draft")

    def test_generate_blog_draft_contains_wordpress_blocks(self):
        draft = generate_blog_draft(
            title="家庭で始める療育",
            topic="家庭療育",
            audience="保護者",
            keywords=["療育", "発達支援"],
        )

        self.assertEqual(draft.title, "家庭で始める療育")
        self.assertIn("<!-- wp:paragraph -->", draft.html)
        self.assertIn("SEOキーワード", draft.html)
        self.assertEqual(draft.keywords, ["療育", "発達支援"])

    def test_save_draft_writes_html_and_metadata(self):
        draft = generate_blog_draft(
            title="Test Blog",
            topic="WordPress",
            audience="Editors",
            keywords=["SEO"],
        )

        with tempfile.TemporaryDirectory() as tmp:
            html_path, json_path = save_draft(draft, Path(tmp))
            self.assertTrue(html_path.exists())
            self.assertTrue(json_path.exists())
            self.assertIn("<!-- wp:post-title /-->", html_path.read_text(encoding="utf-8"))
            metadata = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["slug"], "test-blog")


if __name__ == "__main__":
    unittest.main()

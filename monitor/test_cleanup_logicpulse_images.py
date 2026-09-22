import unittest

from cleanup_logicpulse_images import category_from_image_key, cleanup_categories, matching_image_keys


class CleanupLogicPulseImagesTests(unittest.TestCase):
    def test_cleanup_includes_all_repos_but_preserves_coupons(self):
        categories = cleanup_categories("coupons")
        self.assertIn("emergency_need", categories)
        self.assertIn("buy_now_pay_later", categories)
        self.assertNotIn("coupons", categories)

    def test_extracts_category_only_from_image_path(self):
        key = "sheeel_data/year=2026/month=09/day=22/flowers_chocolate_by_sogha/images/123_0.jpg"
        self.assertEqual(category_from_image_key(key), "flowers_chocolate_by_sogha")
        self.assertIsNone(category_from_image_key(key.replace("images", "excel-files")))

    def test_filters_to_requested_categories(self):
        pages = [
            {
                "Contents": [
                    {"Key": "sheeel_data/year=2026/month=09/day=22/flowers_chocolate_by_sogha/images/a.jpg"},
                    {"Key": "sheeel_data/year=2026/month=09/day=22/coupons/images/b.jpg"},
                    {"Key": "sheeel_data/year=2026/month=09/day=22/flowers_chocolate_by_sogha/excel-files/a.xlsx"},
                ]
            }
        ]
        self.assertEqual(
            matching_image_keys(pages, {"flowers_chocolate_by_sogha"}),
            ["sheeel_data/year=2026/month=09/day=22/flowers_chocolate_by_sogha/images/a.jpg"],
        )


if __name__ == "__main__":
    unittest.main()
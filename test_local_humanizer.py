import unittest

from local_humanizer import mask_content, restore_and_validate


class ProtectedContentTests(unittest.TestCase):
    def test_masks_and_restores_citations_ids_numbers_and_emails(self):
        original = "The model achieved 95.4% accuracy for CVE-2024-12345 [12] (Smith, 2024). Contact a.b@example.org."
        masked, protected = mask_content(original, None)
        self.assertNotIn("a.b@example.org", masked)
        self.assertNotIn("CVE-2024-12345", masked)
        restored, reason = restore_and_validate(original, masked, protected)
        self.assertEqual(reason, "")
        self.assertEqual(restored, original)

    def test_rejects_missing_placeholder(self):
        original = "Accuracy was 95.4% [12]."
        masked, protected = mask_content(original, None)
        bad = masked.replace(next(iter(protected)), "")
        restored, reason = restore_and_validate(original, bad, protected)
        self.assertIsNone(restored)
        self.assertIn("placeholders", reason)

    def test_rejects_numeric_change_after_restore(self):
        original = "The result was 95.4%."
        masked, protected = mask_content(original, None)
        candidate = masked.replace("The result", "The finding")
        restored, reason = restore_and_validate(original, candidate, protected)
        self.assertEqual(restored, "The finding was 95.4%.")
        self.assertEqual(reason, "")

    def test_rejects_missing_numeric_placeholder(self):
        original = "The result was 95.4%."
        masked, protected = mask_content(original, None)
        candidate = masked.replace(next(iter(protected)), "ninety-five percent")
        restored, reason = restore_and_validate(original, candidate, protected)
        self.assertIsNone(restored)
        self.assertIn("placeholders", reason)


if __name__ == "__main__":
    unittest.main()

class DocumentStructureTests(unittest.TestCase):
    def test_iter_all_paragraphs_counts_body_and_table_content(self):
        from docx import Document
        from local_humanizer import iter_all_paragraphs
        doc = Document()
        doc.add_paragraph("A body paragraph.")
        table = doc.add_table(rows=1, cols=1)
        table.cell(0, 0).text = "A table paragraph."
        items = list(iter_all_paragraphs(doc))
        self.assertEqual(len(items), 2)
        self.assertEqual([kind for _, _, kind in items], ["body", "table"])

    def test_heading_detection_uses_word_style(self):
        from docx import Document
        from local_humanizer import is_heading_or_reference
        doc = Document()
        para = doc.add_paragraph("A section title")
        para.style = "Heading 1"
        self.assertIn("Heading 1", is_heading_or_reference(para))

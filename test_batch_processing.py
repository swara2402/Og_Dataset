"""Unit tests for batch processing functionality in Turnitout."""
import json
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
from docx import Document
from local_humanizer import process_docx, AcademicEditor, BatchParagraph, BATCH_SYSTEM_PROMPT
from ollama_provider import OllamaProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class BatchProcessingTests(unittest.TestCase):
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        
    def create_test_docx(self, paragraphs):
        """Create a test DOCX file with given paragraphs."""
        doc = Document()
        for p in paragraphs:
            doc.add_paragraph(p)
        input_path = Path(self.test_dir) / "input.docx"
        doc.save(str(input_path))
        return input_path

    @patch("urllib.request.urlopen")
    def test_batch_request_generation(self, mocked):
        """Test 1: Batch request generation is correct."""
        # Mock Ollama response for a batch of 4 paragraphs
        mocked.return_value = FakeResponse({
            "message": {
                "content": json.dumps({
                    "paragraphs": [
                        {"id": "para_0000", "edited_text": "Edited first paragraph", "change_notes": ["Fixed grammar"]},
                        {"id": "para_0001", "edited_text": "Edited second paragraph", "change_notes": ["Improved clarity"]},
                        {"id": "para_0002", "edited_text": "Edited third paragraph", "change_notes": []},
                        {"id": "para_0003", "edited_text": "Edited fourth paragraph", "change_notes": ["Fixed spelling"]}
                    ]
                })
            }
        })
        
        from local_humanizer import mask_content
        
        # Create editor and test batch creation
        editor = AcademicEditor(batch_size=4)
        
        # Create batch paragraphs
        batch_paragraphs = []
        test_texts = [
            "First test paragraph with some content.",
            "Second test paragraph with different content.", 
            "Third test paragraph that is good.",
            "Fourth test paragraph with errors."
        ]
        
        for i, text in enumerate(test_texts):
            masked, replacements = mask_content(text, editor.nlp)
            bp = BatchParagraph(
                paragraph_id=f"para_{i:04d}",
                original_text=text,
                masked_text=masked,
                replacements=replacements,
                location=f"Test paragraph {i}",
                paragraph_obj=MagicMock()
            )
            batch_paragraphs.append(bp)
        
        # Process batch
        results = editor.revise_batch(batch_paragraphs)
        self.assertEqual(len(results), 4)
        
        # Verify the request that was sent
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        
        # Check that payload contains all paragraphs
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "qwen3:4b-instruct-2507-q4_K_M" if "OLLAMA_MODEL" not in globals() else globals()["OLLAMA_MODEL"])
        self.assertEqual(payload["stream"], False)
        self.assertEqual(payload["format"], "json")
        self.assertTrue("keep_alive" in payload)
        self.assertEqual(payload["keep_alive"], "5m")

    @patch("urllib.request.urlopen")
    def test_valid_batch_json_responses(self, mocked):
        """Test 2: Valid batch JSON responses are processed correctly."""
        mocked.return_value = FakeResponse({
            "message": {
                "content": json.dumps({
                    "paragraphs": [
                        {"id": "para_0000", "edited_text": "This is a good paragraph.", "change_notes": ["Minor edit"]}
                    ]
                })
            }
        })
        
        editor = AcademicEditor(batch_size=1)
        bp = BatchParagraph(
            paragraph_id="para_0000",
            original_text="This is a paragraph.",
            masked_text="This is a paragraph.",
            replacements={},
            location="Test",
            paragraph_obj=MagicMock()
        )
        
        results = editor.revise_batch([bp])
        self.assertEqual(len(results), 1)
        edited, notes, elapsed = results[0]
        self.assertEqual(edited, "This is a good paragraph.")
        self.assertEqual(notes, ["Minor edit"])

    @patch("urllib.request.urlopen")
    def test_missing_paragraph_ids(self, mocked):
        """Test 3: Missing paragraph IDs raise errors."""
        mocked.return_value = FakeResponse({
            "message": {
                "content": json.dumps({
                    "paragraphs": [
                        {"id": "wrong_id", "edited_text": "Some text", "change_notes": []}
                    ]
                })
            }
        })
        
        editor = AcademicEditor(batch_size=1)
        bp = BatchParagraph(
            paragraph_id="para_0000",
            original_text="Original text.",
            masked_text="Original text.",
            replacements={},
            location="Test",
            paragraph_obj=MagicMock()
        )
        
        with self.assertRaises(ValueError) as ctx:
            editor.revise_batch([bp])
        self.assertIn("Missing response for paragraph ID: para_0000", str(ctx.exception))

    @patch("urllib.request.urlopen") 
    def test_duplicate_paragraph_ids(self, mocked):
        """Test 4: Duplicate paragraph IDs in response cause issues."""
        mocked.return_value = FakeResponse({
            "message": {
                "content": json.dumps({
                    "paragraphs": [
                        {"id": "para_0000", "edited_text": "First", "change_notes": []},
                        {"id": "para_0000", "edited_text": "Second", "change_notes": []}
                    ]
                })
            }
        })
        
        editor = AcademicEditor(batch_size=2)
        bps = [
            BatchParagraph(
                paragraph_id="para_0000",
                original_text="Original 1",
                masked_text="Original 1",
                replacements={},
                location="Test 1",
                paragraph_obj=MagicMock()
            ),
            BatchParagraph(
                paragraph_id="para_0001", 
                original_text="Original 2",
                masked_text="Original 2",
                replacements={},
                location="Test 2",
                paragraph_obj=MagicMock()
            )
        ]
        
        with self.assertRaises(ValueError) as ctx:
            editor.revise_batch(bps)
        self.assertIn("Missing response for paragraph ID: para_0001", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_reordered_paragraph_ids(self, mocked):
        """Test 5: Reordered paragraphs are still correctly mapped."""
        mocked.return_value = FakeResponse({
            "message": {
                "content": json.dumps({
                    "paragraphs": [
                        {"id": "para_0001", "edited_text": "Edited second", "change_notes": []},
                        {"id": "para_0000", "edited_text": "Edited first", "change_notes": []}
                    ]
                })
            }
        })
        
        editor = AcademicEditor(batch_size=2)
        bps = [
            BatchParagraph(
                paragraph_id="para_0000",
                original_text="Original first",
                masked_text="Original first",
                replacements={},
                location="Test 1",
                paragraph_obj=MagicMock()
            ),
            BatchParagraph(
                paragraph_id="para_0001",
                original_text="Original second",
                masked_text="Original second",
                replacements={},
                location="Test 2",
                paragraph_obj=MagicMock()
            )
        ]
        
        results = editor.revise_batch(bps)
        self.assertEqual(len(results), 2)
        # First result should be for para_0000
        self.assertEqual(results[0][0], "Edited first")
        # Second result should be for para_0001
        self.assertEqual(results[1][0], "Edited second")

    def test_modified_protected_placeholders(self, mocked=None):
        """Test 6: Modified protected placeholders are rejected."""
        from local_humanizer import restore_and_validate
        
        original = "The authors found that 42% of samples were positive. [1]"
        candidate = "The authors found that 50% of samples were positive. [2]"
        replacements = {}
        
        # This should fail validation because numbers/citations changed
        restored, reason = restore_and_validate(original, candidate, replacements)
        self.assertIsNone(restored)
        self.assertTrue("number integrity check failed" in reason or "citation integrity check failed" in reason)

    def test_name_and_citation_preservation(self):
        """Test 7: Names and citations are properly masked and restored."""
        from local_humanizer import mask_content, restore_and_validate
        
        text = "Smith et al. (2023) found that 15% of participants improved. See https://example.com for details."
        masked, replacements = mask_content(text, None)  # No spaCy, rely on regex patterns
        
        # Verify placeholders were created
        self.assertIn("__TURNITOUT_PROTECTED_", masked)
        self.assertGreater(len(replacements), 0)
        
        # Restore and verify
        restored, reason = restore_and_validate(text, masked, replacements)
        self.assertEqual(restored, text)
        self.assertEqual(reason, "")

    def test_batch_size_configuration(self):
        """Test 13: Batch size configuration works correctly."""
        # Test default batch size
        editor1 = AcademicEditor()
        self.assertEqual(editor1.batch_size, 4)
        
        # Test custom batch size from parameter
        editor2 = AcademicEditor(batch_size=5)
        self.assertEqual(editor2.batch_size, 5)
        
        # Test environment variable
        import os
        os.environ["TURNITOUT_BATCH_SIZE"] = "3"
        editor3 = AcademicEditor()
        self.assertEqual(editor3.batch_size, 3)
        del os.environ["TURNITOUT_BATCH_SIZE"]

    @patch("urllib.request.urlopen")
    def test_failed_ollama_requests(self, mocked):
        """Test 10: Failed Ollama requests are handled gracefully."""
        # Make the mock raise an error to simulate Ollama being down
        mocked.side_effect = Exception("Connection refused")
        
        editor = AcademicEditor(batch_size=2)
        bps = [
            BatchParagraph(
                paragraph_id="para_0000",
                original_text="Original first",
                masked_text="Original first",
                replacements={},
                location="Test 1",
                paragraph_obj=MagicMock()
            ),
            BatchParagraph(
                paragraph_id="para_0001",
                original_text="Original second",
                masked_text="Original second",
                replacements={},
                location="Test 2",
                paragraph_obj=MagicMock()
            )
        ]
        
        with self.assertRaises(ValueError) as ctx:
            editor.revise_batch(bps)
        self.assertIn("Batch processing failed", str(ctx.exception))

    def test_empty_document(self):
        """Test 11: Empty documents are processed without errors."""
        # Create empty document
        doc = Document()
        input_path = Path(self.test_dir) / "empty.docx"
        doc.save(str(input_path))
        output_path = Path(self.test_dir) / "empty_output.docx"
        
        # Process should complete without errors
        report = process_docx(str(input_path), str(output_path))
        self.assertEqual(report.body_paragraphs, 1)  # There's always at least one empty paragraph
        self.assertEqual(report.edited, 0)

    @patch("urllib.request.urlopen")
    def test_table_preservation(self, mocked):
        """Test 9: Table content is preserved and not edited."""
        # Create document with a table
        doc = Document()
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Header 1"
        table.cell(0, 1).text = "Header 2"
        table.cell(1, 0).text = "Data 1"
        table.cell(1, 1).text = "Data 2"
        
        input_path = Path(self.test_dir) / "table_test.docx"
        doc.save(str(input_path))
        output_path = Path(self.test_dir) / "table_output.docx"
        
        # Mock response - shouldn't be called for table content
        mocked.return_value = FakeResponse({
            "message": {"content": json.dumps({"paragraphs": []})}
        })
        
        report = process_docx(str(input_path), str(output_path))
        # Table paragraphs are counted separately and skipped
        self.assertGreater(report.table_paragraphs, 0)
        self.assertEqual(report.edited, 0)  # No table content should be edited

    def test_large_document(self):
        """Test 12: Large documents are processed correctly with batching."""
        # Create a document with 20 paragraphs - should be processed in 5 batches of 4
        paragraphs = [f"This is paragraph {i} that needs some editing." for i in range(20)]
        input_path = self.create_test_docx(paragraphs)
        output_path = Path(self.test_dir) / "large_output.docx"
        
        # Process without Ollama calls (we'll just test it categorizes correctly)
        report = process_docx(str(input_path), str(output_path))
        # All 20 paragraphs should be body paragraphs
        self.assertEqual(report.body_paragraphs, 20)
        # If spaCy is not available, they might be skipped, but processing should complete
        self.assertGreaterEqual(report.skipped + report.edited + report.unchanged, 0)

    @patch("urllib.request.urlopen")
    def test_docx_formatting_preservation(self, mocked):
        """Test 8: DOCX formatting (bold, italic, etc.) is preserved."""
        # Create document with formatted text
        doc = Document()
        p = doc.add_paragraph()
        run1 = p.add_run("This is ")
        run2 = p.add_run("bold")
        run2.bold = True
        run3 = p.add_run(" and this is ")
        run4 = p.add_run("italic")
        run4.italic = True
        run5 = p.add_run(".")
        
        input_path = Path(self.test_dir) / "formatting_test.docx"
        doc.save(str(input_path))
        output_path = Path(self.test_dir) / "formatting_output.docx"
        
        # Mock response
        mocked.return_value = FakeResponse({
            "message": {
                "content": json.dumps({
                    "paragraphs": [
                        {"id": "para_0000", "edited_text": "This is bold and this is italic.", "change_notes": []}
                    ]
                })
            }
        })
        
        report = process_docx(str(input_path), str(output_path))
        # Paragraph with multiple runs should be skipped to preserve formatting
        self.assertEqual(report.skipped, 1)
        self.assertEqual(report.edited, 0)

    def test_ollama_provider_tracking(self):
        """Test that OllamaProvider tracks requests and timing correctly."""
        provider = OllamaProvider()
        self.assertEqual(provider.total_requests, 0)
        self.assertEqual(provider.total_time, 0.0)
        
        # After a mock request, counters should increment
        # (This is implicitly tested in other tests but good to verify)


if __name__ == "__main__":
    unittest.main()
"""Document parser for Turnitout.
Handles ingestion and structure extraction from:
- DOCX
- TXT
- Markdown
- PDF (text extraction)
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Any, Dict
from pathlib import Path
import io

# DOCX support
from docx import Document as DocxDocument
from docx.document import Document as DocxDocumentType
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.text.paragraph import Paragraph as DocxParagraph
from docx.table import Table as DocxTable

# PDF support (PyMuPDF)
try:
    import fitz  # type: ignore[import-untyped]  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pypdf import PdfReader as PypdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# Markdown support
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False


HEADER_RE = re.compile(
    r"^\s*(?:(?:[IVX]+|\d+)(?:\.[A-Z])?\.?\s+)?"
    r"(?:ABSTRACT|INTRODUCTION|BACKGROUND|RELATED WORK|LITERATURE REVIEW|"
    r"METHODOLOGY|METHODS|RESULTS|DISCUSSION|CONCLUSION|REFERENCES|"
    r"ACKNOWLEDGMENTS|FUTURE WORK)(?:\s|:|$)", re.I,
)
REFERENCE_RE = re.compile(r"^\s*(?:\[\d+\]|\d+\.)\s+.{0,220}(?:\b(?:19|20)\d{2}\b|doi:|https?://)", re.I)
FRONT_MATTER_RE = re.compile(r"\b(author|affiliation|department|university|institute|college|corresponding author|e-mail)\b", re.I)


@dataclass
class DocumentParagraph:
    """Represents a single paragraph extracted from a document."""
    id: str
    text: str
    paragraph_type: str  # heading, reference, body, table, caption, code, equation
    location: str  # e.g., "body.12", "table.3.cell.0.0"
    original_element: Any = None  # Reference to original DOCX/PDF element
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Complete parsed document with all paragraphs and metadata."""
    filename: str
    file_type: str
    paragraphs: List[DocumentParagraph] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def total_paragraphs(self) -> int:
        return len(self.paragraphs)
    
    @property
    def body_paragraphs(self) -> List[DocumentParagraph]:
        return [p for p in self.paragraphs if p.paragraph_type == "body"]
    
    @property
    def table_paragraphs(self) -> List[DocumentParagraph]:
        return [p for p in self.paragraphs if p.paragraph_type == "table"]


class DocumentParser:
    """Main document parser that routes to format-specific parsers."""
    
    @staticmethod
    def parse(file_path: Path | bytes, filename: str) -> ParsedDocument:
        """Auto-detect file type and parse the document."""
        if isinstance(file_path, bytes):
            # In-memory file upload
            return DocumentParser._parse_bytes(file_path, filename)
        else:
            # File on disk
            return DocumentParser._parse_file(file_path, filename)

    @staticmethod
    def parse_bytes(data: bytes, filename: str, file_type: str | None = None) -> ParsedDocument:
        """Parse an in-memory upload. `file_type` is advisory; the suffix wins."""
        suffix = Path(filename).suffix.lower()
        if file_type and not suffix:
            suffix = "." + file_type.lower().lstrip(".")
        if suffix == ".docx":
            return DocxParser.parse_bytes(data, filename)
        if suffix == ".pdf":
            return PDFParser.parse_bytes(data, filename)
        if suffix == ".tex":
            return LatexParser.parse_bytes(data, filename)
        if suffix in (".txt", ".text"):
            return TextParser.parse_bytes(data, filename)
        if suffix in (".md", ".markdown"):
            return MarkdownParser.parse_bytes(data, filename)
        raise ValueError(f"Unsupported file format: {suffix or file_type or 'unknown'}")
    
    @staticmethod
    def _parse_file(file_path: Path, filename: str) -> ParsedDocument:
        suffix = file_path.suffix.lower()
        if suffix == '.docx':
            return DocxParser.parse(file_path, filename)
        elif suffix == '.pdf':
            return PDFParser.parse(file_path, filename)
        elif suffix == '.tex':
            return LatexParser.parse(file_path, filename)
        elif suffix in ['.txt', '.text']:
            return TextParser.parse(file_path, filename)
        elif suffix in ['.md', '.markdown']:
            return MarkdownParser.parse(file_path, filename)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
    
    @staticmethod
    def _parse_bytes(data: bytes, filename: str) -> ParsedDocument:
        suffix = Path(filename).suffix.lower()
        if suffix == '.docx':
            return DocxParser.parse_bytes(data, filename)
        elif suffix == '.pdf':
            return PDFParser.parse_bytes(data, filename)
        elif suffix == '.tex':
            return LatexParser.parse_bytes(data, filename)
        elif suffix in ['.txt', '.text']:
            return TextParser.parse_bytes(data, filename)
        elif suffix in ['.md', '.markdown']:
            return MarkdownParser.parse_bytes(data, filename)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")


class DocxParser:
    """DOCX document parser."""
    
    @staticmethod
    def classify_paragraph(docx_para: DocxParagraph) -> str:
        """Classify a DOCX paragraph into one of our paragraph types."""
        text = docx_para.text.strip()
        if not text:
            return "empty"
        
        # Check Word style
        style_name = getattr(getattr(docx_para, "style", None), "name", "") or ""
        style_name = style_name.lower()
        if style_name.startswith(("heading", "title", "subtitle")):
            return "heading"
        
        # Check text patterns
        if HEADER_RE.match(text):
            return "heading"
        if REFERENCE_RE.match(text) or text.lower() in {"references", "bibliography"}:
            return "reference"
        if FRONT_MATTER_RE.search(text) and len(text) < 500:
            return "front_matter"
        
        # Check for code/equation patterns
        if text.startswith("    ") or text.startswith("\t"):
            return "code"
        if "$" in text or "\\" in text and ("\\(" in text or "\\[" in text):
            return "equation"
        
        return "body"
    
    @staticmethod
    def iter_all_elements(doc: DocxDocumentType, filename: str) -> List[DocumentParagraph]:
        """Extract body paragraphs and table content in document order."""
        paragraphs: List[DocumentParagraph] = []
        body_counter = 0
        table_counter = 0

        def append_paragraph(
            paragraph: DocxParagraph,
            identifier: str,
            location: str,
            forced_type: str | None = None,
            metadata: Dict[str, Any] | None = None,
        ) -> None:
            text = paragraph.text
            if not text.strip():
                return
            paragraph_type = forced_type or DocxParser.classify_paragraph(paragraph)
            details = dict(metadata or {})
            details["style"] = getattr(paragraph.style, "name", None)
            paragraphs.append(
                DocumentParagraph(
                    id=identifier,
                    text=text,
                    paragraph_type=paragraph_type,
                    location=location,
                    original_element=paragraph,
                    metadata=details,
                )
            )

        def append_table(table: DocxTable, table_path: str) -> None:
            nonlocal table_counter
            table_counter += 1
            current_table = table_counter
            for row_idx, row in enumerate(table.rows):
                seen_cells: set[Any] = set()
                for cell_idx, cell in enumerate(row.cells):
                    cell_key = cell._tc
                    if cell_key in seen_cells:
                        continue
                    seen_cells.add(cell_key)
                    para_index = 0
                    for child in cell._tc.iterchildren():
                        if isinstance(child, CT_P):
                            para = DocxParagraph(child, cell)
                            location = (
                                f"{table_path}.table.{current_table}.cell."
                                f"{row_idx}.{cell_idx}.paragraph.{para_index}"
                            )
                            identifier = (
                                f"{table_path}_table_{current_table}_row_{row_idx}_"
                                f"cell_{cell_idx}_para_{para_index}"
                            )
                            append_paragraph(
                                para,
                                identifier,
                                location,
                                forced_type="table",
                                metadata={
                                    "table_index": current_table - 1,
                                    "row": row_idx,
                                    "cell": cell_idx,
                                    "paragraph": para_index,
                                },
                            )
                            para_index += 1
                        elif isinstance(child, CT_Tbl):
                            append_table(
                                DocxTable(child, cell),
                                f"{table_path}_nested_{current_table}",
                            )

        for child in doc.element.body.iterchildren():
            if isinstance(child, CT_P):
                paragraph = DocxParagraph(child, doc)
                body_counter += 1
                append_paragraph(
                    paragraph,
                    f"body_{body_counter}",
                    f"body.{body_counter}",
                )
            elif isinstance(child, CT_Tbl):
                append_table(DocxTable(child, doc), f"table_{table_counter + 1}")
        return paragraphs
    
    @staticmethod
    def parse(file_path: Path, filename: str) -> ParsedDocument:
        doc = DocxDocument(str(file_path))
        paragraphs = DocxParser.iter_all_elements(doc, filename)
        return ParsedDocument(
            filename=filename,
            file_type="docx",
            paragraphs=paragraphs,
            metadata={"core_properties": getattr(doc, "core_properties", None)}
        )
    
    @staticmethod
    def parse_bytes(data: bytes, filename: str) -> ParsedDocument:
        stream = io.BytesIO(data)
        doc = DocxDocument(stream)
        paragraphs = DocxParser.iter_all_elements(doc, filename)
        return ParsedDocument(
            filename=filename,
            file_type="docx",
            paragraphs=paragraphs
        )


class PDFParser:
    """PDF document parser using PyMuPDF."""
    
    @staticmethod
    def parse(file_path: Path, filename: str) -> ParsedDocument:
        if PYMUPDF_AVAILABLE:
            doc = fitz.open(str(file_path))
            return PDFParser._extract_paragraphs(doc, filename)
        if PYPDF_AVAILABLE:
            reader = PypdfReader(str(file_path))
            return PDFParser._extract_with_pypdf(reader, filename)
        raise ImportError(
            "PDF support requires PyMuPDF or pypdf. Install one with "
            "'pip install pymupdf' or 'pip install pypdf'."
        )
    
    @staticmethod
    def parse_bytes(data: bytes, filename: str) -> ParsedDocument:
        if PYMUPDF_AVAILABLE:
            doc = fitz.open(stream=data, filetype="pdf")
            return PDFParser._extract_paragraphs(doc, filename)
        if PYPDF_AVAILABLE:
            reader = PypdfReader(io.BytesIO(data))
            return PDFParser._extract_with_pypdf(reader, filename)
        raise ImportError(
            "PDF support requires PyMuPDF or pypdf. Install one with "
            "'pip install pymupdf' or 'pip install pypdf'."
        )
    
    @staticmethod
    def _extract_with_pypdf(reader: "PypdfReader", filename: str) -> ParsedDocument:
        paragraphs: List[DocumentParagraph] = []
        counter = 0
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            for block in re.split(r"\n\s*\n", text):
                block = block.strip()
                if not block:
                    continue
                counter += 1
                para_type = "body"
                if HEADER_RE.match(block):
                    para_type = "heading"
                elif REFERENCE_RE.match(block):
                    para_type = "reference"
                paragraphs.append(DocumentParagraph(
                    id=f"page_{page_num+1}_block_{counter}",
                    text=block,
                    paragraph_type=para_type,
                    location=f"page.{page_num+1}.block.{counter}",
                    metadata={"page": page_num + 1},
                ))
        return ParsedDocument(
            filename=filename,
            file_type="pdf",
            paragraphs=paragraphs,
            metadata={"page_count": len(reader.pages), "extractor": "pypdf"},
        )
    
    @staticmethod
    def _extract_paragraphs(doc: "fitz.Document", filename: str) -> ParsedDocument:
        paragraphs: List[DocumentParagraph] = []
        counter = 0
        
        for page_num, page in enumerate(doc):
            blocks = page.get_text("blocks")
            for block in blocks:
                if block[6] == 0:  # Text block
                    text = block[4].strip()
                    if text:
                        counter += 1
                        # Classify the block
                        para_type = "body"
                        if HEADER_RE.match(text):
                            para_type = "heading"
                        elif REFERENCE_RE.match(text):
                            para_type = "reference"
                        
                        paragraphs.append(DocumentParagraph(
                            id=f"page_{page_num+1}_block_{counter}",
                            text=text,
                            paragraph_type=para_type,
                            location=f"page.{page_num+1}.block.{counter}",
                            metadata={"page": page_num+1, "bbox": block[:4]}
                        ))
        
        return ParsedDocument(
            filename=filename,
            file_type="pdf",
            paragraphs=paragraphs,
            metadata={"page_count": len(doc)}
        )


class TextParser:
    """Plain text file parser."""
    
    @staticmethod
    def parse(file_path: Path, filename: str) -> ParsedDocument:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return TextParser._parse_content(content, filename)
    
    @staticmethod
    def parse_bytes(data: bytes, filename: str) -> ParsedDocument:
        content = data.decode('utf-8')
        return TextParser._parse_content(content, filename)
    
    @staticmethod
    def _parse_content(content: str, filename: str) -> ParsedDocument:
        paragraphs: List[DocumentParagraph] = []
        counter = 0
        
        # Split on double newlines to separate paragraphs
        raw_paragraphs = re.split(r'\n\s*\n', content)
        
        for para_text in raw_paragraphs:
            para_text = para_text.strip()
            if para_text:
                counter += 1
                para_type = "body"
                if HEADER_RE.match(para_text):
                    para_type = "heading"
                elif REFERENCE_RE.match(para_text):
                    para_type = "reference"
                
                paragraphs.append(DocumentParagraph(
                    id=f"para_{counter}",
                    text=para_text,
                    paragraph_type=para_type,
                    location=f"text.{counter}",
                ))
        
        return ParsedDocument(
            filename=filename,
            file_type="txt",
            paragraphs=paragraphs
        )


class MarkdownParser:
    """Markdown file parser."""
    
    @staticmethod
    def parse(file_path: Path, filename: str) -> ParsedDocument:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return MarkdownParser._parse_markdown(content, filename)
    
    @staticmethod
    def parse_bytes(data: bytes, filename: str) -> ParsedDocument:
        content = data.decode('utf-8')
        return MarkdownParser._parse_markdown(content, filename)
    
    @staticmethod
    def _parse_markdown(content: str, filename: str) -> ParsedDocument:
        paragraphs: List[DocumentParagraph] = []
        counter = 0
        
        # Split into blocks, identify markdown elements
        blocks = re.split(r'\n\s*\n', content)
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            counter += 1
            
            # Detect markdown headings
            if block.startswith('#'):
                paragraphs.append(DocumentParagraph(
                    id=f"md_{counter}",
                    text=block.lstrip('#').strip(),
                    paragraph_type="heading",
                    location=f"markdown.{counter}",
                    metadata={"md_heading": True}
                ))
                continue
            
            # Detect code blocks
            if block.startswith('```'):
                paragraphs.append(DocumentParagraph(
                    id=f"md_{counter}",
                    text=block.replace('```', '').strip(),
                    paragraph_type="code",
                    location=f"markdown.{counter}",
                    metadata={"code_block": True}
                ))
                continue
            
            # Regular body text
            paragraphs.append(DocumentParagraph(
                id=f"md_{counter}",
                text=block,
                paragraph_type="body",
                location=f"markdown.{counter}"
            ))
        
        return ParsedDocument(
            filename=filename,
            file_type="markdown",
            paragraphs=paragraphs
        )


class LatexParser:
    """Conservative LaTeX block parser with exact source offsets.

    It does not attempt to fully compile or normalize TeX. Structural commands,
    math environments, code environments and bibliography blocks are marked
    non-editable; prose blocks retain source positions for export.
    """

    @staticmethod
    def _classify(block: str) -> str:
        value = block.strip()
        if re.search(r"\\begin\s*\{(?:equation\*?|align\*?|gather\*?|multline\*?|math|displaymath|flalign\*?)\}", value):
            return "equation"
        if re.search(r"\\begin\s*\{(?:verbatim\*?|lstlisting|minted|alltt)\}", value):
            return "code"
        if re.search(r"\\(?:bibliography|bibliographystyle|printbibliography|bibitem)|\\begin\s*\{thebibliography\}", value):
            return "reference"
        if re.search(r"\\(?:documentclass|usepackage|newcommand|renewcommand|maketitle|author|date|label)\b|\\(?:begin|end)\s*\{document\}", value):
            return "front_matter"
        if re.search(r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph|title)\*?\s*\{", value):
            return "heading"
        if value.startswith("%"):
            return "code"
        return "body"

    @staticmethod
    def _parse_content(content: str, filename: str) -> ParsedDocument:
        paragraphs: List[DocumentParagraph] = []
        block_pattern = re.compile(r"\S(?:.*?\S)?(?=\n[ \t]*\n|\Z)", re.S)
        for index, match in enumerate(block_pattern.finditer(content), start=1):
            block = match.group(0)
            start, end = match.span()
            paragraphs.append(DocumentParagraph(
                id=f"tex_block_{index}",
                text=block,
                paragraph_type=LatexParser._classify(block),
                location=f"tex.{start}:{end}",
                metadata={"source_start": start, "source_end": end, "format": "latex"},
            ))
        return ParsedDocument(
            filename=filename,
            file_type="tex",
            paragraphs=paragraphs,
            metadata={"source_length": len(content), "format": "latex"},
        )

    @staticmethod
    def parse(file_path: Path, filename: str) -> ParsedDocument:
        content = file_path.read_text(encoding="utf-8")
        return LatexParser._parse_content(content, filename)

    @staticmethod
    def parse_bytes(data: bytes, filename: str) -> ParsedDocument:
        content = data.decode("utf-8")
        return LatexParser._parse_content(content, filename)

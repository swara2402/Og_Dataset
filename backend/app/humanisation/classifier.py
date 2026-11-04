"""Paragraph classifier for Turnitout.
Classifies paragraphs into categories to determine which should be humanised:
- Ordinary prose
- Academic writing
- Technical explanations
- Literature reviews
- Methodology
- Results and discussion
- References and bibliography
- Tables, equations and code
- Captions and headings
"""
from __future__ import annotations
import re
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass

from backend.app.document_processing.parser import DocumentParagraph


# Academic section classification patterns
SECTION_PATTERNS = {
    "abstract": [r"abstract"],
    "introduction": [r"introduction"],
    "conclusion": [r"conclusions?"],
    "acknowledgments": [r"acknowledg(?:e)?ments?"],
    "future_work": [r"future\\s+work"],
    "literature_review": [
        r"literature\s*review",
        r"previous\s*work",
        r"related\s*work",
        r"background",
        r"existing\s*research",
        r"prior\s*studies"
    ],
    "methodology": [
        r"methodology",
        r"methods?",
        r"materials\s*and\s*methods",
        r"experimental\s*setup",
        r"experimental\s*design",
        r"data\s*collection",
        r"study\s*design",
        r"research\s*design"
    ],
    "results": [
        r"results",
        r"findings",
        r"evaluation",
        r"experimental\s*results",
        r"performance\s*evaluation",
        r"empirical\s*results"
    ],
    "discussion": [
        r"discussion",
        r"analysis",
        r"(?:data|statistical|thematic|qualitative|quantitative)\s+analysis",
        r"results?\s+(?:and|&)\s+discussion",
        r"interpretation",
        r"implications"
    ],
    "references": [
        r"references",
        r"bibliography",
        r"works\s*cited",
        r"cited\s*literature"
    ]
}

# Compile patterns
COMPILED_SECTION_PATTERNS = {
    category: [re.compile(pattern, re.I) for pattern in patterns]
    for category, patterns in SECTION_PATTERNS.items()
}

# Technical terms that indicate a technical explanation section
TECHNICAL_TERMS = {
    "algorithm", "model", "architecture", "framework", "implementation",
    "computational", "theoretical", "analytical", "empirical", "experimental",
    "parameter", "hyperparameter", "vector", "matrix", "tensor", "neural",
    "network", "classifier", "regression", "clustering", "inference",
    "training", "validation", "testing", "dataset", "benchmark"
}

# Literary review indicators
LITERATURE_INDICATORS = {
    "authors", "researchers", "studies", "paper", "article", "demonstrated",
    "showed", "proposed", "found", "concluded", "argued", "reported",
    "according to", "previously", "recently", "in their work"
}


@dataclass
class ParagraphClassification:
    """Classification result for a paragraph."""
    paragraph_id: str
    primary_category: str
    confidence: float
    eligible_for_refinement: bool
    features: Dict[str, Any]
    section_context: Optional[str] = None


class ParagraphClassifier:
    """Advanced paragraph classifier that determines content type and refinement eligibility."""
    
    def __init__(self):
        self.current_section = None
        self.section_history: List[str] = []
    
    def _detect_section_heading(self, text: str) -> Optional[str]:
        """Detect a short standalone section heading, not a mention inside prose."""
        stripped = text.strip()
        if not stripped:
            return None
        if len(stripped) > 90 or len(stripped.split()) > 12:
            return None
        if stripped.endswith((".", "?", "!", ";", ",", ":")):
            return None
        normalized = re.sub(
            r"^\s*(?:(?:\d+(?:\.\d+)*)|(?:[IVX]+))[.)]?\s+", "", stripped, flags=re.I
        ).strip().rstrip(":").strip()
        for category, patterns in COMPILED_SECTION_PATTERNS.items():
            for pattern in patterns:
                if pattern.fullmatch(normalized):
                    return category
        return None
    
    def _is_technical_explanation(self, text: str) -> Tuple[bool, float]:
        """Determine if text is a technical explanation."""
        words = re.findall(r"\b[a-z][a-z0-9-]*\b", text.lower())
        normalized = set(words)
        normalized.update(
            word[:-1] for word in words if word.endswith("s") and len(word) > 3
        )
        matches = len(normalized & TECHNICAL_TERMS)
        total_words = len(words)

        if total_words == 0:
            return False, 0.0

        density = matches / total_words
        is_technical = density > 0.02 or matches >= 3
        confidence = min(1.0, density * 20)
        if is_technical:
            confidence = max(confidence, 0.55)

        return is_technical, confidence
        return is_technical, confidence
    
    def _is_literature_review_paragraph(self, text: str) -> Tuple[bool, float]:
        """Determine if text is part of a literature review."""
        text_lower = text.lower()
        words = re.findall(r"\b[a-z][a-z'-]*\b", text_lower)
        single_word_indicators = {
            item for item in LITERATURE_INDICATORS if " " not in item
        }
        phrase_indicators = {
            item for item in LITERATURE_INDICATORS if " " in item
        }
        matches = len(set(words) & single_word_indicators)
        matches += sum(
            1 for phrase in phrase_indicators
            if re.search(r"\b" + re.escape(phrase) + r"\b", text_lower)
        )
        total_words = len(words)

        if total_words == 0:
            return False, 0.0

        density = matches / total_words
        is_literature = density > 0.03 or matches >= 2
        confidence = min(1.0, density * 15)
        if is_literature:
            confidence = max(confidence, 0.55)

        # If we're already in a literature review section, boost confidence
        if self.current_section == "literature_review":
            confidence = min(1.0, confidence + 0.4)
            is_literature = True
        
        return is_literature, confidence
    
    def _is_methodology_paragraph(self, text: str) -> Tuple[bool, float]:
        """Determine if text is part of the methodology section."""
        if self.current_section == "methodology":
            return True, 0.9
        
        text_lower = text.lower()
        methodology_markers = {
            "we used", "we conducted", "we implemented", "we designed",
            "we collected", "procedure", "protocol"
        }
        matches = sum(
            1 for marker in methodology_markers
            if re.search(
                r"\b" + re.escape(marker).replace(r"\ ", r"\s+") + r"\b",
                text_lower,
            )
        )

        is_methodology = matches >= 1
        confidence = min(1.0, 0.5 + matches * 0.15) if is_methodology else 0.0
        
        return is_methodology, confidence
    
    def _is_results_discussion(self, text: str) -> Tuple[bool, float]:
        """Determine if text is part of results or discussion."""
        if self.current_section in ["results", "discussion"]:
            return True, 0.9
        
        text_lower = text.lower()
        rd_markers = {
            "figure", "table", "shows", "demonstrates", "indicates",
            "our results", "we found", "the results", "this suggests",
            "consistent with", "in agreement with"
        }
        matches = sum(
            1 for marker in rd_markers
            if re.search(
                r"\b" + re.escape(marker).replace(r"\ ", r"\s+") + r"\b",
                text_lower,
            )
        )

        is_rd = matches >= 2
        confidence = min(1.0, 0.5 + matches * 0.1) if is_rd else 0.0
        
        return is_rd, confidence
    
    def _is_ordinary_prose(self, text: str, technical_conf: float, lit_conf: float, 
                          method_conf: float, rd_conf: float) -> Tuple[bool, float]:
        """Classify as ordinary prose if not fitting other categories."""
        max_other = max(technical_conf, lit_conf, method_conf, rd_conf)
        is_ordinary = max_other < 0.5
        confidence = 1.0 - max_other
        return is_ordinary, confidence
    
    def _should_refine(self, category: str, paragraph_type: str) -> bool:
        """Determine if a paragraph is eligible for refinement."""
        protected = {
            "caption", "code", "empty", "equation", "front_matter", "heading",
            "reference", "references", "table",
        }
        return paragraph_type == "body" and category not in protected
    
    def classify(self, paragraph: DocumentParagraph) -> ParagraphClassification:
        """Classify a single paragraph, updating section context as needed."""
        text = paragraph.text.strip()
        if not text:
            return ParagraphClassification(
                paragraph_id=paragraph.id,
                primary_category="empty",
                confidence=1.0,
                eligible_for_refinement=False,
                features={},
                section_context=self.current_section
            )
        
        # Check if this is a section heading that changes our current context
        detected_section = self._detect_section_heading(text)
        if detected_section:
            self.current_section = detected_section
            self.section_history.append(detected_section)
            return ParagraphClassification(
                paragraph_id=paragraph.id,
                primary_category="heading",
                confidence=1.0,
                eligible_for_refinement=False,
                features={"detected_section": detected_section},
                section_context=None
            )
        
        # If paragraph is already marked as non-body, use that type
        if paragraph.paragraph_type != "body":
            return ParagraphClassification(
                paragraph_id=paragraph.id,
                primary_category=paragraph.paragraph_type,
                confidence=1.0,
                eligible_for_refinement=False,
                features={},
                section_context=self.current_section
            )
        
        # Run all classifiers
        is_technical, tech_conf = self._is_technical_explanation(text)
        is_literature, lit_conf = self._is_literature_review_paragraph(text)
        is_methodology, method_conf = self._is_methodology_paragraph(text)
        is_results_discussion, rd_conf = self._is_results_discussion(text)
        is_ordinary, ord_conf = self._is_ordinary_prose(text, tech_conf, lit_conf, method_conf, rd_conf)
        
        # Determine primary category
        # Only categories whose detector fired compete for the primary label.
        classifications = []
        if is_technical:
            classifications.append(("technical_explanation", tech_conf))
        if is_literature:
            classifications.append(("literature_review", lit_conf))
        if is_methodology:
            classifications.append(("methodology", method_conf))
        if is_results_discussion:
            classifications.append(("results_discussion", rd_conf))
        if not classifications:
            classifications.append(("ordinary_prose", ord_conf))

        classifications.sort(key=lambda item: item[1], reverse=True)
        primary_category, primary_confidence = classifications[0]

        # If we have an active section context, weight that heavily
        if self.current_section:
            section_mapping = {
                "abstract": "ordinary_prose",
                "introduction": "ordinary_prose",
                "conclusion": "ordinary_prose",
                "acknowledgments": "ordinary_prose",
                "future_work": "ordinary_prose",
                "literature_review": "literature_review",
                "methodology": "methodology",
                "results": "results_discussion",
                "discussion": "results_discussion",
                "references": "references"
            }
            if self.current_section in section_mapping:
                expected_category = section_mapping[self.current_section]
                # Boost confidence for the expected category
                if expected_category == primary_category:
                    primary_confidence = min(1.0, primary_confidence + 0.3)
                primary_category = expected_category
                primary_confidence = max(primary_confidence, 0.8)
        
        # Determine eligibility for refinement
        eligible = self._should_refine(primary_category, paragraph.paragraph_type)
        
        return ParagraphClassification(
            paragraph_id=paragraph.id,
            primary_category=primary_category,
            confidence=primary_confidence,
            eligible_for_refinement=eligible,
            features={
                "technical_confidence": tech_conf,
                "literature_confidence": lit_conf,
                "methodology_confidence": method_conf,
                "results_confidence": rd_conf,
                "ordinary_confidence": ord_conf
            },
            section_context=self.current_section
        )
    
    def classify_all(self, paragraphs: List[DocumentParagraph]) -> List[ParagraphClassification]:
        """Classify all paragraphs in sequence, maintaining section context."""
        classifications: List[ParagraphClassification] = []
        # Reset section context for each document
        self.current_section = None
        self.section_history = []
        
        for para in paragraphs:
            classification = self.classify(para)
            classifications.append(classification)
        
        return classifications
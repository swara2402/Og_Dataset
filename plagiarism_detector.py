#!/usr/bin/env python3
"""Turnitout Plagiarism and Source-Similarity Analysis Engine.
Implements genuine source matching, similarity highlighting, citation checking,
and originality reporting. Clearly distinguishes AI-generated writing from plagiarism."""

import re
import hashlib
import string
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import Counter
import math

# For text vectorization and similarity calculation
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Citation and reference patterns
CITATION_PATTERNS = {
    "apa": r"\(([A-Za-z\s]+,?\s+\d{4}[a-z]?)\)",
    "mla": r"[(\s]([A-Za-z]+\s+\d+)[)\s]",
    "chicago": r"\(([A-Za-z]+,\s+\d{4})\)",
    "numeric": r"\[(\d+(?:[,\s-]+\d+)*)\]"
}

@dataclass
class SourceMatch:
    """Represents a matched source from the reference library"""
    source_id: str
    source_title: str
    source_author: str
    source_year: str
    similarity_percentage: float
    matched_text: str
    start_index: int
    end_index: int
    match_type: str  # "direct_copy", "paraphrase", "citation_missing"
    citations_needed: bool = False

@dataclass
class CitationCheck:
    """Represents a citation check result"""
    text_segment: str
    found_in_references: bool
    citation_provided: bool
    issue_type: Optional[str] = None  # "missing_citation", "incorrect_citation", "unused_reference"
    suggestion: Optional[str] = None

@dataclass
class PlagiarismReport:
    """Comprehensive plagiarism and originality report"""
    overall_originality_score: float
    total_matched_text_percentage: float
    unique_content_percentage: float
    matched_sources_count: int
    source_matches: List[SourceMatch]
    citation_issues: List[CitationCheck]
    detailed_analysis: Dict[str, Any]
    warnings: List[str]

class LocalSourceLibrary:
    """Manages a local library of academic sources for similarity checking.
    All processing happens locally - no external API calls."""
    
    def __init__(self, library_path: Optional[str] = None):
        self.library_path = Path(library_path) if library_path else Path.home() / ".turnitout" / "source_library"
        self.library_path.mkdir(parents=True, exist_ok=True)
        self.sources: Dict[str, Dict[str, Any]] = {}
        self.vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1,3))
        self._load_local_sources()
    
    def _load_local_sources(self):
        """Load all locally stored sources from the library directory"""
        for source_file in self.library_path.glob("*.txt"):
            try:
                with open(source_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Parse source metadata from filename or header
                source_id = source_file.stem
                # Simple metadata extraction (would be more sophisticated in production)
                first_lines = content.split('\n')[:5]
                title = first_lines[0].strip() if first_lines else source_id
                author = first_lines[1].replace("Author:", "").strip() if len(first_lines) > 1 else "Unknown"
                year = first_lines[2].replace("Year:", "").strip() if len(first_lines) > 2 else "Unknown"
                
                self.sources[source_id] = {
                    "content": content,
                    "title": title,
                    "author": author,
                    "year": year,
                    "file_path": str(source_file)
                }
            except Exception as e:
                print(f"Warning: Could not load source {source_file}: {e}")
    
    def add_source(self, content: str, metadata: Dict[str, str]) -> str:
        """Add a new source to the local library"""
        source_id = hashlib.md5((content + metadata.get("title", "")).encode()).hexdigest()
        source_path = self.library_path / f"{source_id}.txt"
        
        # Write source with metadata header
        with open(source_path, 'w', encoding='utf-8') as f:
            f.write(f"{metadata.get('title', 'Untitled')}\n")
            f.write(f"Author: {metadata.get('author', 'Unknown')}\n")
            f.write(f"Year: {metadata.get('year', 'Unknown')}\n")
            f.write("\n" + content)
        
        self.sources[source_id] = {
            "content": content,
            "title": metadata.get("title", "Untitled"),
            "author": metadata.get("author", "Unknown"),
            "year": metadata.get("year", "Unknown"),
            "file_path": str(source_path)
        }
        return source_id

class PlagiarismDetector:
    """Core plagiarism and source-similarity detection engine.
    Implements genuine source matching while distinguishing from AI-generated text."""
    
    def __init__(self, source_library: Optional[LocalSourceLibrary] = None):
        self.source_library = source_library or LocalSourceLibrary()
        self.min_match_length = 50  # Minimum character length for a match
        self.similarity_threshold = 0.7  # TF-IDF cosine similarity threshold
    
    def _preprocess_text(self, text: str) -> str:
        """Clean and normalize text for comparison"""
        # Remove punctuation and extra whitespace
        text = text.lower()
        text = text.translate(str.maketrans('', '', string.punctuation))
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _check_citations(self, text: str, references_section: Optional[str] = None) -> List[CitationCheck]:
        """Check for proper citation usage - identify missing or incorrect citations"""
        citation_issues = []
        
        # Find all potential claim segments that should be cited
        sentences = re.split(r'[.!?]+', text)
        
        for sentence in sentences:
            if len(sentence.strip()) < 20:
                continue
                
            # Check if this sentence contains factual claims that likely need citation
            factual_indicators = [
                r'showed that', r'found that', r'demonstrated that',
                r'revealed that', r'proved that', r'indicated that'
            ]
            
            has_factual_indicator = any(re.search(pattern, sentence.lower()) for pattern in factual_indicators)
            has_citation = any(re.search(pattern, sentence) for pattern in CITATION_PATTERNS.values())
            
            if has_factual_indicator and not has_citation:
                citation_issues.append(CitationCheck(
                    text_segment=sentence.strip(),
                    found_in_references=False,
                    citation_provided=False,
                    issue_type="missing_citation",
                    suggestion="This factual claim requires a citation to the original source."
                ))
        
        # Check for unused references if references section is provided
        if references_section:
            # Extract all citation keys from references
            reference_citations = set()
            for pattern in CITATION_PATTERNS.values():
                refs = re.findall(pattern, references_section)
                reference_citations.update(refs)
            
            # Check which references are actually cited in the text
            cited_in_text = set()
            for pattern in CITATION_PATTERNS.values():
                citations = re.findall(pattern, text)
                cited_in_text.update(citations)
            
            # Find unused references
            unused = reference_citations - cited_in_text
            for ref in unused:
                citation_issues.append(CitationCheck(
                    text_segment=ref,
                    found_in_references=True,
                    citation_provided=False,
                    issue_type="unused_reference",
                    suggestion=f"Reference {ref} appears in your references but is not cited in the text."
                ))
        
        return citation_issues
    
    def analyze_document(self, text: str, references_section: Optional[str] = None) -> PlagiarismReport:
        """Perform comprehensive plagiarism and originality analysis on a document"""
        all_source_matches: List[SourceMatch] = []
        total_matched_chars = 0
        document_length = len(text)
        
        # Split document into chunks for comparison
        chunks = self._split_into_chunks(text, chunk_size=300, overlap=50)
        
        # Compare each chunk against all sources in the library
        for chunk in chunks:
            chunk_matches = self._compare_chunk_to_sources(chunk)
            for match in chunk_matches:
                # Calculate start/end indices in the original document
                start_idx = text.find(chunk['text'])
                if start_idx != -1:
                    match.start_index = start_idx
                    match.end_index = start_idx + len(chunk['text'])
                    all_source_matches.append(match)
                    total_matched_chars += match.end_index - match.start_idx
        
        # Remove duplicate matches
        unique_matches = self._deduplicate_matches(all_source_matches)
        
        # Calculate overall originality metrics
        total_matched_percent = (total_matched_chars / document_length) * 100 if document_length > 0 else 0
        unique_percent = 100 - total_matched_percent
        originality_score = max(0, 100 - total_matched_percent)
        
        # Check for citation issues
        citation_issues = self._check_citations(text, references_section)
        
        # Add important disclaimers to distinguish from AI detection
        warnings = [
            "This report analyzes similarity to known sources in your local library only.",
            "AI-generated writing is NOT flagged as plagiarism - only matches to existing human-written sources.",
            "This analysis cannot replace professional plagiarism screening for publication.",
            "Always verify matches manually to confirm they represent actual unattributed copying."
        ]
        
        return PlagiarismReport(
            overall_originality_score=round(originality_score, 1),
            total_matched_text_percentage=round(total_matched_percent, 1),
            unique_content_percentage=round(unique_percent, 1),
            matched_sources_count=len(unique_matches),
            source_matches=unique_matches,
            citation_issues=citation_issues,
            detailed_analysis={
                "total_characters_analyzed": document_length,
                "total_matched_characters": total_matched_chars,
                "number_of_chunks_compared": len(chunks),
                "sources_in_library": len(self.source_library.sources)
            },
            warnings=warnings
        )
    
    def _split_into_chunks(self, text: str, chunk_size: int = 300, overlap: int = 50) -> List[Dict[str, Any]]:
        """Split document into overlapping chunks for comparison"""
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = min(start + chunk_size, text_length)
            # Try to end at a sentence boundary if possible
            if end < text_length:
                # Look for sentence terminators within the last 50 characters
                for i in range(end, max(start, end - 50), -1):
                    if text[i] in '.!?':
                        end = i + 1
                        break
            
            chunk_text = text[start:end]
            chunks.append({
                "text": chunk_text,
                "start": start,
                "end": end
            })
            start += chunk_size - overlap
        
        return chunks
    
    def _compare_chunk_to_sources(self, chunk: Dict[str, Any]) -> List[SourceMatch]:
        """Compare a document chunk against all sources in the local library for similarity"""
        matches = []
        chunk_text = chunk['text']
        
        if len(chunk_text) < self.min_match_length:
            return matches
        
        # Compare with each source
        for source_id, source_data in self.source_library.sources.items():
            source_content = source_data['content']
            similarity = self._calculate_similarity(chunk_text, source_content)
            
            if similarity >= self.similarity_threshold:
                # Determine match type
                match_type = "direct_copy" if similarity > 0.9 else "paraphrase"
                
                matches.append(SourceMatch(
                    source_id=source_id,
                    source_title=source_data['title'],
                    source_author=source_data['author'],
                    source_year=source_data['year'],
                    similarity_percentage=round(similarity * 100, 1),
                    matched_text=chunk_text,
                    start_index=0,  # Will be set by caller
                    end_index=0,
                    match_type=match_type
                ))
        
        return matches
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate cosine similarity between two text segments using TF-IDF"""
        try:
            corpus = [self._preprocess_text(text1), self._preprocess_text(text2)]
            if len(corpus[0]) < 10 or len(corpus[1]) < 10:
                return 0.0
                
            tfidf_matrix = self.source_library.vectorizer.fit_transform(corpus)
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            return float(similarity)
        except Exception:
            return 0.0
    
    def _deduplicate_matches(self, matches: List[SourceMatch]) -> List[SourceMatch]:
        """Remove overlapping or duplicate source matches"""
        if not matches:
            return []
            
        # Sort by start index
        sorted_matches = sorted(matches, key=lambda x: x.start_index)
        unique_matches = [sorted_matches[0]]
        
        for current in sorted_matches[1:]:
            last = unique_matches[-1]
            # Check if current match significantly overlaps with the last one
            overlap = min(current.end_index, last.end_index) - max(current.start_index, last.start_index)
            min_length = min(current.end_index - current.start_index, last.end_index - last.start_index)
            
            if overlap / min_length < 0.5:  # Less than 50% overlap, keep it
                unique_matches.append(current)
            elif current.similarity_percentage > last.similarity_percentage:
                # Replace with better match if they overlap significantly
                unique_matches[-1] = current
        
        return unique_matches

if __name__ == "__main__":
    # Simple test
    detector = PlagiarismDetector()
    print("✅ Plagiarism detector initialized successfully")
    print(f"📚 Loaded {len(detector.source_library.sources)} sources from local library")
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.models.schemas import CurriculumAlignment, CurriculumStandardRef, DocumentProfile

logger = logging.getLogger("gyantra.curriculum")


@dataclass
class CurriculumStandard:
    code: str
    description: str
    subject: str
    grade: str
    board: str
    topic_keywords: list[str]


# Built-in mock database for demonstration
_BUILTIN_STANDARDS = [
    # CBSE Science Class 10
    CurriculumStandard("CBSE-SCI-10-1", "Chemical Reactions and Equations", "Science", "10", "CBSE", ["chemical", "reaction", "equation", "oxidation", "reduction"]),
    CurriculumStandard("CBSE-SCI-10-2", "Acids, Bases and Salts", "Science", "10", "CBSE", ["acid", "base", "salt", "ph"]),
    CurriculumStandard("CBSE-SCI-10-3", "Metals and Non-metals", "Science", "10", "CBSE", ["metal", "non-metal", "alloy", "ionic", "covalent"]),
    CurriculumStandard("CBSE-SCI-10-4", "Carbon and its Compounds", "Science", "10", "CBSE", ["carbon", "compound", "bond", "organic"]),
    CurriculumStandard("CBSE-SCI-10-5", "Life Processes", "Science", "10", "CBSE", ["life", "process", "nutrition", "respiration", "transportation", "excretion"]),
    CurriculumStandard("CBSE-SCI-10-6", "Control and Coordination", "Science", "10", "CBSE", ["control", "coordination", "nervous", "hormone"]),
    CurriculumStandard("CBSE-SCI-10-7", "How do Organisms Reproduce?", "Science", "10", "CBSE", ["reproduction", "organism", "asexual", "sexual"]),
    CurriculumStandard("CBSE-SCI-10-8", "Heredity and Evolution", "Science", "10", "CBSE", ["heredity", "evolution", "genetics", "trait"]),
    CurriculumStandard("CBSE-SCI-10-9", "Light - Reflection and Refraction", "Science", "10", "CBSE", ["light", "reflection", "refraction", "mirror", "lens"]),
    CurriculumStandard("CBSE-SCI-10-10", "The Human Eye and the Colourful World", "Science", "10", "CBSE", ["eye", "vision", "defect", "prism", "dispersion"]),
    CurriculumStandard("CBSE-SCI-10-11", "Electricity", "Science", "10", "CBSE", ["electricity", "current", "voltage", "resistance", "ohm", "power"]),
    CurriculumStandard("CBSE-SCI-10-12", "Magnetic Effects of Electric Current", "Science", "10", "CBSE", ["magnetic", "field", "current", "motor", "generator"]),
    CurriculumStandard("CBSE-SCI-10-13", "Our Environment", "Science", "10", "CBSE", ["environment", "ecosystem", "food chain", "ozone"]),
    
    # Common Core Math Grade 8
    CurriculumStandard("CCSS.MATH.CONTENT.8.EE.A.1", "Know and apply the properties of integer exponents", "Math", "8", "Common Core", ["exponent", "integer", "power", "base"]),
    CurriculumStandard("CCSS.MATH.CONTENT.8.EE.A.2", "Use square root and cube root symbols", "Math", "8", "Common Core", ["square root", "cube root", "radical"]),
    CurriculumStandard("CCSS.MATH.CONTENT.8.EE.B.5", "Graph proportional relationships, interpreting the unit rate as the slope of the graph", "Math", "8", "Common Core", ["graph", "proportional", "unit rate", "slope"]),
    CurriculumStandard("CCSS.MATH.CONTENT.8.F.A.1", "Understand that a function is a rule that assigns to each input exactly one output", "Math", "8", "Common Core", ["function", "input", "output", "rule"]),
]


def align_objectives(objectives: list[str], concepts: list[Any], profile: DocumentProfile) -> CurriculumAlignment | None:
    """Matches extracted objectives and concepts to curriculum standards."""
    board = profile.board
    subject = profile.subject
    grade = profile.grade
    
    # Filter standards by board and optionally subject/grade
    candidates = [
        s for s in _BUILTIN_STANDARDS 
        if s.board.lower() == board.lower()
    ]
    
    if not candidates:
        logger.info(f"No built-in curriculum standards found for board {board}")
        return CurriculumAlignment(
            board=board,
            standards_matched=[],
            coverage_pct=0.0,
            gaps=["No curriculum standards available for the selected board."],
            alignment_map={}
        )

    # Simple keyword matching algorithm
    # In a full production system, this would use semantic similarity or LLM verification
    all_text = " ".join(objectives).lower()
    for concept in concepts:
        all_text += f" {concept.name.lower()} {concept.description.lower()}"

    matched_standards = []
    alignment_map = {}
    gaps = []

    for std in candidates:
        # Check if std is relevant to the extracted content
        matches = sum(1 for kw in std.topic_keywords if kw.lower() in all_text)
        if matches > 0:
            confidence = min(0.95, 0.4 + (matches * 0.15))
            ref = CurriculumStandardRef(
                code=std.code,
                description=std.description,
                board=std.board,
                confidence=confidence
            )
            matched_standards.append(ref)
            
            # Map objectives to this standard if there's keyword overlap
            for obj in objectives:
                obj_lower = obj.lower()
                if any(kw.lower() in obj_lower for kw in std.topic_keywords):
                    if obj not in alignment_map:
                        alignment_map[obj] = []
                    alignment_map[obj].append(ref)
        
        # Check if the standard matches the document profile subject/grade but wasn't covered
        elif std.subject.lower() == subject.lower() and std.grade == str(grade):
            gaps.append(f"Missing coverage for {std.code}: {std.description}")

    # Calculate coverage
    relevant_candidates = [s for s in candidates if s.subject.lower() == subject.lower() and s.grade == str(grade)]
    coverage_pct = 0.0
    if relevant_candidates:
        coverage_pct = min(100.0, (len(matched_standards) / len(relevant_candidates)) * 100.0)
    elif matched_standards:
        coverage_pct = 100.0

    if not gaps and matched_standards:
        gaps.append("All identified standards for this topic are well covered.")
        
    if not matched_standards:
        gaps = ["Could not align content with any specific standards for this board."]

    return CurriculumAlignment(
        board=board,
        standards_matched=matched_standards,
        coverage_pct=coverage_pct,
        gaps=gaps,
        alignment_map=alignment_map
    )


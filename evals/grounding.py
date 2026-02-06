
"""Grounding and hallucination evaluation for itineraries.

Checks:
1. POIs map to dataset records (from search results)
2. Tips cite RAG sources
3. Uncertainty is explicitly stated when data is missing
"""
import re
import logging
from typing import Dict, List, Any, Optional, Set

logger = logging.getLogger("evals.grounding")


class GroundingEval:
    """Evaluates grounding and detects hallucinations."""

    # Patterns for uncertainty markers
    UNCERTAINTY_MARKERS = [
        r'\bmay\b',
        r'\bmight\b',
        r'\bcould\b',
        r'\bpossibly\b',
        r'\bperhaps\b',
        r'\buncertain\b',
        r'\bnot sure\b',
        r'\bno data\b',
        r'\bunavailable\b',
        r'\bcannot confirm\b',
        r'\blimited information\b',
    ]

    # Pattern for RAG source citations
    RAG_SOURCE_PATTERN = r'\[Source:\s*Wikivoyage[^\]]*\]'

    def __init__(self):
        self.results = []

    def extract_poi_names(self, itinerary_text: str) -> List[str]:
        """
        Extract POI/place names from itinerary.

        Args:
            itinerary_text: Raw itinerary markdown text

        Returns:
            List of potential POI names
        """
        poi_names = []
        lines = itinerary_text.split('\n')

        for line in lines:
            # Extract from activity descriptions
            # Pattern: * Morning/Afternoon/Evening: Visit/Explore [Place Name]
            activity_match = re.match(
                r'^\*\s*(?:Morning|Afternoon|Evening)[^:]*:\s*(.+)',
                line,
                re.IGNORECASE
            )

            if activity_match:
                description = activity_match.group(1)

                # Try to extract place names (capitalized words/phrases)
                # Look for patterns like "Visit X", "Explore Y", "Tour Z"
                place_patterns = [
                    r'(?:visit|explore|tour|see|discover)\s+(?:the\s+)?([A-Z][a-zA-Z\s]+?)(?:\s+(?:museum|temple|palace|fort|park|market|restaurant|cafe|gallery|monument|building|church|mosque|square|garden))',
                    r'\bat\s+(?:the\s+)?([A-Z][a-zA-Z\s]+?)(?:\s+(?:museum|temple|palace|fort|park|market|restaurant|cafe|gallery|monument|building|church|mosque|square|garden))',
                    r'\bin\s+(?:the\s+)?([A-Z][a-zA-Z\s]+?)(?:\s+(?:area|district|neighborhood|quarter))',
                ]

                for pattern in place_patterns:
                    matches = re.findall(pattern, description, re.IGNORECASE)
                    for match in matches:
                        cleaned = match.strip()
                        if cleaned and len(cleaned) > 2:
                            poi_names.append(cleaned)

                # Also extract any quoted names or capitalized phrases
                quoted_matches = re.findall(r'"([^"]+)"', description)
                poi_names.extend(quoted_matches)

        return poi_names

    def check_poi_grounding(
        self,
        itinerary_text: str,
        search_results: Optional[Dict[str, List[Dict[str, Any]]]] = None
    ) -> Dict[str, Any]:
        """
        Check if POIs in itinerary are grounded in search results.

        Args:
            itinerary_text: Raw itinerary markdown text
            search_results: Dict mapping category to list of POI search results

        Returns:
            Evaluation result
        """
        itinerary_pois = self.extract_poi_names(itinerary_text)
        issues = []
        grounded_pois = []
        ungrounded_pois = []

        if not search_results:
            issues.append(
                "No search results provided. "
                "Cannot verify POI grounding."
            )
            return {
                "check": "poi_grounding",
                "passed": False,
                "itinerary_pois": itinerary_pois,
                "grounded_count": 0,
                "ungrounded_count": len(itinerary_pois),
                "issues": issues,
            }

        # Build set of all POI names from search results
        search_poi_names = set()
        for category, results in search_results.items():
            for result in results:
                if isinstance(result, dict):
                    name = result.get("name", "")
                    if name:
                        search_poi_names.add(name.lower())

        # Check each itinerary POI against search results
        for poi in itinerary_pois:
            poi_lower = poi.lower()

            # Exact match or partial match
            is_grounded = any(
                poi_lower in search_name or search_name in poi_lower
                for search_name in search_poi_names
            )

            if is_grounded:
                grounded_pois.append(poi)
            else:
                ungrounded_pois.append(poi)
                issues.append(
                    f"POI '{poi}' not found in search results. "
                    "May be hallucinated or from general knowledge."
                )

        # Calculate grounding percentage
        total_pois = len(itinerary_pois)
        grounded_count = len(grounded_pois)

        grounding_percentage = (
            (grounded_count / total_pois * 100) if total_pois > 0 else 100
        )

        # Pass if at least 70% of POIs are grounded
        passed = grounding_percentage >= 70

        return {
            "check": "poi_grounding",
            "passed": passed,
            "itinerary_pois": itinerary_pois,
            "grounded_pois": grounded_pois,
            "ungrounded_pois": ungrounded_pois,
            "grounded_count": grounded_count,
            "ungrounded_count": len(ungrounded_pois),
            "grounding_percentage": grounding_percentage,
            "issues": issues,
        }

    def check_tip_citations(self, itinerary_text: str) -> Dict[str, Any]:
        """
        Check if travel tips cite RAG sources.

        Args:
            itinerary_text: Raw itinerary markdown text

        Returns:
            Evaluation result
        """
        issues = []

        # Extract travel tips section
        tips_section = self._extract_tips_section(itinerary_text)

        if not tips_section:
            issues.append(
                "No 'Travel Tips' section found in itinerary."
            )
            return {
                "check": "tip_citations",
                "passed": False,
                "has_tips_section": False,
                "tips_with_citations": 0,
                "total_tips": 0,
                "issues": issues,
            }

        # Count tips (assume each bullet point is a tip)
        tip_lines = [
            line for line in tips_section.split('\n')
            if line.strip().startswith('*') or line.strip().startswith('-')
        ]
        total_tips = len(tip_lines)

        # Count citations
        citations = re.findall(self.RAG_SOURCE_PATTERN, tips_section)
        tips_with_citations = len(citations)

        # Check if tips have sources cited
        if total_tips > 0 and tips_with_citations == 0:
            issues.append(
                f"Found {total_tips} travel tips but no RAG source citations. "
                "Tips should cite sources like [Source: Wikivoyage - City - Section]."
            )

        # Pass if at least 50% of tips have citations
        citation_percentage = (
            (tips_with_citations / total_tips * 100) if total_tips > 0 else 0
        )
        passed = citation_percentage >= 50 or total_tips == 0

        return {
            "check": "tip_citations",
            "passed": passed,
            "has_tips_section": True,
            "total_tips": total_tips,
            "tips_with_citations": tips_with_citations,
            "citation_percentage": citation_percentage,
            "citations_found": citations,
            "issues": issues,
        }

    def check_uncertainty_markers(self, itinerary_text: str) -> Dict[str, Any]:
        """
        Check if uncertainty is explicitly stated when appropriate.

        Args:
            itinerary_text: Raw itinerary markdown text

        Returns:
            Evaluation result
        """
        issues = []
        uncertainty_instances = []

        # Search for uncertainty markers
        for pattern in self.UNCERTAINTY_MARKERS:
            matches = re.finditer(pattern, itinerary_text, re.IGNORECASE)
            for match in matches:
                # Get context around the match
                start = max(0, match.start() - 50)
                end = min(len(itinerary_text), match.end() + 50)
                context = itinerary_text[start:end]

                uncertainty_instances.append({
                    "marker": match.group(),
                    "context": context.strip()
                })

        # Check for specific scenarios where uncertainty should be stated
        has_weather = "weather" in itinerary_text.lower()
        has_weather_uncertainty = any(
            "weather" in inst["context"].lower()
            for inst in uncertainty_instances
        )

        if has_weather and not has_weather_uncertainty:
            issues.append(
                "Weather mentioned but no uncertainty markers. "
                "Weather predictions should include uncertainty."
            )

        # Check if search failed but no uncertainty stated
        if "could not" in itinerary_text.lower() or "no results" in itinerary_text.lower():
            has_explicit_uncertainty = len(uncertainty_instances) > 0
            if not has_explicit_uncertainty:
                issues.append(
                    "Search failures detected but no explicit uncertainty markers found."
                )

        # Evaluation passes if there are no issues
        passed = len(issues) == 0

        return {
            "check": "uncertainty_markers",
            "passed": passed,
            "uncertainty_instances": uncertainty_instances,
            "total_uncertainty_markers": len(uncertainty_instances),
            "issues": issues,
        }

    def evaluate(
        self,
        itinerary_text: str,
        search_results: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """
        Run all grounding and hallucination checks.

        Args:
            itinerary_text: Raw itinerary markdown text
            search_results: Optional POI search results for validation

        Returns:
            Complete evaluation results
        """
        logger.info("Running Grounding & Hallucination Evaluation...")

        results = []

        # Check 1: POI grounding
        poi_result = self.check_poi_grounding(itinerary_text, search_results)
        results.append(poi_result)

        # Check 2: Tip citations
        citation_result = self.check_tip_citations(itinerary_text)
        results.append(citation_result)

        # Check 3: Uncertainty markers
        uncertainty_result = self.check_uncertainty_markers(itinerary_text)
        results.append(uncertainty_result)

        # Overall pass/fail
        all_passed = all(r["passed"] for r in results)

        # Summary
        summary = {
            "total_checks": len(results),
            "passed_checks": sum(1 for r in results if r["passed"]),
            "failed_checks": sum(1 for r in results if not r["passed"]),
        }

        return {
            "eval_type": "grounding",
            "passed": all_passed,
            "summary": summary,
            "results": results,
        }

    def _extract_tips_section(self, itinerary_text: str) -> Optional[str]:
        """
        Extract the Travel Tips section from itinerary.

        Args:
            itinerary_text: Itinerary text

        Returns:
            Tips section content or None
        """
        # Look for "Travel Tips" or "Tips" section
        pattern = r'\*\*Travel Tips:?\*\*\s*\n((?:.*\n)*?)(?:\n#|\Z)'
        match = re.search(pattern, itinerary_text, re.IGNORECASE)

        if match:
            return match.group(1).strip()

        return None

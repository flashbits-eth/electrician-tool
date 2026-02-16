"""
Fuzzy matching system to map part descriptions to labor unit database entries.
Handles variations like 3/4" vs 3/4 vs .75, emt vs EMT, etc.
"""

import csv
import re
import logging
from thefuzz import fuzz
from pathlib import Path

logger = logging.getLogger(__name__)

# Size normalization map
SIZE_ALIASES = {
    '.5': '1/2',
    '0.5': '1/2',
    '.75': '3/4',
    '0.75': '3/4',
    '1.25': '1 1/4',
    '1.5': '1 1/2',
    '2.5': '2 1/2',
    '3.5': '3 1/2',
}

# Common part type aliases for matching
TYPE_ALIASES = {
    'emt': ['EMT CONDUIT', 'EMT'],
    'rigid': ['RIGID STEEL CONDUIT', 'RIGID CONDUIT'],
    'pvc': ['PVC CONDUIT'],
    'mc': ['MC CABLE'],
    'romex': ['NON-METALLIC SHEATHED CABLE', 'NM CABLE'],
    'thhn': ['WIRE'],
    'awg': ['WIRE'],
    'coupling': ['COUPLINGS', 'COUPLING'],
    'connector': ['CONNECTORS', 'CONNECTOR'],
    'box': ['SQUARE BOXES', 'OCTAGON BOXES', 'SWITCH BOXES', 'PLASTIC BOXES'],
    'breaker': ['PLUG-IN CIRCUIT BREAKERS', 'BOLT-ON BREAKERS'],
    'strut': ['SUPPORT CHANNEL (STRUT)', 'SUPPORT CHANNEL'],
    'beam clamp': ['BEAM CLAMP'],
    'wire nut': ['WIRENUTS'],
    'fan': ['FANS'],
    'switch': ['SWITCHES'],
    'receptacle': ['RECEPTACLES'],
}


def normalize_description(desc: str) -> str:
    """Normalize a part description for matching."""
    desc = desc.lower().strip()
    # Remove quotes and extra whitespace
    desc = desc.replace('"', ' inch ').replace("'", ' ')
    desc = re.sub(r'\s+', ' ', desc).strip()
    # Normalize sizes
    for alias, normalized in SIZE_ALIASES.items():
        desc = re.sub(r'\b' + re.escape(alias) + r'\b', normalized, desc)
    return desc


def extract_size(desc: str) -> str:
    """Extract pipe/conduit size from description."""
    # Match patterns like 3/4, 1/2, 1 1/4, #10, etc.
    size_match = re.search(r'(\d+\s+\d+/\d+|\d+/\d+|\d+)', desc)
    if size_match:
        return size_match.group(1).strip()
    return ""


def extract_size_from_item(item: str) -> str:
    """Extract size from a labor DB item field like '3/4\"' or '1 1/2\"'."""
    item = item.replace('"', '').replace("''", '').strip()
    size_match = re.match(r'^(\d+\s+\d+/\d+|\d+/\d+)\s*$', item)
    if size_match:
        return size_match.group(1)
    return ""


class LaborMatcher:
    def __init__(self, db_path: str = "data/labor_units_db.csv"):
        self.entries = []
        self.load_db(db_path)

    def load_db(self, db_path: str):
        with open(db_path, encoding='utf-8') as f:
            self.entries = list(csv.DictReader(f))
        logger.info(f"Loaded {len(self.entries)} labor unit entries")

    def search(self, query: str, top_n: int = 5) -> list:
        """
        Search for matching labor entries given a part description.
        Returns list of (entry, score, match_reason) tuples.
        """
        query_norm = normalize_description(query)
        query_size = extract_size(query_norm)
        results = []

        # First try keyword-based matching
        keywords = self._extract_keywords(query_norm)

        for entry in self.entries:
            score = 0
            reasons = []

            section_lower = entry['Section'].lower()
            category_lower = entry['Category'].lower()
            item_lower = entry['Item'].lower().replace('"', '')

            # Build a combined text for fuzzy matching
            combined = f"{section_lower} {category_lower} {item_lower}"

            # Check type aliases
            for alias, targets in TYPE_ALIASES.items():
                if alias in query_norm:
                    for target in targets:
                        if target.lower() in combined:
                            score += 40
                            reasons.append(f"type_match:{alias}")
                            break

            # Penalize entries where the section/category is about a
            # DIFFERENT conduit type than what was queried
            conduit_types = ['emt', 'rigid', 'pvc', 'imc', 'ent', 'mc']
            query_conduit = None
            for ct in conduit_types:
                if ct in query_norm.split():
                    query_conduit = ct
                    break
            if query_conduit:
                # If query is for EMT, penalize entries in ENT/RIGID/PVC sections
                for ct in conduit_types:
                    if ct != query_conduit and ct in section_lower.split():
                        score -= 25
                        reasons.append(f"wrong_type_penalty:{ct}")

            # Size matching
            if query_size:
                entry_size = extract_size_from_item(entry['Item'])
                if not entry_size:
                    entry_size = extract_size(item_lower)
                if entry_size == query_size:
                    score += 30
                    reasons.append(f"size_match:{query_size}")

            # Keyword matching
            for kw in keywords:
                if kw in combined:
                    score += 15
                    reasons.append(f"keyword:{kw}")

            # Fuzzy match on combined text
            fuzzy_score = fuzz.token_set_ratio(query_norm, combined)
            score += fuzzy_score * 0.3
            if fuzzy_score > 60:
                reasons.append(f"fuzzy:{fuzzy_score}")

            if score > 20:
                results.append((entry, round(score, 1), ', '.join(reasons)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]

    def best_match(self, query: str) -> tuple:
        """Return the single best match with confidence score (0-100)."""
        results = self.search(query, top_n=1)
        if not results:
            return None, 0, "No match found"
        entry, raw_score, reason = results[0]
        # Normalize score to 0-100
        confidence = min(100, raw_score)
        return entry, confidence, reason

    def _extract_keywords(self, desc: str) -> list:
        """Extract meaningful keywords from a description."""
        # Remove common filler words
        stop_words = {'with', 'and', 'for', 'the', 'a', 'an', 'or', 'in', 'on',
                      'to', 'of', 'inch', 'feet', 'ft', 'ea', 'each', 'per'}
        words = desc.split()
        return [w for w in words if w not in stop_words and len(w) > 1]


if __name__ == '__main__':
    matcher = LaborMatcher()
    test_queries = [
        '3/4 emt',
        '3/4" couplings',
        '3/4" connectors',
        'beam clamps with 3/4 strap',
        'beam clamp with 1/4 hole',
        '#10 awg wire',
        '4 square box',
        'breaker square D 20a breaker',
        'strut',
        'fans',
    ]
    for q in test_queries:
        entry, confidence, reason = matcher.best_match(q)
        if entry:
            print(f"\nQuery: '{q}'")
            print(f"  Match: {entry['Section']} > {entry['Category']} > {entry['Item']}")
            print(f"  Avg Labor: {entry['Average']} per {entry['Unit']}")
            print(f"  Confidence: {confidence}  Reason: {reason}")
        else:
            print(f"\nQuery: '{q}' -> NO MATCH")

from __future__ import annotations
import re

"""
Rails inflection helpers for singularization and table → model conversions.

Implements Rails ActiveSupport::Inflector rules for accurate pluralization
and singularization, ensuring compatibility with Rails naming conventions.
"""

# Uncountable words (no plural/singular distinction)
UNCOUNTABLE_NOUNS = {
    "equipment", "information", "rice", "money", "species",
    "series", "fish", "sheep", "jeans", "police", "metadata",
    "data", "news"  # data and news can be both singular and plural
}

# Irregular mappings (plural -> singular)
IRREGULARS = {
    "people": "person",
    "men": "man",
    "children": "child",
    "sexes": "sex",
    "moves": "move",
    "zombies": "zombie",
}

# Singularization rules (pattern, replacement) - order matters!
SINGULARIZATION_RULES = [
    # Special database case
    (r"(database)s$", r"\1"),
    # quiz -> quiz
    (r"(quiz)zes$", r"\1"),
    # matrix -> matrices, index -> indices
    (r"(matr)ices$", r"\1ix"),
    (r"(vert|ind)ices$", r"\1ex"),
    # ox -> oxen
    (r"^(ox)en", r"\1"),
    # alias, status
    (r"(alias|status)(es)?$", r"\1"),
    # octopus/virus - handle both -i and -us forms
    (r"(octop|vir)i$", r"\1us"),
    # Don't singularize words ending in -us (they're already singular)
    (r"(octop|vir|cact|radi|fung|alumn|stimul|syllab)us$", r"\1us"),
    # axis/axes, crisis/crises, testis/testes - only plurals
    (r"^(a)xes$", r"\1xis"),
    (r"(cris|test)es$", r"\1is"),
    # Don't singularize words ending in -is (they're already singular)
    (r"(analys|bas|diagnos|ellips|hypothes|oas|paralys|parenthes|synops|thes|cris|test)is$", r"\1is"),
    # shoe -> shoes
    (r"(shoe)s$", r"\1"),
    # o -> oes
    (r"(o)es$", r"\1"),
    # bus -> buses
    (r"(bus)(es)?$", r"\1"),
    # mouse -> mice
    (r"^(m|l)ice$", r"\1ouse"),
    # x/ch/ss/sh + es
    (r"(x|ch|ss|sh)es$", r"\1"),
    # movie -> movies
    (r"(m)ovies$", r"\1ovie"),
    # series
    (r"(s)eries$", r"\1eries"),
    # consonant + y -> ies
    (r"([^aeiouy]|qu)ies$", r"\1y"),
    # lf/rf -> lves/rves
    (r"([lr])ves$", r"\1f"),
    # tive -> tives
    (r"(tive)s$", r"\1"),
    # hive -> hives
    (r"(hive)s$", r"\1"),
    # fe -> ves (knife -> knives)
    (r"([^f])ves$", r"\1fe"),
    # analysis, basis, diagnosis, etc. - ONLY match plural forms (ending in -ses)
    (r"(^analy)ses$", r"\1sis"),
    (r"((a)naly|(b)a|(d)iagno|(p)arenthe|(p)rogno|(s)ynop|(t)he)ses$", r"\1sis"),
    # on -> a (phenomenon -> phenomena)
    (r"(phenomen)a$", r"\1on"),
    # news (special case - already singular)
    (r"^news$", r"news"),
    # ta -> tum (datum/data) - but not metadata
    (r"^([^m].*[ti])a$", r"\1um"),
    (r"^(d)ata$", r"\1atum"),
    # ss -> ss (no change)
    (r"(ss)$", r"\1"),
    # s -> '' (default plural removal)
    (r"s$", r""),
]


def singularize(word: str) -> str:
    """Convert a plural word to singular form using Rails inflection rules.

    Implements the same logic as ActiveSupport::Inflector.singularize
    """
    if not word:
        return word

    lower_word = word.lower()

    # Check uncountable nouns first (before any processing)
    # Split on underscores and check the last word
    parts = lower_word.split("_")
    if parts[-1] in UNCOUNTABLE_NOUNS:
        return word

    # Check irregulars
    if lower_word in IRREGULARS:
        return IRREGULARS[lower_word]

    # Apply singularization rules in order
    for pattern, replacement in SINGULARIZATION_RULES:
        # Check if the pattern matches
        if re.search(pattern, lower_word, flags=re.IGNORECASE):
            result = re.sub(pattern, replacement, lower_word, flags=re.IGNORECASE)
            return result

    # No rule matched, return as-is
    return word


def table_to_model(table: str) -> str:
    """Convert a SQL table name to a Rails model name (CamelCase singular).

    Uses Rails ActiveSupport inflection rules for accurate singularization.
    Handles schema prefixes (e.g., "public.users" → "User").

    Examples:
        users -> User
        people -> Person
        analyses -> Analysis
        equipment -> Equipment (uncountable)
    """
    if not table:
        return ""

    # Remove any schema prefix and normalize
    base = table.split(".")[-1].lower()

    # Singularize using Rails rules
    singular = singularize(base)

    # Convert to CamelCase
    return "".join(part.capitalize() for part in singular.split("_"))


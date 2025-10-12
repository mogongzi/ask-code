from __future__ import annotations

"""
Rails naming helpers used by tools for table → model conversions.
"""

def table_to_model(table: str) -> str:
    """Convert a SQL table name to a Rails model name (CamelCase singular).

    Handles common pluralization patterns conservatively and strips any schema
    prefix (e.g., "public.users" → "User").
    """
    if not table:
        return ""

    # Remove any schema prefix and normalize
    base = table.split(".")[-1].lower()

    # Conservative plural → singular handling
    if base.endswith("ies"):
        singular = base[:-3] + "y"
    elif (
        base.endswith("sses")
        or base.endswith("xes")
        or base.endswith("zes")
        or base.endswith("ches")
        or base.endswith("shes")
    ):
        singular = base[:-2]
    elif base.endswith("s"):
        singular = base[:-1]
    else:
        singular = base

    # Convert to CamelCase
    return "".join(part.capitalize() for part in singular.split("_"))


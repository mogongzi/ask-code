"""URL manipulation utilities."""

from urllib.parse import urlparse, urlunparse


def to_mock_url(u: str) -> str:
    """Rewrite a base URL to its /mock sibling.

    Examples:
      http://host:8000/invoke -> http://host:8000/mock
      http://host:8000 -> http://host:8000/mock
      http://host:8000/anything -> http://host:8000/anything/mock
    """
    p = urlparse(u)
    path = p.path or "/"
    # Handle existing /mock endpoints
    if path.endswith("/mock"):
        new_path = path
    # Replace /invoke with /mock
    elif path.endswith("/invoke"):
        new_path = path[: -len("/invoke")] + "/mock"
    # Append /mock to any other path
    else:
        new_path = path + ("mock" if path.endswith("/") else "/mock")
    return urlunparse(p._replace(path=new_path, query=""))
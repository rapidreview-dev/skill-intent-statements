"""Text helpers for the blog."""


def slugify(title):
    """Turn a post's title into the part of its URL that names it."""
    out = []
    dash = False
    for ch in title.strip().lower():
        if ch.isalnum() or ch == "_":
            if dash and out:
                out.append("-")
            out.append(ch)
            dash = False
        else:
            dash = True
    return "".join(out)

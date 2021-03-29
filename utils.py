def get_indent(text: str) -> int:
    return len(text) - len(text.lstrip())


def remove_indent(text: str) -> str:
    indent = get_indent(text)
    return "\n".join(line[indent:] for line in text.split("\n"))

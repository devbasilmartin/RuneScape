"""Turn a color given on the command line (registry name or r,g,b) into RGB."""
from .colors import Registry


def resolve_color(cfg, text: str):
    if "," in text:
        return tuple(int(v) for v in text.split(","))
    return Registry.load(cfg.colors_file).resolve(text)

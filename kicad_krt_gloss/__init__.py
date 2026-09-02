"""KiCad KRT Gloss standalone ActionPlugin package."""

try:
    import pcbnew
except ImportError:
    pcbnew = None

if pcbnew is not None:
    from .action_plugin import KiCadKrtGlossPlugin

    KiCadKrtGlossPlugin().register()

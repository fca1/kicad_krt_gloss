"""KiCad KRT Gloss standalone ActionPlugin package."""

try:
    import pcbnew
except ImportError:
    pcbnew = None

if pcbnew is not None:
    from .action_plugin import KiCadKrtGlossPlugin
    from . import action_plugin as _action
    from .branch_selection_prototype import activate as _activate_eb

    _restore_eb = _activate_eb(_action)

    KiCadKrtGlossPlugin().register()

"""Install KRT's rule channels consistently for both Gloss entry points."""

from dgloss.krt_api import install_layer_clearances, install_track_clearances


def install_gloss_rules(config, pcb_data, net_ids, *, source_path=None,
                        rules=None):
    """Keep KRT's legacy geometry channels and its resolver on the same board.

    The layer installer also attaches the file-backed DesignRules table.
    For the GUI, replace that table with live settings, retaining its fab
    floors. Never let loading the legacy channels overwrite the live table.
    """
    path = source_path or getattr(pcb_data, "source_path", "") or ""
    install_layer_clearances(config, None, path, pcb_data)
    install_track_clearances(config, None, path, pcb_data,
                             routed_net_ids=net_ids)
    if rules is not None:
        rules.fab_floor = dict(getattr(config.rules, "fab_floor", None) or {})
        config.rules = rules
    return config.rules

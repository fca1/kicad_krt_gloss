"""Compare DRC evidence without running KiCad or accepting weaker reports."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'ipc_drc_comparison', Path(__file__).resolve().parents[1] / 'tools/check_ipc_drc.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
compare = MODULE.compare_reports


def report():
    return {'source': 'board.kicad_pcb', 'date': '2026-10-21T12:00:00',
            'kicad_version': '10.99.0', 'coordinate_units': 'mm',
            'included_severities': ['error', 'warning', 'exclusion'], 'ignored_checks': [],
            'violations': [], 'unconnected_items': [], 'schematic_parity': []}


def finding(kind='clearance'):
    return {'type': kind, 'severity': 'error', 'description': 'clearance below minimum',
            'items': [{'uuid': 'old-track', 'description': 'Track [A] on F.Cu',
                       'pos': {'x': 10.0, 'y': 20.0}},
                      {'uuid': 'fixed-pad', 'description': 'Pad 1 [B] of J1',
                       'pos': {'x': 10.1, 'y': 20.1}}]}


def test_clean_reports_and_unchanged_defects_are_distinct():
    before = report()
    assert compare(before, deepcopy(before))['after_has_no_reported_findings']
    before['violations'] = [finding()]
    result = compare(before, deepcopy(before))
    assert result['status'] == 'no_new_reported_findings'
    assert not result['after_has_no_reported_findings']


def test_replaced_track_uuid_and_item_order_do_not_invent_new_defect():
    before = report(); before['violations'] = [finding()]
    after = deepcopy(before)
    after['violations'][0]['items'][0]['uuid'] = 'new-track'
    after['violations'][0]['items'].reverse()
    assert compare(before, after)['added_count'] == 0


@pytest.mark.parametrize('change', ['position', 'net', 'type', 'description', 'severity', 'excluded'])
def test_equal_counts_never_mask_changed_contact(change):
    before = report(); before['violations'] = [finding()]
    after = deepcopy(before); value = after['violations'][0]
    if change == 'position':
        value['items'][0]['pos']['x'] += .01
    elif change == 'net':
        value['items'][0]['description'] = 'Track [C] on F.Cu'
    else:
        value[change] = {'type': 'shorting_items', 'description': 'different distance',
                         'severity': 'warning', 'excluded': True}[change]
    result = compare(before, after)
    assert result['added_count'] == result['removed_count'] == 1


def test_multiplicity_and_connectivity_findings_remain_visible():
    before = report(); before['violations'] = [finding()]
    after = deepcopy(before)
    after['violations'].append(finding())
    after['unconnected_items'].append(finding('unconnected_items'))
    result = compare(before, after)
    assert result['added_count'] == 2
    assert result['added']['violations'][0]['count'] == 1
    assert result['added']['unconnected_items'][0]['finding']['type'] == 'unconnected_items'


@pytest.mark.parametrize('field,value', [
    ('included_severities', ['error']), ('coordinate_units', 'in'),
    ('kicad_version', '10.0.0'),
    ('ignored_checks', [{'key': 'clearance', 'description': 'ignored clearance'}]),
])
def test_changed_coverage_is_refused(field, value):
    before = report(); after = deepcopy(before); after[field] = value
    with pytest.raises(ValueError, match=field):
        compare(before, after)


@pytest.mark.parametrize('field', ['violations', 'unconnected_items', 'schematic_parity',
                                 'included_severities', 'ignored_checks'])
def test_incomplete_reports_are_not_clean(field):
    before = report(); after = deepcopy(before); del after[field]
    with pytest.raises(ValueError):
        compare(before, after)

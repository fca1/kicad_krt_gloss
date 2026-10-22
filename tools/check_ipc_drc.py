"""Compare two KiCad CLI DRC JSON reports; never access or modify a board.

Generate both reports with the same KiCad build, project/rules and CLI options,
preferably --format json --units mm --severity-all --all-track-errors.
The report records only the major/minor/patch version, not the build commit.
Inspect the saved post-IPC state WITHOUT --refill-zones first: refilling in the
CLI could conceal a missing refill in the editor.

Matching ignores item UUIDs because Gloss replaces tracks. Everything else in
a finding is retained, including positions, descriptions, severity, exclusion
and multiplicity. Changed findings are reported conservatively as removed and
added; additions need review and do not alone prove a new physical defect.

Exit 0: no added/changed reported findings (not necessarily a clean DRC).
Exit 1: added/changed findings. Exit 2: invalid or incomparable reports.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys


SECTIONS = ('violations', 'unconnected_items', 'schematic_parity')
SEVERITIES = {'error', 'warning', 'exclusion'}


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _validate(report, label):
    if not isinstance(report, dict):
        raise ValueError(f'{label}: expected a KiCad DRC report object')
    for key in ('source', 'date', 'kicad_version', 'coordinate_units'):
        if not isinstance(report.get(key), str) or not report[key]:
            raise ValueError(f'{label}: missing or invalid {key}')
    if report['coordinate_units'] not in {'mm', 'in', 'mils'}:
        raise ValueError(f'{label}: unsupported coordinate units')
    severities = report.get('included_severities')
    if (not isinstance(severities, list) or not severities or
            any(not isinstance(s, str) or s not in SEVERITIES for s in severities)):
        raise ValueError(f'{label}: included_severities must declare the report filters')
    ignored = report.get('ignored_checks')
    if not isinstance(ignored, list) or any(
            not isinstance(check, dict) or not isinstance(check.get('key'), str) or
            not isinstance(check.get('description'), str) for check in ignored):
        raise ValueError(f'{label}: missing or invalid ignored_checks')
    for section in SECTIONS:
        if not isinstance(report.get(section), list):
            raise ValueError(f'{label}: missing or invalid {section}')
        for finding in report[section]:
            if not isinstance(finding, dict) or any(
                    not isinstance(finding.get(key), str)
                    for key in ('type', 'description', 'severity')):
                raise ValueError(f'{label}: malformed finding in {section}')
            if finding['severity'] not in {'error', 'warning'}:
                raise ValueError(f'{label}: unknown finding severity')
            if not isinstance(finding.get('excluded', False), bool):
                raise ValueError(f'{label}: invalid excluded flag')
            if not isinstance(finding.get('items'), list):
                raise ValueError(f'{label}: missing affected items')
            for item in finding['items']:
                if (not isinstance(item, dict) or
                        not isinstance(item.get('description'), str) or
                        not isinstance(item.get('pos'), dict)):
                    raise ValueError(f'{label}: malformed affected item')
                for axis in ('x', 'y'):
                    coordinate = item['pos'].get(axis)
                    if (isinstance(coordinate, bool) or
                            not isinstance(coordinate, (int, float)) or
                            not math.isfinite(coordinate)):
                        raise ValueError(f'{label}: invalid affected-item position')


def _finding_key(finding):
    normalized = dict(finding)
    normalized['excluded'] = finding.get('excluded', False)
    normalized['items'] = sorted(
        ({key: value for key, value in item.items() if key != 'uuid'}
         for item in finding['items']), key=_canonical)
    return _canonical(normalized)


def _counts(findings):
    return {
        'total': len(findings),
        'excluded': sum(finding.get('excluded', False) for finding in findings),
        'by_severity': dict(sorted(Counter(f['severity'] for f in findings).items())),
        'by_type': dict(sorted(Counter(f['type'] for f in findings).items())),
    }


def compare_reports(before, after):
    for label, report in (('before', before), ('after', after)):
        _validate(report, label)
    for key in ('coordinate_units', 'kicad_version'):
        if before[key] != after[key]:
            raise ValueError(f'Reports have different {key}; generate them with matching settings')
    if set(before['included_severities']) != set(after['included_severities']):
        raise ValueError('Reports have different included_severities')
    if Counter(map(_canonical, before['ignored_checks'])) != Counter(map(_canonical, after['ignored_checks'])):
        raise ValueError('Reports have different ignored_checks')
    output = {
        'coordinate_units': before['coordinate_units'],
        'reported_kicad_version': before['kicad_version'],
        'included_severities': sorted(set(before['included_severities'])),
        'ignored_checks': before['ignored_checks'],
        'before': {'source': before['source'], 'counts': {}},
        'after': {'source': after['source'], 'counts': {}},
        'added': {}, 'removed': {},
    }
    added_count = removed_count = after_count = 0
    for section in SECTIONS:
        old = Counter(map(_finding_key, before[section]))
        new = Counter(map(_finding_key, after[section]))
        additions, removals = new - old, old - new
        output['before']['counts'][section] = _counts(before[section])
        output['after']['counts'][section] = _counts(after[section])
        for label, differences in (('added', additions), ('removed', removals)):
            output[label][section] = [
                {'count': count, 'finding': json.loads(key)}
                for key, count in sorted(differences.items())]
        added_count += sum(additions.values())
        removed_count += sum(removals.values())
        after_count += len(after[section])
    output.update(added_count=added_count, removed_count=removed_count,
                  after_has_no_reported_findings=after_count == 0,
                  status='review_required' if added_count else 'no_new_reported_findings')
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    args = parser.parse_args(argv)
    try:
        before = json.loads(args.before.read_text(encoding='utf-8-sig'))
        after = json.loads(args.after.read_text(encoding='utf-8-sig'))
        result = compare_reports(before, after)
    except (OSError, ValueError) as exc:
        print(f'DRC comparison refused: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 1 if result['added_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

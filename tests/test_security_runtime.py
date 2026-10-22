#!/usr/bin/env python3
"""Offline runtime evidence, NVD applicability and false-confirmation regressions."""
import contextlib
import copy
import io
import json
import os
import sys
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'agent-security'))
from security.cli import main, parser
from security.runtime import (applicability, assess_runtime, cpe_parts, declared_settings,
                              load_inventory, match_component, probe_java)
from security.sources import SourceError
from security.store import new_report, read_report

JAVA = 'cpe:2.3:a:oracle:java_se:17.0.12:*:*:*:*:*:*:*'
PATTERN = 'cpe:2.3:a:oracle:java_se:*:*:*:*:*:*:*:*'
WINDOWS = 'cpe:2.3:o:microsoft:windows_11:23h2:*:*:*:*:*:*:*'


def component(identity='jdk', cpe=JAVA, deployment=None):
    value = {'id': identity, 'cpe': cpe, 'evidence': {'kind': 'manual', 'source': 'fixture java -version', 'observed_at': '2026-10-01T00:00:00Z'}}
    if deployment:
        value['deployment'] = deployment
    return value


def match(cpe=PATTERN, **bounds):
    return {'vulnerable': True, 'criteria': cpe, **bounds}


def advisory(*nodes):
    return {'id': 'CVE-2026-10001', 'descriptions': [{'lang': 'en', 'value': 'Runtime fixture'}],
            'published': '2026-10-01T00:00:00Z', 'lastModified': '2026-10-02T00:00:00Z',
            'configurations': [{'operator': 'OR', 'nodes': list(nodes or [{'operator': 'OR', 'cpeMatch': [match(versionEndExcluding='17.0.13')]}])}]}


class Client:
    def __init__(self, *pages):
        self.pages, self.receipts, self.urls = iter(pages), [], []

    def get(self, url):
        self.urls.append(url)
        self.receipts.append({'url': url, 'fetched_at': '2026-10-22T00:00:00Z', 'stale': False})
        value = next(self.pages)
        if isinstance(value, Exception):
            raise value
        return value, {}


def page(cve=None, total=1):
    return {'totalResults': total, 'vulnerabilities': [{'cve': cve or advisory()}]}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': str(self.root / 'state')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def inventory(self, *entries):
        path = self.root / 'runtimes.json'
        path.write_text(json.dumps({'schema_version': 1, 'components': list(entries or [component()])}))
        return path

    def args(self, *argv):
        return parser().parse_args(['runtime', *argv])

    def cli(self, *argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(list(argv) + ['--json'])
        return code, json.loads(stream.getvalue())

    def test_declarations_never_become_runtime_or_trigger_build(self):
        (self.root / 'pom.xml').write_text('<project><properties><java.version>17</java.version><maven.compiler.release>${java.version}</maven.compiler.release></properties></project>')
        (self.root / 'build.gradle.kts').write_text("java { toolchain { languageVersion.set(JavaLanguageVersion.of(21)) } }; password = 'secret-value'")
        (self.root / 'Dockerfile').write_text('FROM eclipse-temurin:17-jre')
        with patch('security.runtime.run') as run, patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--path', str(self.root))
        self.assertEqual(code, 1)
        self.assertEqual(len(report['declared_settings']), 4)
        self.assertNotIn('secret-value', json.dumps(report))
        self.assertEqual(report['runtime_components'], [])
        self.assertTrue(all(not hint['establishes_installed_runtime'] for hint in report['declared_settings']))
        run.assert_not_called()
        get.assert_not_called()

    def test_inventory_only_offline_and_does_not_claim_cve_assessment(self):
        with patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--inventory', str(self.inventory()), '--inventory-only')
        self.assertEqual(code, 0)
        self.assertEqual(report['scope'], 'runtime_inventory_only')
        self.assertEqual(report['runtime_components'][0]['evidence']['verification'], 'user_supplied_not_independently_verified')
        get.assert_not_called()

    def test_version_boundaries_and_exact_version(self):
        for key, boundary, expected in [('versionStartIncluding', '17.0.12', True), ('versionStartExcluding', '17.0.12', False), ('versionEndIncluding', '17.0.12', True), ('versionEndExcluding', '17.0.12', False), ('versionEndExcluding', '17.0.13', True)]:
            with self.subTest(key=key):
                self.assertIs(match_component(match(**{key: boundary}), component()), expected)
        self.assertIs(match_component(match(cpe=JAVA), component()), True)
        self.assertIs(match_component(match(cpe=JAVA.replace('17.0.12', '17.0.13')), component()), False)

    def test_java_build_metadata_and_legacy_update_bounds(self):
        self.assertIs(match_component(match(versionEndExcluding='17.0.13'), component(cpe=JAVA.replace('17.0.12', '17.0.12+7'))), True)
        old = component(cpe=JAVA.replace('17.0.12:*', '1.8.0:update_422'))
        self.assertIs(match_component(match(versionEndExcluding='1.8.0_431'), old), True)
        self.assertIs(match_component(match(versionEndExcluding='1.8.0_421'), old), False)
        self.assertIs(match_component(match(cpe=PATTERN.replace('*:*:*:*:*:*:*:*', '1.8.0:update_421:*:*:*:*:*:*')), old), False)

    def test_non_numeric_ranges_and_specific_platform_fields_are_uncertain(self):
        self.assertIsNone(match_component(match(versionEndExcluding='17.0.13-ea'), component()))
        self.assertIsNone(match_component(match(cpe=PATTERN.replace(':*:*:*:*:*:*:*:*', ':*:*:*:*:*:linux:*:*')), component()))
        self.assertIs(match_component(match(cpe=PATTERN.replace('oracle', 'other_vendor')), component()), False)

    def test_environment_prerequisite_preserved(self):
        java = component()
        windows = component('os', WINDOWS)
        cve = advisory({'operator': 'AND', 'cpeMatch': [match(), {'vulnerable': False, 'criteria': WINDOWS}]})
        self.assertIsNone(applicability(cve, [java], java))
        self.assertIs(applicability(cve, [java, windows], java), True)
        self.assertIs(applicability(cve, [java, component('os', WINDOWS.replace('23h2', '22h2'))], java), None)  # version label ordering unsupported

    def test_unrelated_or_branch_cannot_confirm_candidate_target(self):
        java, windows = component(), component('os', WINDOWS)
        cve = advisory({'operator': 'AND', 'cpeMatch': [match(), {'vulnerable': False, 'criteria': WINDOWS.replace('23h2', '24h2')}]},
                       {'operator': 'OR', 'cpeMatch': [match(WINDOWS)]})
        self.assertIsNone(applicability(cve, [java, windows], java))

    def test_negated_and_non_vulnerable_match_never_confirms_target(self):
        self.assertIs(applicability(advisory({'negate': True, 'cpeMatch': [match()]}), [component()], component()), False)
        self.assertIs(applicability(advisory({'cpeMatch': [{'criteria': PATTERN, 'vulnerable': False}]}), [component()], component()), False)

    def test_missing_configs_and_unsupported_cpe_remain_candidates(self):
        cve = advisory()
        cve['configurations'] = []
        self.assertIsNone(applicability(cve, [component()], component()))
        cve = advisory({'cpeMatch': [match(PATTERN.replace('oracle', r'oracle\!'))]})
        self.assertIsNone(applicability(cve, [component()], component()))

    def test_exact_probe_values_are_observed_not_project_inferred(self):
        args = self.args('--local-java')
        output = '    java.vendor = Oracle Corporation\n    java.vm.name = Java HotSpot(TM) 64-Bit Server VM\n    java.version = 17.0.12\n    java.runtime.version = 17.0.12+7\n    user.home = /secret\n'
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', output.encode())) as run:
            result = probe_java(args)
        self.assertEqual(result['cpe'], JAVA)
        self.assertNotIn('secret', json.dumps(result))
        self.assertEqual(result['evidence']['verification'], 'observed_local_process')
        self.assertIn('-XshowSettings:properties', run.call_args.args[0])

    @unittest.skipUnless(shutil.which('java'), 'installed Java unavailable')
    def test_installed_java_probe_returns_observed_properties_offline(self):
        with patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--local-java', '--inventory-only')
        self.assertEqual(code, 0)
        self.assertIn('java.version', report['runtime_components'][0]['properties'])
        self.assertEqual(report['runtime_components'][0]['evidence']['verification'], 'observed_local_process')
        get.assert_not_called()

    def test_non_oracle_vendor_needs_explicit_mapping(self):
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', b'java.vendor = Eclipse Adoptium\njava.version = 17.0.12')):
            self.assertNotIn('cpe', probe_java(self.args('--local-java')))
            result = probe_java(self.args('--local-java', '--java-cpe', PATTERN.replace('oracle:java_se', 'fixture:fixture_jdk')))
        self.assertEqual(result['identity_source'], 'caller_selected')

    def test_oracle_identity_on_adoptium_is_incomplete_without_nvd_lookup(self):
        output = b'java.vendor = Eclipse Adoptium\njava.version = 21.0.8\njava.runtime.version = 21.0.8+9-LTS'
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', output)), patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--local-java', '--java-cpe', PATTERN)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['findings'], [])
        self.assertIn('non-Oracle vendor', report['coverage'][0]['error'])
        get.assert_not_called()

    def test_cpe_errors_include_format_example_and_offline_inspection_command(self):
        for value in ('not-a-cpe', PATTERN.replace(':*:*:*:*:*:*:*:*', ':21.*:*:*:*:*:*:*:*'), JAVA):
            with self.subTest(value=value):
                code, report = self.cli('runtime', '--local-java', '--java-cpe', value)
                self.assertEqual(code, 2)
                self.assertIn('format example:', report['error'])
                self.assertIn('--java-cpe "' + PATTERN + '"', report['error'])
                self.assertIn('--inventory-only', report['error'])

    def xstream_fixture(self):
        return json.loads((ROOT / 'tests/fixtures/security/CVE-2021-21349.json').read_text())['cve']

    def test_public_xstream_configuration_excludes_modern_jdk(self):
        cve = self.xstream_fixture()
        target = component(cpe=JAVA.replace('17.0.12', '21.0.8'))
        self.assertIs(applicability(cve, [target], target), False)
        with patch('security.cli.Client', return_value=Client(page(cve))):
            code, report = self.cli('runtime', '--inventory', str(self.inventory(target)))
        self.assertEqual(code, 0)
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['coverage'][0]['records_examined'], 1)

    def test_public_xstream_configuration_retains_affected_historical_jdk(self):
        cve = self.xstream_fixture()
        for version in ('8u311:*', '1.8.0:update_311', '1.8.0_311:*', '7u321:*', '1.7.0:update_321', '1.7.0_321:*'):
            with self.subTest(version=version):
                target = component(cpe=JAVA.replace('17.0.12:*', version))
                self.assertIs(applicability(cve, [target], target), True)
        target = component(cpe=JAVA.replace('17.0.12:*', '8u312:*'))
        self.assertIs(applicability(cve, [target], target), False)

    def test_legacy_short_version_numeric_range_boundaries(self):
        old = component(cpe=JAVA.replace('17.0.12:*', '1.8.0:update_422'))
        self.assertIs(match_component(match(versionEndExcluding='8u431'), old), True)
        self.assertIs(match_component(match(versionEndExcluding='8u421'), old), False)
        self.assertIs(match_component(match(cpe=PATTERN.replace(':*:*:*:*:*:*:*:*', ':8u422:*:*:*:*:*:*:*')), old), True)
        self.assertIs(match_component(match(cpe=PATTERN.replace(':*:*:*:*:*:*:*:*', ':7u321:*:*:*:*:*:*:*')), component()), False)

    def test_project_java17_is_separate_from_observed_java21(self):
        (self.root / 'pom.xml').write_text('<project><properties><java.version>17</java.version></properties></project>')
        output = b'java.vendor = Oracle Corporation\njava.vm.name = Java HotSpot(TM) 64-Bit Server VM\njava.version = 21.0.8\njava.runtime.version = 21.0.8+9-LTS'
        cve = advisory({'cpeMatch': [match(versionStartIncluding='21', versionEndExcluding='21.0.9')]})
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', output)), patch('security.cli.Client', return_value=Client(page(cve))):
            code, report = self.cli('runtime', '--path', str(self.root), '--local-java')
        self.assertEqual(code, 0)
        self.assertEqual(report['declared_settings'][0]['value'], '17')
        self.assertEqual(report['findings'][0]['package']['version'], '21.0.8')
        self.assertIn('21.0.8', report['runtime_components'][0]['cpe'])

    def test_probe_failure_cannot_appear_as_clean_scan(self):
        with patch('security.runtime.shutil.which', return_value=None):
            code, report = self.cli('runtime', '--local-java')
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'incomplete')

    def test_invalid_inventory_rejected_before_any_lookup(self):
        invalid = [component(cpe=PATTERN), component(cpe='not cpe'), {**component(), 'evidence': {'kind': 'verified'}}, {**component(), 'deployment': {'unknown': 'x'}}]
        for entry in invalid:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                load_inventory(self.inventory(entry), 10000)
        with self.assertRaises(ValueError):
            load_inventory(self.inventory(component(), component()), 10000)
        with self.assertRaises(ValueError):
            load_inventory(self.inventory(), 10)

    def test_xml_entities_and_byte_limits_rejected(self):
        (self.root / 'pom.xml').write_text('<!DOCTYPE x [<!ENTITY x "bad">]><project/>')
        with self.assertRaises(ValueError):
            declared_settings(self.root, 1000)
        with self.assertRaises(ValueError):
            declared_settings(self.root, 2)

    def test_invalid_flag_combinations(self):
        for argv in [[], ['--java', '/usr/bin/java'], ['--local-java', '--ecosystem', 'java'], ['--local-java', '--java-cpe', JAVA], ['--local-java', '--inventory-only', '--kev']]:
            with self.subTest(argv=argv):
                code, _ = self.cli('runtime', *argv)
                self.assertEqual(code, 2)

    def test_complete_findings_saved_and_refilterable_exit_zero(self):
        path = self.inventory()
        client = Client(page())
        with patch('security.cli.Client', return_value=client):
            code, report = self.cli('runtime', '--inventory', str(path))
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['findings'][0]['runtime_match']['relation'], 'inventory_match')
        saved = read_report(report['saved_report'])
        self.assertEqual(len(saved['findings']), 1)
        code, view = self.cli('report', '--file', report['saved_report'], '--severity', 'critical')
        self.assertEqual(code, 0)
        self.assertEqual(view['summary']['total'], 1)
        self.assertEqual(view['summary']['shown'], 0)
        self.assertNotIn('maven', json.dumps(saved['findings'][0]['package']))

    def test_truncation_and_failed_second_page_preserve_evidence(self):
        for pages, limit, status in [([page(total=2)], '1', 'truncated'), ([page(total=2), SourceError('fixture failure')], '2', 'error')]:
            with self.subTest(status=status), patch('security.cli.Client', return_value=Client(*pages)):
                code, report = self.cli('runtime', '--inventory', str(self.inventory()), '--limit', limit)
            self.assertEqual(code, 1)
            self.assertEqual(report['coverage'][-1]['status'], status)
            self.assertEqual(len(report['findings']), 1)

    def test_rejected_and_unaffected_advisories_excluded(self):
        rejected = advisory()
        rejected['vulnStatus'] = 'Rejected'
        fixed = advisory({'cpeMatch': [match(versionEndExcluding='17.0.12')]})
        client = Client({'totalResults': 2, 'vulnerabilities': [{'cve': rejected}, {'cve': fixed}]})
        with patch('security.cli.Client', return_value=client):
            code, report = self.cli('runtime', '--inventory', str(self.inventory()))
        self.assertEqual(code, 0)
        self.assertEqual(report['findings'], [])

    def test_cross_host_inventory_cannot_satisfy_environment(self):
        java = component(deployment={'host': 'a'})
        windows = component('os', WINDOWS, {'host': 'b'})
        cve = advisory({'operator': 'AND', 'cpeMatch': [match(), {'vulnerable': False, 'criteria': WINDOWS}]})
        # Second query concerns OS; no Java vulnerable witness for that target.
        for same_host in (False, True):
            windows['deployment']['host'] = 'a' if same_host else 'b'
            with patch('security.cli.Client', return_value=Client(page(cve), page(cve))):
                code, report = self.cli('runtime', '--inventory', str(self.inventory(java, windows)))
            self.assertEqual(code, 0 if same_host else 1)
            self.assertEqual(report['findings'][0]['runtime_match']['relation'], 'inventory_match' if same_host else 'candidate')

    def monitor_init(self, inventory):
        config = self.root / 'monitor.json'
        code, result = self.cli('monitor', 'init', '--config', str(config), '--runtime-inventory', str(inventory))
        self.assertEqual(code, 0)
        return config

    def monitor_run(self, config, *pages):
        with patch('security.monitor.Client', return_value=Client(*pages)):
            return self.cli('monitor', 'run', '--config', str(config))

    def test_runtime_monitor_new_ongoing_and_version_update_resolves(self):
        inventory = self.inventory()
        config = self.monitor_init(inventory)
        code, first = self.monitor_run(config, page())
        self.assertEqual(code, 0)
        self.assertEqual(first['counts']['new'], 1)
        _, second = self.monitor_run(config, page())
        self.assertEqual(second['counts']['ongoing'], 1)
        self.inventory(component(cpe=JAVA.replace('17.0.12', '17.0.13')))
        _, fixed = self.monitor_run(config, page())
        self.assertEqual(fixed['counts']['resolved'], 1)
        self.assertEqual(fixed['counts']['unverified'], 0)

    def test_runtime_monitor_missing_component_scope_stays_unverified(self):
        inventory = self.inventory(component(), component('jdk-other'))
        config = self.monitor_init(inventory)
        _, first = self.monitor_run(config, page(), page())
        self.assertEqual(first['counts']['new'], 2)
        self.inventory(component())
        _, second = self.monitor_run(config, page())
        self.assertEqual(second['counts']['unverified'], 2)
        self.assertEqual(second['counts']['resolved'], 0)

    def test_runtime_monitor_failure_and_deployment_change_never_resolve(self):
        inventory = self.inventory(component(deployment={'host': 'a'}))
        config = self.monitor_init(inventory)
        self.monitor_run(config, page())
        code, failed = self.monitor_run(config, SourceError('fixture offline'))
        self.assertEqual(code, 1)
        self.assertEqual(failed['counts']['unverified'], 1)
        self.inventory(component(cpe=JAVA.replace('17.0.12', '17.0.13'), deployment={'host': 'b'}))
        code, moved = self.monitor_run(config, page())
        self.assertEqual(code, 0)
        self.assertEqual(moved['counts']['unverified'], 1)
        self.assertEqual(moved['counts']['resolved'], 0)

    def test_runtime_monitor_missing_file_preserves_history(self):
        inventory = self.inventory()
        config = self.monitor_init(inventory)
        self.monitor_run(config, page())
        inventory.unlink()
        code, failed = self.monitor_run(config)
        self.assertEqual(code, 1)
        self.assertEqual(failed['counts']['unverified'], 1)
        self.assertEqual(failed['counts']['resolved'], 0)

    def test_mixed_source_and_runtime_portfolio_keeps_independent_transitions(self):
        from security.model import finding
        inventory = self.inventory()
        config = self.monitor_init(inventory)
        value = json.loads(config.read_text())
        value['targets'].append({'path': str(self.root)})
        config.write_text(json.dumps(value))
        row = finding(['CVE-2026-22222'], 'Library fixture', 'fixture', 'https://example.invalid', package={'ecosystem': 'Maven', 'name': 'example:library', 'version': '1.0'})
        def scan(args, report):
            report['findings'] = [copy.deepcopy(row)]
            report['coverage'] = [{'source': 'source fixture', 'status': 'ok'}]
            report['scanner'] = {'version': 'fixture-v2'}
        with patch('security.monitor.scan', side_effect=scan):
            code, first = self.monitor_run(config, page())
            self.assertEqual(code, 0)
            self.assertEqual(first['counts']['new'], 2)
            code, partial = self.monitor_run(config, SourceError('fixture runtime lookup failure'))
            self.assertEqual(code, 1)
            self.assertEqual(partial['counts']['ongoing'], 1)
            self.assertEqual(partial['counts']['unverified'], 1)
            self.assertEqual(partial['counts']['resolved'], 0)
            self.inventory(component(cpe=JAVA.replace('17.0.12', '17.0.13')))
            code, second = self.monitor_run(config, page())
            self.assertEqual(code, 0)
            self.assertEqual(second['counts']['ongoing'], 1)
            self.assertEqual(second['counts']['resolved'], 1)
            self.assertEqual(second['counts']['unverified'], 0)
            code, failed = self.monitor_run(config, SourceError('fixture runtime lookup failure'))
            self.assertEqual(code, 1)
            self.assertEqual(failed['counts']['ongoing'], 1)
            self.assertEqual(failed['counts']['resolved'], 0)
        source_report = read_report(second['source_report'])
        self.assertEqual(source_report['scope'], 'portfolio_source_and_explicit_runtime_inventory')
        self.assertEqual({child['command'] for child in source_report['repositories']}, {'scan', 'runtime'})

    def test_runtime_schedule_exports_same_limit_without_installation_or_scan(self):
        config = self.monitor_init(self.inventory())
        with patch('security.monitor.subprocess.run') as process, patch('security.sources.Client.get') as get:
            code, result = self.cli('monitor', 'schedule', '--config', str(config), '--runtime-limit', '2500')
        self.assertEqual(code, 0)
        self.assertFalse(result['installed'])
        self.assertIn('--runtime-limit 2500', result['cron'])
        self.assertIn('--due', result['cron'])
        process.assert_not_called()
        get.assert_not_called()

    def test_stale_receipts_never_appear_complete(self):
        client = Client(page())
        original = client.get
        def get(url):
            value = original(url)
            client.receipts[-1]['stale'] = True
            return value
        client.get = get
        with patch('security.cli.Client', return_value=client):
            code, report = self.cli('runtime', '--inventory', str(self.inventory()))
        self.assertEqual(code, 1)
        self.assertEqual(report['coverage'][0]['status'], 'stale')


if __name__ == '__main__':
    unittest.main()

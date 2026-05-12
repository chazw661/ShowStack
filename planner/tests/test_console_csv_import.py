"""Unit tests for the Yamaha CSV parser (planner/utils/console_csv_import.py).

Pure-function tests — no Django DB. Integration tests live in Plan 04.

Phase 2 / CSV-01, CSV-02, CSV-04.
"""
import io
import pathlib

from django.test import SimpleTestCase

from planner.utils.console_csv_import import (
    detect_family,
    is_default_row,
    parse_section_file,
    parse_upload,
    OUT_OF_SCOPE_SECTIONS,
    SECTION_TARGET_MAP,
)

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'csv_import'


def _open_fixture(name: str):
    """Return a binary file handle to the named fixture under tests/fixtures/csv_import/."""
    path = FIXTURES / name
    return path.open('rb')


# ---------------------------------------------------------------------------
# Family detection
# ---------------------------------------------------------------------------


class FamilyDetectTest(SimpleTestCase):
    def test_cl5_classified_as_cl_ql(self):
        self.assertEqual(detect_family(['[Information]', 'CL5', 'V4.1']), 'cl_ql')

    def test_ql5_classified_as_cl_ql(self):
        self.assertEqual(detect_family(['[Information]', 'QL5', 'V4.1']), 'cl_ql')

    def test_rivage_classified_as_rivage_pm(self):
        self.assertEqual(
            detect_family(['[Information]', 'CS-R5', 'DSP-RX', 'V6.60']),
            'rivage_pm',
        )

    def test_junk_unknown(self):
        self.assertEqual(detect_family(['hello world']), 'unknown')
        self.assertEqual(detect_family([]), 'unknown')

    def test_empty_list_unknown(self):
        self.assertEqual(detect_family([]), 'unknown')

    def test_detect_via_parsed_files(self):
        """Family detection via real fixture files."""
        cases = [
            ('cl5_inname.csv', 'cl_ql'),
            ('ql5_inname.csv', 'cl_ql'),
            ('rivage_inname.csv', 'rivage_pm'),
        ]
        for fname, expected in cases:
            with _open_fixture(fname) as f:
                result = parse_section_file(f, filename=fname)
            self.assertEqual(
                result['family'],
                expected,
                f'{fname} should classify as {expected}, got {result["family"]}',
            )


# ---------------------------------------------------------------------------
# Fixture parsing — row counts, zero errors on clean files
# ---------------------------------------------------------------------------


class ParserFixtureTest(SimpleTestCase):
    """Each blank fixture parses to the expected row count, zero hard errors."""

    def test_cl5_inname_72_rows(self):
        with _open_fixture('cl5_inname.csv') as f:
            result = parse_section_file(f, filename='cl5_inname.csv')
        self.assertEqual(result['section'], 'InName')
        self.assertEqual(
            len(result['rows']), 72,
            f'expected 72 rows, got {len(result["rows"])}',
        )
        hard_errors = [e for e in result['errors'] if not e['code'].startswith('W_')]
        self.assertEqual(hard_errors, [])

    def test_ql5_inname_64_rows(self):
        with _open_fixture('ql5_inname.csv') as f:
            result = parse_section_file(f, filename='ql5_inname.csv')
        self.assertEqual(result['section'], 'InName')
        self.assertEqual(len(result['rows']), 64)
        hard_errors = [e for e in result['errors'] if not e['code'].startswith('W_')]
        self.assertEqual(hard_errors, [])

    def test_rivage_inname_288_rows_with_leading_zero_strip(self):
        with _open_fixture('rivage_inname.csv') as f:
            result = parse_section_file(f, filename='rivage_inname.csv')
        self.assertEqual(result['section'], 'InName')
        self.assertEqual(len(result['rows']), 288)
        first = result['rows'][0]
        self.assertEqual(first['key'], '_001')
        self.assertEqual(first['channel_number'], 1)
        self.assertEqual(first['name'], 'ch 1')

    def test_cl5_stmononame_3_rows(self):
        with _open_fixture('cl5_stmononame.csv') as f:
            result = parse_section_file(f, filename='cl5_stmononame.csv')
        self.assertEqual(result['section'], 'StMonoName')
        self.assertEqual(len(result['rows']), 3)
        names = [r['name'] for r in result['rows']]
        self.assertEqual(names, ['ST L', 'ST R', 'MONO'])


# ---------------------------------------------------------------------------
# Default-row detection
# ---------------------------------------------------------------------------


class DefaultRowTest(SimpleTestCase):
    """Every row in a blank fixture must be detected as is_default_row=True."""

    def test_cl5_inname_all_defaults(self):
        with _open_fixture('cl5_inname.csv') as f:
            result = parse_section_file(f, filename='cl5_inname.csv')
        for row in result['rows']:
            self.assertTrue(
                is_default_row('InName', 'cl_ql', row),
                f'expected default for row {row}',
            )

    def test_ql5_inname_all_defaults(self):
        with _open_fixture('ql5_inname.csv') as f:
            result = parse_section_file(f, filename='ql5_inname.csv')
        for row in result['rows']:
            self.assertTrue(
                is_default_row('InName', 'cl_ql', row),
                f'expected default for row {row}',
            )

    def test_rivage_inname_all_defaults(self):
        with _open_fixture('rivage_inname.csv') as f:
            result = parse_section_file(f, filename='rivage_inname.csv')
        for row in result['rows']:
            self.assertTrue(
                is_default_row('InName', 'rivage_pm', row),
                f'expected default for row {row}',
            )

    def test_stmononame_defaults(self):
        rows = [
            {'key': '_01', 'channel_number': 1, 'name': 'ST L',  'color': 'Orange', 'icon': 'Blank'},
            {'key': '_02', 'channel_number': 2, 'name': 'ST R',  'color': 'Orange', 'icon': 'Blank'},
            {'key': '_03', 'channel_number': 3, 'name': 'MONO',  'color': 'Orange', 'icon': 'Blank'},
        ]
        for r in rows:
            self.assertTrue(
                is_default_row('StMonoName', 'cl_ql', r),
                f'expected default for {r}',
            )

    def test_mixname_fx_row_defaults(self):
        """CL5 MixName rows 17-24 default to Fx 1..Fx 8 with Effector icon."""
        self.assertTrue(
            is_default_row('MixName', 'cl_ql', {
                'key': '_17', 'channel_number': 17, 'name': 'Fx 1',
                'color': 'Orange', 'icon': 'Effector',
            }),
        )
        self.assertTrue(
            is_default_row('MixName', 'cl_ql', {
                'key': '_24', 'channel_number': 24, 'name': 'Fx 8',
                'color': 'Orange', 'icon': 'Effector',
            }),
        )

    def test_customized_row_not_default(self):
        self.assertFalse(
            is_default_row('InName', 'cl_ql', {
                'key': '_01', 'channel_number': 1, 'name': 'Kick',
                'color': 'Red', 'icon': 'Dynamic',
            }),
        )

    def test_wrong_color_not_default(self):
        self.assertFalse(
            is_default_row('InName', 'cl_ql', {
                'key': '_01', 'channel_number': 1, 'name': 'ch 1',
                'color': 'Red', 'icon': 'Dynamic',
            }),
        )

    def test_wrong_icon_not_default(self):
        self.assertFalse(
            is_default_row('InName', 'cl_ql', {
                'key': '_01', 'channel_number': 1, 'name': 'ch 1',
                'color': 'Blue', 'icon': 'Effector',
            }),
        )

    def test_mixname_mx_1_default(self):
        self.assertTrue(
            is_default_row('MixName', 'cl_ql', {
                'key': '_01', 'channel_number': 1, 'name': 'MX 1',
                'color': 'Orange', 'icon': 'Blank',
            }),
        )

    def test_stmononame_mono_default(self):
        self.assertTrue(
            is_default_row('StMonoName', 'cl_ql', {
                'key': '_03', 'channel_number': 3, 'name': 'MONO',
                'color': 'Orange', 'icon': 'Blank',
            }),
        )

    def test_rivage_stname_al_ar_default(self):
        for key, name in [('_AL', 'ST A'), ('_AR', 'ST A')]:
            self.assertTrue(
                is_default_row('StName', 'rivage_pm', {
                    'key': key, 'channel_number': None, 'name': name,
                    'color': 'Orange', 'icon': 'Blank',
                }),
                f'{key} should be default',
            )


# ---------------------------------------------------------------------------
# Dirty fixture — per-row error catalog
# ---------------------------------------------------------------------------


class DirtyFixtureTest(SimpleTestCase):
    """The hand-crafted dirty fixture exercises the per-row error catalog."""

    def _parse_dirty(self):
        with _open_fixture('cl5_dirty_mixname.csv') as f:
            return parse_section_file(f, filename='cl5_dirty_mixname.csv')

    def test_dirty_mixname_error_codes_present(self):
        result = self._parse_dirty()
        codes = [e['code'] for e in result['errors']]
        self.assertIn('E_UNKNOWN_COLOR', codes)
        self.assertIn('E_KEY_OUT_OF_RANGE', codes)
        self.assertIn('E_BAD_KEY', codes)
        self.assertIn('E_NAME_TOO_LONG', codes)

    def test_dirty_mixname_unknown_color_falls_back_to_blue(self):
        result = self._parse_dirty()
        # The unknown-color row is `_04,Snare,Magenta,...`
        snare_rows = [r for r in result['rows'] if r['key'] == '_04']
        self.assertEqual(len(snare_rows), 1, 'Expected exactly one row with key _04')
        self.assertEqual(snare_rows[0]['color'], 'Blue')

    def test_dirty_mixname_clean_rows_included(self):
        """Default row (_01), customized rows (_02, _03) must all parse successfully."""
        result = self._parse_dirty()
        parsed_keys = {r['key'] for r in result['rows']}
        self.assertIn('_01', parsed_keys)
        self.assertIn('_02', parsed_keys)
        self.assertIn('_03', parsed_keys)

    def test_dirty_mixname_bad_key_row_excluded(self):
        """_AB row must NOT appear in parsed rows (E_BAD_KEY)."""
        result = self._parse_dirty()
        ab_rows = [r for r in result['rows'] if r['key'] == '_AB']
        self.assertEqual(ab_rows, [])

    def test_dirty_mixname_out_of_range_excluded(self):
        """_999 row must NOT appear in parsed rows (E_KEY_OUT_OF_RANGE)."""
        result = self._parse_dirty()
        row999 = [r for r in result['rows'] if r['key'] == '_999']
        self.assertEqual(row999, [])

    def test_dirty_mixname_long_name_truncated_to_100(self):
        """_05 row has a >100 char name; parsed row must be truncated to 100."""
        result = self._parse_dirty()
        row05 = [r for r in result['rows'] if r['key'] == '_05']
        self.assertEqual(len(row05), 1)
        self.assertLessEqual(len(row05[0]['name']), 100)


# ---------------------------------------------------------------------------
# Zip upload
# ---------------------------------------------------------------------------


class ZipUploadTest(SimpleTestCase):
    def test_rivage_zip_parses_four_sections_same_family(self):
        with _open_fixture('rivage_export_zip.zip') as f:
            result = parse_upload(f, filename='rivage_export_zip.zip')
        self.assertTrue(result['is_zip'])
        self.assertEqual(result['family'], 'rivage_pm')
        self.assertIsNone(result['fatal_error'])
        sections = {s['section'] for s in result['sections']}
        self.assertGreaterEqual(
            sections & {'InName', 'MixName', 'MtxName'},
            {'InName', 'MixName', 'MtxName'},
        )

    def test_mixed_family_zip_produces_fatal_error(self):
        """A zip containing CSVs from two different families must set E_MIXED_FAMILIES."""
        import zipfile as zf_module

        # Build an in-memory zip with one CL5 CSV and one Rivage CSV
        cl5_content = b'[Information]\r\nCL5\r\nV4.1\r\n[InName]\r\nIN,NAME,COLOR,ICON,\r\n_01,ch 1,Blue,Dynamic,\r\n'
        rivage_content = b'[Information]\r\nCS-R5\r\nDSP-RX\r\nV6.60\r\n[InName]\r\nIN,NAME,COLOR,ICON,\r\n_001,ch 1,Blue,Dynamic,\r\n'

        buf = io.BytesIO()
        with zf_module.ZipFile(buf, 'w') as z:
            z.writestr('cl5_inname.csv', cl5_content)
            z.writestr('rivage_inname.csv', rivage_content)
        buf.seek(0)

        result = parse_upload(buf, filename='mixed.zip')
        self.assertEqual(result['fatal_error'], 'E_MIXED_FAMILIES')


# ---------------------------------------------------------------------------
# Rivage StName — _AL/_AR imported, _BL/_BR skipped
# ---------------------------------------------------------------------------


class RivageStNameTest(SimpleTestCase):
    def test_rivage_stname_imports_AL_AR_skips_BL_BR(self):
        with _open_fixture('rivage_stname.csv') as f:
            result = parse_section_file(f, filename='rivage_stname.csv')
        self.assertEqual(result['section'], 'StName')
        self.assertEqual(result['family'], 'rivage_pm')

        # Exactly _AL and _AR in parsed rows
        keys = {r['key'] for r in result['rows']}
        self.assertEqual(keys, {'_AL', '_AR'})

        # _BL and _BR must each produce a W_NO_MODEL_TARGET entry
        skip_warnings = [e for e in result['errors'] if e['code'] == 'W_NO_MODEL_TARGET']
        skipped_keys = ' '.join(
            e.get('detail', '') for e in skip_warnings
        )
        self.assertIn('_BL', skipped_keys)
        self.assertIn('_BR', skipped_keys)
        self.assertGreaterEqual(len(skip_warnings), 2)


# ---------------------------------------------------------------------------
# Out-of-scope sections (DCAName, MuteDCAName)
# ---------------------------------------------------------------------------


class OutOfScopeSectionTest(SimpleTestCase):
    def test_dcaname_section_returns_empty_rows_with_warning(self):
        csv_content = (
            '[Information]\r\nCL5\r\nV4.1\r\n'
            '[DCAName]\r\nDCA,NAME,COLOR,ICON,\r\n'
            '_01,DCA 1,Yellow,Blank,\r\n'
            '_02,DCA 2,Yellow,Blank,\r\n'
        )
        result = parse_section_file(
            io.BytesIO(csv_content.encode('utf-8')), filename='cl5_dcaname.csv'
        )
        self.assertEqual(result['section'], 'DCAName')
        self.assertEqual(result['rows'], [])
        codes = [e['code'] for e in result['errors']]
        self.assertIn('W_NO_MODEL_TARGET', codes)

    def test_mutedcaname_section_returns_empty_rows_with_warning(self):
        csv_content = (
            '[Information]\r\nCS-R5\r\nDSP-RX\r\nV6.60\r\n'
            '[MuteDCAName]\r\nDCA,NAME,COLOR,ICON,\r\n'
            'DCA 1,DCA 1,Yellow,Blank,\r\n'
        )
        result = parse_section_file(
            io.BytesIO(csv_content.encode('utf-8')), filename='rivage_mutedca.csv'
        )
        self.assertEqual(result['section'], 'MuteDCAName')
        self.assertEqual(result['rows'], [])
        codes = [e['code'] for e in result['errors']]
        self.assertIn('W_NO_MODEL_TARGET', codes)


# ---------------------------------------------------------------------------
# CL/QL [StName] (stereo returns) — no target model in v2.0 (R-03)
# ---------------------------------------------------------------------------


class ClQlStNameTest(SimpleTestCase):
    """Parser must recognize CL/QL [StName], count skipped rows, emit one
    informational W_NO_MODEL_TARGET entry, and return zero rows.

    Verified against Warning 7 fix in PLAN.md (parser-level skip).
    """

    def test_cl_ql_stname_skipped_with_informational(self):
        csv_content = (
            '[Information]\r\nCL5\r\nV4.1\r\n'
            '[StName]\r\nST,NAME,COLOR,ICON,\r\n'
            '_01,Returns L,Blue,Dynamic,\r\n'
            '_02,Returns R,Blue,Dynamic,\r\n'
        )
        result = parse_section_file(
            io.BytesIO(csv_content.encode('utf-8')), filename='cl5_stname.csv'
        )
        self.assertEqual(result['section'], 'StName')
        self.assertEqual(result['family'], 'cl_ql')
        # Zero rows applied — section is skipped wholesale
        self.assertEqual(result['rows'], [])
        # Exactly one informational entry with the skip metadata
        skip_entries = [e for e in result['errors'] if e.get('code') == 'W_NO_MODEL_TARGET']
        self.assertEqual(len(skip_entries), 1)
        entry = skip_entries[0]
        self.assertEqual(entry.get('section'), 'StName')
        self.assertEqual(entry.get('family'), 'cl_ql')
        self.assertEqual(entry.get('skipped'), 2)
        self.assertEqual(entry.get('reason'), 'no_target_model_v2.0')


# ---------------------------------------------------------------------------
# SECTION_TARGET_MAP and OUT_OF_SCOPE_SECTIONS contract
# ---------------------------------------------------------------------------


class SectionTargetMapTest(SimpleTestCase):
    """Lock the SECTION_TARGET_MAP contract Plan 03 will consume verbatim."""

    def test_target_map_contents(self):
        self.assertEqual(SECTION_TARGET_MAP['InName'], 'ConsoleInput')
        self.assertEqual(SECTION_TARGET_MAP['MixName'], 'ConsoleAuxOutput')
        self.assertEqual(SECTION_TARGET_MAP['MtxName'], 'ConsoleMatrixOutput')
        self.assertEqual(SECTION_TARGET_MAP['StMonoName'], 'ConsoleStereoOutput')

    def test_target_map_has_exactly_four_entries(self):
        self.assertEqual(len(SECTION_TARGET_MAP), 4)

    def test_out_of_scope_includes_dca_sections(self):
        self.assertIn('DCAName', OUT_OF_SCOPE_SECTIONS)
        self.assertIn('MuteDCAName', OUT_OF_SCOPE_SECTIONS)


# ---------------------------------------------------------------------------
# Error-handling edge cases
# ---------------------------------------------------------------------------


class ParserEdgeCaseTest(SimpleTestCase):
    def test_empty_file_produces_fatal_error(self):
        result = parse_section_file(io.BytesIO(b''), filename='empty.csv')
        codes = [e['code'] for e in result['errors']]
        self.assertIn('E_NO_INFORMATION', codes)

    def test_no_information_block_produces_unknown_family(self):
        csv_content = b'[InName]\r\nIN,NAME,COLOR,ICON,\r\n_01,ch 1,Blue,Dynamic,\r\n'
        result = parse_section_file(io.BytesIO(csv_content), filename='noinformation.csv')
        self.assertEqual(result['family'], 'unknown')

    def test_upload_single_csv(self):
        """parse_upload on a single CSV returns is_zip=False and 1 section."""
        csv_content = (
            '[Information]\r\nCL5\r\nV4.1\r\n'
            '[InName]\r\nIN,NAME,COLOR,ICON,\r\n'
            '_01,ch 1,Blue,Dynamic,\r\n'
        )
        result = parse_upload(io.BytesIO(csv_content.encode()), filename='test.csv')
        self.assertFalse(result['is_zip'])
        self.assertEqual(len(result['sections']), 1)
        self.assertEqual(result['family'], 'cl_ql')
        self.assertIsNone(result['fatal_error'])

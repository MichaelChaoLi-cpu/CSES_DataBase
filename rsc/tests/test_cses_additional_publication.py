"""Publication preserves native values and declares restricted harmonization."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'rsc/cses_db'))
from publish_cses_additional_waves import (  # noqa: E402
    catalog_labels,
    clean,
    definitions,
    name,
    ordered_keys,
    prepared_rows,
    primary_key,
    project,
    row_digest,
)


def test_catalog_labels_match_existing_object_contract():
    assert catalog_labels([{'source_value':1.0,'label':'Yes'},{'source_value':2,'label':'No'}]) == {'1':'Yes','2':'No'}
    assert catalog_labels([]) is None
    with pytest.raises(ValueError):
        catalog_labels([{'source_value':1,'label':'Yes'},{'source_value':1.0,'label':'Conflict'}])


def test_database_digest_uses_byte_order_not_locale_path_order():
    query = ordered_keys({'artifact_path':'text','row':'bigint'},['artifact_path','row']).as_string()
    assert query == '"artifact_path" COLLATE "C","row"'


def test_projection_preserves_uuid_leading_zeros_and_native_types():
    frame = pd.DataFrame({'Record Key':['["2025","abc-uuid","01"]'],
                          'source__interview__id':['abc-uuid'], 'source__code':['001'],
                          'source__number':[3.0], 'Age Source Value':[98],
                          'Age Exact Years Qualified':[pd.NA], 'Age Topcoded Qualified':[True]})
    actual = project(frame)
    assert actual.record_key[0] == '["2025","abc-uuid","01"]'
    assert actual.source_values[0] == {'interview__id':'abc-uuid','code':'001','number':3.0}
    assert actual.age_source_value[0] == 98
    assert pd.isna(actual.age_exact_years_qualified[0])
    assert actual.age_topcoded_qualified[0]


def test_sql_types_keep_booleans_json_and_missing_values():
    frame = pd.DataFrame({'id':['b','a'], 'flag':[True,None], 'numeric':[1.25,float('nan')],
                          'source_values':[{'x':'01'},{'x':1}], 'count':[1,2]})
    kinds, rows = prepared_rows(frame,['id'])
    assert kinds == {'id':'text','flag':'boolean','numeric':'double precision','source_values':'jsonb','count':'bigint'}
    assert rows[0] == ['a',None,None,{'x':1},2]
    assert clean({'x':pd.NA,'y':[float('nan')]}) == {'x':None,'y':[None]}
    assert row_digest([[{'a':1,'b':2}]]) == row_digest([[{'b':2,'a':1}]])


def test_refuses_mixed_unqualified_types_and_identifier_truncation():
    with pytest.raises(ValueError):
        prepared_rows(pd.DataFrame({'key':['a','b'],'mixed':[1,'1']}),['key'])
    with pytest.raises(ValueError):
        name('x'*64)
    assert name('Can Read And Write Combined') == 'can_read_and_write_combined'


def test_raw_duplicates_have_row_key_not_person_primary_key():
    assert primary_key('cses_data.cses_additional_ec_2023_source_v1') == ['survey_wave','source_row_number']
    assert primary_key('cses_data.cses_additional_ec_v1') == ['survey_wave','record_key']


def test_geography_version_preserves_legacy_and_explicit_uncertainty():
    views = definitions()
    assert 'UNION ALL' in views['cses_person_geography_v2']
    assert 'cses_person_geography_v1' in views['cses_person_geography_v2']
    assert 'false AS historical_identity_verified' in views['cses_additional_person_geography_v1']
    assert 'additional_native_json' in views['cses_additional_person_geography_v1']
    assert 'USING(survey_wave,household_key)' in views['cses_additional_person_geography_v1']
    assert not any(verb in '\n'.join(views.values()) for verb in ['UPDATE ','DELETE ','DROP '])

"""Remote-only reproduction of isolated predicates from pinned RADAR source."""
import ast
import base64
import gzip
import hashlib
import itertools
import json
import platform
from types import SimpleNamespace

import numpy
import pandas

PAYLOAD_GZIP_BASE64 = '__PINNED_PAYLOAD__'
payload = json.loads(gzip.decompress(base64.b64decode(PAYLOAD_GZIP_BASE64)))
assert platform.python_version() == '3.10.12'
assert pandas.__version__ == '1.5.3'
assert spark.version == '3.5.0'

sources = {}
receipts = {}
for key, item in payload['sources'].items():
    content = base64.b64decode(item['content_base64'])
    assert hashlib.sha256(content).hexdigest() == item['source']['sha256']
    sources[key] = content.decode('utf-8-sig')
    receipts[key] = {'repository': item['repository'], **item['source']}


def definitions(key: str, names: list[str], namespace: dict) -> dict:
    """Select exact original top-level definitions; never import application code."""
    tree = ast.parse(sources[key], filename=receipts[key]['path'])
    selected = []
    found = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            selected.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if set(targets) & set(names):
                selected.append(node)
                found.update(set(targets) & set(names))
    assert found == set(names), (key, found, names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), receipts[key]['path'], 'exec'), namespace)
    return namespace


mh_globals = definitions('mapping', ['append_message'], {'pandas': pandas})
mh = SimpleNamespace(append_message=mh_globals['append_message'])
dh_globals = definitions('dataframe', ['append_error_if_condition'],
                         {'pandas': pandas, 'numpy': numpy, 'mh': mh})
dh = SimpleNamespace(append_error_if_condition=dh_globals['append_error_if_condition'])
th_globals = definitions('transform', ['TRANSFORM_LOG_ENTRY_DELIMITER', 'append_transform_log',
                                      '_append_transform_log_with_condition',
                                      'append_transform_log_if_condition'],
                         {'pandas': pandas, 'numpy': numpy})
th = SimpleNamespace(append_transform_log_if_condition=th_globals['append_transform_log_if_condition'])
loan_globals = definitions('loan', ['DEFAULT_ADJUSTABLE_RATE_INDEX_SCALING_FACTOR',
                                   '_get_adj_rate_index_scaling_factor'],
                          {'pandas': pandas, 'numpy': numpy, 'dh': dh, 'th': th})
helper = loan_globals['_get_adj_rate_index_scaling_factor']

cases = payload['cases']
loans = pandas.DataFrame({
    'CaseId': [r['id'] for r in cases],
    'AdjustableRateIndexScalingFactor': [r['factor'] for r in cases],
    'AdjustableRateIndexScalingFactorImportType': [r['import_type'] for r in cases],
    'AdjustableRateSpread': [r['spread'] for r in cases],
    'ErrorMessage': [''] * len(cases),
    'TransformationLog': [''] * len(cases),
})
# Evaluate the exact original mask assignments, preserving their source line numbers.
loan_tree = ast.parse(sources['loan'])
loan_function = next(n for n in loan_tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == '_get_adj_rate_index_scaling_factor')
mask_nodes = [n for n in loan_function.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id in ('bad_factors_condition', 'bad_spread_condition')
                      for t in n.targets)]
assert len(mask_nodes) == 2
mask_scope = {'loans': loans.copy(deep=True), 'pandas': pandas}
exec(compile(ast.Module(body=mask_nodes, type_ignores=[]), receipts['loan']['path'], 'exec'), mask_scope)
pair = mask_scope['bad_factors_condition']
spread = mask_scope['bad_spread_condition']
joint = pair & spread
result = helper(loans.copy(deep=True))
observations = []
for i, expected in enumerate(cases):
    observed = {'id': expected['id'], 'family': expected['family'],
                'bad_pair': bool(pair.iloc[i]), 'bad_spread': bool(spread.iloc[i]),
                'joint': bool(joint.iloc[i]),
                'output_factor': float(result.iloc[i]['AdjustableRateIndexScalingFactor']),
                'has_error': bool(result.iloc[i]['ErrorMessage']),
                'error': result.iloc[i]['ErrorMessage']}
    observed['matches_go'] = (
        observed['bad_pair'] == expected['expected_bad_pair']
        and observed['bad_spread'] == expected['expected_bad_spread']
        and observed['joint'] == expected['expected_joint']
        and observed['output_factor'] == expected['expected_output_factor']
        and observed['has_error'] == expected['expected_error'])
    observations.append(observed)
assert all(row['matches_go'] for row in observations)
assert not joint.any()

# The notebook fragment is executed with the library helper's ErrorMessage precondition satisfied.
portfolios = ['commcard', 'deposit', 'unknown', '']
notebook_rows = [{'CaseId': f'{p or "empty"}-{active}', 'NotMapped_portfolio_type': p,
                  'NotMapped_active_ind': active, 'ErrorMessage': ''}
                 for p, active in itertools.product(portfolios, ['y', 'n'])]
mapped_others = pandas.DataFrame(notebook_rows)
notebook_tree = ast.parse(sources['notebook'])
selected_lines = (63, 64, 69, 70, 75)
selected = [n for n in notebook_tree.body if n.lineno in selected_lines]
assert tuple(n.lineno for n in selected) == selected_lines
notebook_scope = {'mapped_others': mapped_others, 'dh': dh}
notebook_observations = {}
for node in selected:
    exec(compile(ast.Module(body=[node], type_ignores=[]), receipts['notebook']['path'], 'exec'),
         notebook_scope)
    if node.lineno == 63:
        notebook_observations['ignore_mask'] = notebook_scope['ignore_condition'].tolist()
    if node.lineno in (64, 70, 75):
        notebook_observations[f'errors_after_line_{node.lineno}'] = (
            notebook_scope['mapped_others']['ErrorMessage'].tolist())
assert all(notebook_observations['ignore_mask'])
assert all(notebook_observations['errors_after_line_64'])
assert all(not error for error in notebook_observations['errors_after_line_75'])

# The source expression partitions the entire ordinary-string domain into three classes.
notebook_observations['ordinary_string_classes'] = ['commcard', 'deposit', 'all other strings']
notebook_observations['rows'] = notebook_rows
missing_error_scope = {'mapped_others': mapped_others.drop(columns=['ErrorMessage']).copy(), 'dh': dh}
try:
    exec(compile(ast.Module(body=selected[:2], type_ignores=[]), receipts['notebook']['path'], 'exec'),
         missing_error_scope)
except KeyError as error:
    notebook_observations['without_error_message_column'] = {'error_type': 'KeyError', 'error': str(error)}
else:
    raise AssertionError('Expected the original helper to require ErrorMessage')

report = {
    'format': 'q2-radar-contradiction-observation/v1',
    'runtime': {'python': platform.python_version(), 'pandas': pandas.__version__, 'spark': spark.version},
    'synthetic_only': True, 'whole_job_coverage': False, 'source_modified': False,
    'sources': receipts,
    'seeds': payload['seeds'], 'samples_per_seed': payload['samples_per_seed'],
    'library': {'function': '_get_adj_rate_index_scaling_factor', 'checked_rows': len(observations),
                'joint_true_rows': int(joint.sum()), 'go_prediction_matches': sum(r['matches_go'] for r in observations),
                'observations': observations},
    'notebook': notebook_observations,
}
dbutils.notebook.exit(json.dumps(report, allow_nan=False))

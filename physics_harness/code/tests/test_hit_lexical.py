"""Regression tests for the distinct legacy HIT lexical contracts."""
import pytest

from physics_harness.code.hit_lexical import (
    adapter_block_token, collector_block_token, is_block_close, strip_child_prefix,
)


@pytest.mark.parametrize('raw,cleaned,expected_adapter,expected_collector', [
    ('  [./child] # comment\r\n', '[./child]', './child', './child'),
    ('[]\n', '[]', '', ''),
    ('[../]', '[../]', '../', '../'),
    ('[../peer]', '[../peer]', '../peer', '../peer'),
    ('[한글]', '[한글]', '한글', '한글'),
    ('[a] [b]', '[a] [b]', None, 'a] [b'),
    ('[a#b]', '[a', 'a#b', None),
    ('[a', '[a', None, None),
    ('type = "[literal]"', 'type = "[literal]"', None, None),
])
def test_legacy_token_contracts(raw, cleaned, expected_adapter, expected_collector):
    assert adapter_block_token(raw) == expected_adapter
    assert collector_block_token(cleaned) == expected_collector


@pytest.mark.parametrize('token,closed,child', [
    ('', True, ''), ('../', True, '../'), ('../peer', False, '../peer'),
    ('./child', False, 'child'), ('./', False, ''), ('root', False, 'root'),
])
def test_shared_token_classification(token, closed, child):
    assert is_block_close(token) is closed
    assert strip_child_prefix(token) == child

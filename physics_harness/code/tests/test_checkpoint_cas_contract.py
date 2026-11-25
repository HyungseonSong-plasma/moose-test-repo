"""Local Git semantics only; no connector, credentials or remote mutation."""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


def git(repo, *args, data=None, check=True, env=None):
    return subprocess.run(['git', '-C', str(repo), *args], input=data,
                          capture_output=True, check=check, env=env)


def out(repo, *args, data=None, env=None):
    return git(repo, *args, data=data, env=env).stdout.decode().strip()


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'config', 'user.email', 'test@example.invalid')
    git(repo, 'config', 'user.name', 'qualification')
    (repo / 'source.txt').write_text('base\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'base')
    git(repo, 'branch', 'issue-l1')
    git(repo, 'branch', 'issue-l2')
    return repo


def build(repo, parent, path, payload, index):
    env = {**os.environ, 'GIT_INDEX_FILE': str(repo / index)}
    git(repo, 'read-tree', parent, env=env)
    blob = out(repo, 'hash-object', '-w', '--stdin', data=payload)
    git(repo, 'update-index', '--add', '--cacheinfo', '100644', blob, path, env=env)
    tree = out(repo, 'write-tree', env=env)
    return out(repo, 'commit-tree', tree, '-p', parent, '-m', 'checkpoint '+index)


def publish(repo, branch, parent, commit):
    # Local Git's update-ref expected-old-value is atomic. This does not prove
    # the remote connector's implementation is atomic.
    if out(repo, 'rev-list', '--parents', '-n', '1', commit).split() != [commit, parent]:
        raise ValueError('unexpected parent')
    return git(repo, 'update-ref', 'refs/heads/'+branch, commit, parent, check=False).returncode == 0


def checkpoint(repo, parent, pr, revision, index, payload=None):
    path = f'automation/controller-state/pr-{pr}/r{revision:016}.json'
    if payload is None:
        payload = (json.dumps({'pr':pr, 'revision':revision, 'expected_parent':parent})+'\n').encode()
    assert git(repo, 'cat-file', '-e', f'{parent}:{path}', check=False).returncode != 0
    commit = build(repo, parent, path, payload, index)
    assert out(repo, 'diff-tree', '--no-commit-id', '--name-status', '-r', parent, commit) == f'A\t{path}'
    assert git(repo, 'show', f'{commit}:{path}').stdout == payload
    return commit, path, payload


def test_exact_parent_single_path(repo):
    parent = out(repo,'rev-parse','issue-l1')
    commit,path,payload = checkpoint(repo,parent,886,1,'a')
    assert publish(repo,'issue-l1',parent,commit)
    assert out(repo,'rev-parse','issue-l1') == commit
    assert git(repo,'show',f'issue-l1:{path}').stdout == payload
    assert out(repo,'rev-parse','main') == parent


def test_independent_pr_parallel(repo):
    parent = out(repo,'rev-parse','main')
    a,_,_ = checkpoint(repo,parent,886,1,'a')
    b,_,_ = checkpoint(repo,parent,887,1,'b')
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda x:publish(repo,*x), [('issue-l1',parent,a),('issue-l2',parent,b)]))
    assert results == [True,True]
    assert out(repo,'rev-parse','issue-l1') == a
    assert out(repo,'rev-parse','issue-l2') == b


def test_same_pr_race_exactly_one_wins(repo):
    parent = out(repo,'rev-parse','main')
    a,_,_ = checkpoint(repo,parent,886,1,'a',b'{"attempt":"a"}\n')
    b,_,_ = checkpoint(repo,parent,886,1,'b',b'{"attempt":"b"}\n')
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda x:publish(repo,*x), [('issue-l1',parent,a),('issue-l1',parent,b)]))
    assert sum(results)==1
    assert out(repo,'rev-parse','issue-l1') == (a if results[0] else b)


def test_intervening_code_commit_is_preserved(repo):
    parent = out(repo,'rev-parse','main')
    candidate,_,_ = checkpoint(repo,parent,886,1,'a')
    code = build(repo,parent,'other.txt',b'code\n','code')
    assert publish(repo,'issue-l1',parent,code)
    assert not publish(repo,'issue-l1',parent,candidate)
    assert out(repo,'rev-parse','issue-l1')==code
    assert git(repo,'show','issue-l1:other.txt').stdout==b'code\n'


def test_lost_response_requires_readback_not_replay(repo):
    parent = out(repo,'rev-parse','main')
    a,path,payload = checkpoint(repo,parent,886,1,'a')
    assert publish(repo,'issue-l1',parent,a)
    assert not publish(repo,'issue-l1',parent,a)
    assert out(repo,'rev-parse','issue-l1')==a
    assert git(repo,'show',f'issue-l1:{path}').stdout==payload


def test_record_cannot_be_overwritten(repo):
    parent = out(repo,'rev-parse','main')
    a,_,_ = checkpoint(repo,parent,886,1,'a')
    assert publish(repo,'issue-l1',parent,a)
    with pytest.raises(AssertionError):
        checkpoint(repo,a,886,1,'b')


def test_unexpected_parent_rejected(repo):
    parent = out(repo,'rev-parse','main')
    a,_,_ = checkpoint(repo,parent,886,1,'a')
    b,_,_ = checkpoint(repo,a,886,2,'b')
    with pytest.raises(ValueError,match='unexpected parent'):
        publish(repo,'issue-l1',parent,b)

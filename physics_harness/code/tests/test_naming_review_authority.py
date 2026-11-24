"""P0: GitHub head/review identity is not equivalent to semantic correctness."""
from __future__ import annotations

from dataclasses import replace
from urllib.error import URLError

import pytest

from physics_harness.code.refactor.naming import NamingOption
from physics_harness.code.verification.naming_semantic_review import BlindedSemanticPacket
from physics_harness.code.verification import naming_review_authority as mod

SHA = "a" * 40
REPO = "example/repo"
REVIEWER = "Review-User"


def packet():
    return BlindedSemanticPacket(REPO, "b" * 40, "owner", "FILE", (), (), ())


def option():
    return NamingOption("rename", "RENAME", "Rename verified source owner", proposed_name="collector")


def payloads(*, reviewer=REVIEWER, pr_author="Author", head=SHA, state="APPROVED", review_sha=SHA,
             body=None, bot=False, review_id=12):
    p=packet();o=option()
    digest=mod.naming_review_context_sha256(p,o,SHA)
    pull={"number":3,"state":"open","head":{"sha":head},"base":{"repo":{"full_name":REPO}},
          "user":{"login":pr_author}}
    review={"id":review_id,"commit_id":review_sha,"state":state,
            "submitted_at":"2026-11-22T22:30:00Z", "body": body if body is not None else
             "Naming-Audit-Context: "+digest,
            "user":{"login":reviewer,"type":"Bot" if bot else "User"}}
    return pull, review


def checked(monkeypatch, values=None, **kw):
    if values is None:values=payloads()
    calls=[]
    def read(url, token):
        calls.append(url)
        return values[1] if "/reviews/" in url else values[0]
    monkeypatch.setattr(mod,"_github_get_json",read)
    result=mod.verify_github_naming_review(REPO,3,12,packet(),option(),SHA,
                authorized_reviewers=kw.pop("authorized_reviewers", (REVIEWER,)), **kw)
    return result, calls


def test_genuine_current_head_approved_allowlisted_review_is_only_identity_gate(monkeypatch):
    r,calls=checked(monkeypatch)
    assert r.status=="AUTHENTICATED_REVIEW_ONLY"
    assert len(calls)==3
    assert r.reviewer_account_verified_for_head
    assert not r.independent_semantic_review_proven
    assert not r.semantic_compatibility_proven and not r.mutation_approved
    assert "REVIEW_BLINDED_FIRST_PASS_NOT_ATTESTED" in r.unresolved


def test_mismatched_review_commit_blocks(monkeypatch):
    r,_=checked(monkeypatch,payloads(review_sha="b"*40))
    assert r.status=="BLOCKED"
    assert "REVIEW_WAS_NOT_ON_EXACT_CANDIDATE" in r.blockers


def test_pr_head_changed_blocks(monkeypatch):
    r,_=checked(monkeypatch,payloads(head="c"*40))
    assert "REVIEW_PR_HEAD_NOT_EXACT_CANDIDATE" in r.blockers


def test_reviewer_same_as_proposer_blocks(monkeypatch):
    r,_=checked(monkeypatch,payloads(pr_author=REVIEWER))
    assert "REVIEW_AUTHOR_IS_PROPOSER" in r.blockers


def test_unapproved_and_dismissed_states_block(monkeypatch):
    for state in ("COMMENTED","DISMISSED", "PENDING"):
        r,_=checked(monkeypatch,payloads(state=state))
        assert "REVIEW_NOT_CURRENT_APPROVAL" in r.blockers


def test_unknown_reviewer_and_unapproved_bot_block(monkeypatch):
    r,_=checked(monkeypatch,payloads(reviewer="unknown"))
    assert "REVIEWER_NOT_IN_AUTHORIZED_SET" in r.blockers
    r,_=checked(monkeypatch,payloads(bot=True))
    assert "BOT_REVIEW_REQUIRES_EXPLICIT_POLICY" in r.blockers
    accepted,_=checked(monkeypatch,payloads(bot=True),allow_bots=True)
    assert accepted.status=="AUTHENTICATED_REVIEW_ONLY"


def test_review_context_digest_missing_or_repeated_blocks(monkeypatch):
    for body in ("approved", "Naming-Audit-Context: "+"0"*64,
                 "Naming-Audit-Context: "+mod.naming_review_context_sha256(packet(),option(),SHA)+"\nNaming-Audit-Context: "+mod.naming_review_context_sha256(packet(),option(),SHA)):
        r,_=checked(monkeypatch,payloads(body=body))
        assert "REVIEW_MISSING_EXACT_CONTEXT_FINGERPRINT" in r.blockers


def test_unconfigured_review_allowlist_holds_without_network(monkeypatch):
    r,calls=checked(monkeypatch, authorized_reviewers=())
    assert r.status=="HOLD" and not calls
    assert "REVIEWER_ALLOWLIST_NOT_CONFIGURED" in r.unresolved


def test_authentic_read_unavailable_holds(monkeypatch):
    def failure(url,token):
        raise URLError("not connected")
    monkeypatch.setattr(mod,"_github_get_json",failure)
    r=mod.verify_github_naming_review(REPO,3,12,packet(),option(),SHA,
                                        authorized_reviewers=(REVIEWER,))
    assert r.status=="HOLD" and not r.reviewer_account_verified_for_head
    assert "GITHUB_REVIEW_AUTHENTICATED_READ_UNAVAILABLE" in r.unresolved


def test_second_pr_read_changed_cannot_pass_race(monkeypatch):
    first,review=payloads()
    final,_=payloads(head="d"*40)
    count=[0]
    def read(url,token):
        count[0]+=1
        return first if count[0]==1 else (review if count[0]==2 else final)
    monkeypatch.setattr(mod,"_github_get_json",read)
    r=mod.verify_github_naming_review(REPO,3,12,packet(),option(),SHA,
                                       authorized_reviewers=(REVIEWER,))
    assert "REVIEW_PR_HEAD_NOT_EXACT_CANDIDATE" in r.blockers


def test_review_digest_tracks_code_and_candidate(monkeypatch):
    current=mod.naming_review_context_sha256(packet(),option(),SHA)
    different=mod.naming_review_context_sha256(packet(),replace(option(),proposed_name="source_collector"),SHA)
    assert current!=different
    assert current!=mod.naming_review_context_sha256(packet(),option(),"c"*40)


@pytest.mark.parametrize("repository,number,review_id", [("evil/repo/extra",3,12), (REPO,0,12), (REPO,3,0)])
def test_review_endpoint_validation(repository,number,review_id):
    with pytest.raises(ValueError):
        mod.verify_github_naming_review(repository,number,review_id,packet(),option(),SHA,
                                        authorized_reviewers=(REVIEWER,))


def test_closed_pr_and_malformed_actor_do_not_pass(monkeypatch):
    p,r=payloads()
    r1,_=checked(monkeypatch,({**p,"state":"closed"},r))
    assert "REVIEW_PULL_REQUEST_NOT_OPEN" in r1.blockers
    r2,_=checked(monkeypatch,(p,{**r,"user":None}))
    assert "REVIEW_ACTOR_IDENTITY_MISSING" in r2.blockers


def test_official_http_reader_rejects_redirect_and_excessive_response(monkeypatch):
    # A production adapter will use HTTPS with a strict no-redirect handler.
    class FakeResponse:
        def __init__(self, data, url): self.data,self.url=data,url
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def geturl(self):return self.url
        def read(self,size):return self.data[:size]
    class FakeOpener:
        def __init__(self,actual_url,data):self.url,self.data=actual_url,data
        def open(self,request,timeout):return FakeResponse(self.data,self.url)
    monkeypatch.setattr(mod,"build_opener",lambda *args: FakeOpener("https://evil.invalid/review",b"{}"))
    with pytest.raises(ValueError,match="UNEXPECTED_REDIRECT"):
        mod._github_get_json("https://api.github.com/repos/example/repo/pulls/3",None)
    monkeypatch.setattr(mod,"build_opener",lambda *args: FakeOpener("https://api.github.com/test",b"a"*1_000_001))
    with pytest.raises(ValueError,match="RESPONSE_TOO_LARGE"):
        mod._github_get_json("https://api.github.com/test",None)


def test_packet_for_different_repository_blocks(monkeypatch):
    p=replace(packet(),repository="another/repo")
    dig=mod.naming_review_context_sha256(p,option(),SHA)
    first,review=payloads(body="Naming-Audit-Context: "+dig)
    monkeypatch.setattr(mod,"_github_get_json",lambda url,token: review if "/reviews/" in url else first)
    r=mod.verify_github_naming_review(REPO,3,12,p,option(),SHA,
                                       authorized_reviewers=(REVIEWER,))
    assert r.status=="BLOCKED" and "REVIEW_PACKET_REPOSITORY_MISMATCH" in r.blockers

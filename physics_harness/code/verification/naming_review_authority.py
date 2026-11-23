"""Fresh GitHub PR review identity and exact-candidate binding checks.

A GitHub HTTPS approval authenticates a GitHub account and reviewed commit;
it does not prove a two-pass candidate-blind semantic analysis, behavioral
compatibility, reviewer expertise or authorization to execute an edit.

This module never accepts caller-supplied JSON as authenticated evidence.
Testing may substitute the HTTPS adapter, but a production CI environment
must trust its Python runtime, certificates and network path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from ..refactor.naming import NamingOption
from .naming_semantic_review import BlindedSemanticPacket

_REPO = re.compile(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class NamingReviewAuthorityReceipt:
    repository: str
    pull_number: int
    review_id: int
    candidate_revision: str
    context_sha256: str
    status: str  # AUTHENTICATED_REVIEW_ONLY / HOLD / BLOCKED
    reviewer: str | None
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def reviewer_account_verified_for_head(self) -> bool:
        return self.status == "AUTHENTICATED_REVIEW_ONLY"

    @property
    def independent_semantic_review_proven(self) -> bool:
        # An allowed GitHub user distinct from the PR author can still see the
        # proposal or be the true proposer; independence requires more evidence.
        return False

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False

    @property
    def mutation_approved(self) -> bool:
        return False


def naming_review_context_sha256(
    packet: BlindedSemanticPacket, option: NamingOption, candidate_revision: str,
) -> str:
    """Bind the blind source packet, selected option and exact candidate SHA."""
    if not isinstance(packet, BlindedSemanticPacket) or not isinstance(option, NamingOption):
        raise TypeError("NAMING_REVIEW_PACKET_OPTION_REQUIRED")
    if not isinstance(candidate_revision, str) or not _SHA.fullmatch(candidate_revision):
        raise ValueError("INVALID_REVIEW_CANDIDATE_REVISION")
    payload = {"schema": "naming-review-context-v0.1", "packet": asdict(packet),
               "option": asdict(option), "candidate_revision": candidate_revision}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode("utf-8")).hexdigest()


def _github_get_json(url: str, token: str | None) -> dict:
    """Read a single fresh official GitHub REST object over verified HTTPS."""
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token is not None:
        if not isinstance(token, str) or not token or any(c in token for c in "\r\n"):
            raise ValueError("INVALID_GITHUB_TOKEN")
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers, method="GET")

    class RejectRedirects(HTTPRedirectHandler):
        # Never forward a GitHub bearer token to a redirect destination.
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    with build_opener(RejectRedirects()).open(request, timeout=10) as result:
        # Redirected review metadata must not leak the token to other origins.
        if result.geturl() != url:
            raise ValueError("GITHUB_REVIEW_UNEXPECTED_REDIRECT")
        value = result.read(1_000_001)
    if len(value) > 1_000_000:
        raise ValueError("GITHUB_REVIEW_RESPONSE_TOO_LARGE")
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("GITHUB_REVIEW_NOT_OBJECT")
    return payload


def verify_github_naming_review(
    repository: str, pull_number: int, review_id: int,
    packet: BlindedSemanticPacket, option: NamingOption, candidate_revision: str,
    *, authorized_reviewers: tuple[str, ...], token: str | None = None,
    allow_bots: bool = False,
) -> NamingReviewAuthorityReceipt:
    """Fetch *fresh* PR and review metadata; do not trust a pasted review URL.

    Caller must enroll reviewer accounts in an independently controlled allowlist.
    The review body must include a stand-alone line:
        Naming-Audit-Context: <naming_review_context_sha256(...)>
    This binds the approval to the exact option and immutable source packet,
    but does not authenticate that the reviewer performed a blind first pass.
    """
    if not isinstance(repository, str) or not _REPO.fullmatch(repository):
        raise ValueError("INVALID_REVIEW_REPOSITORY")
    if type(pull_number) is not int or pull_number < 1 or type(review_id) is not int or review_id < 1:
        raise ValueError("INVALID_GITHUB_REVIEW_IDENTIFIERS")
    if not isinstance(authorized_reviewers, tuple) or len(set(authorized_reviewers)) != len(authorized_reviewers) or any(
        not isinstance(x, str) or not x.strip() for x in authorized_reviewers):
        raise ValueError("INVALID_GITHUB_REVIEW_ALLOWLIST")
    if type(allow_bots) is not bool:
        raise ValueError("INVALID_REVIEW_BOT_POLICY")
    context = naming_review_context_sha256(packet, option, candidate_revision)
    blocked: set[str] = set()
    if packet.repository.casefold() != repository.casefold():
        blocked.add("REVIEW_PACKET_REPOSITORY_MISMATCH")
    unknown: set[str] = {"REVIEW_BLINDED_FIRST_PASS_NOT_ATTESTED",
                         "REVIEW_SEMANTIC_CORRECTNESS_NOT_PROVEN",
                         "REVIEWER_RUNTIME_AND_NETWORK_TRUST_EXTERNAL"}
    checks = ("AUTHENTICATE_CANDIDATE_BLIND_FIRST_PASS",
              "VERIFY_SEMANTIC_RESPONSIBILITY_AND_BOUNDARY",
              "REPLAY_BEFORE_AFTER_CONTRACT_TESTS_AT_EXACT_REVISIONS",
              "VERIFY_EXTERNAL_CONSUMERS_AND_POST_INTEGRATION_SHA")
    reviewer = None
    if not authorized_reviewers:
        unknown.add("REVIEWER_ALLOWLIST_NOT_CONFIGURED")
        return NamingReviewAuthorityReceipt(repository, pull_number, review_id,
            candidate_revision, context, "BLOCKED" if blocked else "HOLD", None,
            tuple(sorted(blocked)), tuple(sorted(unknown)), checks)
    url_base = "https://api.github.com/repos/" + repository
    try:
        first = _github_get_json(f"{url_base}/pulls/{pull_number}", token)
        review = _github_get_json(f"{url_base}/pulls/{pull_number}/reviews/{review_id}", token)
        second = _github_get_json(f"{url_base}/pulls/{pull_number}", token)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        unknown.add("GITHUB_REVIEW_AUTHENTICATED_READ_UNAVAILABLE")
        return NamingReviewAuthorityReceipt(repository, pull_number, review_id,
            candidate_revision, context, "BLOCKED" if blocked else "HOLD", None,
            tuple(sorted(blocked)), tuple(sorted(unknown)), checks)
    if first.get("number") != pull_number or second.get("number") != pull_number:
        blocked.add("REVIEW_FOR_DIFFERENT_PULL_REQUEST")
    for source in (first, second):
        if source.get("state") != "open" or source.get("merged") is True:
            blocked.add("REVIEW_PULL_REQUEST_NOT_OPEN")
        if not isinstance(source.get("head"), dict) or source["head"].get("sha") != candidate_revision:
            blocked.add("REVIEW_PR_HEAD_NOT_EXACT_CANDIDATE")
        base = source.get("base")
        base_repo = base.get("repo") if isinstance(base, dict) else None
        if not isinstance(base_repo, dict):
            base_repo = {}
        if base_repo.get("full_name", "").casefold() != repository.casefold():
            blocked.add("REVIEW_FOR_DIFFERENT_BASE_REPOSITORY")
    if review.get("id") != review_id:
        blocked.add("REVIEW_ID_MISMATCH")
    if review.get("commit_id") != candidate_revision:
        blocked.add("REVIEW_WAS_NOT_ON_EXACT_CANDIDATE")
    if review.get("state") != "APPROVED":
        blocked.add("REVIEW_NOT_CURRENT_APPROVAL")
    if not isinstance(review.get("submitted_at"), str) or not review["submitted_at"]:
        blocked.add("REVIEW_NOT_SUBMITTED")
    user = review.get("user")
    if not isinstance(user, dict):
        user = {}
    reviewer = user.get("login") if isinstance(user.get("login"), str) else None
    pr_user = first.get("user")
    author = pr_user.get("login") if isinstance(pr_user, dict) else None
    if not reviewer or not isinstance(author, str) or not author:
        blocked.add("REVIEW_ACTOR_IDENTITY_MISSING")
    else:
        if reviewer.casefold() == author.casefold():
            blocked.add("REVIEW_AUTHOR_IS_PROPOSER")
        if reviewer.casefold() not in {name.casefold() for name in authorized_reviewers}:
            blocked.add("REVIEWER_NOT_IN_AUTHORIZED_SET")
    if not allow_bots and user.get("type") == "Bot":
        blocked.add("BOT_REVIEW_REQUIRES_EXPLICIT_POLICY")
    marker = "Naming-Audit-Context: " + context
    if not isinstance(review.get("body"), str) or review["body"].splitlines().count(marker) != 1:
        blocked.add("REVIEW_MISSING_EXACT_CONTEXT_FINGERPRINT")
    status = "BLOCKED" if blocked else "AUTHENTICATED_REVIEW_ONLY"
    return NamingReviewAuthorityReceipt(repository, pull_number, review_id,
        candidate_revision, context, status, reviewer, tuple(sorted(blocked)),
        tuple(sorted(unknown)), checks)


__all__ = ["NamingReviewAuthorityReceipt", "naming_review_context_sha256",
           "verify_github_naming_review"]

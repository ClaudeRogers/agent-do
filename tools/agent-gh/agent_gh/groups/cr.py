from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ..refs import PrRef, parse_pr_ref
from ..render import print_json, print_table
from ..transport import GhError, gh_bin, gh_json, run_gh
from .pr import pr_detail, pr_diff_text, pr_gh_args, pr_threads


def _require_live(args: Any, reason: str) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(repo_root / "lib"))
    from live.errors import LiveApprovalRequiredError  # noqa: PLC0415
    from live.policy import require_live_control  # noqa: PLC0415

    argv = ["cr"]
    pr = getattr(args, "pr", None)
    if pr:
        argv.append(str(pr))
    if getattr(args, "address", False):
        argv.append("--address")
    if getattr(args, "author", None):
        argv.extend(["--author", str(args.author)])
    try:
        require_live_control(scope="any", tool="gh", argv=argv, app="GitHub", reason=reason)
    except LiveApprovalRequiredError as exc:
        print(json.dumps(exc.payload(), indent=2))
        raise SystemExit(1) from exc


def _run(
    cmd: list[str], *, cwd: str | None = None, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, text=True, capture_output=True, check=False, timeout=timeout
    )


def _claude_bin() -> str | None:
    configured = os.environ.get("AGENT_CLAUDE_BIN")
    if configured:
        return configured
    return shutil.which("claude")


def _git_bin() -> str:
    found = shutil.which("git")
    if not found:
        raise GhError("git not found in PATH")
    return found


def _current_github_user() -> str:
    try:
        data = gh_json(["api", "/user"])
        return (data or {}).get("login", "")
    except GhError:
        return ""


def _open_prs_for_author(author: str, limit: int) -> list[dict[str, Any]]:
    fields = "number,title,headRefName,baseRefName,url,headRepositoryOwner,headRepository"
    return gh_json([
        "pr", "list",
        "--author", author,
        "--state", "open",
        "--limit", str(limit),
        "--json", fields,
    ]) or []


def _pr_repo_slug(pr: dict[str, Any]) -> str | None:
    url = pr.get("url", "")
    parts = url.rstrip("/").split("/")
    if len(parts) >= 5 and parts[-2] == "pull":
        return f"{parts[-4]}/{parts[-3]}"
    owner = (pr.get("headRepositoryOwner") or {}).get("login", "")
    repo = (pr.get("headRepository") or {}).get("name", "")
    if owner and repo:
        return f"{owner}/{repo}"
    return None


def _pr_head_repo_slug(pr: dict[str, Any]) -> str | None:
    owner = (pr.get("headRepositoryOwner") or {}).get("login", "")
    repo = (pr.get("headRepository") or {}).get("name", "")
    if owner and repo:
        return f"{owner}/{repo}"
    return None


def _clone_branch(repo_slug: str, head_branch: str, workdir: str) -> str | None:
    dest = os.path.join(workdir, repo_slug.replace("/", "_"))
    # Use gh repo clone so gh's auth (token/SSH/Enterprise) handles private repos
    result = _run(
        [gh_bin(), "repo", "clone", repo_slug, dest, "--", "--branch", head_branch, "--depth", "50"],
        timeout=120,
    )
    if result.returncode != 0:
        print(f"    clone failed: {result.stderr.strip()[:200]}", file=sys.stderr)
        return None
    return dest


def _get_head_sha(repo_dir: str) -> str:
    result = _run([_git_bin(), "rev-parse", "HEAD"], cwd=repo_dir)
    return result.stdout.strip() if result.returncode == 0 else ""


def _push_branch(repo_dir: str, head_branch: str) -> bool:
    result = _run([_git_bin(), "push", "origin", head_branch], cwd=repo_dir)
    if result.returncode != 0:
        print(f"    push failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def _post_pr_comment(repo_slug: str, pr_number: int, body: str) -> None:
    try:
        run_gh(["pr", "comment", str(pr_number), "--repo", repo_slug, "--body", body])
    except GhError as exc:
        # Changes are already pushed — warn but don't fail the whole operation
        print(f"    warning: failed to post reply comment: {exc}", file=sys.stderr)


def _format_thread_summary(threads: list[dict[str, Any]]) -> str:
    lines = []
    for i, thread in enumerate(threads, 1):
        path = thread.get("path") or ""
        line = thread.get("line")
        first = (thread.get("comments") or [{}])[0]
        author = first.get("author") or "reviewer"
        body = (first.get("body") or "").replace("\n", " ")[:120]
        loc = f"{path}:{line}" if line else path
        lines.append(f"{i}. [{author}] {loc}: {body}")
    return "\n".join(lines)


def _format_review_item_summary(item: dict[str, Any]) -> str:
    kind = item.get("kind") or "review"
    path = item.get("path") or ""
    line = item.get("line")
    loc = f"{path}:{line}" if path and line else path
    if kind == "thread":
        first = (item.get("comments") or [{}])[0]
        author = first.get("author") or "reviewer"
        body = (first.get("body") or "").replace("\n", " ")[:120]
    else:
        author = item.get("author") or "reviewer"
        body = (item.get("body") or "").replace("\n", " ")[:120]
    if loc:
        return f"[{kind}] [{author}] {loc}: {body}"
    return f"[{kind}] [{author}]: {body}"


def _format_review_items_for_prompt(items: list[dict[str, Any]]) -> str:
    parts = []
    for i, item in enumerate(items, 1):
        kind = item.get("kind") or "review"
        path = item.get("path") or ""
        line = item.get("line")
        loc = f"{path} line {line}" if path and line else path
        comment_lines = []
        if kind == "thread":
            for c in item.get("comments") or []:
                author = c.get("author") or "reviewer"
                body = c.get("body") or ""
                comment_lines.append(f"  [{author}]: {body}")
        else:
            author = item.get("author") or "reviewer"
            body = item.get("body") or ""
            label = "CodeRabbit review" if kind == "coderabbit_review" else "CodeRabbit comment"
            if loc:
                comment_lines.append(f"  [{label}] {loc}")
            else:
                comment_lines.append(f"  [{label}]")
            comment_lines.append(f"  [{author}]: {body}")
        parts.append(f"Item {i} — {loc or kind}:\n" + "\n".join(comment_lines))
    return "\n\n".join(parts)


def _thread_items(threads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "kind": "thread",
            "id": thread.get("id"),
            "resolved": thread.get("resolved"),
            "path": thread.get("path"),
            "line": thread.get("line"),
            "comments": thread.get("comments") or [],
        }
        for thread in threads
    ]


def _coderabbit_body_excerpt(body: str) -> str:
    marker = "**Actionable comments posted:"
    idx = body.find(marker)
    if idx != -1:
        return body[idx:].strip()
    marker = "🤖 Prompt for all review comments with AI agents"
    idx = body.find(marker)
    if idx != -1:
        return body[idx:].strip()
    return body.strip()


def _coderabbit_feedback_items(ref: PrRef) -> list[dict[str, Any]]:
    if not ref.repo or not ref.number:
        raise GhError("CodeRabbit feedback requires an explicit PR reference")
    payload = gh_json(["pr", "view", *pr_gh_args(ref), "--json", "comments,reviews"]) or {}
    items: list[dict[str, Any]] = []
    for comment in payload.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        author = (comment.get("author") or {}).get("login")
        body = (comment.get("body") or "").strip()
        if author != "coderabbitai" or not body or "Rate limit exceeded" in body:
            continue
        items.append(
            {
                "kind": "coderabbit_comment",
                "author": author,
                "body": _coderabbit_body_excerpt(body),
                "path": comment.get("path"),
                "line": comment.get("line"),
                "url": comment.get("url"),
                "created_at": comment.get("createdAt"),
            }
        )
    for review in payload.get("reviews") or []:
        if not isinstance(review, dict):
            continue
        author = (review.get("author") or {}).get("login")
        body = (review.get("body") or "").strip()
        if author != "coderabbitai" or not body or "Rate limit exceeded" in body:
            continue
        items.append(
            {
                "kind": "coderabbit_review",
                "author": author,
                "body": _coderabbit_body_excerpt(body),
                "state": review.get("state"),
                "url": review.get("url"),
                "submitted_at": review.get("submittedAt"),
            }
        )
    return items


def _review_items(ref: PrRef) -> list[dict[str, Any]]:
    threads = _thread_items(pr_threads(ref, all_threads=False))
    feedback = _coderabbit_feedback_items(ref)
    return threads + feedback


def _review_items_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = [_format_review_item_summary(item) for item in items[:5]]
    if len(items) > 5:
        lines.append(f"... (+{len(items) - 5} more)")
    return "\n".join(lines)


def _address_with_claude(
    repo_dir: str,
    items: list[dict[str, Any]],
    pr: dict[str, Any],
    repo_slug: str,
    diff_text: str,
    claude_bin: str,
    verbose: bool,
    *,
    silent: bool = False,
) -> bool:
    pr_title = pr.get("title", "")
    head_branch = pr.get("headRefName", "")
    base_branch = pr.get("baseRefName", "main")
    pr_url = pr.get("url", "")
    item_text = _format_review_items_for_prompt(items)
    diff_excerpt = diff_text[:4000] if diff_text else "(diff unavailable)"

    prompt = f"""You are addressing unresolved review comments on a pull request.

PR: {pr_title}
URL: {pr_url}
Branch: {head_branch}
Base branch: {base_branch}
Repository: {repo_slug}
Working directory: {repo_dir}

The following review items are unresolved and need to be addressed:

{item_text}

PR diff (first 4000 chars for context):
```diff
{diff_excerpt}
```

Instructions:
1. Read each file mentioned in the review items using its full path in {repo_dir}
2. Understand what each reviewer is asking for
3. Make the changes needed to address each review comment
4. Stage all changed files with `git add`
5. Commit with message: "Address review feedback\\n\\n{_review_items_summary(items)}"
6. Do not push — the orchestrator will push after you finish

Address every item. Work through them one at a time.
"""

    if verbose:
        print(f"    Invoking claude to address {len(items)} review item(s)...")

    try:
        claude_args = [
            claude_bin,
            "--bare",
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            "Read,Edit,Bash(git status),Bash(git diff*),Bash(git add*),Bash(git commit*)",
            "--print",
            prompt,
        ]
        result = subprocess.run(
            claude_args,
            cwd=repo_dir,
            text=True,
            capture_output=silent,
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"    claude invocation failed: {exc}", file=sys.stderr)
        return False

    if result.returncode != 0:
        print(f"    claude exited {result.returncode}", file=sys.stderr)
        return False

    return True


def _address_pr(ref: PrRef, items: list[dict[str, Any]], args: Any, *, emit_json: bool = True) -> str | None:
    claude_bin = _claude_bin()
    if not claude_bin:
        raise GhError("claude CLI not found. Install Claude Code or set AGENT_CLAUDE_BIN.")

    repo_slug = ref.repo or ""
    if not repo_slug:
        raise GhError(f"Cannot determine repo for PR #{ref.number}")

    detail = pr_detail(ref)

    pr_state = str(detail.get("state") or "").upper()
    if pr_state and pr_state != "OPEN":
        raise GhError(f"PR {repo_slug}#{ref.number} is {pr_state} — only OPEN PRs can be addressed")

    head_branch = detail.get("head") or ""
    if not head_branch:
        raise GhError(f"PR {repo_slug}#{ref.number} has no head branch — cannot clone")

    head_repo_slug = detail.get("head_repo") or repo_slug
    if not head_repo_slug:
        raise GhError(f"PR {repo_slug}#{ref.number} has no head repository — cannot clone")

    base_branch = detail.get("base") or "main"
    verbose = getattr(args, "verbose", False)
    json_mode = getattr(args, "json", False)

    if getattr(args, "dry_run", False):
        if json_mode and emit_json:
            print_json({
                "pr": f"{repo_slug}#{ref.number}",
                "unresolved": len(items),
                "dry_run": True,
                "would_address": [
                    {"kind": item.get("kind"), "path": item.get("path"), "line": item.get("line")}
                    for item in items
                ],
            })
        elif not json_mode:
            print(f"[dry-run] would address {len(items)} review item(s) on {repo_slug}#{ref.number}")
            print(f"[dry-run] would clone {head_branch}, invoke claude, push, post comment")
        return None

    _require_live(args, "gh:cr:address")

    if head_repo_slug != repo_slug:
        raise GhError(
            f"Refusing to address fork PR {repo_slug}#{ref.number}: head repo {head_repo_slug} differs from base repo {repo_slug}."
        )

    pr_dict = {
        "title": detail.get("title", ""),
        "headRefName": head_branch,
        "baseRefName": base_branch,
        "url": detail.get("url", ""),
    }

    try:
        diff_text = pr_diff_text(ref)
    except GhError:
        diff_text = ""

    with tempfile.TemporaryDirectory(prefix="agent-gh-cr-") as workdir:
        if not json_mode:
            print(f"  Cloning {head_repo_slug} branch {head_branch}...")
        repo_dir = _clone_branch(head_repo_slug, head_branch, workdir)
        if not repo_dir:
            raise GhError(f"Failed to clone {head_repo_slug} branch {head_branch}")

        pre_sha = _get_head_sha(repo_dir)

        ok = _address_with_claude(
            repo_dir, items, pr_dict, repo_slug, diff_text, claude_bin, verbose,
            silent=json_mode,
        )
        if not ok:
            raise GhError("claude failed to address review comments")

        post_sha = _get_head_sha(repo_dir)

        if post_sha == pre_sha:
            if json_mode and emit_json:
                print_json({"pr": f"{repo_slug}#{ref.number}", "status": "no_changes", "sha": post_sha})
            elif not json_mode:
                print("  No changes committed by claude — review items may already be addressed")
            return None

        if not json_mode:
            print(f"  Pushing branch {head_branch}...")
        if not _push_branch(repo_dir, head_branch):
            raise GhError("push failed after addressing review comments")

        comment_body = f"Review feedback addressed in {post_sha[:8]}.\n\n"
        comment_body += _review_items_summary(items)
        _post_pr_comment(repo_slug, int(ref.number), comment_body)

        if json_mode and emit_json:
            print_json({
                "pr": f"{repo_slug}#{ref.number}",
                "status": "addressed",
                "sha": post_sha,
                "threads_addressed": len(items),
                "review_items_addressed": len(items),
            })
        elif not json_mode:
            print(f"  ✓ addressed {len(items)} review item(s), pushed, commented ({post_sha[:8]})")

        return post_sha


# ── command handlers ───────────────────────────────────────────────────────────

def cmd_cr(args: Any) -> None:
    if args.pr:
        _cr_single(args)
    else:
        _cr_sweep(args)


def _cr_single(args: Any) -> None:
    ref = parse_pr_ref(args.pr)
    items = _review_items(ref)
    json_mode = getattr(args, "json", False)

    if not items:
        if json_mode:
            print_json({"pr": f"{ref.repo}#{ref.number}", "unresolved": 0, "status": "clean"})
        else:
            print(f"No unresolved review items on {ref.repo}#{ref.number}")
        return

    if not args.address:
        if json_mode:
            print_json({
                "pr": f"{ref.repo}#{ref.number}",
                "unresolved": len(items),
                "items": items,
            })
        else:
            print(f"{len(items)} unresolved review item(s) on {ref.repo}#{ref.number}:")
            rows = []
            for item in items:
                if item.get("kind") == "thread":
                    first = (item.get("comments") or [{}])[0]
                    rows.append({
                        "kind": item.get("kind"),
                        "path": item.get("path"),
                        "line": item.get("line"),
                        "author": first.get("author"),
                        "body": (first.get("body") or "").replace("\n", " ")[:100],
                    })
                    continue
                rows.append({
                    "kind": item.get("kind"),
                    "path": item.get("path"),
                    "line": item.get("line"),
                    "author": item.get("author"),
                    "body": (item.get("body") or "").replace("\n", " ")[:100],
                })
            print_table(rows, ["kind", "path", "line", "author", "body"])
        return

    _address_pr(ref, items, args)


def _cr_sweep(args: Any) -> None:
    author = getattr(args, "author", None) or _current_github_user()
    if not author:
        raise GhError("could not determine GitHub user. Use --author.")

    limit = getattr(args, "limit", 50)
    json_mode = getattr(args, "json", False)

    if getattr(args, "address", False) and not getattr(args, "dry_run", False):
        _require_live(args, "gh:cr:address")

    try:
        prs = _open_prs_for_author(author, limit)
    except GhError as exc:
        if json_mode:
            print_json({"author": author, "count": 0, "items": [], "error": str(exc)})
            return
        raise

    if not prs:
        if json_mode:
            print_json({"author": author, "count": 0, "items": []})
        else:
            print(f"No open PRs for @{author}")
        return

    results: list[dict[str, Any]] = []

    for pr in prs:
        repo_slug = _pr_repo_slug(pr)
        number = pr.get("number")
        title = pr.get("title", "")
        url = pr.get("url", "")
        label = f"#{number} {title[:60]}"

        if not number:
            results.append({"pr": number, "title": title, "status": "skipped", "reason": "no number"})
            if not json_mode:
                print(f"  {title[:60]}  — skipped (no PR number)")
            continue

        if not repo_slug:
            results.append({"pr": number, "title": title, "status": "skipped", "reason": "no repo"})
            if not json_mode:
                print(f"  {label}  — skipped (no repo)")
            continue

        ref = PrRef(repo=repo_slug, number=str(number), original=f"{repo_slug}#{number}")
        try:
            items = _review_items(ref)
        except GhError as exc:
            results.append({"pr": number, "title": title, "status": "error", "reason": str(exc)})
            if not json_mode:
                print(f"  {label}  — error fetching review items: {exc}", file=sys.stderr)
            continue

        if not items:
            results.append({"pr": number, "title": title, "unresolved": 0, "status": "clean"})
            if not json_mode:
                print(f"  {label}  — clean")
            continue

        result: dict[str, Any] = {
            "pr": number,
            "title": title,
            "unresolved": len(items),
            "url": url,
        }
        if not json_mode:
            print(f"  {label}  — {len(items)} unresolved review item(s)")

        if args.address:
            if args.dry_run:
                result["status"] = "dry-run"
                if not json_mode:
                    print(f"    [dry-run] would address {len(items)} review item(s)")
            elif _pr_head_repo_slug(pr) and _pr_head_repo_slug(pr) != repo_slug:
                result["status"] = "skipped"
                result["reason"] = "fork PR head differs from base repo"
                if not json_mode:
                    print("    skipped: fork PR head differs from base repo")
            else:
                try:
                    sha = _address_pr(ref, items, args, emit_json=False)
                    result["status"] = "addressed"
                    if sha:
                        result["sha"] = sha
                except GhError as exc:
                    print(f"    ✗ {exc}", file=sys.stderr)
                    result["status"] = "error"
                    result["reason"] = str(exc)
        else:
            result["status"] = "pending"

        results.append(result)

    if json_mode:
        print_json({"author": author, "count": len(results), "items": results})
    else:
        has_unresolved = sum(1 for r in results if r.get("unresolved", 0) > 0)
        clean = sum(1 for r in results if r.get("status") == "clean")
        print(f"\n{len(results)} PR(s): {has_unresolved} with unresolved threads, {clean} clean")

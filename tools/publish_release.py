#!/usr/bin/env python3
"""Validate and explicitly publish a CxCP GitHub Release."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable
from urllib import error, request


REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_NOTES = REPO_ROOT / "tools" / "release_notes.py"
DEFAULT_CHANGELOG = Path("~/obsidian/知识库/Codex协同Obsidian工作流skill更新日志.md").expanduser()


class ReleaseError(RuntimeError):
    pass


def load_release_notes():
    spec = importlib.util.spec_from_file_location("cxcp_release_notes", RELEASE_NOTES)
    if spec is None or spec.loader is None:
        raise ReleaseError(f"无法加载 Release 正文工具：{RELEASE_NOTES}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验并显式发布 CxCP GitHub Release")
    parser.add_argument("--version", required=True, help="发布版本，例如 1.0.1")
    parser.add_argument("--changelog", type=Path, default=DEFAULT_CHANGELOG)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--remote", default="origin", help="Git 远端名称，默认 origin")
    parser.add_argument("--title", help="Release 标题，默认 CxCP V<版本>")
    parser.add_argument("--token-env", default="GITHUB_TOKEN", help="保存 GitHub Token 的环境变量名")
    parser.add_argument("--publish", action="store_true", help="明确创建 GitHub Release；缺省时只执行预检")
    return parser.parse_args()


def git_output(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise ReleaseError(f"Git 预检失败：{message or '命令返回非零状态。'}")
    return result.stdout.strip()


def github_repository(remote_url: str) -> str:
    value = str(remote_url or "").strip().rstrip("/")
    matched = re.search(
        r"(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/\s]+)/([^/\s]+?)(?:\.git)?$",
        value,
        re.IGNORECASE,
    )
    if matched is None:
        raise ReleaseError("远端不是可发布的 github.com 仓库。")
    return f"{matched.group(1)}/{matched.group(2)}"


def remote_tag_target(repo_root: Path, remote: str, tag: str, git_runner: Callable[..., str]) -> str:
    output = git_runner(
        repo_root,
        "ls-remote",
        "--tags",
        remote,
        f"refs/tags/{tag}",
        f"refs/tags/{tag}^{{}}",
    )
    direct = ""
    peeled = ""
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, ref = parts
        if ref == f"refs/tags/{tag}^{{}}":
            peeled = sha
        elif ref == f"refs/tags/{tag}":
            direct = sha
    return peeled or direct


def preflight(
    repo_root: Path,
    version: str,
    changelog: Path,
    remote: str,
    title: str | None = None,
    *,
    git_runner: Callable[..., str] = git_output,
) -> dict:
    notes = load_release_notes()
    normalized = notes.normalized_version(version)
    body = notes.build_release_body(changelog.expanduser(), normalized)
    root = repo_root.expanduser().resolve()
    if not root.is_dir():
        raise ReleaseError(f"仓库目录不存在：{root}")
    if git_runner(root, "status", "--porcelain"):
        raise ReleaseError("工作区存在未提交改动，不能发布。")
    head = git_runner(root, "rev-parse", "HEAD")
    tag = f"v{normalized}"
    local_target = git_runner(root, "rev-parse", f"refs/tags/{tag}^{{}}")
    if local_target != head:
        raise ReleaseError(f"本地标签 {tag} 没有指向当前 HEAD。")
    remote_url = git_runner(root, "config", "--get", f"remote.{remote}.url")
    repository = github_repository(remote_url)
    remote_target = remote_tag_target(root, remote, tag, git_runner)
    if not remote_target:
        raise ReleaseError(f"远端 {remote} 尚未推送标签 {tag}。")
    if remote_target != local_target:
        raise ReleaseError(f"远端标签 {tag} 没有指向本地标签提交。")
    return {
        "version": normalized,
        "tag": tag,
        "title": title or f"CxCP V{normalized}",
        "body": body,
        "commit": head,
        "repository": repository,
    }


def github_request(method: str, endpoint: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request_value = request.Request(
        f"https://api.github.com{endpoint}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with request.urlopen(request_value, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except error.HTTPError as response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            payload_value = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload_value = {"message": raw}
        return response.code, payload_value
    except error.URLError as response:
        raise ReleaseError(f"无法连接 GitHub API：{response.reason}") from response


def release_matches(release: dict, check: dict) -> bool:
    return bool(
        release.get("name") == check["title"]
        and release.get("tag_name") == check["tag"]
        and release.get("body") == check["body"]
        and not release.get("draft", True)
        and not release.get("prerelease", True)
    )


def publish_release(
    check: dict,
    token: str,
    *,
    request_runner: Callable[[str, str, str, dict | None], tuple[int, dict]] = github_request,
) -> tuple[dict, bool]:
    endpoint = f"/repos/{check['repository']}/releases/tags/{check['tag']}"
    status, existing = request_runner("GET", endpoint, token, None)
    if status == 200:
        if release_matches(existing, check):
            return existing, False
        raise ReleaseError("同名 GitHub Release 已存在，但标题、正文或发布状态与预检不一致。")
    if status != 404:
        raise ReleaseError(f"无法读取现有 GitHub Release：{existing.get('message', status)}")
    payload = {
        "tag_name": check["tag"],
        "target_commitish": check["commit"],
        "name": check["title"],
        "body": check["body"],
        "draft": False,
        "prerelease": False,
        "generate_release_notes": False,
    }
    status, created = request_runner("POST", f"/repos/{check['repository']}/releases", token, payload)
    if status != 201:
        raise ReleaseError(f"GitHub Release 创建失败：{created.get('message', status)}")
    if not release_matches(created, check):
        raise ReleaseError("GitHub 返回的 Release 与预检正文或标签不一致。")
    return created, True


def main() -> int:
    args = parse_args()
    try:
        check = preflight(args.repo_root, args.version, args.changelog, args.remote, args.title)
    except (OSError, ReleaseError, ValueError) as error_value:
        print(str(error_value), file=sys.stderr)
        return 2

    print("## Release 预检通过")
    print(f"仓库：`{check['repository']}`")
    print(f"标签：`{check['tag']}`")
    print(f"提交：`{check['commit']}`")
    print(f"标题：{check['title']}")
    if not args.publish:
        print("未执行远端写入。加入 --publish 并设置令牌环境变量后才会创建 GitHub Release。")
        print("\n## GitHub Release 正文\n")
        print(check["body"].rstrip())
        return 0

    token = os.environ.get(args.token_env, "").strip()
    if not token:
        print(f"缺少 GitHub Token 环境变量：{args.token_env}", file=sys.stderr)
        return 2
    try:
        release, created = publish_release(check, token)
    except ReleaseError as error_value:
        print(str(error_value), file=sys.stderr)
        return 2
    action = "已创建" if created else "已验证已有"
    print(f"{action} GitHub Release：{release.get('html_url', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

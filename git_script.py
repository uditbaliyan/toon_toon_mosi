#!/usr/bin/env python3
"""
ToonToon Animation Generator - Git Commit Helper

Creates meaningful commits from ACTUAL repository changes.

Project categories:
    assets       -> character assets, poses, mouths, manifests
    pipeline     -> parser, aligner, scheduler, compositor, renderer
    audio        -> audio / voice / synchronization work
    docs         -> documentation
    tests        -> tests and integration tests
    config       -> configuration / dependencies
    output       -> generated animation output
    project      -> README / project-level files
    misc         -> everything else

This script does NOT fabricate historical dates.
"""

import random
import subprocess
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

REPO_PATH = Path.home() / "Documents/Github_3.0/toon_toon_mosi"


# ============================================================
# COMMIT MESSAGE TEMPLATES
# ============================================================

COMMIT_TEMPLATES = {
    "assets": [
        "assets: add {file}",
        "assets: update {file}",
        "assets: refine {file}",
        "assets: add new character asset {file}",
        "assets: update animation asset {file}",
        "assets: organize {file}",
    ],
    "pipeline": [
        "pipeline: update {file}",
        "pipeline: improve {file}",
        "feat: improve {file}",
        "refactor: simplify {file}",
        "fix: correct {file}",
        "engine: update {file}",
    ],
    "audio": [
        "audio: update {file}",
        "audio: improve synchronization",
        "audio: refine voice timing",
        "audio: update audio processing",
        "sync: improve audio alignment",
    ],
    "docs": [
        "docs: update {file}",
        "docs: improve {file}",
        "docs: add {file}",
        "docs: clarify {file}",
        "docs: update project documentation",
    ],
    "tests": [
        "test: update {file}",
        "test: add coverage for {file}",
        "test: improve integration tests",
        "test: refine {file}",
        "test: verify animation pipeline",
    ],
    "config": [
        "config: update {file}",
        "build: update {file}",
        "chore: update {file}",
        "setup: update {file}",
        "deps: update {file}",
    ],
    "output": [
        "output: regenerate {file}",
        "render: update {file}",
        "render: generate {file}",
        "output: update animation",
    ],
    "project": [
        "project: update {file}",
        "chore: update {file}",
        "refactor: update {file}",
        "feat: improve {file}",
    ],
    "misc": [
        "update {file}",
        "chore: update {file}",
        "refactor: update {file}",
        "fix: update {file}",
        "add {file}",
    ],
}


# ============================================================
# FOLDER / FILE CLASSIFICATION
# ============================================================


def get_category(filepath):
    """
    Determine what type of project component a file belongs to.
    """

    path = Path(filepath)
    parts = path.parts
    name = path.name.lower()
    suffix = path.suffix.lower()

    # --------------------------------------------------------
    # Character / animation assets
    # --------------------------------------------------------

    if "assets" in parts:
        return "assets"

    # --------------------------------------------------------
    # Source pipeline
    # --------------------------------------------------------

    if "src" in parts:
        pipeline_files = {
            "parser.py",
            "aligner.py",
            "compositor.py",
            "renderer.py",
            "scheduler.py",
            "mouth_blender.py",
            "subtitle_generator.py",
            "models.py",
        }

        if name in pipeline_files:
            return "pipeline"

        if name == "config.py":
            return "config"

        return "pipeline"

    # --------------------------------------------------------
    # Audio
    # --------------------------------------------------------

    audio_extensions = {
        ".wav",
        ".mp3",
        ".ogg",
        ".flac",
        ".aac",
    }

    if suffix in audio_extensions:
        return "audio"

    # --------------------------------------------------------
    # Documentation
    # --------------------------------------------------------

    if "docs" in parts:
        return "docs"

    if name in {
        "readme.md",
        "quickstart.md",
        "implementation_summary.md",
        "project_index.md",
    }:
        return "docs"

    # --------------------------------------------------------
    # Tests
    # --------------------------------------------------------

    if "test" in name or "tests" in parts or name.startswith("test_"):
        return "tests"

    # --------------------------------------------------------
    # Configuration
    # --------------------------------------------------------

    if suffix in {
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
    }:
        return "config"

    if name in {
        "requirements.txt",
        "mkdocs.yml",
        "dockerfile",
        ".gitignore",
    }:
        return "config"

    # --------------------------------------------------------
    # Rendered output
    # --------------------------------------------------------

    if "output" in parts:
        return "output"

    # --------------------------------------------------------
    # Project files
    # --------------------------------------------------------

    if path.parent == Path("."):
        return "project"

    return "misc"


# ============================================================
# FILE NAME CLEANING
# ============================================================


def clean_filename(filepath):
    """
    Convert a filename into a readable commit-message name.
    """

    name = Path(filepath).stem

    return name.replace("_", " ").replace("-", " ").strip()


# ============================================================
# COMMIT MESSAGE GENERATION
# ============================================================


def get_commit_message(files):
    """
    Generate a commit message based on the changed files.
    """

    if not files:
        return "chore: repository maintenance"

    primary_file = files[0]

    category = get_category(primary_file)

    templates = COMMIT_TEMPLATES.get(
        category,
        COMMIT_TEMPLATES["misc"],
    )

    template = random.choice(templates)

    filename = clean_filename(primary_file)

    return template.format(file=filename)


# ============================================================
# GIT HELPERS
# ============================================================


def run_git(*args):
    """
    Execute a git command.
    """

    result = subprocess.run(
        ["git", *args],
        cwd=REPO_PATH,
        capture_output=True,
        text=True,
    )

    return result


def get_untracked_files():
    """
    Get untracked files.
    """

    result = run_git(
        "ls-files",
        "--others",
        "--exclude-standard",
    )

    return [f for f in result.stdout.splitlines() if f.strip()]


def get_modified_files():
    """
    Get modified tracked files.
    """

    result = run_git(
        "diff",
        "--name-only",
    )

    return [f for f in result.stdout.splitlines() if f.strip()]


def get_staged_files():
    """
    Get staged files.
    """

    result = run_git(
        "diff",
        "--cached",
        "--name-only",
    )

    return [f for f in result.stdout.splitlines() if f.strip()]


# ============================================================
# GROUP RELATED FILES
# ============================================================


def group_files(files):
    """
    Group related changes so a commit represents one logical
    piece of work rather than randomly mixing the repository.
    """

    groups = {
        "assets": [],
        "pipeline": [],
        "audio": [],
        "docs": [],
        "tests": [],
        "config": [],
        "output": [],
        "project": [],
        "misc": [],
    }

    for filepath in files:
        category = get_category(filepath)
        groups[category].append(filepath)

    return {category: items for category, items in groups.items() if items}


# ============================================================
# DISPLAY CHANGES
# ============================================================


def show_changes(groups):
    """
    Display detected repository changes.
    """

    print()
    print("=" * 70)
    print("Detected changes")
    print("=" * 70)

    total = 0

    for category, files in groups.items():
        print(f"\n[{category}]")

        for filepath in files:
            print(f"  - {filepath}")

        total += len(files)

    print()
    print(f"Total changed files: {total}")
    print("=" * 70)


# ============================================================
# CREATE COMMITS
# ============================================================


def create_commit(files, message):
    """
    Stage files and create a normal current-time commit.
    """

    for filepath in files:
        result = run_git(
            "add",
            filepath,
        )

        if result.returncode != 0:
            print(f"Failed to stage: {filepath}")
            return False

    result = run_git(
        "commit",
        "-m",
        message,
    )

    if result.returncode != 0:
        print()
        print("Git commit failed:")
        print(result.stderr)

        return False

    return True


# ============================================================
# MAIN
# ============================================================


def main():
    print()
    print("🎬 ToonToon Animation Generator")
    print("=" * 50)
    print(f"Repository: {REPO_PATH}")
    print()

    # --------------------------------------------------------
    # Verify repository
    # --------------------------------------------------------

    if not REPO_PATH.exists():
        print("❌ Repository does not exist.")
        return

    git_check = run_git(
        "rev-parse",
        "--is-inside-work-tree",
    )

    if git_check.returncode != 0:
        print("❌ This directory is not a Git repository.")
        return

    # --------------------------------------------------------
    # Get changes
    # --------------------------------------------------------

    untracked = get_untracked_files()
    modified = get_modified_files()
    staged = get_staged_files()

    all_files = sorted(set(untracked + modified + staged))

    if not all_files:
        print("✓ Working tree is clean.")
        print("Nothing to commit.")
        return

    # --------------------------------------------------------
    # Group changes
    # --------------------------------------------------------

    groups = group_files(all_files)

    show_changes(groups)

    # --------------------------------------------------------
    # Build proposed commits
    # --------------------------------------------------------

    proposed_commits = []

    for category, files in groups.items():
        if not files:
            continue

        # Keep large asset groups manageable.
        if category == "assets":
            # Group assets in small batches.
            for i in range(0, len(files), 20):
                batch = files[i : i + 20]

                message = get_commit_message(batch)

                proposed_commits.append((batch, message))

        else:
            message = get_commit_message(files)

            proposed_commits.append((files, message))

    # --------------------------------------------------------
    # Preview
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("Proposed commits")
    print("=" * 70)

    for index, (files, message) in enumerate(
        proposed_commits,
        start=1,
    ):
        print()
        print(f"{index}. {message}")

        for filepath in files:
            print(f"   └── {filepath}")

    print()
    print("=" * 70)

    # --------------------------------------------------------
    # Confirmation
    # --------------------------------------------------------

    response = input("\nCreate these commits? (y/n): ").strip().lower()

    if response != "y":
        print("❌ Cancelled.")
        return

    # --------------------------------------------------------
    # Commit
    # --------------------------------------------------------

    success = 0
    failed = 0

    print()

    for index, (files, message) in enumerate(
        proposed_commits,
        start=1,
    ):
        print(f"[{index}/{len(proposed_commits)}] {message}")

        if create_commit(files, message):
            success += 1
            print("  ✓ committed")

        else:
            failed += 1
            print("  ✗ failed")

    # --------------------------------------------------------
    # Final statistics
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("Commit Summary")
    print("=" * 70)

    print(f"Successful: {success}")
    print(f"Failed:     {failed}")

    print()
    print("Latest commits:")

    result = run_git(
        "log",
        "--oneline",
        "-10",
    )

    print(result.stdout)

    print("=" * 70)


if __name__ == "__main__":
    main()

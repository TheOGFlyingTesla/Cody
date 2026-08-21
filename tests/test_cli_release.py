from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import re
import stat
import zipfile

from support import SKILL_ROOT, initialize_git, tree_hash


LAUNCHER = SKILL_ROOT / "scripts/coordinator_standard.py"
BUILDER = SKILL_ROOT / "scripts/build_release.py"
INSTALLER = SKILL_ROOT / "scripts/install_skill.py"


def _prepare_release() -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    context = tempfile.TemporaryDirectory(prefix="cody-release-fixture-")
    source = Path(context.name) / "source"
    shutil.copytree(
        SKILL_ROOT,
        source,
        ignore=shutil.ignore_patterns(
            ".DS_Store", "__pycache__", "*.pyc", "release_manifest.json", "SHA256SUMS"
        ),
    )
    import importlib.util

    spec = importlib.util.spec_from_file_location("cody_build_release_fixture", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    archive = Path(context.name) / "cody-coordinator-0.2.0.zip"
    module.build_release(source, archive, check=False)
    root = Path(context.name) / "cody-coordinator"
    root.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(root)
    module.verify_checksums(root)
    return context, root, archive


RELEASE_CONTEXT, RELEASE_ROOT, RELEASE_ZIP = _prepare_release()


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = tempfile.TemporaryDirectory()
        self.temp = Path(self.context.name)

    def tearDown(self) -> None:
        self.context.cleanup()

    def run_cli(self, repo: Path, command: str, *arguments: str, output_format: str = "json"):
        return subprocess.run(
            [
                "python3",
                str(LAUNCHER),
                "--repo",
                str(repo),
                "--format",
                output_format,
                command,
                *arguments,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def test_help_lists_every_stable_command(self) -> None:
        result = subprocess.run(
            ["python3", str(LAUNCHER), "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode)
        text = result.stdout.decode()
        for command in (
            "inspect",
            "init",
            "upgrade",
            "doctor",
            "reconcile",
            "recover",
            "check-current",
        ):
            self.assertIn(command, text)

    def test_skill_launchers_do_not_write_bytecode_into_their_installation(self) -> None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}
        }
        copied = self.temp / "cody-coordinator"
        shutil.copytree(
            SKILL_ROOT / "scripts",
            copied / "scripts",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        result = subprocess.run(
            ["python3", str(copied / "scripts" / "coordinator_standard.py"), "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(list(copied.rglob("__pycache__")))
        self.assertFalse(list(copied.rglob("*.pyc")))

    def test_json_and_human_commands_cover_setup_doctor_and_current(self) -> None:
        repo = self.temp / "cli-project"
        repo.mkdir()
        inspected = self.run_cli(repo, "inspect")
        self.assertEqual(0, inspected.returncode, inspected.stderr)
        self.assertEqual("inspect", json.loads(inspected.stdout)["command"])

        checked = self.run_cli(repo, "init", "--check")
        self.assertEqual(0, checked.returncode, checked.stdout)
        self.assertFalse((repo / ".git").exists())

        initialized = self.run_cli(repo, "init", output_format="human")
        self.assertEqual(0, initialized.returncode, initialized.stdout)
        self.assertTrue(initialized.stdout.startswith(b"OK"))
        self.assertEqual(b"", initialized.stderr)

        doctor = self.run_cli(repo, "doctor")
        current = self.run_cli(repo, "check-current")
        self.assertTrue(json.loads(doctor.stdout)["ok"])
        self.assertTrue(json.loads(current.stdout)["metadata"]["current"])

    def test_expected_blocker_uses_stable_exit_and_never_stderr(self) -> None:
        repo = self.temp / "nonempty"
        repo.mkdir()
        (repo / "app.txt").write_text("product\n", encoding="utf-8")
        result = self.run_cli(repo, "init")
        payload = json.loads(result.stdout)
        self.assertEqual(2, result.returncode)
        self.assertEqual("repository_boundary_decision_required", payload["blockers"][0]["code"])
        self.assertEqual(b"", result.stderr)

    def test_hostile_credential_filename_never_reaches_cli_output(self) -> None:
        repo = self.temp / "credential-path"
        repo.mkdir()
        initialize_git(repo, commit=True)
        sentinel = "gh" + "p_abcdef0123456789abcdef0123456789"
        (repo / "docs/codex").mkdir(parents=True)
        (repo / "docs/codex" / f"CUSTOM-{sentinel}.md").write_text(
            "unknown\n", encoding="utf-8"
        )
        result = self.run_cli(repo, "upgrade")
        combined = result.stdout + result.stderr
        self.assertNotIn(sentinel.encode(), combined)

    def test_check_current_malformed_installation_is_invalid_not_success(self) -> None:
        repo = self.temp / "malformed-current"
        repo.mkdir()
        initialized = self.run_cli(repo, "init")
        self.assertEqual(0, initialized.returncode, initialized.stdout)
        (repo / "docs/codex/STANDARD.json").write_text("{broken\n", encoding="utf-8")

        result = self.run_cli(repo, "check-current")
        payload = json.loads(result.stdout)

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["metadata"]["current"])
        self.assertEqual(3, result.returncode)

    def test_inspect_recursively_redacts_git_controlled_names(self) -> None:
        repo = self.temp / "git-name-redaction"
        initialize_git(repo, commit=True)
        sentinel = "gh" + "p_abcdef0123456789abcdef0123456789"
        (repo / f"untracked-{sentinel}.txt").write_text("safe\n", encoding="utf-8")

        result = self.run_cli(repo, "inspect")

        self.assertEqual(0, result.returncode)
        self.assertNotIn(sentinel.encode(), result.stdout + result.stderr)


class SkillPackageTests(unittest.TestCase):
    def test_windows_preview_uses_one_python_assertion_harness(self) -> None:
        workflow = (SKILL_ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("shell: python", workflow)
        self.assertIn("def run_json(*arguments):", workflow)
        self.assertIn('mutation_payload["blockers"][0]["code"]', workflow)
        self.assertNotIn("%ERRORLEVEL%", workflow)

    def test_coordinator_requires_explicit_skill_invocation(self) -> None:
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", metadata)

    def test_skill_frontmatter_triggers_and_progressive_disclosure(self) -> None:
        path = SKILL_ROOT / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: cody-coordinator\n"))
        frontmatter = text.split("---", 2)[1].lower()
        for trigger in ("set up", "upgrade", "take over", "status"):
            self.assertIn(trigger, frontmatter)
        self.assertLess(len(text.split()), 700)
        self.assertNotRegex(text.lower(), r"\bgpt[- ]?\d|\bmodel[- ]?\d")

    def test_skill_links_resolve_and_operating_contract_is_explicit(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        links = re.findall(r"\]\((references/[^)]+)\)", text)
        self.assertEqual(7, len(set(links)))
        for relative in links:
            self.assertTrue((SKILL_ROOT / relative).is_file(), relative)
        required = (
            "<Project Name> — Coordinator",
            "attempt to pin",
            "explicitly asks",
            "native task metadata",
            "unavailable",
            "directly into this coordinator",
            "$SKILL_ROOT/scripts/coordinator_standard.py",
        )
        for phrase in required:
            self.assertIn(phrase, text)

    def test_references_cover_authority_recovery_and_completion(self) -> None:
        combined = " ".join(
            "\n".join(
                path.read_text(encoding="utf-8")
                for path in sorted((SKILL_ROOT / "references").glob("*.md"))
            ).lower().split()
        )
        for phrase in (
            "**project owner:**",
            "git/worktree evidence",
            "verified, inferred, unknown, stale, or conflicting",
            "p0/p1 status",
            "preserve every byte outside it",
            "project owner is never the message bus",
        ):
            self.assertIn(phrase, combined)


class DocumentationTests(unittest.TestCase):
    def test_behavioral_evidence_map_points_to_real_test_modules(self) -> None:
        document = (RELEASE_ROOT / "docs/BEHAVIORAL_CHECKS.md").read_text(
            encoding="utf-8"
        )
        referenced = set(re.findall(r"`(tests/test_[^`]+\.py)`", document))
        self.assertGreaterEqual(len(referenced), 6)
        for relative in referenced:
            self.assertTrue((SKILL_ROOT / relative).is_file(), relative)
        self.assertIn(
            "does not replace the executable tests",
            " ".join(document.split()),
        )

    def test_adoption_policy_is_opt_in_and_makes_no_pilot_claim(self) -> None:
        policy = (RELEASE_ROOT / "docs/ADOPTION.md").read_text(encoding="utf-8")
        self.assertIn("does not include telemetry", policy)
        self.assertIn("explicit permission", policy)
        self.assertIn("no claimed mobile/cloud pilot", policy)
        self.assertIn("not yet collected", policy)

    def test_user_entry_phrases_and_mutation_boundaries_are_explicit(self) -> None:
        documents = {
            path.name: path.read_text(encoding="utf-8")
            for path in RELEASE_ROOT.glob("*.md")
        }
        combined = " ".join("\n".join(documents.values()).split())
        for phrase in (
            "Set up this repository with its coordinator standard.",
            "Upgrade this repository to its current coordinator standard.",
            "Take over as coordinator for this repository.",
            "Where do we stand?",
        ):
            self.assertIn(phrase, combined)
        for boundary in ("commit", "push", "deploy", "secret", "billing"):
            self.assertIn(boundary, combined.lower())
        self.assertIn("attempt to pin", combined)
        self.assertIn("native metadata is unavailable", combined)
        self.assertNotIn("copy the worker handoff", combined.lower())

    def test_install_update_and_uninstall_commands_are_exact(self) -> None:
        text = (RELEASE_ROOT / "docs/INSTALLATION.md").read_text(
            encoding="utf-8"
        )
        for command in (
            "python3 scripts/install_skill.py --release-root . --check",
            "python3 scripts/install_skill.py --release-root .",
            'python3 "$HOME/.agents/skills/cody-coordinator/scripts/install_skill.py"',
            '--release-root "$HOME/.agents/skills/cody-coordinator" --uninstall --check',
            "--approve-removal <current-decision-token>",
        ):
            self.assertIn(command, text)
        self.assertRegex(text, r"\binstalled offline\b")


class ReleaseIntegrityTests(unittest.TestCase):
    def builder_module(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("coordinator_build_release", BUILDER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_manifest_checksums_and_archive_are_exact(self) -> None:
        manifest = json.loads(
            (RELEASE_ROOT / "release_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(1, manifest["schema_version"])
        self.assertEqual("0.2.0", manifest["standard_version"])
        self.assertIn("python>=3.11", manifest["runtime"])
        self.assertRegex(manifest["source_content_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(sorted(manifest["files"], key=lambda value: value.encode()), manifest["files"])
        checksum_text = (RELEASE_ROOT / "SHA256SUMS").read_text(encoding="utf-8")
        self.assertRegex(checksum_text, r"^(?:[0-9a-f]{64}  [^\n]+\n)+$")
        self.assertNotIn("  SHA256SUMS\n", checksum_text)
        builder = self.builder_module()
        checksums = builder.verify_checksums(RELEASE_ROOT)
        self.assertEqual(
            manifest["source_content_sha256"],
            builder.verify_source_content(RELEASE_ROOT, manifest),
        )
        builder.validate_archive(RELEASE_ZIP, checksums)
        with zipfile.ZipFile(RELEASE_ZIP) as archive:
            self.assertNotIn(".DS_Store", "\n".join(archive.namelist()))

    def test_builder_is_non_mutating_and_archive_is_allowlisted(self) -> None:
        builder = self.builder_module()
        with tempfile.TemporaryDirectory(prefix="cody-clean-export-") as directory:
            source = Path(directory) / "source"
            shutil.copytree(
                SKILL_ROOT,
                source,
                ignore=shutil.ignore_patterns(
                    ".DS_Store", "__pycache__", "*.pyc", "*.zip",
                    "release_manifest.json", "SHA256SUMS",
                ),
            )
            before = tree_hash(source)
            archive_path = Path(directory) / "cody-coordinator-0.2.0.zip"

            builder.build_release(source, archive_path, check=False)

            self.assertEqual(before, tree_hash(source))
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(
                    set(builder.RELEASE_ALLOWLIST)
                    | {builder.MANIFEST_NAME, builder.CHECKSUM_NAME},
                    set(archive.namelist()),
                )
                self.assertFalse(
                    any(
                        name.startswith(("tests/", "docs/codex/", ".github/"))
                        for name in archive.namelist()
                    )
                )

    def test_release_inventory_excludes_linked_worktree_git_pointer(self) -> None:
        builder = self.builder_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").write_text(
                "gitdir: /private/tmp/coordinator-worktrees/example\n",
                encoding="utf-8",
            )
            (root / "safe.txt").write_text("release content\n", encoding="utf-8")

            self.assertEqual(["safe.txt"], builder.inventory_release(root))

    def test_rebuilds_are_byte_identical(self) -> None:
        builder = self.builder_module()
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            first_root = temp / "first"
            second_root = temp / "second"
            shutil.copytree(RELEASE_ROOT, first_root, ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"))
            shutil.copytree(RELEASE_ROOT, second_root, ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"))
            first_zip = temp / "first.zip"
            second_zip = temp / "second.zip"
            builder.build_release(first_root, first_zip, check=False)
            builder.build_release(second_root, second_zip, check=False)
            self.assertEqual(first_zip.read_bytes(), second_zip.read_bytes())

    def test_archive_validator_rejects_traversal_and_symlink_members(self) -> None:
        builder = self.builder_module()
        checksums = {"safe.txt": "0" * 64}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            traversal = root / "traversal.zip"
            with zipfile.ZipFile(traversal, "w") as archive:
                info = zipfile.ZipInfo("../safe.txt")
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, b"content")
            with self.assertRaises(builder.ReleaseError):
                builder.validate_archive(traversal, checksums)

            symlink = root / "symlink.zip"
            with zipfile.ZipFile(symlink, "w") as archive:
                info = zipfile.ZipInfo("safe.txt")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, b"target")
            with self.assertRaises(builder.ReleaseError):
                builder.validate_archive(symlink, checksums)

    def test_manifest_identity_is_pinned_not_just_self_consistent(self) -> None:
        builder = self.builder_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "release"
            shutil.copytree(
                RELEASE_ROOT,
                root,
                ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"),
            )
            manifest_path = root / "release_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["standard_name"] = "not-cody-coordinator"
            manifest["standard_version"] = "99.0.0"
            manifest["runtime"] = "none"
            manifest["archive"] = "unknown"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            checksum_paths = builder.inventory_release(root)
            (root / "SHA256SUMS").write_bytes(
                builder._checksum_bytes(root, checksum_paths)
            )
            forged_zip = Path(directory) / "forged.zip"
            builder._write_zip(
                root,
                forged_zip,
                builder._sort_paths(set(checksum_paths) | {"SHA256SUMS"}),
            )

            with self.assertRaises(builder.ReleaseError):
                builder.build_release(root, forged_zip, check=True)

    def test_manifest_source_content_hash_rejects_rechecksummed_tampering(self) -> None:
        builder = self.builder_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "release"
            shutil.copytree(
                RELEASE_ROOT,
                root,
                ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"),
            )
            (root / "README.md").write_text("changed release source\n", encoding="utf-8")
            inventory = builder.inventory_release(root)
            (root / "SHA256SUMS").write_bytes(builder._checksum_bytes(root, inventory))

            with self.assertRaises(builder.ReleaseError):
                builder.verify_source_content(root)

    def test_manifest_rejects_unsafe_paths_before_source_hashing(self) -> None:
        builder = self.builder_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "schema_version": 1,
                "standard_name": "cody-coordinator",
                "standard_version": "0.2.0",
                "runtime": "python>=3.11; git>=2.39",
                "archive": "deterministic-zip-stored-v1",
                "source_content_sha256": "0" * 64,
                "files": ["/dev/zero"],
            }
            (root / "release_manifest.json").write_text(
                json.dumps(manifest) + "\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(builder.ReleaseError, "unsafe file path"):
                builder._load_manifest(root)

    def test_safe_extract_rejects_symlinked_member_parent(self) -> None:
        builder = self.builder_module()
        checksums = builder.verify_checksums(RELEASE_ROOT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "extract"
            outside = root / "outside"
            destination.mkdir()
            outside.mkdir()
            (destination / "scripts").symlink_to(
                outside, target_is_directory=True
            )

            with self.assertRaises(builder.ReleaseError):
                builder.safe_extract(RELEASE_ZIP, destination, checksums)

            self.assertFalse((outside / "SKILL.md").exists())

    def test_safe_extract_rejects_symlinked_destination_ancestor(self) -> None:
        builder = self.builder_module()
        checksums = builder.verify_checksums(RELEASE_ROOT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            (root / "link").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(builder.ReleaseError):
                builder.safe_extract(
                    RELEASE_ZIP, root / "link/extracted", checksums
                )

            self.assertFalse((outside / "extracted").exists())

    def test_safe_extract_positive_path_writes_exact_release(self) -> None:
        builder = self.builder_module()
        checksums = builder.verify_checksums(RELEASE_ROOT)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "extracted"
            builder.safe_extract(RELEASE_ZIP, destination, checksums)
            self.assertEqual(
                (RELEASE_ROOT / "SKILL.md").read_bytes(),
                (destination / "SKILL.md").read_bytes(),
            )

    def test_safe_extract_uses_one_validated_archive_handle(self) -> None:
        builder = self.builder_module()
        checksums = builder.verify_checksums(RELEASE_ROOT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate.zip"
            replacement = root / "replacement.zip"
            shutil.copyfile(RELEASE_ZIP, candidate)
            with zipfile.ZipFile(RELEASE_ZIP, "r") as source, zipfile.ZipFile(
                replacement, "w", compression=zipfile.ZIP_STORED
            ) as output:
                for info in source.infolist():
                    content = source.read(info)
                    if info.filename == "SKILL.md":
                        content = b"modified after validation\n"
                    output.writestr(info, content)
            real_validate = builder._validate_archive_handle
            swapped = False

            def validate_then_swap(archive, expected):
                nonlocal swapped
                real_validate(archive, expected)
                if not swapped:
                    swapped = True
                    os.replace(replacement, candidate)

            destination = root / "extracted"
            with mock.patch.object(
                builder, "_validate_archive_handle", side_effect=validate_then_swap
            ):
                builder.safe_extract(candidate, destination, checksums)

            self.assertEqual(
                (RELEASE_ROOT / "SKILL.md").read_bytes(),
                (destination / "SKILL.md").read_bytes(),
            )

    def test_archive_validator_rejects_deflated_members(self) -> None:
        builder = self.builder_module()
        content = b"safe content\n"
        digest = __import__("hashlib").sha256(content).hexdigest()
        checksum_content = f"{digest}  safe.txt\n".encode()
        checksums = {"safe.txt": digest}
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "deflated.zip"
            with zipfile.ZipFile(
                archive_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for name, value in (
                    ("safe.txt", content),
                    ("SHA256SUMS", checksum_content),
                ):
                    info = zipfile.ZipInfo(name)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    archive.writestr(info, value)

            with self.assertRaises(builder.ReleaseError):
                builder.validate_archive(archive_path, checksums)

    def test_release_scanner_rejects_generic_tokens_private_keys_and_finder_metadata(self) -> None:
        builder = self.builder_module()
        cases = (
            ("token.txt", ("sk-" + "a" * 24).encode()),
            ("password.txt", b"PASSWORD=hunter2\n"),
            ("api-key.txt", b"API_KEY=abc123\n"),
            ("secret.txt", b"SECRET=supersecretvalue\n"),
            ("opaque-token.txt", b"TOKEN=opaque-sensitive-value\n"),
            ("indented-yaml-password.txt", b"  password: hunter2\n"),
            ("exported-password.txt", b"export PASSWORD=hunter2\n"),
            (
                "authorization.txt",
                ("Authorization: Bearer " + "eyJ" + "a" * 30 + "\n").encode(),
            ),
            (
                "private-key.txt",
                (
                    "-----BEGIN RSA "
                    + "PRIVATE KEY-----\nfixture\n-----END RSA PRIVATE KEY-----\n"
                ).encode(),
            ),
        )
        for name, content in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / name).write_bytes(content)
                with self.assertRaises(builder.ReleaseError):
                    builder.inventory_release(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".DS_Store").write_bytes(b"finder metadata")
            self.assertEqual([], builder.inventory_release(root))

    def test_builder_cli_redacts_credential_bearing_member_name(self) -> None:
        sentinel = "eyJ" + "b" * 30
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "release"
            root.mkdir()
            hostile = root / f"Authorization: Bearer {sentinel}.txt"
            hostile.write_bytes(("sk-" + "c" * 24).encode())
            result = subprocess.run(
                [
                    "python3",
                    str(BUILDER),
                    "--release-root",
                    str(root),
                    "--output",
                    str(Path(directory) / "out.zip"),
                    "--check",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertNotEqual(0, result.returncode)
        self.assertNotIn(sentinel, result.stdout.decode())
        self.assertNotIn(sentinel, result.stderr.decode())

    def test_archive_validator_rejects_nondeterministic_archive_comment(self) -> None:
        builder = self.builder_module()
        checksums = builder.verify_checksums(RELEASE_ROOT)
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "commented.zip"
            shutil.copyfile(RELEASE_ZIP, candidate)
            with zipfile.ZipFile(candidate, "a") as archive:
                archive.comment = b"not deterministic"
            with self.assertRaises(builder.ReleaseError):
                builder.validate_archive(candidate, checksums)


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = tempfile.TemporaryDirectory()
        self.temp = Path(self.context.name)
        self.user_home = self.temp / "user-home"
        self.user_home.mkdir(mode=0o700)
        self.home = self.user_home / ".agents"
        self.home.mkdir(mode=0o700)
        self.environment = {
            **os.environ,
            "HOME": str(self.user_home),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def tearDown(self) -> None:
        self.context.cleanup()

    def run_installer(
        self, *arguments: str, release_root: Path = RELEASE_ROOT
    ):
        return subprocess.run(
            ["python3", str(INSTALLER), "--release-root", str(release_root), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=self.environment,
        )

    def test_installer_does_not_mutate_its_verified_bundle_with_bytecode(self) -> None:
        environment = {
            key: value
            for key, value in self.environment.items()
            if key not in {"PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}
        }
        bundle = self.temp / "verified-bundle"
        shutil.copytree(
            RELEASE_ROOT,
            bundle,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

        result = subprocess.run(
            [
                "python3",
                str(bundle / "scripts/install_skill.py"),
                "--release-root",
                str(bundle),
                "--check",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse(list(bundle.rglob("__pycache__")))
        self.assertFalse(list(bundle.rglob("*.pyc")))

    def test_first_install_exact_noop_and_uninstall_token(self) -> None:
        checked = self.run_installer("--check")
        self.assertEqual(0, checked.returncode, checked.stdout)
        preview = json.loads(checked.stdout)
        self.assertTrue(preview["changed"])
        self.assertEqual("user-agents-home", preview["installation_scope"])
        self.assertEqual("HOME/.agents/skills/cody-coordinator", preview["discovery_path"])
        missing = self.run_installer("--verify-discovery")
        self.assertEqual(2, missing.returncode)
        self.assertEqual("discovery_not_found", json.loads(missing.stdout)["code"])
        self.assertFalse((self.home / "skills/cody-coordinator").exists())

        installed = self.run_installer()
        self.assertEqual(0, installed.returncode, installed.stdout)
        stable = self.home / "skills/cody-coordinator"
        self.assertTrue(stable.is_symlink())
        discovery = self.run_installer("--verify-discovery")
        self.assertEqual(0, discovery.returncode, discovery.stdout)
        self.assertEqual("discovery-path-verified", json.loads(discovery.stdout)["action"])
        repeated = self.run_installer()
        self.assertEqual("already-installed", json.loads(repeated.stdout)["action"])

        installed_installer = stable / "scripts/install_skill.py"
        installed_base = [
            "python3",
            str(installed_installer),
            "--release-root",
            str(stable),
            "--uninstall",
        ]
        removal = subprocess.run(
            [*installed_base, "--check"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=self.environment,
        )
        payload = json.loads(removal.stdout)
        self.assertEqual(2, removal.returncode)
        token = payload["decision_token"]
        removed = subprocess.run(
            [*installed_base, "--approve-removal", token],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=self.environment,
        )
        self.assertEqual(0, removed.returncode, removed.stdout)
        self.assertFalse(stable.exists())

    def test_replacement_keeps_prior_immutable_31_store_untouched(self) -> None:
        store = self.home / "coordinator-standards/cody-coordinator"
        old_target = store / ("3.1.0-" + "a" * 64)
        old_target.mkdir(parents=True)
        old_bytes = b"immutable 3.1 evidence\n"
        (old_target / "VERSION").write_bytes(old_bytes)
        stable = self.home / "skills/cody-coordinator"
        stable.parent.mkdir(parents=True)
        stable.symlink_to(
            "../coordinator-standards/cody-coordinator/" + old_target.name
        )

        checked = self.run_installer("--check")
        self.assertEqual(2, checked.returncode)
        payload = json.loads(checked.stdout)
        self.assertEqual("stable_link_conflict", payload["code"])
        installed = self.run_installer(
            "--approve-replacement", payload["decision_token"]
        )

        self.assertEqual(0, installed.returncode, installed.stdout)
        self.assertTrue(stable.resolve(strict=True).name.startswith("0.2.0-"))
        self.assertEqual(old_bytes, (old_target / "VERSION").read_bytes())

    def test_unknown_stable_path_and_tampered_store_fail_closed(self) -> None:
        stable = self.home / "skills/cody-coordinator"
        stable.parent.mkdir(parents=True)
        stable.write_text("unknown install\n", encoding="utf-8")
        conflict = self.run_installer("--check")
        self.assertEqual("unknown_stable_path", json.loads(conflict.stdout)["code"])
        self.assertEqual("unknown install\n", stable.read_text(encoding="utf-8"))

        stable.unlink()
        installed = self.run_installer()
        self.assertEqual(0, installed.returncode, installed.stdout)
        target = stable.resolve(strict=True)
        (target / "VERSION").write_text("tampered\n", encoding="utf-8")
        tampered = self.run_installer("--check")
        self.assertEqual(2, tampered.returncode)
        self.assertEqual("content_address_conflict", json.loads(tampered.stdout)["code"])

    def test_quick_validate_runs_archive_only_install_and_inspection(self) -> None:
        quick_validate = SKILL_ROOT / "scripts/quick_validate.py"
        result = subprocess.run(
            ["python3", str(quick_validate), "--release-root", str(RELEASE_ROOT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("archive-only-quick-validation-passed", payload["action"])
        self.assertRegex(payload["archive_sha256"], r"^[0-9a-f]{64}$")

    def test_quick_validate_consumes_the_exact_candidate_archive(self) -> None:
        import build_release

        expected = build_release._sha256(RELEASE_ZIP)
        result = subprocess.run(
            [
                "python3",
                str(SKILL_ROOT / "scripts/quick_validate.py"),
                "--archive",
                str(RELEASE_ZIP),
                "--expected-sha256",
                expected,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(expected, json.loads(result.stdout)["archive_sha256"])

    def test_quick_validate_archive_requires_external_sha256(self) -> None:
        result = subprocess.run(
            [
                "python3",
                str(SKILL_ROOT / "scripts/quick_validate.py"),
                "--archive",
                str(RELEASE_ZIP),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("requires --expected-sha256", json.loads(result.stdout)["error"])

    def test_quick_validate_pins_archive_bytes_before_validation(self) -> None:
        import build_release
        import quick_validate

        source = self.temp / "replaceable.zip"
        pinned = self.temp / "pinned.zip"
        original = RELEASE_ZIP.read_bytes()
        source.write_bytes(original)

        digest = quick_validate._pin_archive(source, pinned)
        source.write_bytes(b"replacement")

        self.assertEqual(build_release._sha256(RELEASE_ZIP), digest)
        self.assertEqual(original, pinned.read_bytes())

    def test_symlinked_install_parent_cannot_escape_agents_home(self) -> None:
        outside = self.temp / "outside"
        outside.mkdir()
        (self.home / "coordinator-standards").symlink_to(
            outside, target_is_directory=True
        )

        result = self.run_installer("--check")

        self.assertEqual(2, result.returncode)
        self.assertEqual("unsafe_install_parent", json.loads(result.stdout)["code"])
        self.assertEqual([], list(outside.iterdir()))

    def test_regular_file_install_parent_fails_in_check_without_path_leak(self) -> None:
        blocked = self.home / "skills"
        blocked.write_text("not a directory\n", encoding="utf-8")

        result = self.run_installer("--check")

        self.assertEqual(2, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("unsafe_install_parent", payload["code"])
        self.assertNotIn(str(self.home), result.stdout.decode())
        self.assertEqual(b"", result.stderr)

    def test_installer_pins_manifest_inventory_and_version_identity(self) -> None:
        import build_release

        for case in ("manifest", "version"):
            with self.subTest(case=case):
                root = self.temp / f"release-{case}"
                shutil.copytree(
                    RELEASE_ROOT,
                    root,
                    ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"),
                )
                if case == "manifest":
                    manifest_path = root / "release_manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["standard_name"] = "foreign-standard"
                    manifest_path.write_text(
                        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
                    )
                else:
                    (root / "VERSION").write_text(
                        "99.0.0\n", encoding="utf-8"
                    )
                inventory = build_release.inventory_release(root)
                (root / "SHA256SUMS").write_bytes(
                    build_release._checksum_bytes(root, inventory)
                )

                result = self.run_installer("--check", release_root=root)

                self.assertEqual(2, result.returncode)
                self.assertEqual("invalid_release", json.loads(result.stdout)["code"])

    def test_install_parent_identity_swap_is_detected_before_copy(self) -> None:
        import install_skill

        original = install_skill._open_chain_fd
        moved = self.temp / "moved-store"
        escape = self.temp / "escape"
        escape.mkdir()
        swapped = False

        def swapping_open_chain(home_fd, components, *, create):
            nonlocal swapped
            result = original(home_fd, components, create=create)
            if create and components[0] == "coordinator-standards" and not swapped:
                swapped = True
                store = self.home / "coordinator-standards"
                store.rename(moved)
                store.symlink_to(escape, target_is_directory=True)
            return result

        with mock.patch.dict(os.environ, {"HOME": str(self.user_home)}), mock.patch.object(
            install_skill,
            "_open_chain_fd",
            side_effect=swapping_open_chain,
        ):
            with self.assertRaises(install_skill.InstallError) as caught:
                install_skill.install(RELEASE_ROOT, check=False, approval=None)

        self.assertEqual("link_verification_failed", caught.exception.code)
        self.assertEqual([], list(escape.rglob("SKILL.md")))
        self.assertTrue(list(moved.rglob("SKILL.md")))


if __name__ == "__main__":
    unittest.main()

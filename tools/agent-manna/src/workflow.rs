//! Canonical Manna and handoff workflow scaffolding.
//!
//! A strict board is one recoverable state machine. `.manna/` owns lifecycle
//! state, `.handoff/` owns bound work orders, and an ignored transaction
//! journal closes the small crash window between those two filesystems.

use std::collections::{HashMap, HashSet};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::Command;

use chrono::Utc;
use rand::{rngs::OsRng, RngCore};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::error::MannaError;
use crate::issue::{
    Issue, IssueStatus, IssueType, LegacyMigrationAnnotation, LegacyMigrationDisposition,
    SessionIdentity,
};
use crate::reconcile::prompt_pointer;
use crate::store::MannaStore;

pub const WORKFLOW_VERSION: u32 = 2;
pub const HANDOFF_DIR: &str = ".handoff";
pub const WORKFLOW_FILE: &str = ".manna/workflow.yaml";
pub const BOARD_FILE: &str = ".manna/board.yaml";
pub const HANDOFF_README: &str = ".handoff/README.md";
pub const HANDOFF_ARCHIVE_DIR: &str = ".handoff/.archive";
const TRANSACTION_DIR: &str = ".manna/transactions";
const LEGACY_MIGRATION_TRANSACTION: &str = ".manna/transactions/legacy-board-migration.yaml";
const LEGACY_MIGRATION_VERSION: u32 = 1;

const README_CONTENT: &str = r#"# agent-do handoffs

This directory is generated workflow state. `.manna/` owns status, tracks,
claims, and blockers. Each actionable Manna item owns exactly one Markdown
work order here, and the two are content-bound.

Rules:

- Create work through `agent-do manna create`; do not hand-build parallel
  prompt roots such as `.handoffs/`, `.dev/session-prompts/`, or
  `<campaign>/handoff-prompts/`.
- The Manna item `prompt` field points to `.handoff/mn-xxxxxx-<slug>.md`.
- Frontmatter identifies the item, track, source, base commit, scope, inputs,
  and SHA-256 binding for the complete document.
- Edit a work order, then run `agent-do manna handoff seal mn-xxxxxx` before
  claiming it. A claim fails closed on any unsealed change.
- Board state stays in Manna. The handoff contains scope, authority,
  deliverables, and verification, never a second backlog.
- Commit `.manna/workflow.yaml`, `.manna/issues.jsonl`, and `.handoff/`.
"#;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WorkflowConfig {
    pub version: u32,
    pub handoff_dir: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum BoardMode {
    Strict,
    Legacy,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct BoardConfig {
    version: u32,
    workflow: BoardMode,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    migrated_from_legacy_at: Option<chrono::DateTime<Utc>>,
}

impl BoardConfig {
    fn strict() -> Self {
        BoardConfig {
            version: 1,
            workflow: BoardMode::Strict,
            migrated_from_legacy_at: None,
        }
    }

    fn legacy() -> Self {
        BoardConfig {
            version: 1,
            workflow: BoardMode::Legacy,
            migrated_from_legacy_at: None,
        }
    }
}

impl Default for WorkflowConfig {
    fn default() -> Self {
        WorkflowConfig {
            version: WORKFLOW_VERSION,
            handoff_dir: HANDOFF_DIR.to_string(),
        }
    }
}

impl WorkflowConfig {
    fn validate_loadable(&self) -> Result<(), String> {
        if !(1..=WORKFLOW_VERSION).contains(&self.version) {
            return Err(format!(
                "unsupported Manna workflow version {} (current {})",
                self.version, WORKFLOW_VERSION
            ));
        }
        if self.handoff_dir != HANDOFF_DIR {
            return Err(format!(
                "workflow handoff_dir must be {}, got {}",
                HANDOFF_DIR, self.handoff_dir
            ));
        }
        Ok(())
    }

    pub fn validate(&self) -> Result<(), String> {
        self.validate_loadable()?;
        if self.version != WORKFLOW_VERSION {
            return Err(format!(
                "Manna workflow version {} must be upgraded to {}; run `agent-do manna init`",
                self.version, WORKFLOW_VERSION
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct WorkflowInit {
    pub config: WorkflowConfig,
    pub gitignore_updated: bool,
    pub upgraded_items: usize,
    pub restored_config: bool,
    pub recovered_transactions: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct HandoffFrontmatter {
    workflow: u32,
    manna: String,
    track: Option<String>,
    source: Option<String>,
    base_commit: String,
    scope: String,
    inputs: Vec<String>,
    binding: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum PairAction {
    Create,
    Attach,
    Rebind,
    Detach,
    Delete,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PairTransaction {
    version: u32,
    action: PairAction,
    issue_id: String,
    before: Option<Issue>,
    after: Option<Issue>,
    handoff: String,
    archive: Option<String>,
    document: Option<String>,
    integrity: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct MigrationDocument {
    issue_id: String,
    handoff: String,
    document: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct LegacyBoardTransaction {
    version: u32,
    before: Vec<Issue>,
    after: Vec<Issue>,
    documents: Vec<MigrationDocument>,
    gitignore_before: Option<String>,
    gitignore_after: String,
    board_before: Option<String>,
    board_after: String,
    workflow_before: Option<String>,
    workflow_after: String,
    readme_before: Option<String>,
    readme_after: String,
    integrity: String,
}

#[derive(Debug, Clone)]
pub struct LegacyMigrationResult {
    pub migrated: bool,
    pub recovered_transaction: bool,
    pub paired_items: usize,
    pub historical_rows: usize,
    pub exempt_rows: usize,
    pub released_claims: usize,
}

#[derive(Debug, PartialEq, Eq)]
enum TransactionOutcome {
    Applied,
    DiscardedConflict(String),
}

pub fn workflow_path(base: &Path) -> PathBuf {
    base.join(WORKFLOW_FILE)
}

fn load_board_config(base: &Path) -> Result<Option<BoardConfig>, String> {
    let relative = safe_relative_path(base, Path::new(BOARD_FILE), true)?;
    let path = base.join(relative);
    if !path.is_file() {
        return Ok(None);
    }
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    let config: BoardConfig = serde_yaml::from_str(&text)
        .map_err(|error| format!("invalid {}: {}", path.display(), error))?;
    if config.version != 1 {
        return Err(format!(
            "unsupported Manna board identity version {}",
            config.version
        ));
    }
    Ok(Some(config))
}

fn write_board_config(base: &Path, config: &BoardConfig) -> Result<(), String> {
    let yaml = serde_yaml::to_string(config)
        .map_err(|error| format!("failed to serialize board identity: {}", error))?;
    let relative = safe_relative_path(base, Path::new(BOARD_FILE), true)?;
    atomic_write_replace(&base.join(relative), &yaml)
}

fn path_exists(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok()
}

fn reject_symlink(path: &Path, label: &str) -> Result<(), String> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            Err(format!("refusing symlinked {}: {}", label, path.display()))
        }
        Ok(_) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("failed to inspect {}: {}", path.display(), error)),
    }
}

fn normalize_relative(path: &Path) -> Result<PathBuf, String> {
    let mut clean = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Normal(value) => clean.push(value),
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(format!("handoff path must stay inside {}", HANDOFF_DIR));
            }
        }
    }
    Ok(clean)
}

fn safe_relative_path(
    base: &Path,
    relative: &Path,
    leaf_may_be_missing: bool,
) -> Result<PathBuf, String> {
    let relative = normalize_relative(relative)?;
    let root = base
        .canonicalize()
        .map_err(|error| format!("failed to resolve project root: {}", error))?;
    let mut cursor = base.to_path_buf();
    let component_count = relative.components().count();
    for (index, component) in relative.components().enumerate() {
        let Component::Normal(value) = component else {
            return Err(format!("unsafe workflow path: {}", relative.display()));
        };
        cursor.push(value);
        match fs::symlink_metadata(&cursor) {
            Ok(metadata) => {
                if metadata.file_type().is_symlink() {
                    return Err(format!(
                        "workflow path crosses a symlink: {}",
                        cursor.display()
                    ));
                }
                if index + 1 < component_count && !metadata.is_dir() {
                    return Err(format!(
                        "workflow parent is not a directory: {}",
                        cursor.display()
                    ));
                }
            }
            Err(error)
                if error.kind() == std::io::ErrorKind::NotFound
                    && (leaf_may_be_missing || index + 1 < component_count) => {}
            Err(error) => return Err(format!("failed to inspect {}: {}", cursor.display(), error)),
        }
    }
    if let Some(parent) = cursor.parent() {
        let existing_parent = if parent.exists() {
            parent.to_path_buf()
        } else {
            parent
                .ancestors()
                .find(|candidate| candidate.exists())
                .unwrap_or(base)
                .to_path_buf()
        };
        let resolved = existing_parent.canonicalize().map_err(|error| {
            format!("failed to resolve {}: {}", existing_parent.display(), error)
        })?;
        if !resolved.starts_with(&root) {
            return Err(format!(
                "workflow path escapes the project through {}",
                existing_parent.display()
            ));
        }
    }
    Ok(relative)
}

fn safe_create_dir_all(base: &Path, relative: &Path) -> Result<(), String> {
    let relative = normalize_relative(relative)?;
    let mut cursor = base.to_path_buf();
    for component in relative.components() {
        let Component::Normal(value) = component else {
            return Err(format!("unsafe workflow directory: {}", relative.display()));
        };
        cursor.push(value);
        reject_symlink(&cursor, "workflow directory")?;
        if !cursor.exists() {
            match fs::create_dir(&cursor) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => {
                    return Err(format!("failed to create {}: {}", cursor.display(), error))
                }
            }
        }
        if !cursor.is_dir() {
            return Err(format!(
                "workflow path is not a directory: {}",
                cursor.display()
            ));
        }
    }
    Ok(())
}

fn sync_parent(path: &Path) -> Result<(), String> {
    let Some(parent) = path.parent() else {
        return Ok(());
    };
    File::open(parent)
        .and_then(|file| file.sync_all())
        .map_err(|error| format!("failed to sync {}: {}", parent.display(), error))
}

fn atomic_write(path: &Path, contents: &[u8], replace: bool) -> Result<(), String> {
    reject_symlink(path, "workflow file")?;
    let parent = path
        .parent()
        .ok_or_else(|| format!("path has no parent: {}", path.display()))?;
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| format!("invalid file name: {}", path.display()))?;
    let temp = parent.join(format!(
        ".{}.{}.{}.tmp",
        name,
        std::process::id(),
        Utc::now().timestamp_nanos_opt().unwrap_or_default()
    ));
    reject_symlink(parent, "workflow parent")?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|error| format!("failed to create {}: {}", temp.display(), error))?;
    if let Err(error) = file.write_all(contents).and_then(|_| file.sync_all()) {
        let _ = fs::remove_file(&temp);
        return Err(format!("failed to write {}: {}", temp.display(), error));
    }
    drop(file);
    let install = if replace {
        fs::rename(&temp, path)
    } else {
        // A hard link is an atomic create-if-absent operation when source and
        // destination share a directory. Unlike an existence check followed
        // by rename, it cannot overwrite a transaction another process won.
        fs::hard_link(&temp, path).and_then(|_| fs::remove_file(&temp))
    };
    if let Err(error) = install {
        let _ = fs::remove_file(&temp);
        return Err(
            if !replace && error.kind() == std::io::ErrorKind::AlreadyExists {
                format!("refusing to overwrite existing file {}", path.display())
            } else {
                format!("failed to install {}: {}", path.display(), error)
            },
        );
    }
    sync_parent(path)
}

fn atomic_write_replace(path: &Path, contents: &str) -> Result<(), String> {
    atomic_write(path, contents.as_bytes(), true)
}

pub fn load_workflow(base: &Path) -> Result<Option<WorkflowConfig>, String> {
    let relative = safe_relative_path(base, Path::new(WORKFLOW_FILE), true)?;
    let path = base.join(relative);
    if !path.is_file() {
        return Ok(None);
    }
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    let config: WorkflowConfig = serde_yaml::from_str(&text)
        .map_err(|error| format!("invalid {}: {}", path.display(), error))?;
    config.validate_loadable()?;
    Ok(Some(config))
}

pub fn workflow_markers_present(_base: &Path, issues: &[Issue]) -> bool {
    issues.iter().any(|issue| {
        issue.handoff_digest.is_some()
            || issue.prompt.as_deref().is_some_and(|pointer| {
                normalize_relative(Path::new(pointer))
                    .is_ok_and(|path| path.starts_with(HANDOFF_DIR))
            })
    })
}

/// Load the board mode without permitting deletion of one config file to
/// downgrade a strict board to legacy behavior.
pub fn load_workflow_for_board(
    base: &Path,
    issues: &[Issue],
) -> Result<Option<WorkflowConfig>, String> {
    let board = load_board_config(base)?.ok_or_else(|| {
        "Manna board identity is missing; run `agent-do manna init` before using the board"
            .to_string()
    })?;
    match board.workflow {
        BoardMode::Strict => match load_workflow(base)? {
            Some(config) => {
                config.validate()?;
                Ok(Some(config))
            }
            None => Err(format!(
                "strict Manna board identity exists but {} is missing; run `agent-do manna init` to restore it",
                WORKFLOW_FILE
            )),
        },
        BoardMode::Legacy => {
            if load_workflow(base)?.is_some() || workflow_markers_present(base, issues) {
                return Err(
                    "legacy board identity conflicts with strict workflow state; run `agent-do manna migrate`"
                        .to_string(),
                );
            }
            Ok(None)
        }
    }
}

fn git_path_ignored(base: &Path, relative: &Path) -> Result<bool, String> {
    let inside = Command::new("git")
        .current_dir(base)
        .args(["rev-parse", "--is-inside-work-tree"])
        .output()
        .map_err(|error| format!("git rev-parse unavailable: {}", error))?;
    if !inside.status.success() || String::from_utf8_lossy(&inside.stdout).trim() != "true" {
        return Ok(false);
    }
    let output = Command::new("git")
        .current_dir(base)
        .args(["check-ignore", "--no-index", "--quiet", "--"])
        .arg(relative)
        .output()
        .map_err(|error| format!("git check-ignore unavailable: {}", error))?;
    match output.status.code() {
        Some(0) => Ok(true),
        Some(1) => Ok(false),
        code => Err(format!("git check-ignore failed with status {:?}", code)),
    }
}

fn durable_paths() -> [&'static str; 5] {
    [
        ".manna/issues.jsonl",
        ".manna/sessions.jsonl",
        BOARD_FILE,
        WORKFLOW_FILE,
        HANDOFF_README,
    ]
}

fn read_optional_text(path: &Path, label: &str) -> Result<Option<String>, String> {
    reject_symlink(path, label)?;
    match fs::read_to_string(path) {
        Ok(text) => Ok(Some(text)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!("failed to read {}: {}", path.display(), error)),
    }
}

fn workflow_gitignore_content(existing: &str) -> String {
    let marker = "# agent-do workflow: .manna and .handoff are durable state";
    if existing.contains(marker) && existing.lines().any(|line| line == "!.manna/board.yaml") {
        return existing.to_string();
    }

    let mut updated = existing.to_string();
    if !updated.is_empty() && !updated.ends_with('\n') {
        updated.push('\n');
    }
    if !existing.contains(marker) {
        updated.push_str(&format!(
            "\n{}\n!.manna/\n.manna/*\n!.manna/issues.jsonl\n!.manna/sessions.jsonl\n!.manna/board.yaml\n!.manna/workflow.yaml\n!.manna/drift.yaml\n.manna/board.lock\n.manna/transactions/\n!.handoff/\n!.handoff/**\n",
            marker
        ));
    } else {
        updated.push_str("!.manna/board.yaml\n.manna/transactions/\n");
    }
    updated
}

fn ensure_workflow_tracked(base: &Path) -> Result<bool, String> {
    let ignored_before = durable_paths()
        .into_iter()
        .map(|path| git_path_ignored(base, Path::new(path)))
        .collect::<Result<Vec<_>, _>>()?;
    if ignored_before.iter().all(|ignored| !ignored) {
        return Ok(false);
    }

    let gitignore = base.join(".gitignore");
    reject_symlink(&gitignore, ".gitignore")?;
    let existing = fs::read_to_string(&gitignore).unwrap_or_default();
    let updated = workflow_gitignore_content(&existing);
    if updated != existing {
        atomic_write_replace(&gitignore, &updated)?;
    }
    let still_ignored: Vec<&str> = durable_paths()
        .into_iter()
        .filter_map(|path| {
            git_path_ignored(base, Path::new(path))
                .ok()
                .filter(|ignored| *ignored)
                .map(|_| path)
        })
        .collect();
    if !still_ignored.is_empty() {
        return Err(format!(
            "durable Manna workflow state is still ignored by Git: {}",
            still_ignored.join(", ")
        ));
    }
    Ok(true)
}

fn validate_new_handoff_root(base: &Path) -> Result<(), String> {
    let handoff_dir = base.join(HANDOFF_DIR);
    reject_symlink(&handoff_dir, "handoff root")?;
    if !handoff_dir.is_dir() {
        return Ok(());
    }
    let mut entries = fs::read_dir(&handoff_dir)
        .map_err(|error| format!("failed to inspect {}: {}", handoff_dir.display(), error))?;
    let first = match entries.next() {
        None => return Ok(()),
        Some(Ok(entry)) => entry,
        Some(Err(error)) => {
            return Err(format!(
                "failed to inspect {}: {}",
                handoff_dir.display(),
                error
            ))
        }
    };
    if first.path() == base.join(HANDOFF_README)
        && entries.next().is_none()
        && first.path().is_file()
    {
        return Ok(());
    }
    Err(format!(
        "{} already contains non-workflow files; migrate or archive them before initializing a strict board",
        HANDOFF_DIR
    ))
}

fn current_base_commit(base: &Path) -> String {
    let output = Command::new("git")
        .current_dir(base)
        .args(["rev-parse", "--verify", "HEAD"])
        .output();
    match output {
        Ok(result) if result.status.success() => {
            String::from_utf8_lossy(&result.stdout).trim().to_string()
        }
        _ => "unborn".to_string(),
    }
}

pub fn slugify(title: &str) -> String {
    let mut slug = String::new();
    let mut pending_dash = false;
    for character in title.chars() {
        if character.is_ascii_alphanumeric() {
            if pending_dash && !slug.is_empty() {
                slug.push('-');
            }
            slug.push(character.to_ascii_lowercase());
            pending_dash = false;
            if slug.len() >= 64 {
                break;
            }
        } else if !slug.is_empty() {
            pending_dash = true;
        }
    }
    while slug.ends_with('-') {
        slug.pop();
    }
    if slug.is_empty() {
        "item".to_string()
    } else {
        slug
    }
}

pub fn canonical_handoff_path(
    base: &Path,
    config: &WorkflowConfig,
    issue: &Issue,
    requested: Option<&str>,
) -> Result<PathBuf, String> {
    config.validate()?;
    let relative = if let Some(raw) = requested.map(str::trim).filter(|path| !path.is_empty()) {
        let requested_path = Path::new(raw);
        if requested_path.is_absolute() {
            let base_abs = base
                .canonicalize()
                .map_err(|error| format!("failed to resolve project root: {}", error))?;
            requested_path
                .strip_prefix(&base_abs)
                .map_err(|_| format!("handoff path must live under {}/", HANDOFF_DIR))?
                .to_path_buf()
        } else {
            normalize_relative(requested_path)?
        }
    } else {
        Path::new(&config.handoff_dir).join(format!("{}-{}.md", issue.id, slugify(&issue.title)))
    };

    let relative = safe_relative_path(base, &relative, true)?;
    if !relative.starts_with(&config.handoff_dir)
        || relative
            .extension()
            .and_then(|extension| extension.to_str())
            != Some("md")
        || relative == Path::new(HANDOFF_README)
        || relative.starts_with(HANDOFF_ARCHIVE_DIR)
    {
        return Err(format!(
            "actionable item handoffs must be Markdown files under {}/",
            HANDOFF_DIR
        ));
    }
    Ok(relative)
}

fn split_handoff(text: &str) -> Result<(HandoffFrontmatter, &str), String> {
    let rest = text
        .strip_prefix("---\n")
        .ok_or_else(|| "handoff must begin with YAML frontmatter".to_string())?;
    let boundary = rest
        .find("\n---\n")
        .ok_or_else(|| "handoff frontmatter is not terminated".to_string())?;
    let yaml = &rest[..boundary];
    let body = &rest[boundary + 5..];
    let frontmatter: HandoffFrontmatter = serde_yaml::from_str(yaml)
        .map_err(|error| format!("invalid handoff frontmatter: {}", error))?;
    Ok((frontmatter, body))
}

fn binding_material(text: &str) -> Result<String, String> {
    let rest = text
        .strip_prefix("---\n")
        .ok_or_else(|| "handoff must begin with YAML frontmatter".to_string())?;
    let boundary = rest
        .find("\n---\n")
        .ok_or_else(|| "handoff frontmatter is not terminated".to_string())?;
    let yaml = &rest[..boundary];
    let mut binding_lines = 0;
    let normalized_yaml = yaml
        .lines()
        .map(|line| {
            if line.starts_with("binding:") {
                binding_lines += 1;
                "binding: ''".to_string()
            } else {
                line.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    if binding_lines != 1 {
        return Err("handoff frontmatter must contain exactly one binding field".to_string());
    }
    Ok(format!(
        "---\n{}\n---\n{}",
        normalized_yaml,
        &rest[boundary + 5..]
    ))
}

fn calculate_binding(text: &str) -> Result<String, String> {
    let material = binding_material(text)?;
    let digest = Sha256::digest(material.as_bytes());
    Ok(format!("sha256:{:x}", digest))
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right)
        .fold(0_u8, |difference, (left, right)| {
            difference | (left ^ right)
        })
        == 0
}

fn hmac_sha256(key: &[u8], message: &[u8]) -> [u8; 32] {
    const BLOCK: usize = 64;
    let mut normalized = [0_u8; BLOCK];
    if key.len() > BLOCK {
        normalized[..32].copy_from_slice(&Sha256::digest(key));
    } else {
        normalized[..key.len()].copy_from_slice(key);
    }
    let mut inner_pad = [0x36_u8; BLOCK];
    let mut outer_pad = [0x5c_u8; BLOCK];
    for index in 0..BLOCK {
        inner_pad[index] ^= normalized[index];
        outer_pad[index] ^= normalized[index];
    }
    let mut inner = Sha256::new();
    inner.update(inner_pad);
    inner.update(message);
    let inner_digest = inner.finalize();
    let mut outer = Sha256::new();
    outer.update(outer_pad);
    outer.update(inner_digest);
    outer.finalize().into()
}

fn transaction_material(base: &Path, transaction: &PairTransaction) -> Result<Vec<u8>, String> {
    let mut unsigned = transaction.clone();
    unsigned.integrity.clear();
    let project = base.canonicalize().map_err(|error| {
        format!(
            "failed to resolve project root {}: {}",
            base.display(),
            error
        )
    })?;
    let payload = serde_json::to_vec(&unsigned).map_err(|error| {
        format!(
            "failed to serialize transaction integrity material: {}",
            error
        )
    })?;
    let mut material = b"agent-do/manna/pair/v2\0".to_vec();
    material.extend_from_slice(project.to_string_lossy().as_bytes());
    material.push(0);
    material.extend_from_slice(&payload);
    Ok(material)
}

fn transaction_signature(
    base: &Path,
    key: &[u8],
    transaction: &PairTransaction,
) -> Result<String, String> {
    let digest = hmac_sha256(key, &transaction_material(base, transaction)?);
    let hex = digest
        .iter()
        .map(|byte| format!("{:02x}", byte))
        .collect::<String>();
    Ok(format!("hmac-sha256:{}", hex))
}

fn legacy_migration_path(base: &Path) -> PathBuf {
    base.join(LEGACY_MIGRATION_TRANSACTION)
}

fn legacy_migration_material(
    base: &Path,
    transaction: &LegacyBoardTransaction,
) -> Result<Vec<u8>, String> {
    let mut unsigned = transaction.clone();
    unsigned.integrity.clear();
    let project = base.canonicalize().map_err(|error| {
        format!(
            "failed to resolve project root {}: {}",
            base.display(),
            error
        )
    })?;
    let payload = serde_json::to_vec(&unsigned).map_err(|error| {
        format!(
            "failed to serialize legacy migration integrity material: {}",
            error
        )
    })?;
    let mut material = b"agent-do/manna/legacy-migration/v1\0".to_vec();
    material.extend_from_slice(project.to_string_lossy().as_bytes());
    material.push(0);
    material.extend_from_slice(&payload);
    Ok(material)
}

fn legacy_migration_signature(
    base: &Path,
    key: &[u8],
    transaction: &LegacyBoardTransaction,
) -> Result<String, String> {
    let digest = hmac_sha256(key, &legacy_migration_material(base, transaction)?);
    let hex = digest
        .iter()
        .map(|byte| format!("{:02x}", byte))
        .collect::<String>();
    Ok(format!("hmac-sha256:{}", hex))
}

fn resolve_missing_leaf(path: PathBuf) -> Result<PathBuf, String> {
    let name = path
        .file_name()
        .ok_or_else(|| format!("path has no file name: {}", path.display()))?
        .to_os_string();
    let parent = path
        .parent()
        .ok_or_else(|| format!("path has no parent: {}", path.display()))?;
    let existing = parent
        .ancestors()
        .find(|candidate| candidate.exists())
        .ok_or_else(|| format!("path has no existing ancestor: {}", path.display()))?;
    let canonical = existing
        .canonicalize()
        .map_err(|error| format!("failed to resolve {}: {}", existing.display(), error))?;
    let remainder = parent
        .strip_prefix(existing)
        .map_err(|_| format!("failed to normalize {}", path.display()))?;
    Ok(canonical.join(remainder).join(name))
}

fn recovery_key_path(base: &Path) -> Result<PathBuf, String> {
    let git = Command::new("git")
        .current_dir(base)
        .args(["rev-parse", "--absolute-git-dir"])
        .output()
        .map_err(|error| format!("failed to locate Git metadata: {}", error))?;
    if git.status.success() {
        let root = String::from_utf8_lossy(&git.stdout).trim().to_string();
        if root.is_empty() {
            return Err("Git returned an empty metadata directory".to_string());
        }
        return resolve_missing_leaf(
            PathBuf::from(root)
                .join("agent-do")
                .join("manna-recovery.key"),
        );
    }

    let home = std::env::var_os("AGENT_DO_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".agent-do")))
        .ok_or_else(|| {
            "cannot protect Manna recovery journals outside Git without AGENT_DO_HOME or HOME"
                .to_string()
        })?;
    let canonical = base
        .canonicalize()
        .map_err(|error| format!("failed to resolve project root: {}", error))?;
    let project = Sha256::digest(canonical.to_string_lossy().as_bytes());
    resolve_missing_leaf(
        home.join("manna")
            .join("recovery-keys")
            .join(format!("{:x}.key", project)),
    )
}

fn reject_symlink_components(path: &Path, label: &str) -> Result<(), String> {
    let mut cursor = PathBuf::new();
    for component in path.components() {
        cursor.push(component.as_os_str());
        match fs::symlink_metadata(&cursor) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(format!(
                    "refusing {} through symlink {}",
                    label,
                    cursor.display()
                ))
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => break,
            Err(error) => return Err(format!("failed to inspect {}: {}", cursor.display(), error)),
        }
    }
    Ok(())
}

fn read_private_key(path: &Path, label: &str) -> Result<Vec<u8>, String> {
    reject_symlink_components(path, label)?;
    let mut key = Vec::new();
    File::open(path)
        .and_then(|mut file| file.read_to_end(&mut key))
        .map_err(|error| format!("failed to read {} {}: {}", label, path.display(), error))?;
    if key.len() != 32 {
        return Err(format!(
            "{} {} has invalid length {}; expected 32 bytes",
            label,
            path.display(),
            key.len()
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = fs::metadata(path)
            .map_err(|error| format!("failed to inspect {}: {}", label, error))?
            .permissions()
            .mode();
        if mode & 0o077 != 0 {
            return Err(format!(
                "{} {} must not be readable by group or others",
                label,
                path.display()
            ));
        }
    }
    Ok(key)
}

fn load_private_key(path: &Path, create: bool, label: &str) -> Result<Vec<u8>, String> {
    if path.is_file() {
        return read_private_key(path, label);
    }
    if path_exists(path) {
        return Err(format!(
            "{} path is not a regular file: {}",
            label,
            path.display()
        ));
    }
    if !create {
        return Err(format!("{} {} is missing", label, path.display()));
    }
    let parent = path
        .parent()
        .ok_or_else(|| format!("{} has no parent: {}", label, path.display()))?;
    reject_symlink_components(parent, &format!("{} directory", label))?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("failed to create {}: {}", parent.display(), error))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(parent, fs::Permissions::from_mode(0o700))
            .map_err(|error| format!("failed to protect {}: {}", parent.display(), error))?;
    }

    let mut key = [0_u8; 32];
    OsRng.fill_bytes(&mut key);
    let mut nonce = [0_u8; 16];
    OsRng.fill_bytes(&mut nonce);
    let nonce = nonce
        .iter()
        .map(|byte| format!("{:02x}", byte))
        .collect::<String>();
    let temp = parent.join(format!(".manna-key.{}.{}.tmp", std::process::id(), nonce));
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&temp)
        .map_err(|error| format!("failed to create {}: {}", temp.display(), error))?;
    if let Err(error) = file.write_all(&key).and_then(|_| file.sync_all()) {
        let _ = fs::remove_file(&temp);
        return Err(format!("failed to write {}: {}", temp.display(), error));
    }
    drop(file);
    match fs::hard_link(&temp, path) {
        Ok(()) => {
            fs::remove_file(&temp)
                .map_err(|error| format!("failed to remove {}: {}", temp.display(), error))?;
            sync_parent(path)?;
            Ok(key.to_vec())
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            let _ = fs::remove_file(&temp);
            read_private_key(path, label)
        }
        Err(error) => {
            let _ = fs::remove_file(&temp);
            Err(format!(
                "failed to install {} {}: {}",
                label,
                path.display(),
                error
            ))
        }
    }
}

fn load_recovery_key(base: &Path, create: bool) -> Result<Vec<u8>, String> {
    let path = recovery_key_path(base)?;
    load_private_key(&path, create, "Manna recovery key").map_err(|error| {
        if !create && error.ends_with(" is missing") {
            format!(
                "pending Manna transaction cannot be authenticated because {}",
                error
            )
        } else {
            error
        }
    })
}

fn session_identity_key_path() -> Result<PathBuf, String> {
    let home = std::env::var_os("AGENT_DO_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".agent-do")))
        .ok_or_else(|| {
            "cannot derive host session ownership without AGENT_DO_HOME or HOME".to_string()
        })?;
    resolve_missing_leaf(home.join("manna").join("session-identity.key"))
}

fn compact_runtime_id(value: &str) -> String {
    value
        .chars()
        .filter(|character| character.is_ascii_alphanumeric())
        .flat_map(char::to_lowercase)
        .take(16)
        .collect()
}

pub fn runtime_session_label(runtime: &str, opaque_id: &str) -> Result<String, String> {
    let compact = compact_runtime_id(opaque_id);
    if compact.is_empty() {
        return Err(format!(
            "{} session identity is empty after normalization",
            runtime
        ));
    }
    Ok(format!("{}-{}", runtime, compact))
}

/// Derive an authenticated Manna identity from an opaque host-owned session
/// identifier. The public label matches agent-do coord, while the ownership
/// proof is an HMAC under a machine-local key outside the repository. Knowing
/// the visible label is therefore insufficient to forge lifecycle authority.
pub fn runtime_session_identity(runtime: &str, opaque_id: &str) -> Result<SessionIdentity, String> {
    let label = runtime_session_label(runtime, opaque_id)?;
    let key_path = session_identity_key_path()?;
    let key = load_private_key(&key_path, true, "Manna session identity key")?;
    let material = format!("agent-do/manna/session/v1\0{}\0{}", runtime, opaque_id);
    let proof = hmac_sha256(&key, material.as_bytes())
        .iter()
        .map(|byte| format!("{:02x}", byte))
        .collect::<String>();
    SessionIdentity::from_token(&label, &proof)
}

fn render_document(frontmatter: &HandoffFrontmatter, body: &str) -> Result<String, String> {
    let mut unsigned = frontmatter.clone();
    unsigned.binding.clear();
    let yaml = serde_yaml::to_string(&unsigned)
        .map_err(|error| format!("failed to serialize handoff frontmatter: {}", error))?;
    let unsigned_document = format!("---\n{}---\n{}", yaml, body);
    let binding = calculate_binding(&unsigned_document)?;
    let mut signed = frontmatter.clone();
    signed.binding = binding;
    let yaml = serde_yaml::to_string(&signed)
        .map_err(|error| format!("failed to serialize handoff frontmatter: {}", error))?;
    Ok(format!("---\n{}---\n{}", yaml, body))
}

fn generated_body(issue: &Issue) -> String {
    let work_order = issue
        .description
        .as_deref()
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .unwrap_or(&issue.title);
    let inputs = if let Some(source) = issue.source.as_deref() {
        format!("- {}", source)
    } else {
        "- None declared.".to_string()
    };
    format!(
        "\n# Handoff: {}\n\nBoard state is canonical in `.manna/`. This file is the work order for one item only.\n\n## Claim\n\n```bash\nagent-do manna claim {}\n```\n\n## Scope\n\n{}\n\n## Inputs\n\n{}\n\n## Work order\n\n{}\n\n## Completion\n\n1. Produce the scoped deliverables and verification receipts.\n2. Update this handoff only when continuation context changed.\n3. Seal changes with `agent-do manna handoff seal {}`.\n4. Commit with `Manna: {}` and run `agent-do manna done {}` only after the work is verified.\n",
        issue.title,
        issue.id,
        issue.title,
        inputs,
        work_order,
        issue.id,
        issue.id,
        issue.id
    )
}

fn frontmatter_for(base: &Path, issue: &Issue) -> HandoffFrontmatter {
    HandoffFrontmatter {
        workflow: WORKFLOW_VERSION,
        manna: issue.id.clone(),
        track: issue.track.clone(),
        source: issue.source.clone(),
        base_commit: current_base_commit(base),
        scope: issue.title.clone(),
        inputs: issue.source.iter().cloned().collect(),
        binding: String::new(),
    }
}

pub fn render_handoff(base: &Path, issue: &Issue) -> Result<String, String> {
    render_document(&frontmatter_for(base, issue), &generated_body(issue))
}

fn validate_document(issue: &Issue, text: &str) -> Result<String, String> {
    let (frontmatter, body) = split_handoff(text)?;
    if frontmatter.workflow != WORKFLOW_VERSION {
        return Err(format!(
            "handoff workflow version {} is not current {}",
            frontmatter.workflow, WORKFLOW_VERSION
        ));
    }
    if frontmatter.manna != issue.id {
        return Err(format!(
            "handoff frontmatter points to {}, expected {}",
            frontmatter.manna, issue.id
        ));
    }
    if frontmatter.track != issue.track {
        return Err("handoff track does not match the Manna item".to_string());
    }
    if frontmatter.source != issue.source {
        return Err("handoff source does not match the Manna item".to_string());
    }
    if frontmatter.inputs != issue.source.iter().cloned().collect::<Vec<_>>() {
        return Err("handoff inputs do not match the Manna item source".to_string());
    }
    if frontmatter.scope != issue.title {
        return Err("handoff scope does not match the Manna item title".to_string());
    }
    if frontmatter.base_commit.trim().is_empty() {
        return Err("handoff base_commit cannot be empty".to_string());
    }
    let expected_claim = format!(
        "## Claim\n\n```bash\nagent-do manna claim {}\n```",
        issue.id
    );
    if !body.contains(&expected_claim)
        || body
            .lines()
            .filter(|line| line.trim() == format!("agent-do manna claim {}", issue.id))
            .count()
            != 1
    {
        return Err(format!(
            "handoff Claim section must contain exactly `agent-do manna claim {}`",
            issue.id
        ));
    }
    for section in ["## Scope", "## Inputs", "## Work order", "## Completion"] {
        if !body.contains(section) {
            return Err(format!("handoff is missing required section {}", section));
        }
    }
    let calculated = calculate_binding(text)?;
    if frontmatter.binding != calculated {
        return Err(format!(
            "handoff content binding is stale: frontmatter {}, calculated {}",
            frontmatter.binding, calculated
        ));
    }
    match issue.handoff_digest.as_deref() {
        Some(binding) if binding == calculated => Ok(calculated),
        Some(binding) => Err(format!(
            "Manna item binding {} does not match handoff {}",
            binding, calculated
        )),
        None => Err(format!("{} has no authoritative handoff binding", issue.id)),
    }
}

fn transaction_path(base: &Path, issue_id: &str) -> PathBuf {
    base.join(TRANSACTION_DIR)
        .join(format!("{}.yaml", issue_id))
}

fn same_lifecycle(before: &Issue, after: &Issue) -> bool {
    before.id == after.id
        && before.created_at == after.created_at
        && before.status == after.status
        && before.blocked_by == after.blocked_by
        && before.claimed_by == after.claimed_by
        && before.claimed_at == after.claimed_at
        && before.claim_token_hash == after.claim_token_hash
}

fn validate_legacy_migration_transaction(
    base: &Path,
    path: &Path,
    transaction: &LegacyBoardTransaction,
    key: &[u8],
) -> Result<WorkflowConfig, String> {
    if transaction.version != LEGACY_MIGRATION_VERSION {
        return Err(format!(
            "unsupported legacy migration transaction version {}",
            transaction.version
        ));
    }
    let expected_path = legacy_migration_path(base);
    if path != expected_path {
        return Err(format!(
            "legacy migration transaction path {} is not {}",
            path.display(),
            expected_path.display()
        ));
    }
    let expected_signature = legacy_migration_signature(base, key, transaction)?;
    if !constant_time_eq(
        transaction.integrity.as_bytes(),
        expected_signature.as_bytes(),
    ) {
        return Err(format!(
            "legacy migration transaction {} failed HMAC authentication",
            path.display()
        ));
    }
    if transaction.before.len() != transaction.after.len() {
        return Err("legacy migration cannot add or delete board rows".to_string());
    }
    let mut row_ids = HashSet::new();
    for (before, after) in transaction.before.iter().zip(&transaction.after) {
        if before.id != after.id || !row_ids.insert(after.id.clone()) {
            return Err(
                "legacy migration must preserve one unique row for every issue id".to_string(),
            );
        }
        after
            .validate()
            .map_err(|error| format!("invalid migrated row {}: {}", after.id, error))?;
        if after.legacy_migration.is_none() {
            return Err(format!(
                "migrated row {} has no legacy migration annotation",
                after.id
            ));
        }
        match after.legacy_migration.as_ref().unwrap().disposition {
            LegacyMigrationDisposition::Paired
                if after.issue_type != IssueType::Item
                    || after.status == IssueStatus::Done
                    || after.prompt.is_none()
                    || after.handoff_digest.is_none() =>
            {
                return Err(format!(
                    "migrated paired row {} is not an active item with a bound handoff",
                    after.id
                ));
            }
            LegacyMigrationDisposition::History
                if after.status != IssueStatus::Done
                    || after.prompt.is_some()
                    || after.handoff_digest.is_some() =>
            {
                return Err(format!(
                    "migrated history row {} is not closed, pointer-free history",
                    after.id
                ));
            }
            LegacyMigrationDisposition::Exempt
                if after.status == IssueStatus::Done
                    || after.issue_type == IssueType::Item
                    || after.prompt.is_some()
                    || after.handoff_digest.is_some() =>
            {
                return Err(format!(
                    "migrated exempt row {} is not an active track or dream",
                    after.id
                ));
            }
            _ => {}
        }
    }

    let board: BoardConfig = serde_yaml::from_str(&transaction.board_after)
        .map_err(|error| format!("invalid migrated board identity: {}", error))?;
    if board.version != 1
        || board.workflow != BoardMode::Strict
        || board.migrated_from_legacy_at.is_none()
    {
        return Err(
            "legacy migration must publish a strict, migration-stamped board identity".to_string(),
        );
    }
    let config: WorkflowConfig = serde_yaml::from_str(&transaction.workflow_after)
        .map_err(|error| format!("invalid migrated workflow config: {}", error))?;
    config.validate()?;
    if transaction.readme_after != README_CONTENT {
        return Err("legacy migration README is not the canonical generated content".to_string());
    }
    let expected_gitignore =
        workflow_gitignore_content(transaction.gitignore_before.as_deref().unwrap_or_default());
    if transaction.gitignore_after != expected_gitignore {
        return Err("legacy migration Git visibility update is not canonical".to_string());
    }

    let rows = transaction
        .after
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect::<HashMap<_, _>>();
    let mut document_ids = HashSet::new();
    for migration_document in &transaction.documents {
        if !document_ids.insert(migration_document.issue_id.clone()) {
            return Err(format!(
                "legacy migration carries duplicate handoff documents for {}",
                migration_document.issue_id
            ));
        }
        let issue = rows
            .get(migration_document.issue_id.as_str())
            .ok_or_else(|| {
                format!(
                    "legacy migration handoff targets missing issue {}",
                    migration_document.issue_id
                )
            })?;
        if issue.issue_type != IssueType::Item || issue.status == IssueStatus::Done {
            return Err(format!(
                "legacy migration handoff {} does not target an active item",
                migration_document.issue_id
            ));
        }
        let canonical = canonical_handoff_path(base, &config, issue, issue.prompt.as_deref())?;
        let supplied = normalize_relative(Path::new(&migration_document.handoff))?;
        if supplied != canonical {
            return Err(format!(
                "legacy migration handoff {} is not authoritative path {}",
                supplied.display(),
                canonical.display()
            ));
        }
        validate_document(issue, &migration_document.document)?;
    }
    for issue in &transaction.after {
        let requires_document =
            issue.issue_type == IssueType::Item && issue.status != IssueStatus::Done;
        if requires_document != document_ids.contains(&issue.id) {
            return Err(format!(
                "legacy migration document set does not match active item {}",
                issue.id
            ));
        }
    }
    Ok(config)
}

fn validate_transaction(
    base: &Path,
    config: &WorkflowConfig,
    path: &Path,
    transaction: &PairTransaction,
    key: &[u8],
) -> Result<(), String> {
    if transaction.version != WORKFLOW_VERSION {
        return Err(format!(
            "unsupported pair transaction version {}",
            transaction.version
        ));
    }
    let expected_path = transaction_path(base, &transaction.issue_id);
    if path != expected_path {
        return Err(format!(
            "transaction filename {} does not match authenticated issue {}",
            path.display(),
            transaction.issue_id
        ));
    }
    let expected_signature = transaction_signature(base, key, transaction)?;
    if !constant_time_eq(
        transaction.integrity.as_bytes(),
        expected_signature.as_bytes(),
    ) {
        return Err(format!(
            "transaction {} failed HMAC authentication",
            path.display()
        ));
    }
    for row in [&transaction.before, &transaction.after]
        .into_iter()
        .flatten()
    {
        row.validate()
            .map_err(|error| format!("invalid transaction row {}: {}", row.id, error))?;
        if row.id != transaction.issue_id {
            return Err(format!(
                "transaction issue {} contains row {}",
                transaction.issue_id, row.id
            ));
        }
    }

    let (path_issue, document_expected, archive_expected) = match transaction.action {
        PairAction::Create => {
            if transaction.before.is_some()
                || transaction.after.is_none()
                || transaction.document.is_none()
                || transaction.archive.is_some()
                || transaction.after.as_ref().unwrap().issue_type != IssueType::Item
            {
                return Err("create transaction has an invalid shape".to_string());
            }
            (transaction.after.as_ref().unwrap(), true, false)
        }
        PairAction::Attach => {
            let (Some(before), Some(after)) = (&transaction.before, &transaction.after) else {
                return Err("attach transaction is missing a board row".to_string());
            };
            if transaction.document.is_none()
                || transaction.archive.is_some()
                || before.issue_type == IssueType::Item
                || after.issue_type != IssueType::Item
                || !same_lifecycle(before, after)
            {
                return Err(
                    "attach transaction has an invalid shape or lifecycle delta".to_string()
                );
            }
            (after, true, false)
        }
        PairAction::Rebind => {
            let (Some(before), Some(after)) = (&transaction.before, &transaction.after) else {
                return Err("rebind transaction is missing a board row".to_string());
            };
            if transaction.document.is_none()
                || transaction.archive.is_some()
                || before.issue_type != IssueType::Item
                || after.issue_type != IssueType::Item
                || before.prompt != after.prompt
                || !same_lifecycle(before, after)
            {
                return Err(
                    "rebind transaction has an invalid shape or lifecycle delta".to_string()
                );
            }
            (after, true, false)
        }
        PairAction::Detach => {
            let (Some(before), Some(after)) = (&transaction.before, &transaction.after) else {
                return Err("detach transaction is missing a board row".to_string());
            };
            if transaction.document.is_some()
                || transaction.archive.is_none()
                || before.issue_type != IssueType::Item
                || after.issue_type == IssueType::Item
                || after.prompt.is_some()
                || after.handoff_digest.is_some()
                || !same_lifecycle(before, after)
            {
                return Err(
                    "detach transaction has an invalid shape or lifecycle delta".to_string()
                );
            }
            (before, false, true)
        }
        PairAction::Delete => {
            let Some(before) = transaction.before.as_ref() else {
                return Err("delete transaction has no before row".to_string());
            };
            if transaction.after.is_some()
                || transaction.document.is_some()
                || transaction.archive.is_none()
                || before.issue_type != IssueType::Item
            {
                return Err("delete transaction has an invalid shape".to_string());
            }
            (before, false, true)
        }
    };

    let canonical = canonical_handoff_path(base, config, path_issue, path_issue.prompt.as_deref())?;
    let supplied = normalize_relative(Path::new(&transaction.handoff))?;
    if supplied != canonical {
        return Err(format!(
            "transaction handoff {} is not the authoritative path {}",
            supplied.display(),
            canonical.display()
        ));
    }
    if document_expected {
        let after = transaction.after.as_ref().unwrap();
        let document = transaction.document.as_deref().unwrap();
        validate_document(after, document)?;
    }
    if archive_expected {
        let before = transaction.before.as_ref().unwrap();
        let expected = archive_path(before);
        let actual = normalize_relative(Path::new(transaction.archive.as_deref().unwrap()))?;
        if actual != expected {
            return Err(format!(
                "transaction archive {} is not the authoritative path {}",
                actual.display(),
                expected.display()
            ));
        }
    }
    Ok(())
}

fn write_transaction(
    base: &Path,
    config: &WorkflowConfig,
    transaction: &PairTransaction,
) -> Result<PathBuf, String> {
    safe_create_dir_all(base, Path::new(TRANSACTION_DIR))?;
    let path = transaction_path(base, &transaction.issue_id);
    let key = load_recovery_key(base, true)?;
    let mut signed = transaction.clone();
    signed.integrity = transaction_signature(base, &key, &signed)?;
    validate_transaction(base, config, &path, &signed, &key)?;
    let yaml = serde_yaml::to_string(&signed)
        .map_err(|error| format!("failed to serialize pair transaction: {}", error))?;
    atomic_write(&path, yaml.as_bytes(), false).map_err(|error| {
        format!(
            "{}; pending Manna pair transaction already exists for {}; run `agent-do manna init`",
            error, transaction.issue_id
        )
    })?;
    Ok(path)
}

fn remove_transaction_if_unchanged(
    path: &Path,
    opened_metadata: &fs::Metadata,
    opened_text: &str,
) -> Result<(), String> {
    reject_symlink(path, "transaction")?;
    let current_metadata = match fs::metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(format!("failed to recheck {}: {}", path.display(), error)),
    };
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if opened_metadata.dev() != current_metadata.dev()
            || opened_metadata.ino() != current_metadata.ino()
        {
            return Err(format!(
                "transaction {} changed during recovery and was left in place",
                path.display()
            ));
        }
    }
    let current = fs::read_to_string(path)
        .map_err(|error| format!("failed to recheck {}: {}", path.display(), error))?;
    if current != opened_text {
        return Err(format!(
            "transaction {} changed during recovery and was left in place",
            path.display()
        ));
    }
    fs::remove_file(path)
        .map_err(|error| format!("failed to remove {}: {}", path.display(), error))?;
    sync_parent(path)
}

fn install_transaction_document(
    base: &Path,
    relative: &Path,
    document: &str,
) -> Result<(), String> {
    let relative = safe_relative_path(base, relative, true)?;
    if !relative.starts_with(HANDOFF_DIR)
        || relative.starts_with(HANDOFF_ARCHIVE_DIR)
        || relative
            .extension()
            .and_then(|extension| extension.to_str())
            != Some("md")
    {
        return Err("transaction document target is outside canonical .handoff/".to_string());
    }
    let parent = relative
        .parent()
        .ok_or_else(|| format!("handoff has no parent: {}", relative.display()))?;
    safe_create_dir_all(base, parent)?;
    let target = base.join(&relative);
    if target.is_file() {
        let existing = fs::read_to_string(&target)
            .map_err(|error| format!("failed to read {}: {}", target.display(), error))?;
        if existing == document {
            return Ok(());
        }
    }
    atomic_write_replace(&target, document)
}

fn check_managed_text_state(
    path: &Path,
    before: Option<&str>,
    after: &str,
    label: &str,
) -> Result<(), String> {
    let current = read_optional_text(path, label)?;
    if current.as_deref() != before && current.as_deref() != Some(after) {
        return Err(format!(
            "{} changed after legacy migration was prepared: {}",
            label,
            path.display()
        ));
    }
    Ok(())
}

fn install_managed_text(
    path: &Path,
    before: Option<&str>,
    after: &str,
    label: &str,
) -> Result<(), String> {
    check_managed_text_state(path, before, after, label)?;
    if read_optional_text(path, label)?.as_deref() == Some(after) {
        return Ok(());
    }
    atomic_write_replace(path, after)
}

fn check_migration_document_state(
    base: &Path,
    migration_document: &MigrationDocument,
) -> Result<(), String> {
    let relative = safe_relative_path(base, Path::new(&migration_document.handoff), true)?;
    let target = base.join(relative);
    reject_symlink(&target, "legacy migration handoff")?;
    match fs::read_to_string(&target) {
        Ok(existing) if existing == migration_document.document => Ok(()),
        Ok(_) => Err(format!(
            "legacy migration refuses to overwrite existing handoff {}",
            migration_document.handoff
        )),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("failed to read {}: {}", target.display(), error)),
    }
}

fn apply_legacy_migration_files(
    base: &Path,
    transaction: &LegacyBoardTransaction,
) -> Result<(), String> {
    let gitignore = base.join(".gitignore");
    let workflow = base.join(WORKFLOW_FILE);
    let readme = base.join(HANDOFF_README);

    // Validate every compare-and-swap precondition before the first write so
    // a concurrent human edit cannot leave a partly applied file set.
    check_managed_text_state(
        &gitignore,
        transaction.gitignore_before.as_deref(),
        &transaction.gitignore_after,
        ".gitignore",
    )?;
    check_managed_text_state(
        &workflow,
        transaction.workflow_before.as_deref(),
        &transaction.workflow_after,
        "workflow config",
    )?;
    check_managed_text_state(
        &readme,
        transaction.readme_before.as_deref(),
        &transaction.readme_after,
        "handoff README",
    )?;
    for migration_document in &transaction.documents {
        check_migration_document_state(base, migration_document)?;
    }

    install_managed_text(
        &gitignore,
        transaction.gitignore_before.as_deref(),
        &transaction.gitignore_after,
        ".gitignore",
    )?;
    safe_create_dir_all(base, Path::new(HANDOFF_DIR))?;
    safe_create_dir_all(base, Path::new(".manna"))?;
    install_managed_text(
        &workflow,
        transaction.workflow_before.as_deref(),
        &transaction.workflow_after,
        "workflow config",
    )?;
    install_managed_text(
        &readme,
        transaction.readme_before.as_deref(),
        &transaction.readme_after,
        "handoff README",
    )?;
    for migration_document in &transaction.documents {
        install_transaction_document(
            base,
            Path::new(&migration_document.handoff),
            &migration_document.document,
        )?;
    }

    for relative in durable_paths().into_iter().map(Path::new).chain(
        transaction
            .documents
            .iter()
            .map(|document| Path::new(document.handoff.as_str())),
    ) {
        if git_path_ignored(base, relative)? {
            return Err(format!(
                "legacy migration durable state is ignored by Git: {}",
                relative.display()
            ));
        }
    }
    Ok(())
}

fn archive_handoff(base: &Path, handoff: &Path, archive: &Path) -> Result<(), String> {
    let handoff = safe_relative_path(base, handoff, true)?;
    let archive = safe_relative_path(base, archive, true)?;
    if !archive.starts_with(HANDOFF_ARCHIVE_DIR) {
        return Err("handoff archive path is outside the canonical archive".to_string());
    }
    safe_create_dir_all(base, Path::new(HANDOFF_ARCHIVE_DIR))?;
    let source = base.join(&handoff);
    let target = base.join(&archive);
    reject_symlink(&source, "handoff")?;
    reject_symlink(&target, "handoff archive")?;
    if target.is_file() && !source.exists() {
        return Ok(());
    }
    if !source.is_file() {
        return Err(format!(
            "cannot archive missing handoff {}",
            handoff.display()
        ));
    }
    if target.exists() {
        return Err(format!(
            "handoff archive already exists: {}",
            archive.display()
        ));
    }
    fs::rename(&source, &target).map_err(|error| {
        format!(
            "failed to archive {} as {}: {}",
            handoff.display(),
            archive.display(),
            error
        )
    })?;
    sync_parent(&source)?;
    sync_parent(&target)
}

fn execute_transaction(
    base: &Path,
    store: &MannaStore,
    transaction: &PairTransaction,
) -> Result<(), MannaError> {
    let handoff = Path::new(&transaction.handoff);
    match transaction.action {
        PairAction::Create => {
            let after = transaction.after.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("create transaction has no after row".to_string())
            })?;
            let document = transaction.document.as_deref().ok_or_else(|| {
                MannaError::MutationRejected(
                    "create transaction has no handoff document".to_string(),
                )
            })?;
            store.recover_issue_with(after, || {
                install_transaction_document(base, handoff, document)
            })?;
        }
        PairAction::Attach | PairAction::Rebind => {
            let before = transaction.before.as_ref().ok_or_else(|| {
                MannaError::MutationRejected(
                    "pair update transaction has no before row".to_string(),
                )
            })?;
            let after = transaction.after.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("pair update transaction has no after row".to_string())
            })?;
            let document = transaction.document.as_deref().ok_or_else(|| {
                MannaError::MutationRejected(
                    "pair update transaction has no handoff document".to_string(),
                )
            })?;
            store.recover_replace_issue_with(before, after, || {
                install_transaction_document(base, handoff, document)
            })?;
        }
        PairAction::Detach => {
            let before = transaction.before.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("detach transaction has no before row".to_string())
            })?;
            let after = transaction.after.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("detach transaction has no after row".to_string())
            })?;
            let archive = transaction.archive.as_deref().ok_or_else(|| {
                MannaError::MutationRejected("detach transaction has no archive path".to_string())
            })?;
            store.recover_replace_issue_with(before, after, || {
                archive_handoff(base, handoff, Path::new(archive))
            })?;
        }
        PairAction::Delete => {
            let before = transaction.before.as_ref().ok_or_else(|| {
                MannaError::MutationRejected("delete transaction has no before row".to_string())
            })?;
            let archive = transaction.archive.as_deref().ok_or_else(|| {
                MannaError::MutationRejected("delete transaction has no archive path".to_string())
            })?;
            store.recover_delete_issue_with(before, || {
                archive_handoff(base, handoff, Path::new(archive))
            })?;
        }
    }
    Ok(())
}

fn execute_legacy_migration(
    base: &Path,
    store: &MannaStore,
    transaction: &LegacyBoardTransaction,
) -> Result<(), MannaError> {
    let board_path = base.join(BOARD_FILE);
    store.recover_replace_board_with(
        &transaction.before,
        &transaction.after,
        || apply_legacy_migration_files(base, transaction),
        || {
            // Board identity is the commit point. Until this succeeds, every
            // ordinary write remains legacy or fail-closed; no reader can see
            // a strict identity backed by only part of the migrated state.
            install_managed_text(
                &board_path,
                transaction.board_before.as_deref(),
                &transaction.board_after,
                "board identity",
            )
        },
    )
}

fn write_legacy_migration_transaction(
    base: &Path,
    transaction: &LegacyBoardTransaction,
) -> Result<PathBuf, String> {
    safe_create_dir_all(base, Path::new(TRANSACTION_DIR))?;
    let path = legacy_migration_path(base);
    let key = load_recovery_key(base, true)?;
    let mut signed = transaction.clone();
    signed.integrity = legacy_migration_signature(base, &key, &signed)?;
    validate_legacy_migration_transaction(base, &path, &signed, &key)?;
    let yaml = serde_yaml::to_string(&signed)
        .map_err(|error| format!("failed to serialize legacy migration: {}", error))?;
    atomic_write(&path, yaml.as_bytes(), false).map_err(|error| {
        format!(
            "{}; a legacy-board migration is already pending; rerun `agent-do manna migrate`",
            error
        )
    })?;
    Ok(path)
}

fn complete_legacy_migration_path(
    base: &Path,
    store: &MannaStore,
    path: &Path,
    key: &[u8],
) -> Result<TransactionOutcome, String> {
    safe_relative_path(
        base,
        path.strip_prefix(base).map_err(|_| {
            format!(
                "legacy migration path is outside project: {}",
                path.display()
            )
        })?,
        false,
    )?;
    reject_symlink(path, "legacy migration transaction")?;
    let mut file = File::open(path)
        .map_err(|error| format!("failed to open {}: {}", path.display(), error))?;
    let metadata = file
        .metadata()
        .map_err(|error| format!("failed to inspect {}: {}", path.display(), error))?;
    if !metadata.is_file() {
        return Err(format!(
            "legacy migration transaction is not a regular file: {}",
            path.display()
        ));
    }
    let mut text = String::new();
    file.read_to_string(&mut text)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    let transaction: LegacyBoardTransaction = serde_yaml::from_str(&text).map_err(|error| {
        format!(
            "invalid legacy migration transaction {}: {}",
            path.display(),
            error
        )
    })?;
    validate_legacy_migration_transaction(base, path, &transaction, key)?;
    match execute_legacy_migration(base, store, &transaction) {
        Ok(()) => {
            remove_transaction_if_unchanged(path, &metadata, &text)?;
            Ok(TransactionOutcome::Applied)
        }
        Err(MannaError::RecoveryConflict(reason)) => {
            remove_transaction_if_unchanged(path, &metadata, &text)?;
            Ok(TransactionOutcome::DiscardedConflict(reason))
        }
        Err(error) => Err(error.to_string()),
    }
}

pub fn recover_legacy_migration(base: &Path, store: &MannaStore) -> Result<usize, String> {
    let path = legacy_migration_path(base);
    if !path.exists() {
        return Ok(0);
    }
    let key = load_recovery_key(base, false)?;
    match complete_legacy_migration_path(base, store, &path, &key)? {
        TransactionOutcome::Applied => Ok(1),
        TransactionOutcome::DiscardedConflict(reason) => Err(format!(
            "legacy-board migration lost a concurrent update and was discarded safely: {}",
            reason
        )),
    }
}

fn run_legacy_migration_transaction(
    base: &Path,
    store: &MannaStore,
    transaction: LegacyBoardTransaction,
) -> Result<(), String> {
    let path = write_legacy_migration_transaction(base, &transaction)?;
    let key = load_recovery_key(base, false)?;
    match complete_legacy_migration_path(base, store, &path, &key) {
        Ok(TransactionOutcome::Applied) => Ok(()),
        Ok(TransactionOutcome::DiscardedConflict(reason)) => Err(format!(
            "legacy-board migration lost a concurrent board update and was discarded safely: {}. Reload and retry.",
            reason
        )),
        Err(error) => Err(format!(
            "legacy-board migration is pending recovery: {}. Rerun `agent-do manna migrate`.",
            error
        )),
    }
}

fn complete_transaction_path(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    path: &Path,
    key: &[u8],
) -> Result<TransactionOutcome, String> {
    safe_relative_path(
        base,
        path.strip_prefix(base)
            .map_err(|_| format!("transaction path is outside project: {}", path.display()))?,
        false,
    )?;
    reject_symlink(path, "transaction")?;
    let mut file = File::open(path)
        .map_err(|error| format!("failed to open {}: {}", path.display(), error))?;
    let metadata = file
        .metadata()
        .map_err(|error| format!("failed to inspect {}: {}", path.display(), error))?;
    if !metadata.is_file() {
        return Err(format!(
            "transaction is not a regular file: {}",
            path.display()
        ));
    }
    let mut text = String::new();
    file.read_to_string(&mut text)
        .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
    let transaction: PairTransaction = serde_yaml::from_str(&text)
        .map_err(|error| format!("invalid pair transaction {}: {}", path.display(), error))?;
    validate_transaction(base, config, path, &transaction, key)?;
    match execute_transaction(base, store, &transaction) {
        Ok(()) => {
            remove_transaction_if_unchanged(path, &metadata, &text)?;
            Ok(TransactionOutcome::Applied)
        }
        Err(MannaError::RecoveryConflict(reason)) => {
            // Store recovery checks the complete row before touching the file
            // half of a pair. A conflict therefore proves this authenticated
            // intent is obsolete, not partially applied. Remove it so one
            // losing optimistic writer cannot poison every later command.
            remove_transaction_if_unchanged(path, &metadata, &text)?;
            Ok(TransactionOutcome::DiscardedConflict(reason))
        }
        Err(error) => Err(error.to_string()),
    }
}

fn run_transaction(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    transaction: PairTransaction,
) -> Result<(), String> {
    let path = write_transaction(base, config, &transaction)?;
    let key = load_recovery_key(base, false)?;
    match complete_transaction_path(base, store, config, &path, &key) {
        Ok(TransactionOutcome::Applied) => Ok(()),
        Ok(TransactionOutcome::DiscardedConflict(reason)) => Err(format!(
            "Manna pair transaction for {} lost a concurrent update and was discarded safely: {}. Reload the item and retry.",
            transaction.issue_id, reason
        )),
        Err(error) => Err(format!(
            "Manna pair transaction for {} is pending recovery: {}. Run `agent-do manna init`.",
            transaction.issue_id, error
        )),
    }
}

pub fn recover_pair_transactions(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
) -> Result<usize, String> {
    let relative = safe_relative_path(base, Path::new(TRANSACTION_DIR), true)?;
    let directory = base.join(relative);
    if !directory.exists() {
        return Ok(0);
    }
    let mut paths = fs::read_dir(&directory)
        .map_err(|error| format!("failed to inspect {}: {}", directory.display(), error))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.starts_with("mn-") && name.ends_with(".yaml"))
        })
        .collect::<Vec<_>>();
    paths.sort();
    if paths.is_empty() {
        return Ok(0);
    }
    // A journal is published only after its key. The directory itself may be
    // visible earlier because writers create it before generating the key, so
    // an empty directory carries no authentication prerequisite.
    let key = load_recovery_key(base, false)?;
    let mut recovered = 0;
    for path in paths {
        match complete_transaction_path(base, store, config, &path, &key) {
            Ok(_) => recovered += 1,
            // Recovery scans are cooperative. Another process may complete
            // and unlink an authenticated journal after this process lists
            // the directory but before it opens or rechecks that path. An
            // absent path has no remaining intent to execute; the initiating
            // writer still uses run_transaction, which does not suppress it.
            Err(_) if !path.exists() => {}
            Err(error) => return Err(error),
        }
    }
    Ok(recovered)
}

fn prepare_bound_issue(issue: &Issue, document: String) -> Result<(Issue, String), String> {
    let binding = calculate_binding(&document)?;
    let mut bound = issue.clone();
    bound.handoff_digest = Some(binding);
    bound.updated_at = Utc::now();
    Ok((bound, document))
}

fn preflight_handoff(base: &Path, relative: &Path) -> Result<(), String> {
    safe_relative_path(base, relative, true)?;
    if git_path_ignored(base, relative)? {
        return Err(format!("handoff is ignored by Git: {}", relative.display()));
    }
    Ok(())
}

pub fn create_paired_issue(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    issue: &Issue,
    requested: Option<&str>,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, issue, requested)?;
    preflight_handoff(base, &relative)?;
    if path_exists(&base.join(&relative)) {
        return Err(format!(
            "refusing to overwrite existing handoff {}",
            relative.display()
        ));
    }
    let mut paired = issue.clone();
    paired.prompt = Some(relative.to_string_lossy().into_owned());
    let document = render_handoff(base, &paired)?;
    let (paired, document) = prepare_bound_issue(&paired, document)?;
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Create,
        issue_id: paired.id.clone(),
        before: None,
        after: Some(paired.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: None,
        document: Some(document),
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(paired)
}

pub fn attach_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
    requested: Option<&str>,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, after_metadata, requested)?;
    preflight_handoff(base, &relative)?;
    if path_exists(&base.join(&relative)) {
        return Err(format!("handoff already exists: {}", relative.display()));
    }
    let mut after = after_metadata.clone();
    after.prompt = Some(relative.to_string_lossy().into_owned());
    let document = render_handoff(base, &after)?;
    let (after, document) = prepare_bound_issue(&after, document)?;
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Attach,
        issue_id: before.id.clone(),
        before: Some(before.clone()),
        after: Some(after.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: None,
        document: Some(document),
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(after)
}

fn archive_path(issue: &Issue) -> PathBuf {
    Path::new(HANDOFF_ARCHIVE_DIR).join(format!(
        "{}-{}.md",
        issue.id,
        issue.updated_at.format("%Y%m%dT%H%M%S%.fZ")
    ))
}

pub fn detach_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, before, before.prompt.as_deref())?;
    let archive = archive_path(before);
    let mut after = after_metadata.clone();
    after.prompt = None;
    after.handoff_digest = None;
    after.updated_at = Utc::now();
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Detach,
        issue_id: before.id.clone(),
        before: Some(before.clone()),
        after: Some(after.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: Some(archive.to_string_lossy().into_owned()),
        document: None,
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(after)
}

pub fn delete_paired_issue(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<(), String> {
    let relative = canonical_handoff_path(base, config, issue, issue.prompt.as_deref())?;
    let archive = archive_path(issue);
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Delete,
        issue_id: issue.id.clone(),
        before: Some(issue.clone()),
        after: None,
        handoff: relative.to_string_lossy().into_owned(),
        archive: Some(archive.to_string_lossy().into_owned()),
        document: None,
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)
}

fn update_frontmatter_for_issue(text: &str, issue: &Issue) -> Result<String, String> {
    let (mut frontmatter, body) = split_handoff(text)?;
    frontmatter.workflow = WORKFLOW_VERSION;
    frontmatter.manna = issue.id.clone();
    frontmatter.track = issue.track.clone();
    frontmatter.source = issue.source.clone();
    frontmatter.inputs = issue.source.iter().cloned().collect();
    frontmatter.scope = issue.title.clone();
    render_document(&frontmatter, body)
}

fn commit_rebind(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
    document: String,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, before, before.prompt.as_deref())?;
    preflight_handoff(base, &relative)?;
    let (mut after, document) = prepare_bound_issue(after_metadata, document)?;
    after.prompt = before.prompt.clone();
    validate_document(&after, &document)?;
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Rebind,
        issue_id: before.id.clone(),
        before: Some(before.clone()),
        after: Some(after.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: None,
        document: Some(document),
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(after)
}

/// Explicitly approve the current handoff contents and bind them to the row.
/// This is the only operation allowed to consume an unsealed document.
pub fn seal_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, issue, issue.prompt.as_deref())?;
    preflight_handoff(base, &relative)?;
    let existing = fs::read_to_string(base.join(&relative))
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    let document = update_frontmatter_for_issue(&existing, issue)?;
    commit_rebind(base, store, config, issue, issue, document)
}

/// Propagate authoritative row metadata into a handoff only after proving the
/// existing body is still sealed. Ordinary updates cannot bless hand-edited
/// scope merely because some unrelated title or source field changed.
pub fn rebind_handoff_metadata(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, before, before.prompt.as_deref())?;
    preflight_handoff(base, &relative)?;
    let existing = fs::read_to_string(base.join(&relative))
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    validate_document(before, &existing).map_err(|error| {
        format!(
            "cannot update Manna metadata while the handoff is unsealed: {}. Seal it explicitly first with `agent-do manna handoff seal {}`",
            error, before.id
        )
    })?;
    let document = update_frontmatter_for_issue(&existing, after_metadata)?;
    commit_rebind(base, store, config, before, after_metadata, document)
}

fn upgrade_legacy_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, issue, issue.prompt.as_deref())?;
    let path = base.join(&relative);
    let old = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    let body = if let Ok((_, body)) = split_handoff(&old) {
        body.to_string()
    } else {
        generated_body(issue)
    };
    let document = render_document(&frontmatter_for(base, issue), &body)?;
    let (after, document) = prepare_bound_issue(issue, document)?;
    validate_document(&after, &document)?;
    let transaction = PairTransaction {
        version: WORKFLOW_VERSION,
        action: PairAction::Rebind,
        issue_id: issue.id.clone(),
        before: Some(issue.clone()),
        after: Some(after.clone()),
        handoff: relative.to_string_lossy().into_owned(),
        archive: None,
        document: Some(document),
        integrity: String::new(),
    };
    run_transaction(base, store, config, transaction)?;
    Ok(after)
}

fn valid_claim_token_hash(value: Option<&str>) -> bool {
    value.is_some_and(|proof| {
        proof.strip_prefix("sha256:").is_some_and(|hex| {
            hex.len() == 64
                && hex
                    .bytes()
                    .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
        })
    })
}

fn release_invalid_legacy_claim(issue: &mut Issue) -> bool {
    let has_claim_state = issue.claimed_by.is_some()
        || issue.claimed_at.is_some()
        || issue.claim_token_hash.is_some()
        || issue.status == IssueStatus::InProgress;
    let coherent_live_claim = issue.status != IssueStatus::Done
        && issue.claimed_by.is_some()
        && issue.claimed_at.is_some()
        && valid_claim_token_hash(issue.claim_token_hash.as_deref());
    if !has_claim_state || coherent_live_claim {
        return false;
    }

    issue.claimed_by = None;
    issue.claimed_at = None;
    issue.claim_token_hash = None;
    if issue.status != IssueStatus::Done {
        issue.status = if issue.blocked_by.is_empty() {
            IssueStatus::Open
        } else {
            IssueStatus::Blocked
        };
    }
    true
}

fn legacy_migration_result(
    issues: &[Issue],
    migrated: bool,
    recovered: bool,
) -> LegacyMigrationResult {
    let paired_items = issues
        .iter()
        .filter(|issue| {
            issue.legacy_migration.as_ref().is_some_and(|migration| {
                migration.disposition == LegacyMigrationDisposition::Paired
            })
        })
        .count();
    let historical_rows = issues
        .iter()
        .filter(|issue| {
            issue.legacy_migration.as_ref().is_some_and(|migration| {
                migration.disposition == LegacyMigrationDisposition::History
            })
        })
        .count();
    let exempt_rows = issues
        .iter()
        .filter(|issue| {
            issue.legacy_migration.as_ref().is_some_and(|migration| {
                migration.disposition == LegacyMigrationDisposition::Exempt
            })
        })
        .count();
    let released_claims = issues
        .iter()
        .filter(|issue| {
            issue
                .legacy_migration
                .as_ref()
                .is_some_and(|migration| migration.released_claimed_by.is_some())
        })
        .count();
    LegacyMigrationResult {
        migrated,
        recovered_transaction: recovered,
        paired_items,
        historical_rows,
        exempt_rows,
        released_claims,
    }
}

fn validate_migrated_board(base: &Path, issues: &[Issue]) -> Result<WorkflowConfig, String> {
    let config = load_workflow(base)?
        .ok_or_else(|| format!("migrated board is missing {}", WORKFLOW_FILE))?;
    config.validate()?;
    validate_scaffold(base, &config)?;
    for issue in issues
        .iter()
        .filter(|issue| issue.issue_type == IssueType::Item && issue.status != IssueStatus::Done)
    {
        validate_handoff(base, &config, issue).map_err(|error| {
            format!(
                "migrated item {} has an invalid authoritative handoff: {}",
                issue.id, error
            )
        })?;
    }
    Ok(config)
}

fn build_legacy_migration(
    base: &Path,
    before: Vec<Issue>,
) -> Result<LegacyBoardTransaction, String> {
    if before.is_empty() {
        return Err(
            "the Manna board is empty; run `agent-do manna init` instead of legacy migration"
                .to_string(),
        );
    }
    if before.iter().any(|issue| issue.legacy_migration.is_some()) {
        return Err(
            "legacy migration annotations are incomplete or inconsistent; refusing to reseal rows"
                .to_string(),
        );
    }
    if before.iter().any(|issue| issue.handoff_digest.is_some()) {
        return Err(
            "board mixes strict handoff bindings with legacy rows; repair the strict workflow instead of migrating it again"
                .to_string(),
        );
    }

    let migration_time = Utc::now();
    let config = WorkflowConfig::default();
    let mut after = Vec::with_capacity(before.len());
    let mut documents = Vec::new();
    for original in &before {
        let mut issue = original.clone();
        let previous_prompt = prompt_pointer(original);
        let released_owner = original.claimed_by.clone();
        let released = release_invalid_legacy_claim(&mut issue);
        if released {
            issue.updated_at = migration_time;
        }

        let disposition = if issue.status == IssueStatus::Done {
            issue.prompt = None;
            issue.handoff_digest = None;
            LegacyMigrationDisposition::History
        } else if issue.issue_type != IssueType::Item {
            issue.prompt = None;
            issue.handoff_digest = None;
            LegacyMigrationDisposition::Exempt
        } else {
            let relative = canonical_handoff_path(base, &config, &issue, None)?;
            issue.prompt = Some(relative.to_string_lossy().into_owned());
            let document = render_handoff(base, &issue)?;
            issue.handoff_digest = Some(calculate_binding(&document)?);
            validate_document(&issue, &document)?;
            documents.push(MigrationDocument {
                issue_id: issue.id.clone(),
                handoff: relative.to_string_lossy().into_owned(),
                document,
            });
            LegacyMigrationDisposition::Paired
        };
        issue.legacy_migration = Some(LegacyMigrationAnnotation {
            version: LEGACY_MIGRATION_VERSION,
            disposition,
            migrated_at: migration_time,
            previous_prompt,
            released_claimed_by: released.then_some(released_owner).flatten(),
        });
        issue
            .validate()
            .map_err(|error| format!("cannot migrate {}: {}", issue.id, error))?;
        after.push(issue);
    }

    let mut board = BoardConfig::strict();
    board.migrated_from_legacy_at = Some(migration_time);
    let board_after = serde_yaml::to_string(&board)
        .map_err(|error| format!("failed to serialize migrated board identity: {}", error))?;
    let workflow_after = serde_yaml::to_string(&config)
        .map_err(|error| format!("failed to serialize workflow config: {}", error))?;
    let gitignore_before = read_optional_text(&base.join(".gitignore"), ".gitignore")?;
    let gitignore_after =
        workflow_gitignore_content(gitignore_before.as_deref().unwrap_or_default());
    for document in &documents {
        check_migration_document_state(base, document)?;
    }
    Ok(LegacyBoardTransaction {
        version: LEGACY_MIGRATION_VERSION,
        before,
        after,
        documents,
        gitignore_before,
        gitignore_after,
        board_before: read_optional_text(&base.join(BOARD_FILE), "board identity")?,
        board_after,
        workflow_before: read_optional_text(&base.join(WORKFLOW_FILE), "workflow config")?,
        workflow_after,
        readme_before: read_optional_text(&base.join(HANDOFF_README), "handoff README")?,
        readme_after: README_CONTENT.to_string(),
        integrity: String::new(),
    })
}

/// Admit a pre-workflow board into strict mode as one authenticated,
/// recoverable transaction. Ordinary strict writes never call this operation
/// or relax their pair validation.
pub fn migrate_legacy_board(
    base: &Path,
    store: &MannaStore,
) -> Result<LegacyMigrationResult, String> {
    store
        .validate_storage_root()
        .map_err(|error| error.to_string())?;
    let recovered = recover_legacy_migration(base, store)? > 0;
    let issues = store
        .load_issues_strict()
        .map_err(|error| error.to_string())?;
    let board = load_board_config(base)?;

    if let Some(identity) = board.as_ref() {
        if identity.workflow == BoardMode::Strict && identity.migrated_from_legacy_at.is_some() {
            validate_migrated_board(base, &issues)?;
            return Ok(legacy_migration_result(&issues, recovered, recovered));
        }
        if identity.workflow == BoardMode::Strict {
            let active_items = issues.iter().filter(|issue| {
                issue.issue_type == IssueType::Item && issue.status != IssueStatus::Done
            });
            let fully_strict = active_items
                .clone()
                .all(|issue| issue.prompt.is_some() && issue.handoff_digest.is_some());
            let has_strict_binding = issues.iter().any(|issue| issue.handoff_digest.is_some());
            if fully_strict && has_strict_binding && load_workflow(base)?.is_some() {
                validate_migrated_board(base, &issues)?;
                return Ok(legacy_migration_result(&issues, false, recovered));
            }
        }
    }

    let transaction = build_legacy_migration(base, issues)?;
    let migrated_rows = transaction.after.clone();
    run_legacy_migration_transaction(base, store, transaction)?;
    validate_migrated_board(base, &migrated_rows)?;
    Ok(legacy_migration_result(&migrated_rows, true, recovered))
}

pub fn initialize_workflow(
    base: &Path,
    store: &MannaStore,
) -> Result<Option<WorkflowInit>, String> {
    store
        .validate_storage_root()
        .map_err(|error| error.to_string())?;
    let recovered_migration = recover_legacy_migration(base, store)?;
    let initial_issues = store.load_issues().map_err(|error| error.to_string())?;
    let existing = load_workflow(base)?;
    let strict_markers = workflow_markers_present(base, &initial_issues);
    let board = match load_board_config(base)? {
        Some(board) => board,
        None if strict_markers || initial_issues.is_empty() => {
            let board = BoardConfig::strict();
            write_board_config(base, &board)?;
            board
        }
        None => {
            let board = BoardConfig::legacy();
            write_board_config(base, &board)?;
            board
        }
    };
    if board.workflow == BoardMode::Legacy {
        if strict_markers || existing.is_some() {
            return Err(
                "legacy board identity conflicts with strict workflow markers; archive or migrate them explicitly"
                    .to_string(),
            );
        }
        return Ok(None);
    }

    let restored_config = existing.is_none() && board.workflow == BoardMode::Strict;
    if !strict_markers {
        validate_new_handoff_root(base)?;
    } else {
        reject_symlink(&base.join(HANDOFF_DIR), "handoff root")?;
    }
    safe_create_dir_all(base, Path::new(HANDOFF_DIR))?;
    safe_create_dir_all(base, Path::new(".manna"))?;
    let gitignore_updated = ensure_workflow_tracked(base)?;
    atomic_write_replace(&base.join(HANDOFF_README), README_CONTENT)?;

    let config = WorkflowConfig::default();
    let yaml = serde_yaml::to_string(&config)
        .map_err(|error| format!("failed to serialize workflow config: {}", error))?;
    // A missing strict config is repairable only by restoring the current
    // version. A real v1 config stays v1 until every item migration finishes,
    // so interruption cannot strand a partially upgraded board behind a v2
    // marker that suppresses the remaining work on the next init.
    if restored_config {
        atomic_write_replace(&workflow_path(base), &yaml)?;
    }
    validate_scaffold(base, &config)?;

    // Recovery begins only after board identity, scaffold paths, Git
    // visibility, and journal authentication can all be checked. A planted
    // journal is never the input that decides where validation occurs.
    let recovered_transactions =
        recovered_migration + recover_pair_transactions(base, store, &config)?;
    let issues = store.load_issues().map_err(|error| error.to_string())?;

    let old_workflow = existing
        .as_ref()
        .is_some_and(|workflow| workflow.version < WORKFLOW_VERSION);
    let mut upgraded_items = 0;
    if old_workflow {
        for issue in issues.iter().filter(|issue| {
            issue.issue_type == IssueType::Item
                && issue.status != IssueStatus::Done
                && issue.prompt.is_some()
                && issue.handoff_digest.is_none()
        }) {
            upgrade_legacy_handoff(base, store, &config, issue)?;
            upgraded_items += 1;
        }
        atomic_write_replace(&workflow_path(base), &yaml)?;
    }

    let current = store.load_issues().map_err(|error| error.to_string())?;
    for issue in current
        .iter()
        .filter(|issue| issue.issue_type == IssueType::Item && issue.status != IssueStatus::Done)
    {
        if issue.prompt.is_none() || issue.handoff_digest.is_none() {
            return Err(format!(
                "strict workflow item {} is missing its authoritative handoff pair",
                issue.id
            ));
        }
        validate_handoff(base, &config, issue).map_err(|error| {
            format!(
                "strict workflow item {} has an invalid handoff: {}",
                issue.id, error
            )
        })?;
    }
    Ok(Some(WorkflowInit {
        config,
        gitignore_updated,
        upgraded_items,
        restored_config,
        recovered_transactions,
    }))
}

pub fn validate_scaffold(base: &Path, config: &WorkflowConfig) -> Result<(), String> {
    config.validate()?;
    let board = load_board_config(base)?
        .ok_or_else(|| format!("missing durable workflow file {}", BOARD_FILE))?;
    if board.workflow != BoardMode::Strict {
        return Err("board identity is not strict".to_string());
    }
    for relative in durable_paths() {
        safe_relative_path(base, Path::new(relative), false)?;
        let path = base.join(relative);
        if !path.is_file() {
            return Err(format!("missing durable workflow file {}", relative));
        }
        if git_path_ignored(base, Path::new(relative))? {
            return Err(format!(
                "durable workflow file {} is ignored by Git",
                relative
            ));
        }
    }
    Ok(())
}

pub fn validate_handoff(
    base: &Path,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<PathBuf, String> {
    validate_scaffold(base, config)?;
    let pointer = issue
        .prompt
        .as_deref()
        .ok_or_else(|| format!("{} has no canonical handoff pointer", issue.id))?;
    let relative = canonical_handoff_path(base, config, issue, Some(pointer))?;
    let path = base.join(&relative);
    reject_symlink(&path, "handoff")?;
    if !path.is_file() {
        return Err(format!("handoff does not exist: {}", relative.display()));
    }
    if git_path_ignored(base, &relative)? {
        return Err(format!("handoff is ignored by Git: {}", relative.display()));
    }
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    validate_document(issue, &text)?;
    Ok(relative)
}

pub fn handoff_manna_id(text: &str) -> Option<String> {
    split_handoff(text)
        .ok()
        .map(|(frontmatter, _)| frontmatter.manna)
}

pub fn find_orphan_handoffs(base: &Path, issues: &[Issue]) -> Vec<(PathBuf, String)> {
    let root = base.join(HANDOFF_DIR);
    let by_id = issues
        .iter()
        .map(|issue| (issue.id.as_str(), issue))
        .collect::<std::collections::HashMap<_, _>>();
    let mut findings = Vec::new();
    let mut stack = vec![root];
    while let Some(directory) = stack.pop() {
        let entries = match fs::read_dir(&directory) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path == base.join(HANDOFF_README) || path.starts_with(base.join(HANDOFF_ARCHIVE_DIR))
            {
                continue;
            }
            let file_type = match entry.file_type() {
                Ok(file_type) => file_type,
                Err(_) => continue,
            };
            if file_type.is_symlink() {
                findings.push((path, "symlink inside canonical handoff root".to_string()));
            } else if file_type.is_dir() {
                stack.push(path);
            } else if path.extension().and_then(|extension| extension.to_str()) == Some("md") {
                let text = fs::read_to_string(&path).unwrap_or_default();
                let Some(manna_id) = handoff_manna_id(&text) else {
                    // `.handoff/` is also the durable home for research and
                    // session-continuation documents. Only structured Manna
                    // work orders participate in the orphan invariant.
                    continue;
                };
                match by_id.get(manna_id.as_str()).copied() {
                    None => findings.push((path, "handoff has no live Manna item".to_string())),
                    Some(issue) if issue.issue_type != IssueType::Item => findings.push((
                        path,
                        format!("handoff belongs to non-actionable {}", issue.issue_type),
                    )),
                    Some(issue)
                        if issue
                            .prompt
                            .as_deref()
                            .is_none_or(|pointer| base.join(pointer) != path) =>
                    {
                        findings.push((
                            path,
                            "handoff is not the item's canonical pointer".to_string(),
                        ))
                    }
                    Some(_) => {}
                }
            }
        }
    }
    findings
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Barrier};
    use std::thread;
    use tempfile::TempDir;

    #[test]
    fn hmac_sha256_matches_rfc_4231_case_one() {
        let key = [0x0b_u8; 20];
        let digest = hmac_sha256(&key, b"Hi There");
        let actual = digest
            .iter()
            .map(|byte| format!("{:02x}", byte))
            .collect::<String>();
        assert_eq!(
            actual,
            "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
        );
    }

    fn setup() -> (TempDir, MannaStore, WorkflowConfig) {
        let temp = TempDir::new().unwrap();
        Command::new("git")
            .current_dir(temp.path())
            .args(["init", "-q"])
            .status()
            .unwrap();
        let store = MannaStore::new(temp.path());
        store.init().unwrap();
        let init = initialize_workflow(temp.path(), &store).unwrap().unwrap();
        (temp, store, init.config)
    }

    fn issue(id: &str, title: &str) -> Issue {
        Issue::new(id.to_string(), title.to_string()).unwrap()
    }

    fn legacy_board() -> (TempDir, MannaStore, Vec<Issue>) {
        let temp = TempDir::new().unwrap();
        Command::new("git")
            .current_dir(temp.path())
            .args(["init", "-q"])
            .status()
            .unwrap();
        let store = MannaStore::new(temp.path());
        store.init().unwrap();
        fs::create_dir(temp.path().join(HANDOFF_DIR)).unwrap();
        fs::write(
            temp.path().join(HANDOFF_DIR).join("legacy-research.md"),
            "Research context, not a strict work order.\n",
        )
        .unwrap();

        let track = {
            let mut row = issue("mn-a00001", "Legacy track");
            row.issue_type = IssueType::Track;
            row
        };
        let active = {
            let mut row = issue("mn-a00002", "Unpaired active item");
            row.track = Some(track.id.clone());
            row
        };
        let blocked = {
            let mut row = issue("mn-a00003", "Blocked unpaired item");
            row.track = Some(track.id.clone());
            row.blocked_by = vec![active.id.clone()];
            row.status = IssueStatus::Blocked;
            row
        };
        let claimed = {
            let mut row = issue("mn-a00004", "Claim without proof");
            row.track = Some(track.id.clone());
            row.status = IssueStatus::InProgress;
            row.claimed_by = Some("legacy-session".to_string());
            row.claimed_at = Some(Utc::now());
            row
        };
        let done = {
            let mut row = issue("mn-a00005", "Historical item");
            row.track = Some(track.id.clone());
            row.status = IssueStatus::Done;
            row.prompt = Some(".dev/session-prompts/deleted.md".to_string());
            row.claimed_by = Some("legacy-history".to_string());
            row.claimed_at = Some(Utc::now());
            row
        };
        let dream = {
            let mut row = issue("mn-a00006", "Parked dream");
            row.issue_type = IssueType::Dream;
            row.track = Some(track.id.clone());
            row
        };
        let rows = vec![track, active, blocked, claimed, done, dream];
        for row in &rows {
            store.append_issue(row).unwrap();
        }
        (temp, store, rows)
    }

    #[test]
    fn preexisting_handoff_directory_does_not_misclassify_a_legacy_board() {
        let (temp, store, _) = legacy_board();
        let initialized = initialize_workflow(temp.path(), &store).unwrap();
        assert!(initialized.is_none());
        assert_eq!(
            load_board_config(temp.path()).unwrap().unwrap().workflow,
            BoardMode::Legacy
        );
    }

    #[test]
    fn legacy_migration_pairs_history_and_exemptions_in_one_idempotent_pass() {
        let (temp, store, _) = legacy_board();
        assert!(initialize_workflow(temp.path(), &store).unwrap().is_none());

        let migrated = migrate_legacy_board(temp.path(), &store).unwrap();
        assert!(migrated.migrated);
        assert!(!migrated.recovered_transaction);
        assert_eq!(migrated.paired_items, 3);
        assert_eq!(migrated.historical_rows, 1);
        assert_eq!(migrated.exempt_rows, 2);
        assert_eq!(migrated.released_claims, 2);

        let rows = store.load_issues().unwrap();
        let config = validate_migrated_board(temp.path(), &rows).unwrap();
        for row in rows
            .iter()
            .filter(|row| row.issue_type == IssueType::Item && row.status != IssueStatus::Done)
        {
            validate_handoff(temp.path(), &config, row).unwrap();
        }
        let released = rows.iter().find(|row| row.id == "mn-a00004").unwrap();
        assert_eq!(released.status, IssueStatus::Open);
        assert!(released.claimed_by.is_none());
        assert_eq!(
            released
                .legacy_migration
                .as_ref()
                .unwrap()
                .released_claimed_by
                .as_deref(),
            Some("legacy-session")
        );
        let history = rows.iter().find(|row| row.id == "mn-a00005").unwrap();
        assert!(history.prompt.is_none());
        assert_eq!(
            history
                .legacy_migration
                .as_ref()
                .unwrap()
                .previous_prompt
                .as_deref(),
            Some(".dev/session-prompts/deleted.md")
        );
        let dream = rows.iter().find(|row| row.id == "mn-a00006").unwrap();
        assert!(dream.prompt.is_none());
        assert_eq!(
            dream.legacy_migration.as_ref().unwrap().disposition,
            LegacyMigrationDisposition::Exempt
        );

        let rows_before_replay = rows.clone();
        let documents_before_replay = rows
            .iter()
            .filter_map(|row| row.prompt.as_deref())
            .map(|path| {
                (
                    path.to_string(),
                    fs::read_to_string(temp.path().join(path)).unwrap(),
                )
            })
            .collect::<Vec<_>>();
        let replay = migrate_legacy_board(temp.path(), &store).unwrap();
        assert!(!replay.migrated);
        assert!(!replay.recovered_transaction);
        assert_eq!(store.load_issues().unwrap(), rows_before_replay);
        for (path, contents) in documents_before_replay {
            assert_eq!(
                fs::read_to_string(temp.path().join(path)).unwrap(),
                contents
            );
        }
        initialize_workflow(temp.path(), &store).unwrap().unwrap();
    }

    #[test]
    fn stale_legacy_writer_cannot_bypass_the_migrated_strict_board() {
        let (temp, store, _) = legacy_board();
        initialize_workflow(temp.path(), &store).unwrap();
        let legacy_snapshot = store.load_issues().unwrap();
        assert!(load_workflow_for_board(temp.path(), &legacy_snapshot)
            .unwrap()
            .is_none());
        migrate_legacy_board(temp.path(), &store).unwrap();

        let unpaired = issue("mn-a00007", "Stale legacy create");
        let error = store.append_issue(&unpaired).unwrap_err().to_string();
        assert!(error.contains("missing its authoritative handoff pair"));

        let current = store
            .load_issues()
            .unwrap()
            .into_iter()
            .find(|row| row.id == "mn-a00002")
            .unwrap();
        let session = SessionIdentity::from_token(
            "migration-race",
            "migration-race-token-0123456789abcdef0123456789abcdef",
        )
        .unwrap();
        let error = store
            .mutate_issue_metadata(&current.id, &session, |row, _| {
                row.title = "Stale legacy metadata".to_string();
                Ok(())
            })
            .unwrap_err()
            .to_string();
        assert!(error.contains("handoff transaction"));
        let error = store
            .delete_issue_owned(&current.id, &session)
            .unwrap_err()
            .to_string();
        assert!(error.contains("archive through the handoff transaction"));

        let handoff = temp.path().join(current.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&handoff).unwrap();
        text.push_str("\nTampered after a stale legacy read.\n");
        fs::write(&handoff, text).unwrap();
        let error = store
            .claim_issue_checked(&current.id, &session, |row, board| {
                let config = load_workflow_for_board(temp.path(), board)?
                    .ok_or_else(|| "expected strict board".to_string())?;
                validate_handoff(temp.path(), &config, row)?;
                Ok(())
            })
            .unwrap_err()
            .to_string();
        assert!(error.contains("binding is stale"));
    }

    #[test]
    fn pending_legacy_migration_recovers_before_pair_journals() {
        let (temp, store, _) = legacy_board();
        initialize_workflow(temp.path(), &store).unwrap();
        let before = store.load_issues().unwrap();
        let transaction = build_legacy_migration(temp.path(), before).unwrap();
        write_legacy_migration_transaction(temp.path(), &transaction).unwrap();

        assert_eq!(
            recover_pair_transactions(temp.path(), &store, &WorkflowConfig::default()).unwrap(),
            0
        );
        assert_eq!(recover_legacy_migration(temp.path(), &store).unwrap(), 1);
        assert!(!legacy_migration_path(temp.path()).exists());
        let rows = store.load_issues().unwrap();
        validate_migrated_board(temp.path(), &rows).unwrap();
    }

    #[test]
    fn tampered_legacy_migration_journal_cannot_mutate_the_board() {
        let (temp, store, original) = legacy_board();
        initialize_workflow(temp.path(), &store).unwrap();
        let transaction = build_legacy_migration(temp.path(), original.clone()).unwrap();
        let path = write_legacy_migration_transaction(temp.path(), &transaction).unwrap();
        let text = fs::read_to_string(&path).unwrap();
        fs::write(&path, text.replace("hmac-sha256:", "hmac-sha256:00")).unwrap();

        let error = recover_legacy_migration(temp.path(), &store).unwrap_err();
        assert!(error.contains("failed HMAC authentication"));
        assert_eq!(store.load_issues().unwrap(), original);
        assert!(path.is_file());
        assert!(!temp.path().join(WORKFLOW_FILE).exists());
    }

    #[test]
    fn legacy_migration_refuses_to_rewrite_a_board_with_a_malformed_line() {
        let (temp, store, _) = legacy_board();
        initialize_workflow(temp.path(), &store).unwrap();
        let board_path = temp.path().join(".manna/issues.jsonl");
        let mut original = fs::read_to_string(&board_path).unwrap();
        original.push_str("{not valid json}\n");
        fs::write(&board_path, &original).unwrap();

        let error = migrate_legacy_board(temp.path(), &store).unwrap_err();
        assert!(error.contains("cannot migrate malformed board line"));
        assert_eq!(fs::read_to_string(&board_path).unwrap(), original);
        assert!(!legacy_migration_path(temp.path()).exists());
    }

    #[test]
    fn migrate_never_reseals_a_tampered_strict_handoff() {
        let (temp, store, config) = setup();
        let paired = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-a00001", "Already strict"),
            None,
        )
        .unwrap();
        let digest = paired.handoff_digest.clone();
        let path = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&path).unwrap();
        text.push_str("\nUnsealed strict edit.\n");
        fs::write(&path, text).unwrap();

        let error = migrate_legacy_board(temp.path(), &store).unwrap_err();
        assert!(error.contains("invalid authoritative handoff"));
        assert_eq!(store.load_issues().unwrap()[0].handoff_digest, digest);
    }

    #[test]
    fn strict_workflow_scaffolds_and_binds_one_item() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Fix the prompt graph");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        assert!(paired.handoff_digest.is_some());
        assert!(validate_handoff(temp.path(), &config, &paired).is_ok());
    }

    #[test]
    fn handoff_paths_cannot_escape_or_cross_symlinks() {
        let (temp, _store, config) = setup();
        let item = issue("mn-abc123", "Bounded work");
        assert!(canonical_handoff_path(temp.path(), &config, &item, Some("../work.md")).is_err());
        assert!(
            canonical_handoff_path(temp.path(), &config, &item, Some(".handoffs/work.md")).is_err()
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::symlink;
            fs::remove_dir_all(temp.path().join(HANDOFF_DIR)).unwrap();
            let outside = TempDir::new().unwrap();
            symlink(outside.path(), temp.path().join(HANDOFF_DIR)).unwrap();
            assert!(
                canonical_handoff_path(temp.path(), &config, &item, Some(".handoff/work.md"))
                    .is_err()
            );
        }
    }

    #[test]
    fn loose_comment_cannot_satisfy_binding() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "One claim only");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let path = temp.path().join(paired.prompt.as_deref().unwrap());
        fs::write(&path, "<!-- agent-do manna claim mn-abc123 -->\n").unwrap();
        assert!(validate_handoff(temp.path(), &config, &paired).is_err());
    }

    #[test]
    fn any_unsealed_content_change_breaks_the_binding() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Bound work");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let path = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&path).unwrap();
        text.push_str("\nExtra scope that was not sealed.\n");
        fs::write(&path, text).unwrap();
        let error = validate_handoff(temp.path(), &config, &paired).unwrap_err();
        assert!(error.contains("binding is stale"));
    }

    #[test]
    fn metadata_update_cannot_silently_seal_a_body_edit() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Bound work");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let path = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&path).unwrap();
        text.push_str("\nUnapproved scope expansion.\n");
        fs::write(&path, text).unwrap();

        let mut renamed = paired.clone();
        renamed.title = "Unrelated metadata update".to_string();
        renamed.updated_at = Utc::now();
        let error =
            rebind_handoff_metadata(temp.path(), &store, &config, &paired, &renamed).unwrap_err();
        assert!(error.contains("unsealed"));
        assert_eq!(store.load_issues().unwrap()[0], paired);

        let sealed = seal_handoff(temp.path(), &store, &config, &paired).unwrap();
        assert!(validate_handoff(temp.path(), &config, &sealed).is_ok());
    }

    #[test]
    fn restoring_config_does_not_bless_an_unsealed_handoff() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Bound work");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let digest = paired.handoff_digest.clone();
        let handoff = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&handoff).unwrap();
        text.push_str("\nUnsealed after config deletion.\n");
        fs::write(&handoff, text).unwrap();
        fs::remove_file(temp.path().join(WORKFLOW_FILE)).unwrap();

        let error = initialize_workflow(temp.path(), &store).unwrap_err();
        assert!(error.contains("invalid handoff"));
        assert!(temp.path().join(WORKFLOW_FILE).is_file());
        assert_eq!(store.load_issues().unwrap()[0].handoff_digest, digest);
    }

    #[test]
    fn workflow_version_downgrade_does_not_reopen_the_seal() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Bound work");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let digest = paired.handoff_digest.clone();
        let handoff = temp.path().join(paired.prompt.as_deref().unwrap());
        let mut text = fs::read_to_string(&handoff).unwrap();
        text.push_str("\nAttempted downgrade reseal.\n");
        fs::write(&handoff, text).unwrap();
        fs::write(
            temp.path().join(WORKFLOW_FILE),
            "version: 1\nhandoff_dir: .handoff\n",
        )
        .unwrap();

        let error = initialize_workflow(temp.path(), &store).unwrap_err();
        assert!(error.contains("invalid handoff"));
        assert_eq!(store.load_issues().unwrap()[0].handoff_digest, digest);
        assert_eq!(load_workflow(temp.path()).unwrap().unwrap().version, 2);
    }

    #[test]
    fn interrupted_v1_migration_finishes_only_unbound_items() {
        let (temp, store, config) = setup();
        let first = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-abc123", "Already migrated"),
            None,
        )
        .unwrap();
        let second = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-def456", "Still legacy"),
            None,
        )
        .unwrap();
        let first_document =
            fs::read_to_string(temp.path().join(first.prompt.as_deref().unwrap())).unwrap();
        let mut legacy_second = second.clone();
        legacy_second.handoff_digest = None;
        store
            .recover_replace_issue(&second, &legacy_second)
            .unwrap();
        fs::write(
            temp.path().join(WORKFLOW_FILE),
            "version: 1\nhandoff_dir: .handoff\n",
        )
        .unwrap();

        let initialized = initialize_workflow(temp.path(), &store).unwrap().unwrap();
        assert_eq!(initialized.upgraded_items, 1);
        let rows = store.load_issues().unwrap();
        let current_first = rows.iter().find(|row| row.id == first.id).unwrap();
        let current_second = rows.iter().find(|row| row.id == second.id).unwrap();
        assert_eq!(current_first.handoff_digest, first.handoff_digest);
        assert_eq!(
            fs::read_to_string(temp.path().join(first.prompt.as_deref().unwrap())).unwrap(),
            first_document
        );
        assert!(current_second.handoff_digest.is_some());
        validate_handoff(temp.path(), &config, current_second).unwrap();
        assert_eq!(load_workflow(temp.path()).unwrap().unwrap().version, 2);
    }

    #[test]
    fn authenticated_journal_still_cannot_target_outside_handoff() {
        let (temp, store, config) = setup();
        let mut item = issue("mn-abc123", "Forged destination");
        item.prompt = Some("victim.md".to_string());
        let document = render_handoff(temp.path(), &item).unwrap();
        let (item, document) = prepare_bound_issue(&item, document).unwrap();
        let mut transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Create,
            issue_id: item.id.clone(),
            before: None,
            after: Some(item),
            handoff: "victim.md".to_string(),
            archive: None,
            document: Some(document),
            integrity: String::new(),
        };
        let key = load_recovery_key(temp.path(), true).unwrap();
        transaction.integrity = transaction_signature(temp.path(), &key, &transaction).unwrap();
        safe_create_dir_all(temp.path(), Path::new(TRANSACTION_DIR)).unwrap();
        let path = transaction_path(temp.path(), &transaction.issue_id);
        fs::write(&path, serde_yaml::to_string(&transaction).unwrap()).unwrap();

        let error = recover_pair_transactions(temp.path(), &store, &config).unwrap_err();
        assert!(error.contains("under .handoff") || error.contains("must live under"));
        assert!(!temp.path().join("victim.md").exists());
        assert!(store.load_issues().unwrap().is_empty());
        assert!(path.is_file());
    }

    #[test]
    fn journal_signature_is_bound_to_the_project_root() {
        let (temp, _store, _config) = setup();
        let other = TempDir::new().unwrap();
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Delete,
            issue_id: "mn-abc123".to_string(),
            before: Some(issue("mn-abc123", "Bound project")),
            after: None,
            handoff: ".handoff/mn-abc123-bound-project.md".to_string(),
            archive: Some(".handoff/.archive/mn-abc123-bound-project.md".to_string()),
            document: None,
            integrity: String::new(),
        };
        let key = [7_u8; 32];
        let original = transaction_signature(temp.path(), &key, &transaction).unwrap();
        let copied = transaction_signature(other.path(), &key, &transaction).unwrap();
        assert_ne!(original, copied);
    }

    #[test]
    fn planted_unsigned_journal_is_never_executed() {
        let (temp, store, config) = setup();
        load_recovery_key(temp.path(), true).unwrap();
        safe_create_dir_all(temp.path(), Path::new(TRANSACTION_DIR)).unwrap();
        let path = transaction_path(temp.path(), "mn-abc123");
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Delete,
            issue_id: "mn-abc123".to_string(),
            before: Some(issue("mn-abc123", "Planted")),
            after: None,
            handoff: ".handoff/mn-abc123-planted.md".to_string(),
            archive: Some(".handoff/.archive/mn-abc123-forged.md".to_string()),
            document: None,
            integrity: "hmac-sha256:00".to_string(),
        };
        fs::write(&path, serde_yaml::to_string(&transaction).unwrap()).unwrap();
        let error = recover_pair_transactions(temp.path(), &store, &config).unwrap_err();
        assert!(error.contains("failed HMAC authentication"), "{error}");
        assert!(store.load_issues().unwrap().is_empty());
        assert!(path.is_file());
    }

    #[test]
    fn no_replace_install_has_exactly_one_concurrent_winner() {
        let temp = TempDir::new().unwrap();
        let target = Arc::new(temp.path().join("journal.yaml"));
        let barrier = Arc::new(Barrier::new(12));
        let mut handles = Vec::new();
        for contender in 0..12 {
            let target = Arc::clone(&target);
            let barrier = Arc::clone(&barrier);
            handles.push(thread::spawn(move || {
                let payload = format!("writer:{}", contender);
                barrier.wait();
                (
                    payload.clone(),
                    atomic_write(&target, payload.as_bytes(), false),
                )
            }));
        }
        let outcomes = handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .collect::<Vec<_>>();
        let winners = outcomes
            .iter()
            .filter(|(_, result)| result.is_ok())
            .collect::<Vec<_>>();
        assert_eq!(winners.len(), 1);
        assert_eq!(fs::read_to_string(&*target).unwrap(), winners[0].0);
    }

    #[test]
    fn empty_transaction_directory_does_not_require_a_recovery_key() {
        let (temp, store, config) = setup();
        safe_create_dir_all(temp.path(), Path::new(TRANSACTION_DIR)).unwrap();
        let key = recovery_key_path(temp.path()).unwrap();
        assert!(!key.exists());
        assert_eq!(
            recover_pair_transactions(temp.path(), &store, &config).unwrap(),
            0
        );
        assert!(!key.exists());
    }

    #[test]
    fn obsolete_authenticated_intent_is_discarded_without_applying_it() {
        let (temp, store, config) = setup();
        let before = create_paired_issue(
            temp.path(),
            &store,
            &config,
            &issue("mn-abc123", "Original"),
            None,
        )
        .unwrap();
        let handoff = Path::new(before.prompt.as_deref().unwrap());
        let original_document = fs::read_to_string(temp.path().join(handoff)).unwrap();

        let mut stale_metadata = before.clone();
        stale_metadata.title = "Stale writer".to_string();
        stale_metadata.updated_at = Utc::now();
        let stale_document =
            update_frontmatter_for_issue(&original_document, &stale_metadata).unwrap();
        let (stale_after, stale_document) =
            prepare_bound_issue(&stale_metadata, stale_document).unwrap();
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Rebind,
            issue_id: before.id.clone(),
            before: Some(before.clone()),
            after: Some(stale_after),
            handoff: handoff.to_string_lossy().into_owned(),
            archive: None,
            document: Some(stale_document),
            integrity: String::new(),
        };
        let path = write_transaction(temp.path(), &config, &transaction).unwrap();

        let mut winner = before.clone();
        winner.description = Some("A different writer won".to_string());
        winner.updated_at = Utc::now();
        store.recover_replace_issue(&before, &winner).unwrap();

        let key = load_recovery_key(temp.path(), false).unwrap();
        let outcome = complete_transaction_path(temp.path(), &store, &config, &path, &key).unwrap();
        assert!(matches!(outcome, TransactionOutcome::DiscardedConflict(_)));
        assert!(!path.exists());
        assert_eq!(store.load_issues().unwrap()[0], winner);
        assert_eq!(
            fs::read_to_string(temp.path().join(handoff)).unwrap(),
            original_document
        );
    }

    #[test]
    fn pending_create_transaction_recovers_both_sides() {
        let (temp, store, config) = setup();
        let mut item = issue("mn-abc123", "Interrupted create");
        let relative = canonical_handoff_path(temp.path(), &config, &item, None).unwrap();
        item.prompt = Some(relative.to_string_lossy().into_owned());
        let document = render_handoff(temp.path(), &item).unwrap();
        let (item, document) = prepare_bound_issue(&item, document).unwrap();
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Create,
            issue_id: item.id.clone(),
            before: None,
            after: Some(item.clone()),
            handoff: relative.to_string_lossy().into_owned(),
            archive: None,
            document: Some(document),
            integrity: String::new(),
        };
        write_transaction(temp.path(), &config, &transaction).unwrap();

        assert!(store.load_issues().unwrap().is_empty());
        assert!(!temp.path().join(&relative).exists());
        assert_eq!(
            recover_pair_transactions(temp.path(), &store, &config).unwrap(),
            1
        );
        assert_eq!(store.load_issues().unwrap().len(), 1);
        assert!(validate_handoff(temp.path(), &config, &item).is_ok());
        assert!(!transaction_path(temp.path(), &item.id).exists());
    }

    #[test]
    fn concurrent_recovery_tolerates_a_peer_removing_the_same_journal() {
        let (temp, store, config) = setup();
        let mut item = issue("mn-abc123", "Concurrent recovery");
        let relative = canonical_handoff_path(temp.path(), &config, &item, None).unwrap();
        item.prompt = Some(relative.to_string_lossy().into_owned());
        let document = render_handoff(temp.path(), &item).unwrap();
        let (item, document) = prepare_bound_issue(&item, document).unwrap();
        let transaction = PairTransaction {
            version: WORKFLOW_VERSION,
            action: PairAction::Create,
            issue_id: item.id.clone(),
            before: None,
            after: Some(item.clone()),
            handoff: relative.to_string_lossy().into_owned(),
            archive: None,
            document: Some(document),
            integrity: String::new(),
        };
        write_transaction(temp.path(), &config, &transaction).unwrap();

        let barrier = Arc::new(Barrier::new(12));
        let mut handles = Vec::new();
        for _ in 0..12 {
            let base = temp.path().to_path_buf();
            let store = store.clone();
            let config = config.clone();
            let barrier = Arc::clone(&barrier);
            handles.push(thread::spawn(move || {
                barrier.wait();
                recover_pair_transactions(&base, &store, &config)
            }));
        }
        for handle in handles {
            handle.join().unwrap().unwrap();
        }
        assert_eq!(store.load_issues().unwrap(), vec![item.clone()]);
        assert!(validate_handoff(temp.path(), &config, &item).is_ok());
        assert!(!transaction_path(temp.path(), &item.id).exists());
    }

    #[test]
    fn deleting_a_pair_archives_its_handoff_without_an_orphan() {
        let (temp, store, config) = setup();
        let item = issue("mn-abc123", "Delete pair");
        let paired = create_paired_issue(temp.path(), &store, &config, &item, None).unwrap();
        let original = temp.path().join(paired.prompt.as_deref().unwrap());
        delete_paired_issue(temp.path(), &store, &config, &paired).unwrap();
        assert!(store.load_issues().unwrap().is_empty());
        assert!(!original.exists());
        assert!(temp.path().join(archive_path(&paired)).is_file());
        assert!(find_orphan_handoffs(temp.path(), &[]).is_empty());
    }

    #[test]
    fn freeform_handoff_research_is_not_an_orphan_work_order() {
        let (temp, _store, _config) = setup();
        fs::write(
            temp.path().join(HANDOFF_DIR).join("62-research.md"),
            "Research protocol without Manna frontmatter.\n",
        )
        .unwrap();
        assert!(find_orphan_handoffs(temp.path(), &[]).is_empty());

        let orphan = issue("mn-a00001", "Structured orphan");
        let document = render_handoff(temp.path(), &orphan).unwrap();
        fs::write(
            temp.path().join(HANDOFF_DIR).join("mn-a00001-orphan.md"),
            document,
        )
        .unwrap();
        let findings = find_orphan_handoffs(temp.path(), &[]);
        assert_eq!(findings.len(), 1);
        assert!(findings[0].1.contains("no live Manna item"));
    }

    #[test]
    fn strict_scaffold_checks_the_board_file_visibility() {
        let temp = TempDir::new().unwrap();
        Command::new("git")
            .current_dir(temp.path())
            .args(["init", "-q"])
            .status()
            .unwrap();
        let store = MannaStore::new(temp.path());
        store.init().unwrap();
        let config = initialize_workflow(temp.path(), &store)
            .unwrap()
            .unwrap()
            .config;
        let mut gitignore = fs::read_to_string(temp.path().join(".gitignore")).unwrap_or_default();
        gitignore.push_str("\n.manna/issues.jsonl\n");
        fs::write(temp.path().join(".gitignore"), gitignore).unwrap();
        assert!(validate_scaffold(temp.path(), &config)
            .unwrap_err()
            .contains("issues.jsonl is ignored"));
    }

    #[test]
    fn ancestor_repository_ignore_rules_are_enforced() {
        let parent = TempDir::new().unwrap();
        Command::new("git")
            .current_dir(parent.path())
            .args(["init", "-q"])
            .status()
            .unwrap();
        fs::write(parent.path().join(".gitignore"), "/nested/\n").unwrap();
        let nested = parent.path().join("nested");
        fs::create_dir(&nested).unwrap();
        let store = MannaStore::new(&nested);
        store.init().unwrap();
        let error = initialize_workflow(&nested, &store).unwrap_err();
        assert!(error.contains("still ignored by Git"));
    }

    #[test]
    fn missing_workflow_config_is_corruption_not_legacy() {
        let (temp, store, _config) = setup();
        let item = issue("mn-abc123", "Strict marker");
        // Manufacture the impossible row through the recovery fixture path;
        // the public append path now correctly rejects unpaired strict items.
        store.recover_issue(&item).unwrap();
        fs::remove_file(temp.path().join(WORKFLOW_FILE)).unwrap();
        let issues = store.load_issues().unwrap();
        assert!(load_workflow_for_board(temp.path(), &issues).is_err());
    }

    #[test]
    fn init_restores_a_deleted_strict_config_even_on_an_empty_board() {
        let (temp, store, _config) = setup();
        fs::remove_file(temp.path().join(WORKFLOW_FILE)).unwrap();
        fs::remove_dir_all(temp.path().join(HANDOFF_DIR)).unwrap();
        assert!(load_workflow_for_board(temp.path(), &[]).is_err());
        let init = initialize_workflow(temp.path(), &store).unwrap().unwrap();
        assert!(init.restored_config);
        assert!(temp.path().join(WORKFLOW_FILE).is_file());
        assert!(temp.path().join(HANDOFF_README).is_file());
    }
}

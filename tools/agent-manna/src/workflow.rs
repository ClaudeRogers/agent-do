//! Canonical Manna and handoff workflow scaffolding.
//!
//! A strict board is one recoverable state machine. `.manna/` owns lifecycle
//! state, `.handoff/` owns bound work orders, and an ignored transaction
//! journal closes the small crash window between those two filesystems.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

use chrono::Utc;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::issue::{Issue, IssueStatus, IssueType};
use crate::store::MannaStore;

pub const WORKFLOW_VERSION: u32 = 2;
pub const HANDOFF_DIR: &str = ".handoff";
pub const WORKFLOW_FILE: &str = ".manna/workflow.yaml";
pub const BOARD_FILE: &str = ".manna/board.yaml";
pub const HANDOFF_README: &str = ".handoff/README.md";
pub const HANDOFF_ARCHIVE_DIR: &str = ".handoff/.archive";
const TRANSACTION_DIR: &str = ".manna/transactions";

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
}

impl BoardConfig {
    fn strict() -> Self {
        BoardConfig {
            version: 1,
            workflow: BoardMode::Strict,
        }
    }

    fn legacy() -> Self {
        BoardConfig {
            version: 1,
            workflow: BoardMode::Legacy,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum PairAction {
    Create,
    Attach,
    Rebind,
    Detach,
    Delete,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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
}

pub fn workflow_path(base: &Path) -> PathBuf {
    base.join(WORKFLOW_FILE)
}

fn board_path(base: &Path) -> PathBuf {
    base.join(BOARD_FILE)
}

fn load_board_config(base: &Path) -> Result<Option<BoardConfig>, String> {
    let path = board_path(base);
    reject_symlink(&path, "board identity")?;
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
    atomic_write_replace(&board_path(base), &yaml)
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
    if !replace && path_exists(path) {
        return Err(format!(
            "refusing to overwrite existing file {}",
            path.display()
        ));
    }
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
    if let Err(error) = fs::rename(&temp, path) {
        let _ = fs::remove_file(&temp);
        return Err(format!("failed to install {}: {}", path.display(), error));
    }
    sync_parent(path)
}

fn atomic_write_replace(path: &Path, contents: &str) -> Result<(), String> {
    atomic_write(path, contents.as_bytes(), true)
}

pub fn load_workflow(base: &Path) -> Result<Option<WorkflowConfig>, String> {
    let path = workflow_path(base);
    reject_symlink(&path, "workflow config")?;
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

pub fn workflow_markers_present(base: &Path, issues: &[Issue]) -> bool {
    path_exists(&base.join(HANDOFF_DIR))
        || issues.iter().any(|issue| {
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
                    "legacy board identity conflicts with strict workflow state; run `agent-do manna init`"
                        .to_string(),
                );
            }
            Ok(None)
        }
    }
}

fn git_path_ignored(base: &Path, relative: &Path) -> Result<bool, String> {
    if !base.join(".git").exists() {
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
    let marker = "# agent-do workflow: .manna and .handoff are durable state";
    if !existing.contains(marker) {
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&gitignore)
            .map_err(|error| format!("failed to update {}: {}", gitignore.display(), error))?;
        if !existing.is_empty() && !existing.ends_with('\n') {
            writeln!(file).map_err(|error| error.to_string())?;
        }
        writeln!(
            file,
            "\n{}\n!.manna/\n.manna/*\n!.manna/issues.jsonl\n!.manna/sessions.jsonl\n!.manna/board.yaml\n!.manna/workflow.yaml\n!.manna/drift.yaml\n.manna/board.lock\n.manna/transactions/\n!.handoff/\n!.handoff/**",
            marker
        )
        .map_err(|error| format!("failed to update {}: {}", gitignore.display(), error))?;
    } else if !existing.lines().any(|line| line == "!.manna/board.yaml") {
        let mut file = OpenOptions::new()
            .append(true)
            .open(&gitignore)
            .map_err(|error| format!("failed to update {}: {}", gitignore.display(), error))?;
        writeln!(file, "!.manna/board.yaml\n.manna/transactions/")
            .map_err(|error| format!("failed to update {}: {}", gitignore.display(), error))?;
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

fn write_transaction(base: &Path, transaction: &PairTransaction) -> Result<(), String> {
    safe_create_dir_all(base, Path::new(TRANSACTION_DIR))?;
    let path = transaction_path(base, &transaction.issue_id);
    if path_exists(&path) {
        return Err(format!(
            "pending Manna pair transaction already exists for {}; run `agent-do manna init`",
            transaction.issue_id
        ));
    }
    let yaml = serde_yaml::to_string(transaction)
        .map_err(|error| format!("failed to serialize pair transaction: {}", error))?;
    atomic_write(&path, yaml.as_bytes(), false)
}

fn remove_transaction(base: &Path, issue_id: &str) -> Result<(), String> {
    let path = transaction_path(base, issue_id);
    reject_symlink(&path, "transaction")?;
    if path.exists() {
        match fs::remove_file(&path) {
            Ok(()) => sync_parent(&path)?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(format!("failed to remove {}: {}", path.display(), error)),
        }
    }
    Ok(())
}

fn install_transaction_document(
    base: &Path,
    relative: &Path,
    document: &str,
) -> Result<(), String> {
    let relative = safe_relative_path(base, relative, true)?;
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

fn complete_transaction(
    base: &Path,
    store: &MannaStore,
    transaction: &PairTransaction,
) -> Result<(), String> {
    if transaction.version != WORKFLOW_VERSION {
        return Err(format!(
            "unsupported pair transaction version {}",
            transaction.version
        ));
    }
    let handoff = Path::new(&transaction.handoff);
    match transaction.action {
        PairAction::Create => {
            let after = transaction
                .after
                .as_ref()
                .ok_or_else(|| "create transaction has no after row".to_string())?;
            let document = transaction
                .document
                .as_deref()
                .ok_or_else(|| "create transaction has no handoff document".to_string())?;
            store
                .recover_issue_with(after, || {
                    install_transaction_document(base, handoff, document)
                })
                .map_err(|error| error.to_string())?;
        }
        PairAction::Attach | PairAction::Rebind => {
            let before = transaction
                .before
                .as_ref()
                .ok_or_else(|| "pair update transaction has no before row".to_string())?;
            let after = transaction
                .after
                .as_ref()
                .ok_or_else(|| "pair update transaction has no after row".to_string())?;
            let document = transaction
                .document
                .as_deref()
                .ok_or_else(|| "pair update transaction has no handoff document".to_string())?;
            store
                .recover_replace_issue_with(before, after, || {
                    install_transaction_document(base, handoff, document)
                })
                .map_err(|error| error.to_string())?;
        }
        PairAction::Detach => {
            let before = transaction
                .before
                .as_ref()
                .ok_or_else(|| "detach transaction has no before row".to_string())?;
            let after = transaction
                .after
                .as_ref()
                .ok_or_else(|| "detach transaction has no after row".to_string())?;
            let archive = transaction
                .archive
                .as_deref()
                .ok_or_else(|| "detach transaction has no archive path".to_string())?;
            store
                .recover_replace_issue_with(before, after, || {
                    archive_handoff(base, handoff, Path::new(archive))
                })
                .map_err(|error| error.to_string())?;
        }
        PairAction::Delete => {
            let before = transaction
                .before
                .as_ref()
                .ok_or_else(|| "delete transaction has no before row".to_string())?;
            let archive = transaction
                .archive
                .as_deref()
                .ok_or_else(|| "delete transaction has no archive path".to_string())?;
            store
                .recover_delete_issue_with(before, || {
                    archive_handoff(base, handoff, Path::new(archive))
                })
                .map_err(|error| error.to_string())?;
        }
    }
    remove_transaction(base, &transaction.issue_id)
}

fn run_transaction(
    base: &Path,
    store: &MannaStore,
    transaction: PairTransaction,
) -> Result<(), String> {
    write_transaction(base, &transaction)?;
    complete_transaction(base, store, &transaction).map_err(|error| {
        format!(
            "Manna pair transaction for {} is pending recovery: {}. Run `agent-do manna init`.",
            transaction.issue_id, error
        )
    })
}

pub fn recover_pair_transactions(base: &Path, store: &MannaStore) -> Result<usize, String> {
    let directory = base.join(TRANSACTION_DIR);
    reject_symlink(&directory, "transaction directory")?;
    if !directory.exists() {
        return Ok(0);
    }
    let mut paths = fs::read_dir(&directory)
        .map_err(|error| format!("failed to inspect {}: {}", directory.display(), error))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|extension| extension.to_str()) == Some("yaml"))
        .collect::<Vec<_>>();
    paths.sort();
    let mut recovered = 0;
    for path in paths {
        reject_symlink(&path, "transaction")?;
        let text = fs::read_to_string(&path)
            .map_err(|error| format!("failed to read {}: {}", path.display(), error))?;
        let transaction: PairTransaction = serde_yaml::from_str(&text)
            .map_err(|error| format!("invalid pair transaction {}: {}", path.display(), error))?;
        complete_transaction(base, store, &transaction)?;
        recovered += 1;
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
    };
    run_transaction(base, store, transaction)?;
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
    };
    run_transaction(base, store, transaction)?;
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
    };
    run_transaction(base, store, transaction)?;
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
    };
    run_transaction(base, store, transaction)
}

fn update_frontmatter_for_issue(text: &str, issue: &Issue) -> Result<String, String> {
    let (mut frontmatter, body) = split_handoff(text)?;
    frontmatter.workflow = WORKFLOW_VERSION;
    frontmatter.manna = issue.id.clone();
    frontmatter.track = issue.track.clone();
    frontmatter.source = issue.source.clone();
    frontmatter.scope = issue.title.clone();
    render_document(&frontmatter, body)
}

pub fn rebind_handoff(
    base: &Path,
    store: &MannaStore,
    config: &WorkflowConfig,
    before: &Issue,
    after_metadata: &Issue,
    use_file_contents: bool,
) -> Result<Issue, String> {
    let relative = canonical_handoff_path(base, config, before, before.prompt.as_deref())?;
    preflight_handoff(base, &relative)?;
    let path = base.join(&relative);
    let existing = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {}", relative.display(), error))?;
    let document = if use_file_contents {
        update_frontmatter_for_issue(&existing, after_metadata)?
    } else {
        render_handoff(base, after_metadata)?
    };
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
    };
    run_transaction(base, store, transaction)?;
    Ok(after)
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
    };
    run_transaction(base, store, transaction)?;
    Ok(after)
}

pub fn initialize_workflow(
    base: &Path,
    store: &MannaStore,
) -> Result<Option<WorkflowInit>, String> {
    let recovered_transactions = recover_pair_transactions(base, store)?;
    let issues = store.load_issues().map_err(|error| error.to_string())?;
    let existing = load_workflow(base)?;
    let strict_markers = workflow_markers_present(base, &issues);
    let board = match load_board_config(base)? {
        Some(board) => board,
        None if strict_markers || issues.is_empty() => {
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

    let requires_upgrade = existing
        .as_ref()
        .is_some_and(|workflow| workflow.version < WORKFLOW_VERSION)
        || restored_config;
    let mut upgraded_items = 0;
    if requires_upgrade {
        for issue in issues.iter().filter(|issue| {
            issue.issue_type == IssueType::Item
                && issue.status != IssueStatus::Done
                && issue.prompt.is_some()
        }) {
            upgrade_legacy_handoff(base, store, &config, issue)?;
            upgraded_items += 1;
        }
    }
    atomic_write_replace(&workflow_path(base), &yaml)?;
    validate_scaffold(base, &config)?;
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
                match handoff_manna_id(&text).and_then(|id| by_id.get(id.as_str()).copied()) {
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
    use tempfile::TempDir;

    fn setup() -> (TempDir, MannaStore, WorkflowConfig) {
        let temp = TempDir::new().unwrap();
        let store = MannaStore::new(temp.path());
        store.init().unwrap();
        let init = initialize_workflow(temp.path(), &store).unwrap().unwrap();
        (temp, store, init.config)
    }

    fn issue(id: &str, title: &str) -> Issue {
        Issue::new(id.to_string(), title.to_string()).unwrap()
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
        };
        write_transaction(temp.path(), &transaction).unwrap();

        assert!(store.load_issues().unwrap().is_empty());
        assert!(!temp.path().join(&relative).exists());
        assert_eq!(recover_pair_transactions(temp.path(), &store).unwrap(), 1);
        assert_eq!(store.load_issues().unwrap().len(), 1);
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
    fn missing_workflow_config_is_corruption_not_legacy() {
        let (temp, store, _config) = setup();
        let item = issue("mn-abc123", "Strict marker");
        store.append_issue(&item).unwrap();
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

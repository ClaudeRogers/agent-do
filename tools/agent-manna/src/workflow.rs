//! Canonical Manna and handoff workflow scaffolding.
//!
//! New boards are strict: `.manna/` owns status and dependency state, while
//! `.handoff/` owns one portable work order for every actionable item.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

use serde::{Deserialize, Serialize};

use crate::issue::Issue;
use crate::reconcile::claim_command_ids;

pub const WORKFLOW_VERSION: u32 = 1;
pub const HANDOFF_DIR: &str = ".handoff";
pub const WORKFLOW_FILE: &str = ".manna/workflow.yaml";
pub const HANDOFF_README: &str = ".handoff/README.md";

const README_CONTENT: &str = r#"# agent-do handoffs

This directory is generated workflow state. `.manna/` owns status, tracks,
claims, and blockers. Each actionable Manna item owns exactly one Markdown
work order here, and the two point at each other.

Rules:

- Create work through `agent-do manna create`; do not hand-build parallel
  prompt roots such as `.handoffs/`, `.dev/session-prompts/`, or
  `<campaign>/handoff-prompts/`.
- The Manna item `prompt` field points to `.handoff/mn-xxxxxx-<slug>.md`.
- The handoff contains exactly one `agent-do manna claim mn-xxxxxx` command.
- Board state stays in Manna. The handoff contains scope, authority,
  deliverables, and verification, never a second backlog.
- Commit `.manna/workflow.yaml`, `.manna/issues.jsonl`, and `.handoff/`.
"#;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WorkflowConfig {
    pub version: u32,
    pub handoff_dir: String,
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
    pub fn validate(&self) -> Result<(), String> {
        if self.version != WORKFLOW_VERSION {
            return Err(format!(
                "unsupported Manna workflow version {} (expected {})",
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
}

#[derive(Debug, Clone)]
pub struct WorkflowInit {
    pub config: WorkflowConfig,
    pub gitignore_updated: bool,
}

pub fn workflow_path(base: &Path) -> PathBuf {
    base.join(WORKFLOW_FILE)
}

pub fn load_workflow(base: &Path) -> Result<Option<WorkflowConfig>, String> {
    let path = workflow_path(base);
    if !path.is_file() {
        return Ok(None);
    }
    let text = fs::read_to_string(&path)
        .map_err(|e| format!("failed to read {}: {}", path.display(), e))?;
    let config: WorkflowConfig =
        serde_yaml::from_str(&text).map_err(|e| format!("invalid {}: {}", path.display(), e))?;
    config.validate()?;
    Ok(Some(config))
}

fn atomic_write_new(path: &Path, contents: &str) -> Result<bool, String> {
    if path.exists() {
        return Ok(false);
    }
    let parent = path
        .parent()
        .ok_or_else(|| format!("path has no parent: {}", path.display()))?;
    fs::create_dir_all(parent)
        .map_err(|e| format!("failed to create {}: {}", parent.display(), e))?;
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| format!("invalid file name: {}", path.display()))?;
    let temp = parent.join(format!(".{}.{}.tmp", name, std::process::id()));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|e| format!("failed to create {}: {}", temp.display(), e))?;
    if let Err(e) = file
        .write_all(contents.as_bytes())
        .and_then(|_| file.sync_all())
    {
        let _ = fs::remove_file(&temp);
        return Err(format!("failed to write {}: {}", temp.display(), e));
    }
    drop(file);
    if let Err(e) = fs::rename(&temp, path) {
        let _ = fs::remove_file(&temp);
        return Err(format!("failed to install {}: {}", path.display(), e));
    }
    Ok(true)
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
        .map_err(|e| format!("git check-ignore unavailable: {}", e))?;
    match output.status.code() {
        Some(0) => Ok(true),
        Some(1) => Ok(false),
        code => Err(format!("git check-ignore failed with status {:?}", code)),
    }
}

fn ensure_workflow_tracked(base: &Path) -> Result<bool, String> {
    let handoff_probe = Path::new(HANDOFF_README);
    let manna_probe = Path::new(WORKFLOW_FILE);
    if !git_path_ignored(base, handoff_probe)? && !git_path_ignored(base, manna_probe)? {
        return Ok(false);
    }

    let gitignore = base.join(".gitignore");
    if gitignore.is_symlink() {
        return Err("refusing to edit a symlinked .gitignore".to_string());
    }
    let existing = fs::read_to_string(&gitignore).unwrap_or_default();
    let marker = "# agent-do workflow: .manna and .handoff are durable state";
    if !existing.contains(marker) {
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&gitignore)
            .map_err(|e| format!("failed to update {}: {}", gitignore.display(), e))?;
        if !existing.is_empty() && !existing.ends_with('\n') {
            writeln!(file).map_err(|e| e.to_string())?;
        }
        writeln!(
            file,
            "\n{}\n!.manna/\n.manna/*\n!.manna/issues.jsonl\n!.manna/sessions.jsonl\n!.manna/workflow.yaml\n!.manna/drift.yaml\n.manna/board.lock\n!.handoff/\n!.handoff/**",
            marker
        )
            .map_err(|e| format!("failed to update {}: {}", gitignore.display(), e))?;
    }
    if git_path_ignored(base, handoff_probe)? || git_path_ignored(base, manna_probe)? {
        return Err(
            ".manna or .handoff is still ignored after adding the local tracking rule"
                .to_string(),
        );
    }
    Ok(true)
}

fn validate_new_handoff_root(base: &Path) -> Result<(), String> {
    let handoff_dir = base.join(HANDOFF_DIR);
    if !handoff_dir.is_dir() {
        return Ok(());
    }
    let mut entries = fs::read_dir(&handoff_dir)
        .map_err(|e| format!("failed to inspect {}: {}", handoff_dir.display(), e))?;
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
        && fs::read_to_string(first.path()).ok().as_deref() == Some(README_CONTENT)
    {
        return Ok(());
    }
    Err(format!(
        "{} already contains non-workflow files; migrate or archive them before initializing a strict board",
        HANDOFF_DIR
    ))
}

pub fn initialize_workflow(base: &Path) -> Result<WorkflowInit, String> {
    if let Some(config) = load_workflow(base)? {
        let gitignore_updated = ensure_workflow_tracked(base)?;
        atomic_write_new(&base.join(HANDOFF_README), README_CONTENT)?;
        return Ok(WorkflowInit {
            config,
            gitignore_updated,
        });
    }

    validate_new_handoff_root(base)?;
    let gitignore_updated = ensure_workflow_tracked(base)?;
    let config = WorkflowConfig::default();
    atomic_write_new(&base.join(HANDOFF_README), README_CONTENT)?;
    let yaml = serde_yaml::to_string(&config)
        .map_err(|e| format!("failed to serialize workflow config: {}", e))?;
    atomic_write_new(&workflow_path(base), &yaml)?;
    Ok(WorkflowInit {
        config,
        gitignore_updated,
    })
}

pub fn validate_scaffold(base: &Path, config: &WorkflowConfig) -> Result<(), String> {
    config.validate()?;
    let readme = base.join(HANDOFF_README);
    if !readme.is_file() {
        return Err(format!(
            "missing generated workflow file {}",
            HANDOFF_README
        ));
    }
    if git_path_ignored(base, Path::new(HANDOFF_README))? {
        return Err(format!("{} is ignored by Git", HANDOFF_DIR));
    }
    if git_path_ignored(base, Path::new(WORKFLOW_FILE))? {
        return Err(".manna workflow state is ignored by Git".to_string());
    }
    Ok(())
}

pub fn slugify(title: &str) -> String {
    let mut slug = String::new();
    let mut pending_dash = false;
    for ch in title.chars() {
        if ch.is_ascii_alphanumeric() {
            if pending_dash && !slug.is_empty() {
                slug.push('-');
            }
            slug.push(ch.to_ascii_lowercase());
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

pub fn canonical_handoff_path(
    base: &Path,
    config: &WorkflowConfig,
    issue: &Issue,
    requested: Option<&str>,
) -> Result<PathBuf, String> {
    config.validate()?;
    let relative = if let Some(raw) = requested.map(str::trim).filter(|p| !p.is_empty()) {
        let requested_path = Path::new(raw);
        if requested_path.is_absolute() {
            let base_abs = base
                .canonicalize()
                .map_err(|e| format!("failed to resolve project root: {}", e))?;
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

    let relative = normalize_relative(&relative)?;
    if !relative.starts_with(&config.handoff_dir)
        || relative.extension().and_then(|e| e.to_str()) != Some("md")
        || relative == Path::new(HANDOFF_README)
    {
        return Err(format!(
            "actionable item handoffs must be Markdown files under {}/",
            HANDOFF_DIR
        ));
    }
    Ok(relative)
}

fn yaml_scalar(value: Option<&str>) -> String {
    value
        .map(|v| serde_json::to_string(v).unwrap_or_else(|_| "null".to_string()))
        .unwrap_or_else(|| "null".to_string())
}

pub fn render_handoff(issue: &Issue) -> String {
    let work_order = issue
        .description
        .as_deref()
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .unwrap_or(&issue.title);
    format!(
        "---\nmanna: {}\ntrack: {}\nsource: {}\n---\n\n# Handoff: {}\n\nBoard state is canonical in `.manna/`. This file is the work order for one item only.\n\n## Claim\n\n```bash\nagent-do manna claim {}\n```\n\n## Work order\n\n{}\n\n## Completion\n\n1. Produce the scoped deliverables and verification receipts.\n2. Update this handoff only when continuation context changed.\n3. Commit with `Manna: {}` and run `agent-do manna done {}` only after the work is verified.\n",
        issue.id,
        yaml_scalar(issue.track.as_deref()),
        yaml_scalar(issue.source.as_deref()),
        issue.title,
        issue.id,
        work_order,
        issue.id,
        issue.id
    )
}

pub fn create_handoff(base: &Path, relative: &Path, issue: &Issue) -> Result<(), String> {
    let target = base.join(relative);
    if target.exists() {
        return Err(format!(
            "refusing to overwrite existing handoff {}",
            target.display()
        ));
    }
    atomic_write_new(&target, &render_handoff(issue))?;
    Ok(())
}

pub fn remove_created_handoff(base: &Path, relative: &Path) {
    if relative.starts_with(HANDOFF_DIR) {
        let _ = fs::remove_file(base.join(relative));
    }
}

pub fn validate_handoff(
    base: &Path,
    config: &WorkflowConfig,
    issue: &Issue,
) -> Result<PathBuf, String> {
    let pointer = issue
        .prompt
        .as_deref()
        .ok_or_else(|| format!("{} has no canonical handoff pointer", issue.id))?;
    let relative = canonical_handoff_path(base, config, issue, Some(pointer))?;
    let path = base.join(&relative);
    if !path.is_file() {
        return Err(format!("handoff does not exist: {}", relative.display()));
    }
    if git_path_ignored(base, &relative)? {
        return Err(format!("handoff is ignored by Git: {}", relative.display()));
    }
    let text = fs::read_to_string(&path)
        .map_err(|e| format!("failed to read {}: {}", relative.display(), e))?;
    let ids = claim_command_ids(&text);
    if ids != vec![issue.id.clone()] {
        return Err(format!(
            "handoff {} must contain exactly one claim target, {}, got {:?}",
            relative.display(),
            issue.id,
            ids
        ));
    }
    Ok(relative)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn issue(id: &str, title: &str) -> Issue {
        Issue::new(id.to_string(), title.to_string()).unwrap()
    }

    #[test]
    fn strict_workflow_scaffolds_and_pairs_one_item() {
        let temp = TempDir::new().unwrap();
        let init = initialize_workflow(temp.path()).unwrap();
        assert_eq!(init.config, WorkflowConfig::default());
        assert!(temp.path().join(WORKFLOW_FILE).is_file());
        assert!(temp.path().join(HANDOFF_README).is_file());

        let mut item = issue("mn-abc123", "Fix the prompt graph");
        let path = canonical_handoff_path(temp.path(), &init.config, &item, None).unwrap();
        item.prompt = Some(path.to_string_lossy().into_owned());
        create_handoff(temp.path(), &path, &item).unwrap();
        assert_eq!(
            validate_handoff(temp.path(), &init.config, &item).unwrap(),
            path
        );
    }

    #[test]
    fn handoff_paths_cannot_escape_or_use_a_parallel_root() {
        let temp = TempDir::new().unwrap();
        let config = WorkflowConfig::default();
        let item = issue("mn-abc123", "Bounded work");
        assert!(canonical_handoff_path(temp.path(), &config, &item, Some("../work.md")).is_err());
        assert!(
            canonical_handoff_path(temp.path(), &config, &item, Some(".handoffs/work.md")).is_err()
        );
        assert!(
            canonical_handoff_path(temp.path(), &config, &item, Some(".handoff/work.md")).is_ok()
        );
    }

    #[test]
    fn existing_nonworkflow_handoff_root_is_not_adopted_silently() {
        let temp = TempDir::new().unwrap();
        fs::create_dir_all(temp.path().join(HANDOFF_DIR)).unwrap();
        fs::write(
            temp.path().join(HANDOFF_DIR).join("old-session.md"),
            "legacy",
        )
        .unwrap();

        let error = initialize_workflow(temp.path()).unwrap_err();
        assert!(error.contains("already contains non-workflow files"));
        assert!(!temp.path().join(WORKFLOW_FILE).exists());
    }

    #[test]
    fn duplicate_claim_commands_break_the_handoff_contract() {
        let temp = TempDir::new().unwrap();
        let init = initialize_workflow(temp.path()).unwrap();
        let mut item = issue("mn-abc123", "One claim only");
        let path = canonical_handoff_path(temp.path(), &init.config, &item, None).unwrap();
        item.prompt = Some(path.to_string_lossy().into_owned());
        create_handoff(temp.path(), &path, &item).unwrap();
        let target = temp.path().join(&path);
        let mut text = fs::read_to_string(&target).unwrap();
        text.push_str("\nagent-do manna claim mn-abc123\n");
        fs::write(target, text).unwrap();

        assert!(validate_handoff(temp.path(), &init.config, &item).is_err());
    }
}

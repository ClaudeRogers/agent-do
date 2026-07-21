//! Manna CLI - Issue tracking for AI agents.
//!
//! All output is YAML format for machine parsing.
//! Exit codes: 0=success, 1=user error, 2=system error.

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use chrono::{SecondsFormat, Utc};
use clap::{Parser, Subcommand};
use serde::Serialize;

use manna_core::error::MannaError;
use manna_core::id::generate_unique_id;
use manna_core::issue::{is_default_type, Issue, IssueStatus, IssueType};
use manna_core::reconcile::{
    check_blocker_desync, check_dangling_track, check_landed_open, check_stale_dream,
    extract_manna_ids, lint_board, manna_trailer_ids, parse_session_pid, Finding, FindingKind,
    LintFinding,
};
use manna_core::store::MannaStore;

/// Exit codes
const EXIT_SUCCESS: i32 = 0;
const EXIT_USER_ERROR: i32 = 1;
const EXIT_SYSTEM_ERROR: i32 = 2;

#[derive(Parser)]
#[command(name = "manna-core")]
#[command(version)]
#[command(about = "Manna issue tracking system for AI agents", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Initialize .manna/ directory
    Init,

    /// Show current session status
    Status,

    /// Create a new issue
    Create {
        /// Issue title (1-500 characters)
        title: String,

        /// Optional description
        description: Option<String>,

        /// Issue type (track, item, dream)
        #[arg(long = "type", value_name = "TYPE")]
        issue_type: Option<String>,

        /// Track to attach to (must be an existing issue with type track)
        #[arg(long)]
        track: Option<String>,

        /// Where this issue came from (note path, URL, conversation)
        #[arg(long)]
        source: Option<String>,
    },

    /// Claim an issue for the current session
    Claim {
        /// Issue ID (e.g., mn-abc123)
        id: String,
    },

    /// Mark an issue as done
    Done {
        /// Issue ID (e.g., mn-abc123)
        id: String,
    },

    /// Abandon/release a claimed issue
    Abandon {
        /// Issue ID (e.g., mn-abc123)
        id: String,
    },

    /// Add a blocker dependency
    Block {
        /// Issue ID to mark as blocked
        id: String,

        /// ID of the blocking issue
        blocker_id: String,
    },

    /// Remove a blocker dependency
    Unblock {
        /// Issue ID to unblock
        id: String,

        /// ID of the blocker to remove
        blocker_id: String,
    },

    /// List issues with optional status filter
    List {
        /// Filter by status (open, in_progress, blocked, done)
        #[arg(long)]
        status: Option<String>,

        /// Filter by issue type (track, item, dream)
        #[arg(long = "type", value_name = "TYPE")]
        issue_type: Option<String>,

        /// Filter by track membership
        #[arg(long)]
        track: Option<String>,

        /// Emit JSON instead of YAML
        #[arg(long)]
        json: bool,
    },

    /// Show issue details
    Show {
        /// Issue ID (e.g., mn-abc123)
        id: String,
    },

    /// Update an issue's title, description, status, type, track, or source
    Update {
        /// Issue ID (e.g., mn-abc123)
        id: String,

        /// New title
        #[arg(long)]
        title: Option<String>,

        /// New description
        #[arg(long)]
        description: Option<String>,

        /// New status (open, in_progress, blocked, done)
        #[arg(long)]
        status: Option<String>,

        /// New issue type (track, item, dream)
        #[arg(long = "type", value_name = "TYPE")]
        issue_type: Option<String>,

        /// New track edge (empty string clears it)
        #[arg(long)]
        track: Option<String>,

        /// New source citation (empty string clears it)
        #[arg(long)]
        source: Option<String>,
    },

    /// Delete an issue permanently
    Delete {
        /// Issue ID (e.g., mn-abc123)
        id: String,
    },

    /// Output context blob for AI agents
    Context {
        /// Maximum tokens for context (default 8000)
        #[arg(long, default_value = "8000")]
        max_tokens: usize,

        /// Emit JSON instead of YAML
        #[arg(long)]
        json: bool,
    },

    /// File a dream (idea spark) on the nearest board or the global inbox
    Dream {
        /// The spark (issue title)
        spark: String,

        /// Track to attach to (must be an existing issue with type track)
        #[arg(long)]
        track: Option<String>,

        /// Where the spark came from (note path, URL, conversation)
        #[arg(long)]
        source: Option<String>,
    },

    /// Check board grammar; findings exit 1, clean exits 0
    Lint {
        /// Emit JSON instead of YAML
        #[arg(long)]
        json: bool,
    },

    /// Detect drift between the board and reality (git, claims, blockers, docs)
    Reconcile {
        /// Apply safe fixes (abandon dead claims, unblock resolved blockers)
        #[arg(long)]
        fix: bool,

        /// Write findings to .manna/drift.yaml
        #[arg(long)]
        write_drift: bool,

        /// Days before an open dream counts as stale
        #[arg(long, default_value = "14")]
        dream_age_days: i64,

        /// Emit JSON instead of YAML
        #[arg(long)]
        json: bool,
    },
}

// ============================================================================
// YAML Response Types
// ============================================================================

#[derive(Serialize)]
struct SuccessResponse<T: Serialize> {
    success: bool,
    #[serde(flatten)]
    data: T,
}

#[derive(Serialize)]
struct ErrorResponse {
    success: bool,
    error: String,
}

#[derive(Serialize)]
struct IssueData {
    issue: Issue,
}

#[derive(Serialize)]
struct IssueListData {
    issues: Vec<IssueSummary>,
}

#[derive(Serialize)]
struct IssueSummary {
    id: String,
    title: String,
    status: IssueStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    claimed_by: Option<String>,
    #[serde(rename = "type", skip_serializing_if = "is_default_type")]
    issue_type: IssueType,
    #[serde(skip_serializing_if = "Option::is_none")]
    track: Option<String>,
}

#[derive(Serialize)]
struct StatusData {
    session_id: String,
    claimed_issues: Vec<String>,
}

#[derive(Serialize)]
struct ContextData {
    context: String,
}

#[derive(Serialize)]
struct InitData {
    initialized: bool,
    path: String,
}

#[derive(Serialize)]
struct DreamData {
    issue: Issue,
    /// Which board received the dream (directory containing .manna/)
    board: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    note: Option<String>,
}

#[derive(Serialize)]
struct LintData {
    clean: bool,
    findings: Vec<LintFinding>,
}

#[derive(Serialize)]
struct ReconcileData {
    findings: Vec<Finding>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    fixed: Vec<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    fix_failures: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    drift_written: Option<String>,
}

/// Shape pinned by the drift.yaml integration contract.
#[derive(Serialize)]
struct DriftReport {
    generated_at: String,
    session: Option<String>,
    findings: Vec<Finding>,
}

// ============================================================================
// Helper Functions
// ============================================================================

/// Get session ID from environment or generate default.
fn get_session_id() -> String {
    std::env::var("MANNA_SESSION_ID")
        .unwrap_or_else(|_| format!("ses_pid{}_{}", std::process::id(), Utc::now().timestamp()))
}

/// Output success response as YAML and exit with success code.
fn output_success<T: Serialize>(data: T) -> ! {
    let response = SuccessResponse {
        success: true,
        data,
    };
    println!(
        "{}",
        serde_yaml::to_string(&response).unwrap_or_else(|e| {
            format!("success: false\nerror: \"YAML serialization error: {}\"", e)
        })
    );
    std::process::exit(EXIT_SUCCESS);
}

/// Output success response as JSON and exit with success code.
fn output_success_json<T: Serialize>(data: T) -> ! {
    let response = SuccessResponse {
        success: true,
        data,
    };
    println!(
        "{}",
        serde_json::to_string(&response).unwrap_or_else(|e| {
            format!("{{\"success\":false,\"error\":\"JSON serialization error: {}\"}}", e)
        })
    );
    std::process::exit(EXIT_SUCCESS);
}

/// Print a success-shaped response and exit with the given code.
///
/// Lint and reconcile are gates: the body reports findings, the exit code
/// carries the verdict, so they cannot use output_success (always 0).
fn output_with_exit<T: Serialize>(data: T, json: bool, exit_code: i32) -> ! {
    let response = SuccessResponse {
        success: true,
        data,
    };
    if json {
        println!(
            "{}",
            serde_json::to_string(&response).unwrap_or_else(|e| {
                format!("{{\"success\":false,\"error\":\"JSON serialization error: {}\"}}", e)
            })
        );
    } else {
        println!(
            "{}",
            serde_yaml::to_string(&response).unwrap_or_else(|e| {
                format!("success: false\nerror: \"YAML serialization error: {}\"", e)
            })
        );
    }
    std::process::exit(exit_code);
}

/// Output error response as YAML and exit with specified code.
fn output_error(error: &str, exit_code: i32) -> ! {
    let response = ErrorResponse {
        success: false,
        error: error.to_string(),
    };
    println!(
        "{}",
        serde_yaml::to_string(&response).unwrap_or_else(|e| {
            format!("success: false\nerror: \"YAML serialization error: {}\"", e)
        })
    );
    std::process::exit(exit_code);
}

/// Convert MannaError to exit code.
fn error_to_exit_code(err: &MannaError) -> i32 {
    match err {
        MannaError::IssueNotFound(_) => EXIT_USER_ERROR,
        MannaError::IssueAlreadyExists(_) => EXIT_USER_ERROR,
        MannaError::InvalidStatusTransition { .. } => EXIT_USER_ERROR,
        MannaError::InvalidId(_) => EXIT_USER_ERROR,
        MannaError::Io(_) => EXIT_SYSTEM_ERROR,
        MannaError::Json(_) => EXIT_SYSTEM_ERROR,
        MannaError::NotInitialized => EXIT_USER_ERROR,
        MannaError::LockFailed(_) => EXIT_SYSTEM_ERROR,
    }
}

/// Handle MannaError by outputting YAML error and exiting.
fn handle_manna_error(err: MannaError) -> ! {
    let exit_code = error_to_exit_code(&err);
    output_error(&err.to_string(), exit_code);
}

/// Parse status string to IssueStatus.
fn parse_status(s: &str) -> Result<IssueStatus, String> {
    match s.to_lowercase().as_str() {
        "open" => Ok(IssueStatus::Open),
        "in_progress" => Ok(IssueStatus::InProgress),
        "blocked" => Ok(IssueStatus::Blocked),
        "done" => Ok(IssueStatus::Done),
        _ => Err(format!(
            "Invalid status '{}'. Valid options: open, in_progress, blocked, done",
            s
        )),
    }
}

/// Parse issue type string to IssueType.
fn parse_issue_type(s: &str) -> Result<IssueType, String> {
    match s.to_lowercase().as_str() {
        "track" => Ok(IssueType::Track),
        "item" => Ok(IssueType::Item),
        "dream" => Ok(IssueType::Dream),
        _ => Err(format!(
            "Invalid type '{}'. Valid options: track, item, dream",
            s
        )),
    }
}

/// Validate that a --track target exists on the board and is a track.
fn validate_track_target(issues: &[Issue], track_id: &str) -> Result<(), String> {
    match issues.iter().find(|i| i.id == track_id) {
        None => Err(format!("Track {} not found", track_id)),
        Some(target) if target.issue_type != IssueType::Track => Err(format!(
            "Issue {} is not a track (type: {})",
            track_id, target.issue_type
        )),
        Some(_) => Ok(()),
    }
}

/// Find issue by ID or exit with error.
fn find_issue(issues: &[Issue], id: &str) -> Issue {
    issues
        .iter()
        .find(|i| i.id == id)
        .cloned()
        .unwrap_or_else(|| {
            output_error(&format!("Issue {} not found", id), EXIT_USER_ERROR);
        })
}

// ============================================================================
// Command Implementations
// ============================================================================

fn cmd_init() -> ! {
    let store = MannaStore::new(Path::new("."));
    match store.init() {
        Ok(()) => output_success(InitData {
            initialized: true,
            path: ".manna".to_string(),
        }),
        Err(err) => handle_manna_error(err),
    }
}

fn cmd_status() -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    let session_id = get_session_id();

    let claimed_issues: Vec<String> = match store.load_issues() {
        Ok(issues) => issues
            .iter()
            .filter(|i| i.claimed_by.as_ref() == Some(&session_id))
            .map(|i| i.id.clone())
            .collect(),
        Err(err) => handle_manna_error(err),
    };

    output_success(StatusData {
        session_id,
        claimed_issues,
    });
}

fn cmd_create(
    title: String,
    description: Option<String>,
    issue_type: Option<String>,
    track: Option<String>,
    source: Option<String>,
) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Validate title
    if title.is_empty() || title.len() > 500 {
        output_error(
            &format!("Title must be 1-500 characters, got {}", title.len()),
            EXIT_USER_ERROR,
        );
    }

    // Parse type before touching the store
    let parsed_type = match issue_type.as_deref().map(parse_issue_type).transpose() {
        Ok(t) => t.unwrap_or_default(),
        Err(e) => output_error(&e, EXIT_USER_ERROR),
    };

    if parsed_type == IssueType::Track && track.is_some() {
        output_error(
            "Track issues cannot have a track edge (tracks don't nest)",
            EXIT_USER_ERROR,
        );
    }

    // Load existing issues for track validation and unique ID generation
    let existing_issues = match store.load_issues() {
        Ok(issues) => issues,
        Err(err) => handle_manna_error(err),
    };

    if let Some(track_id) = &track {
        if let Err(e) = validate_track_target(&existing_issues, track_id) {
            output_error(&e, EXIT_USER_ERROR);
        }
    }

    let existing_ids: HashSet<String> = existing_issues.into_iter().map(|i| i.id).collect();

    // Generate unique ID
    let id = generate_unique_id(&existing_ids);

    // Create issue
    let mut issue = match Issue::new(id, title) {
        Ok(i) => i,
        Err(e) => output_error(&e, EXIT_USER_ERROR),
    };

    // Set optional fields if provided
    issue.description = description;
    issue.issue_type = parsed_type;
    issue.track = track;
    issue.source = source;

    // Append to store
    if let Err(err) = store.append_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_claim(id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    let session_id = get_session_id();

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Claim it
    if let Err(e) = issue.claim(session_id) {
        output_error(&e, EXIT_USER_ERROR);
    }

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_done(id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Complete it
    if let Err(e) = issue.complete() {
        output_error(&e, EXIT_USER_ERROR);
    }

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_abandon(id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Release it
    if let Err(e) = issue.release() {
        output_error(&e, EXIT_USER_ERROR);
    }

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_block(id: String, blocker_id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Verify blocker exists
    if !issues.iter().any(|i| i.id == blocker_id) {
        output_error(
            &format!("Blocker issue {} not found", blocker_id),
            EXIT_USER_ERROR,
        );
    }

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Add blocker
    issue.add_blocker(blocker_id);

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_unblock(id: String, blocker_id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let mut issue = find_issue(&issues, &id);

    // Remove blocker
    issue.remove_blocker(&blocker_id);

    // Update store
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(IssueData { issue });
}

fn cmd_list(
    status_filter: Option<String>,
    type_filter: Option<String>,
    track_filter: Option<String>,
    json: bool,
) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Parse filters if provided
    let filter: Option<IssueStatus> = match status_filter {
        Some(s) => match parse_status(&s) {
            Ok(status) => Some(status),
            Err(e) => output_error(&e, EXIT_USER_ERROR),
        },
        None => None,
    };
    let type_filter: Option<IssueType> = match type_filter {
        Some(s) => match parse_issue_type(&s) {
            Ok(t) => Some(t),
            Err(e) => output_error(&e, EXIT_USER_ERROR),
        },
        None => None,
    };

    // Filter and map to summaries
    let summaries: Vec<IssueSummary> = issues
        .into_iter()
        .filter(|i| filter.as_ref().map_or(true, |f| &i.status == f))
        .filter(|i| type_filter.map_or(true, |f| i.issue_type == f))
        .filter(|i| {
            track_filter
                .as_ref()
                .map_or(true, |f| i.track.as_ref() == Some(f))
        })
        .map(|i| IssueSummary {
            id: i.id,
            title: i.title,
            status: i.status,
            claimed_by: i.claimed_by,
            issue_type: i.issue_type,
            track: i.track,
        })
        .collect();

    if json {
        output_success_json(IssueListData { issues: summaries });
    }
    output_success(IssueListData { issues: summaries });
}

fn cmd_show(id: String) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    // Find issue
    let issue = find_issue(&issues, &id);

    output_success(IssueData { issue });
}

fn cmd_update(
    id: String,
    title: Option<String>,
    description: Option<String>,
    status: Option<String>,
    issue_type: Option<String>,
    track: Option<String>,
    source: Option<String>,
) -> ! {
    let store = MannaStore::new(Path::new("."));
    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }
    if title.is_none()
        && description.is_none()
        && status.is_none()
        && issue_type.is_none()
        && track.is_none()
        && source.is_none()
    {
        output_error(
            "Nothing to update: pass --title, --description, --status, --type, --track, or --source",
            EXIT_USER_ERROR,
        );
    }
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };
    let mut issue = find_issue(&issues, &id);
    if let Some(new_title) = title {
        if new_title.is_empty() || new_title.len() > 500 {
            output_error("Title must be 1-500 characters", EXIT_USER_ERROR);
        }
        issue.title = new_title;
    }
    if let Some(new_description) = description {
        issue.description = if new_description.is_empty() { None } else { Some(new_description) };
    }
    if let Some(new_status) = status {
        issue.status = match new_status.as_str() {
            "open" => IssueStatus::Open,
            "in_progress" => IssueStatus::InProgress,
            "blocked" => IssueStatus::Blocked,
            "done" => IssueStatus::Done,
            other => output_error(
                &format!("Invalid status '{}': use open, in_progress, blocked, or done", other),
                EXIT_USER_ERROR,
            ),
        };
    }
    if let Some(new_type) = issue_type {
        issue.issue_type = match parse_issue_type(&new_type) {
            Ok(t) => t,
            Err(e) => output_error(&e, EXIT_USER_ERROR),
        };
    }
    if let Some(new_track) = track {
        if new_track.is_empty() {
            issue.track = None;
        } else {
            if let Err(e) = validate_track_target(&issues, &new_track) {
                output_error(&e, EXIT_USER_ERROR);
            }
            issue.track = Some(new_track);
        }
    }
    if let Some(new_source) = source {
        issue.source = if new_source.is_empty() { None } else { Some(new_source) };
    }
    if issue.issue_type == IssueType::Track && issue.track.is_some() {
        output_error(
            "Track issues cannot have a track edge (tracks don't nest)",
            EXIT_USER_ERROR,
        );
    }
    issue.updated_at = chrono::Utc::now();
    if let Err(err) = store.update_issue(&issue) {
        handle_manna_error(err);
    }
    output_success(IssueData { issue });
}

fn cmd_delete(id: String) -> ! {
    let store = MannaStore::new(Path::new("."));
    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };
    let issue = find_issue(&issues, &id);
    if let Err(err) = store.delete_issue(&issue.id) {
        handle_manna_error(err);
    }
    output_success(IssueData { issue });
}

/// One context line for an issue, matching the v1 per-status format.
fn context_line(issue: &Issue) -> String {
    match issue.status {
        IssueStatus::InProgress => {
            let claimed = issue
                .claimed_by
                .as_ref()
                .map_or("".to_string(), |s| format!(", claimed by {}", s));
            format!("- {}: {} [in_progress{}]\n", issue.id, issue.title, claimed)
        }
        IssueStatus::Blocked => format!(
            "- {}: {} [blocked by: {}]\n",
            issue.id,
            issue.title,
            issue.blocked_by.join(", ")
        ),
        _ => format!("- {}: {} [{}]\n", issue.id, issue.title, issue.status),
    }
}

/// Build the context blob. Boards with track rows render a track tree
/// (per-track sections, then Untracked, then Dreams); boards with zero
/// tracks keep the v1 by-status render byte for byte.
fn build_context(issues: &[Issue]) -> String {
    let mut context = String::new();
    context.push_str("# Manna Context\n\n");

    let tracks: Vec<&Issue> = issues
        .iter()
        .filter(|i| i.issue_type == IssueType::Track)
        .collect();

    if !tracks.is_empty() {
        // Track tree: sections for every track (any status; tracks are
        // structure, not work lines), done items excluded as always.
        let track_ids: HashSet<&str> = tracks.iter().map(|t| t.id.as_str()).collect();
        for track in &tracks {
            context.push_str(&format!("## {} ({})\n", track.title, track.id));
            for issue in issues.iter().filter(|i| {
                i.issue_type == IssueType::Item
                    && i.status != IssueStatus::Done
                    && i.track.as_deref() == Some(track.id.as_str())
            }) {
                context.push_str(&context_line(issue));
            }
            context.push('\n');
        }

        // Untracked: trackless items, plus items whose track edge dangles
        // (pointing at no known track) so no work line ever vanishes.
        let untracked: Vec<&Issue> = issues
            .iter()
            .filter(|i| {
                i.issue_type == IssueType::Item
                    && i.status != IssueStatus::Done
                    && i.track.as_deref().map_or(true, |t| !track_ids.contains(t))
            })
            .collect();
        if !untracked.is_empty() {
            context.push_str("## Untracked\n");
            for issue in &untracked {
                context.push_str(&context_line(issue));
            }
            context.push('\n');
        }

        let dreams: Vec<&Issue> = issues
            .iter()
            .filter(|i| i.issue_type == IssueType::Dream && i.status != IssueStatus::Done)
            .collect();
        if !dreams.is_empty() {
            context.push_str("## Dreams\n");
            for dream in &dreams {
                context.push_str(&context_line(dream));
            }
        }
        return context;
    }

    // Zero-track board: v1 by-status render, unchanged.
    let open: Vec<_> = issues
        .iter()
        .filter(|i| i.status == IssueStatus::Open)
        .collect();
    let in_progress: Vec<_> = issues
        .iter()
        .filter(|i| i.status == IssueStatus::InProgress)
        .collect();
    let blocked: Vec<_> = issues
        .iter()
        .filter(|i| i.status == IssueStatus::Blocked)
        .collect();

    // Open issues
    context.push_str(&format!("## Open Issues ({})\n", open.len()));
    for issue in &open {
        context.push_str(&format!("- {}: {} [open]\n", issue.id, issue.title));
    }
    context.push('\n');

    // In-progress issues
    context.push_str(&format!("## In Progress Issues ({})\n", in_progress.len()));
    for issue in &in_progress {
        let claimed = issue
            .claimed_by
            .as_ref()
            .map_or("".to_string(), |s| format!(", claimed by {}", s));
        context.push_str(&format!(
            "- {}: {} [in_progress{}]\n",
            issue.id, issue.title, claimed
        ));
    }
    context.push('\n');

    // Blocked issues
    context.push_str(&format!("## Blocked Issues ({})\n", blocked.len()));
    for issue in &blocked {
        let blockers = issue.blocked_by.join(", ");
        context.push_str(&format!(
            "- {}: {} [blocked by: {}]\n",
            issue.id, issue.title, blockers
        ));
    }

    context
}

fn cmd_context(max_tokens: usize, json: bool) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    // Load issues
    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    let mut context = build_context(&issues);

    // Truncate if needed (rough estimate: 1 token ≈ 4 chars)
    let max_chars = max_tokens * 4;
    if context.len() > max_chars {
        context.truncate(max_chars - 20);
        context.push_str("\n\n[truncated]");
    }

    if json {
        output_success_json(ContextData { context });
    }
    output_success(ContextData { context });
}

// ============================================================================
// Dream / Lint / Reconcile
// ============================================================================

/// Resolve the board for `dream`: walk up from cwd to the first directory
/// containing `.manna/`; fall back to the global inbox under AGENT_DO_HOME.
///
/// Returns (board directory, is_global_inbox).
fn resolve_dream_board() -> (PathBuf, bool) {
    if let Ok(cwd) = std::env::current_dir() {
        let mut dir = cwd.as_path();
        loop {
            if dir.join(".manna").is_dir() {
                return (dir.to_path_buf(), false);
            }
            match dir.parent() {
                Some(parent) => dir = parent,
                None => break,
            }
        }
    }
    let home = std::env::var("AGENT_DO_HOME").map(PathBuf::from).unwrap_or_else(|_| {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        Path::new(&home).join(".agent-do")
    });
    (home.join("inbox"), true)
}

fn cmd_dream(spark: String, track: Option<String>, source: Option<String>) -> ! {
    if spark.is_empty() || spark.len() > 500 {
        output_error(
            &format!("Title must be 1-500 characters, got {}", spark.len()),
            EXIT_USER_ERROR,
        );
    }

    let (board_dir, is_inbox) = resolve_dream_board();
    let store = MannaStore::new(&board_dir);

    // Auto-init: creates the inbox board on first use, heals missing files
    // on a local board found by the walk-up (init is idempotent).
    if is_inbox {
        if let Err(e) = std::fs::create_dir_all(&board_dir) {
            output_error(
                &format!("Cannot create global inbox at {}: {}", board_dir.display(), e),
                EXIT_SYSTEM_ERROR,
            );
        }
    }
    if let Err(err) = store.init() {
        handle_manna_error(err);
    }

    let existing_issues = match store.load_issues() {
        Ok(issues) => issues,
        Err(err) => handle_manna_error(err),
    };

    if let Some(track_id) = &track {
        if let Err(e) = validate_track_target(&existing_issues, track_id) {
            output_error(&e, EXIT_USER_ERROR);
        }
    }

    let existing_ids: HashSet<String> = existing_issues.into_iter().map(|i| i.id).collect();
    let id = generate_unique_id(&existing_ids);

    let mut issue = match Issue::new(id, spark) {
        Ok(i) => i,
        Err(e) => output_error(&e, EXIT_USER_ERROR),
    };
    issue.issue_type = IssueType::Dream;
    issue.track = track;
    issue.source = source;

    if let Err(err) = store.append_issue(&issue) {
        handle_manna_error(err);
    }

    output_success(DreamData {
        issue,
        board: board_dir.display().to_string(),
        note: is_inbox.then(|| "filed to global inbox".to_string()),
    });
}

fn cmd_lint(json: bool) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    let findings = lint_board(&issues);
    let clean = findings.is_empty();
    let exit_code = if clean { EXIT_SUCCESS } else { EXIT_USER_ERROR };
    output_with_exit(LintData { clean, findings }, json, exit_code);
}

/// Collect `Manna: mn-xxxxxx` trailers from recent git history.
///
/// Bounded to the last 500 commits: trailers reference recently landed work,
/// and the bound keeps reconcile fast on deep histories.
fn collect_landed_trailers() -> Result<HashMap<String, Vec<String>>, String> {
    let out = std::process::Command::new("git")
        .args(["log", "-z", "-n", "500", "--format=%H%n%B"])
        .stderr(std::process::Stdio::null())
        .output()
        .map_err(|e| format!("git unavailable: {}", e))?;
    if !out.status.success() {
        return Err("git log failed (not a git repository?)".to_string());
    }
    let text = String::from_utf8_lossy(&out.stdout);
    let mut landed: HashMap<String, Vec<String>> = HashMap::new();
    for record in text.split('\0') {
        let mut lines = record.splitn(2, '\n');
        let sha = match lines.next() {
            Some(s) if !s.trim().is_empty() => s.trim().to_string(),
            _ => continue,
        };
        let body = lines.next().unwrap_or("");
        for id in manna_trailer_ids(body) {
            landed.entry(id).or_default().push(sha.clone());
        }
    }
    Ok(landed)
}

/// True when a process with this pid is alive (`kill -0` semantics).
fn pid_alive(pid: u32) -> bool {
    std::process::Command::new("kill")
        .args(["-0", &pid.to_string()])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        // If the probe itself cannot run, assume alive: no false dead-claims.
        .unwrap_or(true)
}

/// Run `agent-do coord peers --json` bounded to ~2s; map agent_id -> status.
fn coord_peer_statuses() -> Result<HashMap<String, String>, String> {
    use std::io::Read;

    let mut child = std::process::Command::new("agent-do")
        .args(["coord", "peers", "--json"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|e| format!("agent-do unavailable: {}", e))?;

    // Drain stdout on a thread so a large peers list cannot deadlock the pipe.
    let mut stdout = child.stdout.take().ok_or("no stdout handle")?;
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let mut buf = String::new();
        let _ = stdout.read_to_string(&mut buf);
        let _ = tx.send(buf);
    });

    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                if !status.success() {
                    return Err("coord peers exited nonzero".to_string());
                }
                break;
            }
            Ok(None) => {
                if std::time::Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err("coord peers timed out after 2s".to_string());
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            Err(e) => return Err(format!("coord peers failed: {}", e)),
        }
    }

    let raw = rx
        .recv_timeout(std::time::Duration::from_millis(500))
        .map_err(|_| "coord peers produced no output".to_string())?;
    let value: serde_json::Value =
        serde_json::from_str(&raw).map_err(|e| format!("coord peers JSON invalid: {}", e))?;
    let mut statuses = HashMap::new();
    if let Some(peers) = value.get("peers").and_then(|p| p.as_array()) {
        for peer in peers {
            if let (Some(agent_id), Some(status)) = (
                peer.get("agent_id").and_then(|v| v.as_str()),
                peer.get("status").and_then(|v| v.as_str()),
            ) {
                statuses.insert(agent_id.to_string(), status.to_string());
            }
        }
    }
    Ok(statuses)
}

/// dead_claim: claims held by sessions that are provably gone.
///
/// Default-format sessions are probed by pid; other formats are matched
/// against coord peer statuses (finding only when coord reports the agent
/// dead/stale/stopped — absent from coord is inconclusive, not dead).
fn check_dead_claims(issues: &[Issue]) -> Vec<Finding> {
    let mut findings = Vec::new();
    let mut coord_lookups: Vec<&Issue> = Vec::new();

    for issue in issues {
        let claimed_by = match &issue.claimed_by {
            Some(s) if issue.status != IssueStatus::Done => s,
            _ => continue,
        };
        match parse_session_pid(claimed_by) {
            Some(pid) => {
                if !pid_alive(pid) {
                    findings.push(Finding {
                        kind: FindingKind::DeadClaim,
                        issue_id: Some(issue.id.clone()),
                        detail: format!("claimed by dead session {}", claimed_by),
                        evidence: Some(format!("pid {} not running", pid)),
                        proposed_fix: Some("abandon the claim".to_string()),
                    });
                }
            }
            None => coord_lookups.push(issue),
        }
    }

    if !coord_lookups.is_empty() {
        match coord_peer_statuses() {
            Ok(statuses) => {
                for issue in coord_lookups {
                    let claimed_by = issue.claimed_by.as_ref().unwrap();
                    if let Some(status) = statuses.get(claimed_by) {
                        if matches!(status.as_str(), "dead" | "stale" | "stopped") {
                            findings.push(Finding {
                                kind: FindingKind::DeadClaim,
                                issue_id: Some(issue.id.clone()),
                                detail: format!("claimed by {} session {}", status, claimed_by),
                                evidence: Some(format!("coord status: {}", status)),
                                proposed_fix: Some("abandon the claim".to_string()),
                            });
                        }
                    }
                }
            }
            Err(reason) => findings.push(Finding::skipped("dead_claim", &reason)),
        }
    }

    findings
}

/// Directories scanned for doc references: repo-local handoff/dev/zpc plus
/// the Claude memory directory derived from cwd (`/` -> `-`).
fn doc_reference_dirs() -> Vec<PathBuf> {
    let mut dirs = vec![
        PathBuf::from(".handoff"),
        PathBuf::from(".dev"),
        PathBuf::from(".zpc"),
    ];
    if let (Ok(cwd), Ok(home)) = (std::env::current_dir(), std::env::var("HOME")) {
        let flat = cwd.to_string_lossy().replace('/', "-");
        dirs.push(
            Path::new(&home)
                .join(".claude")
                .join("projects")
                .join(flat)
                .join("memory"),
        );
    }
    dirs
}

/// Recursively collect (file, line, id) references under a directory.
///
/// Skips symlinks and files over 1MB; tolerates non-UTF8 content. A missing
/// directory is a successful empty scan, not a skipped check.
fn scan_dir_for_ids(dir: &Path, refs: &mut Vec<(PathBuf, usize, String)>) {
    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let file_type = match entry.file_type() {
            Ok(t) => t,
            Err(_) => continue,
        };
        if file_type.is_symlink() {
            continue;
        }
        if file_type.is_dir() {
            scan_dir_for_ids(&path, refs);
            continue;
        }
        if entry.metadata().map_or(true, |m| m.len() > 1_000_000) {
            continue;
        }
        let bytes = match std::fs::read(&path) {
            Ok(b) => b,
            Err(_) => continue,
        };
        let text = String::from_utf8_lossy(&bytes);
        for (line_no, line) in text.lines().enumerate() {
            for id in extract_manna_ids(line) {
                refs.push((path.clone(), line_no + 1, id));
            }
        }
    }
}

/// doc_reference: IDs referenced in docs that do not exist on this board.
///
/// Deduplicated per (file, id) with the first line as evidence.
fn check_doc_references(issues: &[Issue]) -> Vec<Finding> {
    let board_ids: HashSet<&str> = issues.iter().map(|i| i.id.as_str()).collect();
    let mut refs = Vec::new();
    for dir in doc_reference_dirs() {
        scan_dir_for_ids(&dir, &mut refs);
    }

    let mut seen: HashSet<(PathBuf, String)> = HashSet::new();
    let mut findings = Vec::new();
    for (file, line_no, id) in refs {
        if board_ids.contains(id.as_str()) {
            continue;
        }
        if !seen.insert((file.clone(), id.clone())) {
            continue;
        }
        findings.push(Finding {
            kind: FindingKind::DocReference,
            issue_id: Some(id.clone()),
            detail: "referenced id does not exist on this board".to_string(),
            evidence: Some(format!("{}:{}", file.display(), line_no)),
            proposed_fix: None,
        });
    }
    findings
}

/// Write findings to `.manna/drift.yaml` atomically (temp + rename).
fn write_drift_file(findings: &[Finding]) -> Result<String, String> {
    let report = DriftReport {
        generated_at: Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true),
        // The pid-based fallback id would be this transient CLI invocation,
        // not a real session; only a caller-pinned session id is meaningful.
        session: std::env::var("MANNA_SESSION_ID").ok(),
        findings: findings.to_vec(),
    };
    let yaml = serde_yaml::to_string(&report).map_err(|e| e.to_string())?;
    // Pinned contract: generated_at is a quoted string. Unquoted, YAML 1.1
    // parsers (pyyaml) would resolve the timestamp scalar to a datetime.
    let yaml = yaml.replacen(
        &format!("generated_at: {}", report.generated_at),
        &format!("generated_at: \"{}\"", report.generated_at),
        1,
    );
    let path = Path::new(".manna").join("drift.yaml");
    let temp_path = Path::new(".manna").join("drift.yaml.tmp");
    std::fs::write(&temp_path, yaml).map_err(|e| e.to_string())?;
    std::fs::rename(&temp_path, &path).map_err(|e| e.to_string())?;
    Ok(path.display().to_string())
}

/// Apply --fix for dead_claim and blocker_desync findings through the
/// existing state machine. Returns (fixed issue ids, failure messages).
fn apply_reconcile_fixes(
    store: &MannaStore,
    issues: &[Issue],
    findings: &[Finding],
) -> (Vec<String>, Vec<String>) {
    let mut working: HashMap<String, Issue> =
        issues.iter().map(|i| (i.id.clone(), i.clone())).collect();
    let by_id_status: HashMap<String, IssueStatus> =
        issues.iter().map(|i| (i.id.clone(), i.status.clone())).collect();
    let mut touched: Vec<String> = Vec::new();
    let mut failures: Vec<String> = Vec::new();

    for finding in findings {
        let id = match &finding.issue_id {
            Some(id) => id.clone(),
            None => continue,
        };
        let issue = match working.get_mut(&id) {
            Some(i) => i,
            None => continue,
        };
        match finding.kind {
            FindingKind::DeadClaim => {
                if issue.status == IssueStatus::InProgress {
                    match issue.release() {
                        Ok(()) => touched.push(id),
                        Err(e) => failures.push(format!("{}: {}", id, e)),
                    }
                } else {
                    // Blocked-but-claimed: release() requires in_progress, so
                    // clear the claim directly; blocked status stays derived.
                    issue.claimed_by = None;
                    issue.claimed_at = None;
                    issue.updated_at = Utc::now();
                    touched.push(id);
                }
            }
            FindingKind::BlockerDesync => {
                let resolved: Vec<String> = issue
                    .blocked_by
                    .iter()
                    .filter(|b| {
                        by_id_status
                            .get(*b)
                            .map_or(true, |status| *status == IssueStatus::Done)
                    })
                    .cloned()
                    .collect();
                for blocker in &resolved {
                    issue.remove_blocker(blocker);
                }
                if issue.status == IssueStatus::Blocked && issue.blocked_by.is_empty() {
                    issue.update_blocked_status();
                    issue.updated_at = Utc::now();
                }
                touched.push(id);
            }
            _ => {}
        }
    }

    let mut fixed = Vec::new();
    touched.sort();
    touched.dedup();
    for id in touched {
        let issue = &working[&id];
        match store.update_issue(issue) {
            Ok(()) => fixed.push(id),
            Err(e) => failures.push(format!("{}: {}", id, e)),
        }
    }
    (fixed, failures)
}

fn cmd_reconcile(fix: bool, write_drift: bool, dream_age_days: i64, json: bool) -> ! {
    let store = MannaStore::new(Path::new("."));

    if !store.is_initialized() {
        output_error(
            "Storage not initialized. Run 'manna-core init' first.",
            EXIT_USER_ERROR,
        );
    }

    let issues = match store.load_issues() {
        Ok(i) => i,
        Err(err) => handle_manna_error(err),
    };

    let mut findings: Vec<Finding> = Vec::new();

    // 1. landed_open (report-only)
    match collect_landed_trailers() {
        Ok(landed) => findings.extend(check_landed_open(&issues, &landed)),
        Err(reason) => findings.push(Finding::skipped("landed_open", &reason)),
    }

    // 2. dead_claim
    findings.extend(check_dead_claims(&issues));

    // 3. blocker_desync
    findings.extend(check_blocker_desync(&issues));

    // 4. stale_dream
    findings.extend(check_stale_dream(&issues, Utc::now(), dream_age_days));

    // 5. dangling_track
    findings.extend(check_dangling_track(&issues));

    // 6. doc_reference
    findings.extend(check_doc_references(&issues));

    // Findings describe pre-fix drift; `fixed` lists what --fix addressed.
    let (fixed, fix_failures) = if fix {
        apply_reconcile_fixes(&store, &issues, &findings)
    } else {
        (Vec::new(), Vec::new())
    };

    let drift_written = if write_drift {
        match write_drift_file(&findings) {
            Ok(path) => Some(path),
            Err(e) => output_error(&format!("Failed to write drift.yaml: {}", e), EXIT_SYSTEM_ERROR),
        }
    } else {
        None
    };

    // Advisory verb: findings alone never fail the run; --fix failures do.
    let exit_code = if fix_failures.is_empty() { EXIT_SUCCESS } else { EXIT_USER_ERROR };
    output_with_exit(
        ReconcileData {
            findings,
            fixed,
            fix_failures,
            drift_written,
        },
        json,
        exit_code,
    );
}

// ============================================================================
// Main Entry Point
// ============================================================================

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Init => cmd_init(),
        Commands::Status => cmd_status(),
        Commands::Create { title, description, issue_type, track, source } => {
            cmd_create(title, description, issue_type, track, source)
        }
        Commands::Claim { id } => cmd_claim(id),
        Commands::Done { id } => cmd_done(id),
        Commands::Abandon { id } => cmd_abandon(id),
        Commands::Block { id, blocker_id } => cmd_block(id, blocker_id),
        Commands::Unblock { id, blocker_id } => cmd_unblock(id, blocker_id),
        Commands::List { status, issue_type, track, json } => cmd_list(status, issue_type, track, json),
        Commands::Show { id } => cmd_show(id),
        Commands::Update { id, title, description, status, issue_type, track, source } => {
            cmd_update(id, title, description, status, issue_type, track, source)
        }
        Commands::Delete { id } => cmd_delete(id),
        Commands::Context { max_tokens, json } => cmd_context(max_tokens, json),
        Commands::Dream { spark, track, source } => cmd_dream(spark, track, source),
        Commands::Lint { json } => cmd_lint(json),
        Commands::Reconcile { fix, write_drift, dream_age_days, json } => {
            cmd_reconcile(fix, write_drift, dream_age_days, json)
        }
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use tempfile::TempDir;

    // Mutex to serialize tests that modify MANNA_SESSION_ID env var
    static ENV_MUTEX: Mutex<()> = Mutex::new(());

    fn setup_store() -> (TempDir, MannaStore) {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());
        store.init().unwrap();
        (temp_dir, store)
    }

    #[test]
    fn test_get_session_id_default() {
        let _lock = ENV_MUTEX.lock().unwrap();
        // Clear env var if set
        std::env::remove_var("MANNA_SESSION_ID");

        let session_id = get_session_id();
        assert!(session_id.starts_with("ses_pid"));
    }

    #[test]
    fn test_get_session_id_from_env() {
        let _lock = ENV_MUTEX.lock().unwrap();
        std::env::set_var("MANNA_SESSION_ID", "ses_test_123");
        let session_id = get_session_id();
        assert_eq!(session_id, "ses_test_123");
        std::env::remove_var("MANNA_SESSION_ID");
    }

    #[test]
    fn test_parse_status_valid() {
        assert_eq!(parse_status("open").unwrap(), IssueStatus::Open);
        assert_eq!(
            parse_status("in_progress").unwrap(),
            IssueStatus::InProgress
        );
        assert_eq!(parse_status("blocked").unwrap(), IssueStatus::Blocked);
        assert_eq!(parse_status("done").unwrap(), IssueStatus::Done);
        // Case insensitive
        assert_eq!(parse_status("OPEN").unwrap(), IssueStatus::Open);
        assert_eq!(
            parse_status("In_Progress").unwrap(),
            IssueStatus::InProgress
        );
    }

    #[test]
    fn test_parse_status_invalid() {
        let result = parse_status("invalid");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Invalid status"));
    }

    #[test]
    fn test_error_to_exit_code_user_errors() {
        assert_eq!(
            error_to_exit_code(&MannaError::IssueNotFound("x".to_string())),
            EXIT_USER_ERROR
        );
        assert_eq!(
            error_to_exit_code(&MannaError::IssueAlreadyExists("x".to_string())),
            EXIT_USER_ERROR
        );
        assert_eq!(
            error_to_exit_code(&MannaError::InvalidId("x".to_string())),
            EXIT_USER_ERROR
        );
        assert_eq!(
            error_to_exit_code(&MannaError::NotInitialized),
            EXIT_USER_ERROR
        );
    }

    #[test]
    fn test_error_to_exit_code_system_errors() {
        assert_eq!(
            error_to_exit_code(&MannaError::LockFailed("x".to_string())),
            EXIT_SYSTEM_ERROR
        );
    }

    #[test]
    fn test_find_issue_found() {
        let issues = vec![
            Issue::new("mn-abc123".to_string(), "Test 1".to_string()).unwrap(),
            Issue::new("mn-def456".to_string(), "Test 2".to_string()).unwrap(),
        ];

        let found = find_issue(&issues, "mn-def456");
        assert_eq!(found.id, "mn-def456");
        assert_eq!(found.title, "Test 2");
    }

    #[test]
    fn test_issue_summary_serialization() {
        let summary = IssueSummary {
            id: "mn-abc123".to_string(),
            title: "Test".to_string(),
            status: IssueStatus::Open,
            claimed_by: None,
            issue_type: IssueType::Item,
            track: None,
        };

        let yaml = serde_yaml::to_string(&summary).unwrap();
        assert!(yaml.contains("id: mn-abc123"));
        assert!(yaml.contains("title: Test"));
        assert!(yaml.contains("status: open"));
        // claimed_by should be skipped when None
        assert!(!yaml.contains("claimed_by"));
        // default type and absent track are skipped: v1 output shape unchanged
        assert!(!yaml.contains("type"));
        assert!(!yaml.contains("track"));
    }

    #[test]
    fn test_issue_summary_with_claimed_by() {
        let summary = IssueSummary {
            id: "mn-abc123".to_string(),
            title: "Test".to_string(),
            status: IssueStatus::InProgress,
            claimed_by: Some("ses_123".to_string()),
            issue_type: IssueType::Item,
            track: None,
        };

        let yaml = serde_yaml::to_string(&summary).unwrap();
        assert!(yaml.contains("claimed_by: ses_123"));
    }

    #[test]
    fn test_issue_summary_with_type_and_track() {
        let summary = IssueSummary {
            id: "mn-abc123".to_string(),
            title: "Test".to_string(),
            status: IssueStatus::Open,
            claimed_by: None,
            issue_type: IssueType::Dream,
            track: Some("mn-def456".to_string()),
        };

        let yaml = serde_yaml::to_string(&summary).unwrap();
        assert!(yaml.contains("type: dream"));
        assert!(yaml.contains("track: mn-def456"));
    }

    #[test]
    fn test_parse_issue_type_valid() {
        assert_eq!(parse_issue_type("track").unwrap(), IssueType::Track);
        assert_eq!(parse_issue_type("item").unwrap(), IssueType::Item);
        assert_eq!(parse_issue_type("dream").unwrap(), IssueType::Dream);
        // Case insensitive, matching parse_status
        assert_eq!(parse_issue_type("Track").unwrap(), IssueType::Track);
    }

    #[test]
    fn test_parse_issue_type_invalid() {
        let result = parse_issue_type("epic");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Invalid type"));
    }

    #[test]
    fn test_validate_track_target() {
        let mut track = Issue::new("mn-aaa111".to_string(), "Track".to_string()).unwrap();
        track.issue_type = IssueType::Track;
        let item = Issue::new("mn-bbb222".to_string(), "Item".to_string()).unwrap();
        let issues = vec![track, item];

        assert!(validate_track_target(&issues, "mn-aaa111").is_ok());
        assert!(validate_track_target(&issues, "mn-404404")
            .unwrap_err()
            .contains("not found"));
        assert!(validate_track_target(&issues, "mn-bbb222")
            .unwrap_err()
            .contains("not a track"));
    }

    #[test]
    fn test_build_context_zero_tracks_byte_stable() {
        // A board with no track rows must render the v1 by-status format
        // exactly — pinned here byte for byte.
        let open = Issue::new("mn-aaa111".to_string(), "Open item".to_string()).unwrap();
        let mut working = Issue::new("mn-bbb222".to_string(), "Working item".to_string()).unwrap();
        working.claim("ses_x".to_string()).unwrap();
        let mut blocked = Issue::new("mn-ccc333".to_string(), "Blocked item".to_string()).unwrap();
        blocked.add_blocker("mn-aaa111".to_string());
        let mut finished = Issue::new("mn-ddd444".to_string(), "Done item".to_string()).unwrap();
        finished.claim("ses_x".to_string()).unwrap();
        finished.complete().unwrap();

        let context = build_context(&[open, working, blocked, finished]);
        assert_eq!(
            context,
            "# Manna Context\n\n\
             ## Open Issues (1)\n\
             - mn-aaa111: Open item [open]\n\n\
             ## In Progress Issues (1)\n\
             - mn-bbb222: Working item [in_progress, claimed by ses_x]\n\n\
             ## Blocked Issues (1)\n\
             - mn-ccc333: Blocked item [blocked by: mn-aaa111]\n"
        );
    }

    #[test]
    fn test_build_context_track_tree() {
        let mut track = Issue::new("mn-aaa111".to_string(), "Harness".to_string()).unwrap();
        track.issue_type = IssueType::Track;
        let mut on_track = Issue::new("mn-bbb222".to_string(), "Tracked item".to_string()).unwrap();
        on_track.track = Some("mn-aaa111".to_string());
        let mut claimed = Issue::new("mn-ccc333".to_string(), "Claimed item".to_string()).unwrap();
        claimed.track = Some("mn-aaa111".to_string());
        claimed.claim("ses_x".to_string()).unwrap();
        let mut done_on_track = Issue::new("mn-ddd444".to_string(), "Done item".to_string()).unwrap();
        done_on_track.track = Some("mn-aaa111".to_string());
        done_on_track.claim("ses_x".to_string()).unwrap();
        done_on_track.complete().unwrap();
        let loose = Issue::new("mn-eee555".to_string(), "Loose item".to_string()).unwrap();
        let mut dangling = Issue::new("mn-fff666".to_string(), "Dangling item".to_string()).unwrap();
        dangling.track = Some("mn-404404".to_string());
        let mut spark = Issue::new("mn-abc123".to_string(), "Spark".to_string()).unwrap();
        spark.issue_type = IssueType::Dream;

        let context = build_context(&[track, on_track, claimed, done_on_track, loose, dangling, spark]);

        assert!(context.contains("## Harness (mn-aaa111)\n"));
        assert!(context.contains("- mn-bbb222: Tracked item [open]\n"));
        assert!(context.contains("- mn-ccc333: Claimed item [in_progress, claimed by ses_x]\n"));
        // Done still excluded
        assert!(!context.contains("mn-ddd444"));
        // Trackless and dangling-edge items both land under Untracked
        assert!(context.contains("## Untracked\n"));
        assert!(context.contains("- mn-eee555: Loose item [open]\n"));
        assert!(context.contains("- mn-fff666: Dangling item [open]\n"));
        assert!(context.contains("## Dreams\n- mn-abc123: Spark [open]\n"));
        // v1 by-status sections replaced by the tree
        assert!(!context.contains("## Open Issues"));
        // Ordering: track section, then Untracked, then Dreams
        let track_pos = context.find("## Harness").unwrap();
        let untracked_pos = context.find("## Untracked").unwrap();
        let dreams_pos = context.find("## Dreams").unwrap();
        assert!(track_pos < untracked_pos && untracked_pos < dreams_pos);
    }

    #[test]
    fn test_build_context_track_tree_skips_empty_optional_sections() {
        let mut track = Issue::new("mn-aaa111".to_string(), "Harness".to_string()).unwrap();
        track.issue_type = IssueType::Track;
        let mut on_track = Issue::new("mn-bbb222".to_string(), "Tracked item".to_string()).unwrap();
        on_track.track = Some("mn-aaa111".to_string());

        let context = build_context(&[track, on_track]);
        assert!(context.contains("## Harness (mn-aaa111)\n"));
        assert!(!context.contains("## Untracked"));
        assert!(!context.contains("## Dreams"));
    }

    #[test]
    fn test_drift_report_shape() {
        let report = DriftReport {
            generated_at: "2026-07-21T00:00:00Z".to_string(),
            session: None,
            findings: vec![Finding {
                kind: FindingKind::StaleDream,
                issue_id: Some("mn-abc123".to_string()),
                detail: "open dream older than 14 days".to_string(),
                evidence: None,
                proposed_fix: Some("promote or close".to_string()),
            }],
        };

        let yaml = serde_yaml::to_string(&report).unwrap();
        assert!(yaml.contains("generated_at: "));
        // Pinned contract: session is null when no session id is pinned
        assert!(yaml.contains("session: null"));
        assert!(yaml.contains("kind: stale_dream"));
        assert!(yaml.contains("issue_id: mn-abc123"));
        assert!(yaml.contains("proposed_fix: promote or close"));
        assert!(!yaml.contains("evidence"));
    }

    #[test]
    fn test_success_response_serialization() {
        let response = SuccessResponse {
            success: true,
            data: InitData {
                initialized: true,
                path: ".manna".to_string(),
            },
        };

        let yaml = serde_yaml::to_string(&response).unwrap();
        assert!(yaml.contains("success: true"));
        assert!(yaml.contains("initialized: true"));
        assert!(yaml.contains("path: .manna"));
    }

    #[test]
    fn test_error_response_serialization() {
        let response = ErrorResponse {
            success: false,
            error: "Test error".to_string(),
        };

        let yaml = serde_yaml::to_string(&response).unwrap();
        assert!(yaml.contains("success: false"));
        assert!(yaml.contains("error: Test error"));
    }

    // Integration tests using temp directory
    #[test]
    fn test_store_init_and_load() {
        let (_temp_dir, store) = setup_store();

        assert!(store.is_initialized());
        let issues = store.load_issues().unwrap();
        assert!(issues.is_empty());
    }

    #[test]
    fn test_create_and_retrieve_issue() {
        let (_temp_dir, store) = setup_store();

        let issue = Issue::new("mn-test01".to_string(), "Test Issue".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].id, "mn-test01");
        assert_eq!(issues[0].title, "Test Issue");
    }

    #[test]
    fn test_claim_and_release_workflow() {
        let (_temp_dir, store) = setup_store();

        let mut issue = Issue::new("mn-claim1".to_string(), "Claim Test".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        // Claim
        issue.claim("ses_test".to_string()).unwrap();
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues[0].status, IssueStatus::InProgress);
        assert_eq!(issues[0].claimed_by, Some("ses_test".to_string()));

        // Release
        issue.release().unwrap();
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues[0].status, IssueStatus::Open);
        assert!(issues[0].claimed_by.is_none());
    }

    #[test]
    fn test_complete_workflow() {
        let (_temp_dir, store) = setup_store();

        let mut issue = Issue::new("mn-done01".to_string(), "Complete Test".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        issue.claim("ses_test".to_string()).unwrap();
        store.update_issue(&issue).unwrap();

        issue.complete().unwrap();
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues[0].status, IssueStatus::Done);
    }

    #[test]
    fn test_block_workflow() {
        let (_temp_dir, store) = setup_store();

        let blocker = Issue::new("mn-block1".to_string(), "Blocker".to_string()).unwrap();
        store.append_issue(&blocker).unwrap();

        let mut issue = Issue::new("mn-block2".to_string(), "Blocked Issue".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        issue.add_blocker("mn-block1".to_string());
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        let blocked_issue = issues.iter().find(|i| i.id == "mn-block2").unwrap();
        assert_eq!(blocked_issue.status, IssueStatus::Blocked);
        assert!(blocked_issue.blocked_by.contains(&"mn-block1".to_string()));
    }

    #[test]
    fn test_unblock_workflow() {
        let (_temp_dir, store) = setup_store();

        let blocker = Issue::new("mn-unblk1".to_string(), "Blocker".to_string()).unwrap();
        store.append_issue(&blocker).unwrap();

        let mut issue = Issue::new("mn-unblk2".to_string(), "Blocked".to_string()).unwrap();
        issue.add_blocker("mn-unblk1".to_string());
        store.append_issue(&issue).unwrap();

        issue.remove_blocker("mn-unblk1");
        store.update_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        let unblocked = issues.iter().find(|i| i.id == "mn-unblk2").unwrap();
        assert_eq!(unblocked.status, IssueStatus::Open);
        assert!(unblocked.blocked_by.is_empty());
    }

    #[test]
    fn test_context_generation() {
        let issues = vec![
            Issue::new("mn-ctx001".to_string(), "Open Issue".to_string()).unwrap(),
            {
                let mut i = Issue::new("mn-ctx002".to_string(), "In Progress".to_string()).unwrap();
                i.claim("ses_test".to_string()).unwrap();
                i
            },
            {
                let mut i =
                    Issue::new("mn-ctx003".to_string(), "Blocked Issue".to_string()).unwrap();
                i.add_blocker("mn-ctx001".to_string());
                i
            },
        ];

        // Verify structure
        let open: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::Open)
            .collect();
        let in_progress: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::InProgress)
            .collect();
        let blocked: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::Blocked)
            .collect();

        assert_eq!(open.len(), 1);
        assert_eq!(in_progress.len(), 1);
        assert_eq!(blocked.len(), 1);
    }

    #[test]
    fn test_list_filtering() {
        let issues = vec![
            Issue::new("mn-flt001".to_string(), "Open 1".to_string()).unwrap(),
            Issue::new("mn-flt002".to_string(), "Open 2".to_string()).unwrap(),
            {
                let mut i = Issue::new("mn-flt003".to_string(), "Done".to_string()).unwrap();
                i.claim("ses".to_string()).unwrap();
                i.complete().unwrap();
                i
            },
        ];

        let open_only: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::Open)
            .collect();
        assert_eq!(open_only.len(), 2);

        let done_only: Vec<_> = issues
            .iter()
            .filter(|i| i.status == IssueStatus::Done)
            .collect();
        assert_eq!(done_only.len(), 1);
    }
}

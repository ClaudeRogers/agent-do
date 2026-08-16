//! Issue data structures and operations.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Issue status enum matching SCHEMA.md
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IssueStatus {
    #[default]
    Open,
    InProgress,
    Blocked,
    Done,
}

impl std::fmt::Display for IssueStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            IssueStatus::Open => write!(f, "open"),
            IssueStatus::InProgress => write!(f, "in_progress"),
            IssueStatus::Blocked => write!(f, "blocked"),
            IssueStatus::Done => write!(f, "done"),
        }
    }
}

/// Issue type enum: track (umbrella), item (work unit, default), dream (intake spark)
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IssueType {
    Track,
    #[default]
    Item,
    Dream,
}

impl std::fmt::Display for IssueType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            IssueType::Track => write!(f, "track"),
            IssueType::Item => write!(f, "item"),
            IssueType::Dream => write!(f, "dream"),
        }
    }
}

/// True when the type is the default (`item`); v1 rows round-trip unchanged.
pub fn is_default_type(issue_type: &IssueType) -> bool {
    *issue_type == IssueType::Item
}

/// Marker rendered beside every dream in `list` and `context`.
///
/// Dreams stay visible on purpose; the marker is what makes the visibility
/// safe, so an agent reads the idea and its un-actionable status at once.
pub const DREAM_INERT_MARKER: &str = "[DREAM: not claimable, needs conversion]";

/// The refusal text for claiming a dream.
///
/// A dream is a parked spark, not work. Conversion (`update --type item`) is
/// the authorization act, and Erik is the one who performs it; refusing here,
/// rather than hiding the row, is what keeps an agent from building it unasked.
pub fn dream_claim_refusal(id: &str) -> String {
    format!(
        "{id} is a dream, not claimable work: nothing was written. \
         A dream is a parked spark and becomes work only when Erik converts it. \
         Authorize with: agent-do manna update {id} --type item"
    )
}

/// An issue in Manna.
///
/// See SCHEMA.md for field definitions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Issue {
    /// Unique identifier (format: mn-{6-hex})
    pub id: String,

    /// Issue title/summary (1-500 characters)
    pub title: String,

    /// Current issue state
    pub status: IssueStatus,

    /// Optional detailed description
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,

    /// When issue was created
    pub created_at: DateTime<Utc>,

    /// Last modification time
    pub updated_at: DateTime<Utc>,

    /// Issues blocking this one
    #[serde(default)]
    pub blocked_by: Vec<String>,

    /// Session ID of who is working on this
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub claimed_by: Option<String>,

    /// When it was claimed
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub claimed_at: Option<DateTime<Utc>>,

    /// Issue type: track, item (default), or dream
    #[serde(rename = "type", default, skip_serializing_if = "is_default_type")]
    pub issue_type: IssueType,

    /// Track this issue belongs to (edge to a `type: track` issue)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub track: Option<String>,

    /// Where this issue came from (vault note, conversation, commit, ...)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,

    /// Work-order prompt file paired with this issue. Strict boards use a
    /// repository-relative `.handoff/` path; legacy boards may carry an
    /// absolute pointer.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prompt: Option<String>,

    /// SHA-256 binding for the complete canonical handoff document. The same
    /// value is carried in the handoff frontmatter and is re-derived before a
    /// claim, so a syntactic claim mention cannot impersonate a work order.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub handoff_digest: Option<String>,
}

impl Issue {
    /// Create a new issue with the given ID and title.
    ///
    /// # Arguments
    /// * `id` - Unique issue identifier (format: mn-{6-hex})
    /// * `title` - Issue title (1-500 characters)
    ///
    /// # Returns
    /// Result with new Issue or validation error
    pub fn new(id: String, title: String) -> Result<Self, String> {
        if title.is_empty() || title.len() > 500 {
            return Err(format!(
                "Title must be 1-500 characters, got {}",
                title.len()
            ));
        }

        let now = Utc::now();
        Ok(Issue {
            id,
            title,
            status: IssueStatus::Open,
            description: None,
            created_at: now,
            updated_at: now,
            blocked_by: Vec::new(),
            claimed_by: None,
            claimed_at: None,
            issue_type: IssueType::default(),
            track: None,
            source: None,
            prompt: None,
            handoff_digest: None,
        })
    }

    /// Claim this issue for a session
    ///
    /// # Arguments
    /// * `session_id` - Session identifier claiming the issue
    ///
    /// # Returns
    /// Result indicating success or error if already claimed
    pub fn claim(&mut self, session_id: String) -> Result<(), String> {
        // The gate lives on the model so no caller can claim a dream, whatever
        // path it arrives by. The CLI checks first to exit 2 with the same text.
        if self.issue_type == IssueType::Dream {
            return Err(dream_claim_refusal(&self.id));
        }

        if self.status != IssueStatus::Open {
            return Err(format!(
                "Cannot claim issue with status '{}', must be 'open'",
                self.status
            ));
        }

        if self.claimed_by.is_some() {
            return Err("Issue is already claimed".to_string());
        }

        let now = Utc::now();
        self.claimed_by = Some(session_id);
        self.claimed_at = Some(now);
        self.status = IssueStatus::InProgress;
        self.updated_at = now;

        Ok(())
    }

    /// Release (abandon) this issue
    ///
    /// # Returns
    /// Result indicating success or error if not claimed
    pub fn release(&mut self, session_id: &str) -> Result<(), String> {
        if self.claimed_by.is_none() {
            return Err("Issue is not claimed".to_string());
        }

        self.require_owner(session_id)?;

        if self.status != IssueStatus::InProgress {
            return Err(format!(
                "Cannot release issue with status '{}', must be 'in_progress'",
                self.status
            ));
        }

        self.claimed_by = None;
        self.claimed_at = None;
        self.status = IssueStatus::Open;
        self.updated_at = Utc::now();

        Ok(())
    }

    /// Mark this issue as complete
    ///
    /// # Returns
    /// Result indicating success or error if not in progress
    pub fn complete(&mut self, session_id: &str) -> Result<(), String> {
        if self.status != IssueStatus::InProgress {
            return Err(format!(
                "Cannot complete issue with status '{}', must be 'in_progress'",
                self.status
            ));
        }

        self.require_owner(session_id)?;

        self.status = IssueStatus::Done;
        self.updated_at = Utc::now();

        Ok(())
    }

    /// Close an unworked dream through an explicit lifecycle verb. Dreams are
    /// intentionally unclaimable, so requiring `in_progress` would make them
    /// impossible to retire without reviving the raw `update --status` bypass.
    pub fn close_dream(&mut self, session_id: &str) -> Result<(), String> {
        if self.issue_type != IssueType::Dream {
            return Err("Only dreams use the unclaimed close transition".to_string());
        }
        self.require_owner(session_id)?;
        if !matches!(self.status, IssueStatus::Open | IssueStatus::Blocked) {
            return Err(format!(
                "Cannot close dream with status '{}', must be 'open' or 'blocked'",
                self.status
            ));
        }
        self.status = IssueStatus::Done;
        self.updated_at = Utc::now();
        Ok(())
    }

    /// Require the current session to own a claimed issue.
    ///
    /// Unclaimed rows remain editable. Once a claim exists, every lifecycle
    /// and metadata mutation must present the same pinned session identity.
    pub fn require_owner(&self, session_id: &str) -> Result<(), String> {
        if let Some(owner) = self.claimed_by.as_deref() {
            if owner != session_id {
                return Err(format!(
                    "Issue {} is claimed by session {}; current session {} cannot mutate it",
                    self.id, owner, session_id
                ));
            }
        }
        Ok(())
    }

    /// Administrative release used only for a dead-session reconcile repair.
    /// Ordinary callers must use `release`, which enforces session ownership.
    pub fn release_dead_claim(&mut self) -> Result<(), String> {
        if self.claimed_by.is_none() {
            return Err("Issue is not claimed".to_string());
        }
        self.claimed_by = None;
        self.claimed_at = None;
        if self.status != IssueStatus::Done {
            self.status = if self.blocked_by.is_empty() {
                IssueStatus::Open
            } else {
                IssueStatus::Blocked
            };
        }
        self.updated_at = Utc::now();
        Ok(())
    }

    /// Add a blocker to this issue
    ///
    /// # Arguments
    /// * `blocker_id` - ID of the blocking issue
    pub fn add_blocker(&mut self, blocker_id: String) {
        if !self.blocked_by.contains(&blocker_id) {
            self.blocked_by.push(blocker_id);
            self.update_blocked_status();
            self.updated_at = Utc::now();
        }
    }

    /// Remove a blocker from this issue
    ///
    /// # Arguments
    /// * `blocker_id` - ID of the blocking issue to remove
    pub fn remove_blocker(&mut self, blocker_id: &str) {
        if let Some(pos) = self.blocked_by.iter().position(|id| id == blocker_id) {
            self.blocked_by.remove(pos);
            self.update_blocked_status();
            self.updated_at = Utc::now();
        }
    }

    /// Update blocked status based on blocked_by list
    pub fn update_blocked_status(&mut self) {
        if !self.blocked_by.is_empty() && self.status != IssueStatus::Done {
            self.status = IssueStatus::Blocked;
        } else if self.blocked_by.is_empty() && self.status == IssueStatus::Blocked {
            self.status = if self.claimed_by.is_some() {
                IssueStatus::InProgress
            } else {
                IssueStatus::Open
            };
        }
    }

    /// Validate issue data integrity
    pub fn validate(&self) -> Result<(), String> {
        if self.title.is_empty() || self.title.len() > 500 {
            return Err(format!(
                "Title must be 1-500 characters, got {}",
                self.title.len()
            ));
        }

        if !self.id.starts_with("mn-") {
            return Err(format!("ID must start with 'mn-', got '{}'", self.id));
        }

        if self.status == IssueStatus::InProgress && self.claimed_by.is_none() {
            return Err("Issue in_progress must have claimed_by set".to_string());
        }

        if self.claimed_by.is_some() && self.claimed_at.is_none() {
            return Err("Issue with claimed_by must have claimed_at set".to_string());
        }

        if self.claimed_by.is_none() && self.claimed_at.is_some() {
            return Err("Issue without claimed_by cannot have claimed_at set".to_string());
        }

        if self.issue_type == IssueType::Track && self.track.is_some() {
            return Err("Track issues cannot have a track edge (tracks don't nest)".to_string());
        }

        if let Some(digest) = self.handoff_digest.as_deref() {
            let hex = digest.strip_prefix("sha256:").ok_or_else(|| {
                "handoff_digest must use the sha256:<64 lowercase hex> format".to_string()
            })?;
            if hex.len() != 64
                || !hex
                    .bytes()
                    .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
            {
                return Err(
                    "handoff_digest must use the sha256:<64 lowercase hex> format".to_string(),
                );
            }
            if self.prompt.is_none() {
                return Err("Issue with handoff_digest must have a prompt pointer".to_string());
            }
        }

        Ok(())
    }
}

/// Session event types matching SCHEMA.md
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SessionEventType {
    Start,
    Claim,
    Release,
    Done,
    End,
}

impl std::fmt::Display for SessionEventType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SessionEventType::Start => write!(f, "start"),
            SessionEventType::Claim => write!(f, "claim"),
            SessionEventType::Release => write!(f, "release"),
            SessionEventType::Done => write!(f, "done"),
            SessionEventType::End => write!(f, "end"),
        }
    }
}

/// A session event in the session log.
///
/// See SCHEMA.md for field definitions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionEvent {
    /// Session identifier
    pub session_id: String,

    /// Event type
    pub event: SessionEventType,

    /// When event occurred
    pub timestamp: DateTime<Utc>,

    /// Issue ID (required for claim, release, done events)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub issue_id: Option<String>,

    /// Context data (required for start, end events)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub context: Option<serde_json::Value>,
}

impl SessionEvent {
    /// Create a new session start event.
    pub fn start(session_id: String, context: serde_json::Value) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::Start,
            timestamp: Utc::now(),
            issue_id: None,
            context: Some(context),
        }
    }

    /// Create a new claim event.
    pub fn claim(session_id: String, issue_id: String) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::Claim,
            timestamp: Utc::now(),
            issue_id: Some(issue_id),
            context: None,
        }
    }

    /// Create a new release event.
    pub fn release(session_id: String, issue_id: String) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::Release,
            timestamp: Utc::now(),
            issue_id: Some(issue_id),
            context: None,
        }
    }

    /// Create a new done event.
    pub fn done(session_id: String, issue_id: String) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::Done,
            timestamp: Utc::now(),
            issue_id: Some(issue_id),
            context: None,
        }
    }

    /// Create a new session end event.
    pub fn end(session_id: String, context: serde_json::Value) -> Self {
        SessionEvent {
            session_id,
            event: SessionEventType::End,
            timestamp: Utc::now(),
            issue_id: None,
            context: Some(context),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_issue_valid() {
        let issue = Issue::new("mn-abc123".to_string(), "Test issue".to_string()).unwrap();
        assert_eq!(issue.id, "mn-abc123");
        assert_eq!(issue.title, "Test issue");
        assert_eq!(issue.status, IssueStatus::Open);
        assert!(issue.description.is_none());
        assert!(issue.blocked_by.is_empty());
        assert!(issue.claimed_by.is_none());
        assert!(issue.claimed_at.is_none());
    }

    #[test]
    fn test_new_issue_empty_title() {
        let result = Issue::new("mn-abc123".to_string(), "".to_string());
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("1-500 characters"));
    }

    #[test]
    fn test_new_issue_title_too_long() {
        let long_title = "x".repeat(501);
        let result = Issue::new("mn-abc123".to_string(), long_title);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("1-500 characters"));
    }

    #[test]
    fn test_claim_issue() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let result = issue.claim("ses_123".to_string());
        assert!(result.is_ok());
        assert_eq!(issue.status, IssueStatus::InProgress);
        assert_eq!(issue.claimed_by, Some("ses_123".to_string()));
        assert!(issue.claimed_at.is_some());
    }

    #[test]
    fn test_claim_already_claimed() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_123".to_string()).unwrap();
        let result = issue.claim("ses_456".to_string());
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("must be 'open'"));
    }

    #[test]
    fn test_claim_wrong_status() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.status = IssueStatus::Done;
        let result = issue.claim("ses_123".to_string());
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("must be 'open'"));
    }

    #[test]
    fn test_release_issue() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_123".to_string()).unwrap();
        let result = issue.release("ses_123");
        assert!(result.is_ok());
        assert_eq!(issue.status, IssueStatus::Open);
        assert!(issue.claimed_by.is_none());
        assert!(issue.claimed_at.is_none());
    }

    #[test]
    fn test_release_not_claimed() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let result = issue.release("ses_123");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("not claimed"));
    }

    #[test]
    fn test_release_rejects_non_owner_without_mutation() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_owner".to_string()).unwrap();
        let before = serde_json::to_string(&issue).unwrap();
        let error = issue.release("ses_intruder").unwrap_err();
        assert!(error.contains("claimed by session ses_owner"));
        assert_eq!(serde_json::to_string(&issue).unwrap(), before);
    }

    #[test]
    fn test_complete_issue() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_123".to_string()).unwrap();
        let result = issue.complete("ses_123");
        assert!(result.is_ok());
        assert_eq!(issue.status, IssueStatus::Done);
    }

    #[test]
    fn test_complete_not_in_progress() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let result = issue.complete("ses_123");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("must be 'in_progress'"));
    }

    #[test]
    fn test_complete_rejects_non_owner_without_mutation() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_owner".to_string()).unwrap();
        let before = serde_json::to_string(&issue).unwrap();
        let error = issue.complete("ses_intruder").unwrap_err();
        assert!(error.contains("claimed by session ses_owner"));
        assert_eq!(serde_json::to_string(&issue).unwrap(), before);
    }

    #[test]
    fn test_close_dream_uses_explicit_unclaimed_transition() {
        let mut dream = Issue::new("mn-abc123".to_string(), "Parked".to_string()).unwrap();
        dream.issue_type = IssueType::Dream;
        dream.close_dream("ses_curator").unwrap();
        assert_eq!(dream.status, IssueStatus::Done);
        assert!(dream.claimed_by.is_none());
    }

    #[test]
    fn test_add_blocker() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.add_blocker("mn-def456".to_string());
        assert_eq!(issue.blocked_by.len(), 1);
        assert_eq!(issue.status, IssueStatus::Blocked);
    }

    #[test]
    fn test_add_duplicate_blocker() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.add_blocker("mn-def456".to_string());
        issue.add_blocker("mn-def456".to_string());
        assert_eq!(issue.blocked_by.len(), 1);
    }

    #[test]
    fn test_remove_blocker() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.add_blocker("mn-def456".to_string());
        issue.remove_blocker("mn-def456");
        assert!(issue.blocked_by.is_empty());
        assert_eq!(issue.status, IssueStatus::Open);
    }

    #[test]
    fn test_blocked_status_with_claim() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.claim("ses_123".to_string()).unwrap();
        assert_eq!(issue.status, IssueStatus::InProgress);

        issue.add_blocker("mn-def456".to_string());
        assert_eq!(issue.status, IssueStatus::Blocked);

        issue.remove_blocker("mn-def456");
        assert_eq!(issue.status, IssueStatus::InProgress);
    }

    #[test]
    fn test_validate_valid_issue() {
        let issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        assert!(issue.validate().is_ok());
    }

    #[test]
    fn test_validate_in_progress_without_claim() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        issue.status = IssueStatus::InProgress;
        let result = issue.validate();
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("must have claimed_by"));
    }

    #[test]
    fn test_serde_roundtrip() {
        let issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let json = serde_json::to_string(&issue).unwrap();
        let deserialized: Issue = serde_json::from_str(&json).unwrap();
        assert_eq!(issue.id, deserialized.id);
        assert_eq!(issue.title, deserialized.title);
        assert_eq!(issue.status, deserialized.status);
    }

    #[test]
    fn test_status_serialization() {
        let issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        let json = serde_json::to_string(&issue).unwrap();
        assert!(json.contains(r#""status":"open"#));
    }

    #[test]
    fn test_new_issue_defaults_to_item_type() {
        let issue = Issue::new("mn-abc123".to_string(), "Test".to_string()).unwrap();
        assert_eq!(issue.issue_type, IssueType::Item);
        assert!(issue.track.is_none());
        assert!(issue.source.is_none());
        assert!(issue.prompt.is_none());
    }

    #[test]
    fn test_v1_row_deserializes_and_reserializes_unchanged() {
        // A v1 line has no type/track/source/prompt fields; it must parse as
        // an item and re-serialize without adding any of the new fields.
        let v1_line = r#"{"id":"mn-abc123","title":"V1 row","status":"open","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[]}"#;
        let issue: Issue = serde_json::from_str(v1_line).unwrap();
        assert_eq!(issue.issue_type, IssueType::Item);
        assert!(issue.track.is_none());
        assert!(issue.source.is_none());
        assert!(issue.prompt.is_none());

        let json = serde_json::to_string(&issue).unwrap();
        assert!(!json.contains(r#""type""#));
        assert!(!json.contains(r#""track""#));
        assert!(!json.contains(r#""source""#));
        assert!(!json.contains(r#""prompt""#));
    }

    #[test]
    fn test_prompt_field_roundtrip() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Prompted".to_string()).unwrap();
        issue.prompt = Some("/abs/path/lane-4.md".to_string());

        let json = serde_json::to_string(&issue).unwrap();
        assert!(json.contains(r#""prompt":"/abs/path/lane-4.md""#));

        let deserialized: Issue = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.prompt, Some("/abs/path/lane-4.md".to_string()));
    }

    #[test]
    fn test_typed_issue_roundtrip() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Dream".to_string()).unwrap();
        issue.issue_type = IssueType::Dream;
        issue.track = Some("mn-def456".to_string());
        issue.source = Some("vault:+/idea.md".to_string());

        let json = serde_json::to_string(&issue).unwrap();
        assert!(json.contains(r#""type":"dream""#));
        assert!(json.contains(r#""track":"mn-def456""#));
        assert!(json.contains(r#""source":"vault:+/idea.md""#));

        let deserialized: Issue = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.issue_type, IssueType::Dream);
        assert_eq!(deserialized.track, Some("mn-def456".to_string()));
        assert_eq!(deserialized.source, Some("vault:+/idea.md".to_string()));
    }

    #[test]
    fn test_track_type_serializes_type_field() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Umbrella".to_string()).unwrap();
        issue.issue_type = IssueType::Track;
        let json = serde_json::to_string(&issue).unwrap();
        assert!(json.contains(r#""type":"track""#));
    }

    #[test]
    fn test_validate_track_with_track_edge_fails() {
        let mut issue = Issue::new("mn-abc123".to_string(), "Nested track".to_string()).unwrap();
        issue.issue_type = IssueType::Track;
        issue.track = Some("mn-def456".to_string());
        let result = issue.validate();
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("tracks don't nest"));
    }

    #[test]
    fn test_is_default_type() {
        assert!(is_default_type(&IssueType::Item));
        assert!(!is_default_type(&IssueType::Track));
        assert!(!is_default_type(&IssueType::Dream));
    }

    #[test]
    fn test_claim_dream_refused_and_unchanged() {
        let mut spark = Issue::new("mn-abc123".to_string(), "Parked spark".to_string()).unwrap();
        spark.issue_type = IssueType::Dream;

        let result = spark.claim("ses_123".to_string());

        assert!(result.is_err());
        assert_eq!(spark.status, IssueStatus::Open);
        assert!(spark.claimed_by.is_none());
        assert!(spark.claimed_at.is_none());
    }

    #[test]
    fn test_dream_refusal_names_id_and_conversion() {
        let message = dream_claim_refusal("mn-abc123");
        assert!(message.contains("mn-abc123"));
        assert!(message.contains("not claimable work"));
        assert!(message.contains("agent-do manna update mn-abc123 --type item"));
        assert!(message.contains("Erik"));
    }

    #[test]
    fn test_dream_refusal_beats_status_check() {
        // A dream that somehow reached done still refuses as a dream, not with
        // the generic status message: the type is the reason.
        let mut spark = Issue::new("mn-abc123".to_string(), "Parked spark".to_string()).unwrap();
        spark.issue_type = IssueType::Dream;
        spark.status = IssueStatus::Done;

        let err = spark.claim("ses_123".to_string()).unwrap_err();
        assert!(err.contains("not claimable work"));
        assert!(!err.contains("must be 'open'"));
    }

    #[test]
    fn test_claim_after_conversion_to_item_succeeds() {
        let mut spark = Issue::new("mn-abc123".to_string(), "Parked spark".to_string()).unwrap();
        spark.issue_type = IssueType::Dream;
        assert!(spark.claim("ses_123".to_string()).is_err());

        spark.issue_type = IssueType::Item;
        assert!(spark.claim("ses_123".to_string()).is_ok());
        assert_eq!(spark.status, IssueStatus::InProgress);
    }

    #[test]
    fn test_claim_track_still_allowed() {
        // Only dreams are gated; tracks and items keep their v1 claim path.
        let mut umbrella = Issue::new("mn-abc123".to_string(), "Umbrella".to_string()).unwrap();
        umbrella.issue_type = IssueType::Track;
        assert!(umbrella.claim("ses_123".to_string()).is_ok());
    }
}

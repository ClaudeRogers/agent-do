//! JSONL storage with file locking for Manna.
//!
//! Storage files:
//! - `.manna/issues.jsonl` - Issue records
//! - `.manna/sessions.jsonl` - Session event log

use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

use fs2::FileExt;

use crate::error::{MannaError, Result};
use crate::issue::{Issue, SessionEvent};

/// Directory name for Manna storage.
const MANNA_DIR: &str = ".manna";

/// Issues JSONL file name.
const ISSUES_FILE: &str = "issues.jsonl";

/// Sessions JSONL file name.
const SESSIONS_FILE: &str = "sessions.jsonl";

/// Manna storage backed by JSONL files.
///
/// All writes acquire exclusive file locks to prevent corruption
/// during concurrent access.
#[derive(Debug, Clone)]
pub struct MannaStore {
    /// Base directory containing `.manna/`.
    base_dir: PathBuf,
}

impl MannaStore {
    /// Create a new MannaStore rooted at the given directory.
    ///
    /// Does not initialize storage; call `init()` first.
    pub fn new<P: AsRef<Path>>(base_dir: P) -> Self {
        MannaStore {
            base_dir: base_dir.as_ref().to_path_buf(),
        }
    }

    /// Get the `.manna` directory path.
    fn manna_dir(&self) -> PathBuf {
        self.base_dir.join(MANNA_DIR)
    }

    /// Get the issues.jsonl file path.
    fn issues_path(&self) -> PathBuf {
        self.manna_dir().join(ISSUES_FILE)
    }

    /// Get the sessions.jsonl file path.
    fn sessions_path(&self) -> PathBuf {
        self.manna_dir().join(SESSIONS_FILE)
    }

    /// Initialize storage by creating `.manna/` directory and JSONL files.
    ///
    /// This is idempotent - running twice does not error.
    pub fn init(&self) -> Result<()> {
        let manna_dir = self.manna_dir();

        // Create .manna directory if it doesn't exist
        if !manna_dir.exists() {
            fs::create_dir_all(&manna_dir)?;
        }

        // Create issues.jsonl if it doesn't exist
        let issues_path = self.issues_path();
        if !issues_path.exists() {
            File::create(&issues_path)?;
        }

        // Create sessions.jsonl if it doesn't exist
        let sessions_path = self.sessions_path();
        if !sessions_path.exists() {
            File::create(&sessions_path)?;
        }

        Ok(())
    }

    /// Check if storage is initialized.
    pub fn is_initialized(&self) -> bool {
        self.manna_dir().exists() && self.issues_path().exists() && self.sessions_path().exists()
    }

    /// Load all issues from issues.jsonl.
    ///
    /// Skips malformed lines with a warning to stderr.
    pub fn load_issues(&self) -> Result<Vec<Issue>> {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let file = File::open(&path)?;
        let reader = BufReader::new(file);
        let mut issues = Vec::new();

        for (line_num, line_result) in reader.lines().enumerate() {
            let line = match line_result {
                Ok(l) => l,
                Err(e) => {
                    eprintln!(
                        "Warning: Failed to read line {} in {}: {}",
                        line_num + 1,
                        path.display(),
                        e
                    );
                    continue;
                }
            };

            // Skip empty lines
            if line.trim().is_empty() {
                continue;
            }

            match serde_json::from_str::<Issue>(&line) {
                Ok(issue) => issues.push(issue),
                Err(e) => {
                    eprintln!(
                        "Warning: Skipping malformed line {} in {}: {}",
                        line_num + 1,
                        path.display(),
                        e
                    );
                }
            }
        }

        Ok(issues)
    }

    /// Append a new issue to issues.jsonl with exclusive file lock.
    /// Acquire the board-wide mutation lock.
    ///
    /// Every mutating operation must hold this for its FULL read-modify-write
    /// span. Per-file locks are not enough: rewrite paths build a new file and
    /// rename it over the board, so a writer locking only its own temp file
    /// excludes nobody, and two concurrent mutations silently revert each
    /// other (observed live 2026-07-22: a `done` lost to a description edit).
    /// The lock releases when the returned handle drops.
    fn lock_board(&self) -> Result<File> {
        let lock_path = self.manna_dir().join("board.lock");
        let lock_file = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(false)
            .open(&lock_path)?;
        lock_file
            .lock_exclusive()
            .map_err(|e| MannaError::LockFailed(e.to_string()))?;
        Ok(lock_file)
    }

    pub fn append_issue(&self, issue: &Issue) -> Result<()> {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let _board_lock = self.lock_board()?;
        let issues = self.load_issues()?;
        if issues.iter().any(|existing| existing.id == issue.id) {
            return Err(MannaError::IssueAlreadyExists(issue.id.clone()));
        }

        let file = OpenOptions::new().append(true).open(&path)?;

        // Acquire exclusive lock
        file.lock_exclusive()
            .map_err(|e| MannaError::LockFailed(e.to_string()))?;

        // Write issue as JSON line
        let mut writer = std::io::BufWriter::new(&file);
        serde_json::to_writer(&mut writer, issue)?;
        writeln!(writer)?;
        writer.flush()?;

        // Lock is released when file is dropped
        Ok(())
    }

    fn write_issues_locked(&self, issues: &[Issue]) -> Result<()> {
        let path = self.issues_path();
        let temp_path = path.with_extension("jsonl.tmp");
        {
            let temp_file = OpenOptions::new()
                .create(true)
                .truncate(true)
                .write(true)
                .open(&temp_path)?;

            // Acquire exclusive lock on temp file
            temp_file
                .lock_exclusive()
                .map_err(|e| MannaError::LockFailed(e.to_string()))?;

            let mut writer = std::io::BufWriter::new(&temp_file);
            for issue in issues {
                serde_json::to_writer(&mut writer, issue)?;
                writeln!(writer)?;
            }
            writer.flush()?;
            temp_file.sync_all()?;
        }

        fs::rename(&temp_path, &path)?;
        if let Some(parent) = path.parent() {
            File::open(parent)?.sync_all()?;
        }

        Ok(())
    }

    fn mutate_issue_locked<F>(&self, id: &str, mutation: F) -> Result<Issue>
    where
        F: FnOnce(&mut Issue, &[Issue]) -> std::result::Result<(), String>,
    {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        let snapshot = issues.clone();
        let issue = issues
            .iter_mut()
            .find(|issue| issue.id == id)
            .ok_or_else(|| MannaError::IssueNotFound(id.to_string()))?;
        mutation(issue, &snapshot).map_err(MannaError::MutationRejected)?;
        issue.validate().map_err(MannaError::MutationRejected)?;
        let updated = issue.clone();
        self.write_issues_locked(&issues)?;
        Ok(updated)
    }

    /// Claim an issue under one board lock. The row is reloaded only after
    /// the lock is held, so exactly one contender can observe `open`.
    pub fn claim_issue(&self, id: &str, session_id: &str) -> Result<Issue> {
        self.mutate_issue_locked(id, |issue, _| issue.claim(session_id.to_string()))
    }

    /// Claim with an integrity precondition evaluated after acquiring the
    /// board lock and reloading the row. This closes the validate-then-claim
    /// race as well as the open-then-write race.
    pub fn claim_issue_checked<F>(
        &self,
        id: &str,
        session_id: &str,
        precondition: F,
    ) -> Result<Issue>
    where
        F: FnOnce(&Issue, &[Issue]) -> std::result::Result<(), String>,
    {
        self.mutate_issue_locked(id, |issue, issues| {
            precondition(issue, issues)?;
            issue.claim(session_id.to_string())
        })
    }

    /// Complete a claimed issue only for the session that owns it.
    pub fn complete_issue(&self, id: &str, session_id: &str) -> Result<Issue> {
        self.mutate_issue_locked(id, |issue, _| {
            if issue.issue_type == crate::issue::IssueType::Dream {
                issue.close_dream(session_id)
            } else {
                issue.complete(session_id)
            }
        })
    }

    /// Release a claimed issue only for the session that owns it.
    pub fn release_issue(&self, id: &str, session_id: &str) -> Result<Issue> {
        self.mutate_issue_locked(id, |issue, _| issue.release(session_id))
    }

    /// Mutate metadata without allowing a caller to smuggle a lifecycle
    /// transition through an update path.
    pub fn mutate_issue_metadata<F>(&self, id: &str, session_id: &str, mutation: F) -> Result<Issue>
    where
        F: FnOnce(&mut Issue, &[Issue]) -> std::result::Result<(), String>,
    {
        self.mutate_issue_locked(id, |issue, issues| {
            issue.require_owner(session_id)?;
            let lifecycle = (
                issue.status.clone(),
                issue.claimed_by.clone(),
                issue.claimed_at,
                issue.blocked_by.clone(),
            );
            mutation(issue, issues)?;
            if lifecycle
                != (
                    issue.status.clone(),
                    issue.claimed_by.clone(),
                    issue.claimed_at,
                    issue.blocked_by.clone(),
                )
            {
                return Err(
                    "metadata update attempted to bypass a lifecycle transition".to_string()
                );
            }
            Ok(())
        })
    }

    pub fn add_blocker(&self, id: &str, blocker_id: &str, session_id: &str) -> Result<Issue> {
        self.mutate_issue_locked(id, |issue, issues| {
            issue.require_owner(session_id)?;
            if !issues.iter().any(|candidate| candidate.id == blocker_id) {
                return Err(format!("Blocker issue {} not found", blocker_id));
            }
            issue.add_blocker(blocker_id.to_string());
            Ok(())
        })
    }

    pub fn remove_blocker(&self, id: &str, blocker_id: &str, session_id: &str) -> Result<Issue> {
        self.mutate_issue_locked(id, |issue, _| {
            issue.require_owner(session_id)?;
            issue.remove_blocker(blocker_id);
            Ok(())
        })
    }

    /// Reconcile-only mutation path. Callers must first prove the repair from
    /// external evidence, such as a dead pinned session or a resolved blocker.
    pub fn repair_issue<F>(&self, id: &str, mutation: F) -> Result<Issue>
    where
        F: FnOnce(&mut Issue, &[Issue]) -> std::result::Result<(), String>,
    {
        self.mutate_issue_locked(id, mutation)
    }

    /// Replace a row only when recovery can prove the existing record has the
    /// same identity. Used by the pair transaction journal.
    pub fn recover_issue(&self, expected: &Issue) -> Result<Issue> {
        self.recover_issue_with(expected, || Ok(()))
    }

    pub fn recover_issue_with<F>(&self, expected: &Issue, commit_pair: F) -> Result<Issue>
    where
        F: FnOnce() -> std::result::Result<(), String>,
    {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }
        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        if let Some(existing) = issues.iter().find(|issue| issue.id == expected.id) {
            if existing.prompt == expected.prompt
                && existing.handoff_digest == expected.handoff_digest
            {
                commit_pair().map_err(MannaError::MutationRejected)?;
                return Ok(existing.clone());
            }
            return Err(MannaError::MutationRejected(format!(
                "transaction recovery found a conflicting row for {}",
                expected.id
            )));
        }
        expected.validate().map_err(MannaError::MutationRejected)?;
        commit_pair().map_err(MannaError::MutationRejected)?;
        issues.push(expected.clone());
        self.write_issues_locked(&issues)?;
        Ok(expected.clone())
    }

    /// Replace one row during a recoverable pair attach/detach operation.
    pub fn recover_replace_issue(&self, expected_before: &Issue, after: &Issue) -> Result<Issue> {
        self.recover_replace_issue_with(expected_before, after, || Ok(()))
    }

    pub fn recover_replace_issue_with<F>(
        &self,
        expected_before: &Issue,
        after: &Issue,
        commit_pair: F,
    ) -> Result<Issue>
    where
        F: FnOnce() -> std::result::Result<(), String>,
    {
        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        let row = issues
            .iter_mut()
            .find(|issue| issue.id == expected_before.id)
            .ok_or_else(|| MannaError::IssueNotFound(expected_before.id.clone()))?;
        if row.updated_at != expected_before.updated_at {
            if row.prompt == after.prompt
                && row.handoff_digest == after.handoff_digest
                && row.issue_type == after.issue_type
            {
                commit_pair().map_err(MannaError::MutationRejected)?;
                return Ok(row.clone());
            }
            return Err(MannaError::MutationRejected(format!(
                "transaction recovery found concurrent changes to {}",
                expected_before.id
            )));
        }
        commit_pair().map_err(MannaError::MutationRejected)?;
        *row = after.clone();
        row.validate().map_err(MannaError::MutationRejected)?;
        self.write_issues_locked(&issues)?;
        Ok(after.clone())
    }

    /// Delete an issue under the board lock after enforcing current-session
    /// ownership. Pair-aware callers archive the handoff first through the
    /// workflow transaction journal.
    pub fn delete_issue_owned(&self, id: &str, session_id: &str) -> Result<Issue> {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }
        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        let index = issues
            .iter()
            .position(|issue| issue.id == id)
            .ok_or_else(|| MannaError::IssueNotFound(id.to_string()))?;
        issues[index]
            .require_owner(session_id)
            .map_err(MannaError::MutationRejected)?;
        let removed = issues.remove(index);
        self.write_issues_locked(&issues)?;
        Ok(removed)
    }

    /// Delete an exact transaction row idempotently.
    pub fn recover_delete_issue(&self, expected: &Issue) -> Result<()> {
        self.recover_delete_issue_with(expected, || Ok(()))
    }

    pub fn recover_delete_issue_with<F>(&self, expected: &Issue, commit_pair: F) -> Result<()>
    where
        F: FnOnce() -> std::result::Result<(), String>,
    {
        let path = self.issues_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }
        let _board_lock = self.lock_board()?;
        let mut issues = self.load_issues()?;
        let Some(index) = issues.iter().position(|issue| issue.id == expected.id) else {
            commit_pair().map_err(MannaError::MutationRejected)?;
            return Ok(());
        };
        let current = &issues[index];
        if current.updated_at != expected.updated_at
            || current.prompt != expected.prompt
            || current.handoff_digest != expected.handoff_digest
        {
            return Err(MannaError::MutationRejected(format!(
                "transaction recovery found a conflicting row for {}",
                expected.id
            )));
        }
        commit_pair().map_err(MannaError::MutationRejected)?;
        issues.remove(index);
        self.write_issues_locked(&issues)?;

        Ok(())
    }

    /// Load all session events from sessions.jsonl.
    ///
    /// Skips malformed lines with a warning to stderr.
    pub fn load_sessions(&self) -> Result<Vec<SessionEvent>> {
        let path = self.sessions_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let file = File::open(&path)?;
        let reader = BufReader::new(file);
        let mut events = Vec::new();

        for (line_num, line_result) in reader.lines().enumerate() {
            let line = match line_result {
                Ok(l) => l,
                Err(e) => {
                    eprintln!(
                        "Warning: Failed to read line {} in {}: {}",
                        line_num + 1,
                        path.display(),
                        e
                    );
                    continue;
                }
            };

            // Skip empty lines
            if line.trim().is_empty() {
                continue;
            }

            match serde_json::from_str::<SessionEvent>(&line) {
                Ok(event) => events.push(event),
                Err(e) => {
                    eprintln!(
                        "Warning: Skipping malformed line {} in {}: {}",
                        line_num + 1,
                        path.display(),
                        e
                    );
                }
            }
        }

        Ok(events)
    }

    /// Append a session event to sessions.jsonl with exclusive file lock.
    pub fn append_session(&self, event: &SessionEvent) -> Result<()> {
        let path = self.sessions_path();
        if !path.exists() {
            return Err(MannaError::NotInitialized);
        }

        let file = OpenOptions::new().append(true).open(&path)?;

        // Acquire exclusive lock
        file.lock_exclusive()
            .map_err(|e| MannaError::LockFailed(e.to_string()))?;

        // Write event as JSON line
        let mut writer = std::io::BufWriter::new(&file);
        serde_json::to_writer(&mut writer, event)?;
        writeln!(writer)?;
        writer.flush()?;

        // Lock is released when file is dropped
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Barrier};
    use std::thread;
    use tempfile::TempDir;

    fn setup_store() -> (TempDir, MannaStore) {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());
        store.init().unwrap();
        (temp_dir, store)
    }

    #[test]
    fn test_init_creates_directory_and_files() {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());

        assert!(!store.is_initialized());

        store.init().unwrap();

        assert!(store.is_initialized());
        assert!(store.manna_dir().exists());
        assert!(store.issues_path().exists());
        assert!(store.sessions_path().exists());
    }

    #[test]
    fn test_init_is_idempotent() {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());

        // First init
        store.init().unwrap();

        // Second init should not error
        store.init().unwrap();

        assert!(store.is_initialized());
    }

    #[test]
    fn test_append_and_load_issue() {
        let (_temp_dir, store) = setup_store();

        let issue = Issue::new("mn-abc123".to_string(), "Test issue".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].id, "mn-abc123");
        assert_eq!(issues[0].title, "Test issue");
    }

    #[test]
    fn test_append_multiple_issues() {
        let (_temp_dir, store) = setup_store();

        let issue1 = Issue::new("mn-111111".to_string(), "First".to_string()).unwrap();
        let issue2 = Issue::new("mn-222222".to_string(), "Second".to_string()).unwrap();
        let issue3 = Issue::new("mn-333333".to_string(), "Third".to_string()).unwrap();

        store.append_issue(&issue1).unwrap();
        store.append_issue(&issue2).unwrap();
        store.append_issue(&issue3).unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 3);
        assert_eq!(issues[0].id, "mn-111111");
        assert_eq!(issues[1].id, "mn-222222");
        assert_eq!(issues[2].id, "mn-333333");
    }

    #[test]
    fn test_update_issue() {
        let (_temp_dir, store) = setup_store();

        let issue = Issue::new("mn-update".to_string(), "Original".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        store
            .mutate_issue_metadata("mn-update", "ses-test", |issue, _| {
                issue.title = "Updated".to_string();
                Ok(())
            })
            .unwrap();

        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].title, "Updated");
    }

    #[test]
    fn test_update_nonexistent_issue_fails() {
        let (_temp_dir, store) = setup_store();

        let result = store.mutate_issue_metadata("mn-ghost", "ses-test", |_, _| Ok(()));
        assert!(matches!(result, Err(MannaError::IssueNotFound(_))));
    }

    #[test]
    fn test_skip_malformed_lines() {
        let (_temp_dir, store) = setup_store();

        // Write a valid issue
        let issue = Issue::new("mn-valid".to_string(), "Valid".to_string()).unwrap();
        store.append_issue(&issue).unwrap();

        // Manually append a malformed line
        let path = store.issues_path();
        let mut file = OpenOptions::new().append(true).open(&path).unwrap();
        writeln!(file, "{{not valid json").unwrap();

        // Append another valid issue
        let issue2 = Issue::new("mn-valid2".to_string(), "Valid2".to_string()).unwrap();
        store.append_issue(&issue2).unwrap();

        // Should load both valid issues, skipping the malformed line
        let issues = store.load_issues().unwrap();
        assert_eq!(issues.len(), 2);
        assert_eq!(issues[0].id, "mn-valid");
        assert_eq!(issues[1].id, "mn-valid2");
    }

    #[test]
    fn test_append_and_load_session() {
        let (_temp_dir, store) = setup_store();

        let event = SessionEvent::start("ses_123".to_string(), serde_json::json!({}));
        store.append_session(&event).unwrap();

        let events = store.load_sessions().unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].session_id, "ses_123");
    }

    #[test]
    fn test_concurrent_writes_dont_corrupt() {
        let temp_dir = TempDir::new().unwrap();
        let store = Arc::new(MannaStore::new(temp_dir.path()));
        store.init().unwrap();

        let mut handles = vec![];

        // Spawn 10 threads, each writing 10 issues
        for thread_id in 0..10 {
            let store_clone = Arc::clone(&store);
            let handle = thread::spawn(move || {
                for i in 0..10 {
                    let issue = Issue::new(
                        format!("mn-t{:02}i{:02}", thread_id, i),
                        format!("Thread {} Issue {}", thread_id, i),
                    )
                    .unwrap();
                    store_clone.append_issue(&issue).unwrap();
                }
            });
            handles.push(handle);
        }

        // Wait for all threads to complete
        for handle in handles {
            handle.join().unwrap();
        }

        // Verify all 100 issues are present and file is not corrupted
        let issues = store.load_issues().unwrap();
        assert_eq!(
            issues.len(),
            100,
            "Expected 100 issues, got {}",
            issues.len()
        );

        // Verify each issue is valid JSON and has correct format
        for issue in &issues {
            assert!(issue.id.starts_with("mn-"));
            assert!(!issue.title.is_empty());
        }
    }

    #[test]
    fn test_concurrent_claims_have_exactly_one_winner() {
        let temp_dir = TempDir::new().unwrap();
        let store = Arc::new(MannaStore::new(temp_dir.path()));
        store.init().unwrap();
        store
            .append_issue(&Issue::new("mn-race01".to_string(), "Race".to_string()).unwrap())
            .unwrap();
        let barrier = Arc::new(Barrier::new(12));
        let mut handles = Vec::new();
        for contender in 0..12 {
            let store = Arc::clone(&store);
            let barrier = Arc::clone(&barrier);
            handles.push(thread::spawn(move || {
                barrier.wait();
                store
                    .claim_issue("mn-race01", &format!("ses_{}", contender))
                    .is_ok()
            }));
        }
        let wins = handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .filter(|won| *won)
            .count();
        assert_eq!(wins, 1);
        let issue = store.load_issues().unwrap().pop().unwrap();
        assert_eq!(issue.status, crate::issue::IssueStatus::InProgress);
        assert!(issue.claimed_by.is_some());
    }

    #[test]
    fn test_metadata_update_rejects_non_owner() {
        let (_temp_dir, store) = setup_store();
        store
            .append_issue(&Issue::new("mn-owner1".to_string(), "Owned".to_string()).unwrap())
            .unwrap();
        store.claim_issue("mn-owner1", "ses_owner").unwrap();
        let result = store.mutate_issue_metadata("mn-owner1", "ses_intruder", |issue, _| {
            issue.title = "Hijacked".to_string();
            Ok(())
        });
        assert!(matches!(result, Err(MannaError::MutationRejected(_))));
        assert_eq!(store.load_issues().unwrap()[0].title, "Owned");
    }

    #[test]
    fn test_concurrent_mutations_lose_no_writes() {
        // The 2026-07-22 incident class: rewrite paths (update/delete) built
        // from a stale load used to revert concurrent writers at rename time.
        // Ten threads each own one issue and update it 20 times while other
        // threads do the same; every issue must end at its final value, and
        // interleaved appends must all survive the rewrites.
        let temp_dir = TempDir::new().unwrap();
        let store = Arc::new(MannaStore::new(temp_dir.path()));
        store.init().unwrap();

        for t in 0..10 {
            let issue = Issue::new(format!("mn-mut{:03}", t), format!("Mutator {}", t)).unwrap();
            store.append_issue(&issue).unwrap();
        }

        let mut handles = vec![];
        for t in 0..10 {
            let store_clone = Arc::clone(&store);
            handles.push(thread::spawn(move || {
                for round in 1..=20 {
                    let id = format!("mn-mut{:03}", t);
                    store_clone
                        .mutate_issue_metadata(&id, "ses-test", |issue, _| {
                            issue.title = format!("Mutator {} round {}", t, round);
                            Ok(())
                        })
                        .unwrap();
                }
            }));
        }
        // Appenders race the rewriters: their rows must never vanish.
        for a in 0..4 {
            let store_clone = Arc::clone(&store);
            handles.push(thread::spawn(move || {
                for i in 0..5 {
                    let issue = Issue::new(
                        format!("mn-app{}{:02}", a, i),
                        format!("Appender {} Issue {}", a, i),
                    )
                    .unwrap();
                    store_clone.append_issue(&issue).unwrap();
                }
            }));
        }
        for handle in handles {
            handle.join().unwrap();
        }

        let issues = store.load_issues().unwrap();
        assert_eq!(
            issues.len(),
            30,
            "lost rows: expected 30, got {}",
            issues.len()
        );
        for t in 0..10 {
            let issue = issues
                .iter()
                .find(|i| i.id == format!("mn-mut{:03}", t))
                .unwrap();
            assert_eq!(
                issue.title,
                format!("Mutator {} round 20", t),
                "lost update on {}",
                issue.id
            );
        }
    }

    #[test]
    fn test_not_initialized_errors() {
        let temp_dir = TempDir::new().unwrap();
        let store = MannaStore::new(temp_dir.path());

        // Don't call init()

        let result = store.load_issues();
        assert!(matches!(result, Err(MannaError::NotInitialized)));

        let issue = Issue::new("mn-test".to_string(), "Test".to_string()).unwrap();
        let result = store.append_issue(&issue);
        assert!(matches!(result, Err(MannaError::NotInitialized)));
    }

    #[test]
    fn test_empty_file_loads_empty_vec() {
        let (_temp_dir, store) = setup_store();

        let issues = store.load_issues().unwrap();
        assert!(issues.is_empty());

        let sessions = store.load_sessions().unwrap();
        assert!(sessions.is_empty());
    }

    #[test]
    fn test_session_event_types() {
        let (_temp_dir, store) = setup_store();

        // Test all event types
        let start = SessionEvent::start("ses_1".to_string(), serde_json::json!({"key": "value"}));
        let claim = SessionEvent::claim("ses_1".to_string(), "mn-123".to_string());
        let release = SessionEvent::release("ses_1".to_string(), "mn-123".to_string());
        let done = SessionEvent::done("ses_1".to_string(), "mn-123".to_string());
        let end = SessionEvent::end("ses_1".to_string(), serde_json::json!({}));

        store.append_session(&start).unwrap();
        store.append_session(&claim).unwrap();
        store.append_session(&release).unwrap();
        store.append_session(&done).unwrap();
        store.append_session(&end).unwrap();

        let events = store.load_sessions().unwrap();
        assert_eq!(events.len(), 5);
    }
}

//! Portable cross-board relation declarations for Manna.
//!
//! The tracked manifest is authority for relation declarations. The local
//! serve registry is only a resolver cache: missing boards degrade to
//! `unavailable`, and no result in this module mutates issue lifecycle state.

use std::collections::{HashMap, HashSet};
use std::fmt;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::str::FromStr;

use chrono::{DateTime, SecondsFormat, Utc};
use rand::{rngs::OsRng, RngCore};
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use sha2::{Digest, Sha256};

use crate::error::{MannaError, Result};
use crate::issue::{Issue, IssueStatus, SessionIdentity};
use crate::store::MannaStore;
use crate::workflow::{
    atomic_write, constant_time_eq, hmac_sha256, load_private_key, recovery_key_path,
    safe_create_dir_all, sync_parent,
};

pub const FEDERATION_FILE: &str = ".manna/federation.yaml";
pub const FEDERATION_ARCHIVE_DIR: &str = ".manna/federation-archive";
const FEDERATION_TRANSACTION_FILE: &str = ".manna/transactions/federation.yaml";
const FEDERATION_VERSION: u32 = 1;
const FEDERATION_ARCHIVE_VERSION: u32 = 1;
const FEDERATION_TRANSACTION_VERSION: u32 = 1;
const BOARD_ID_PREFIX: &str = "mb-";
const BOARD_ID_HEX_LEN: usize = 32;

fn rejected(message: impl Into<String>) -> MannaError {
    MannaError::MutationRejected(message.into())
}

fn valid_issue_id(value: &str) -> bool {
    let Some(hex) = value.strip_prefix("mn-") else {
        return false;
    };
    hex.len() >= 6
        && hex
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
}

pub fn valid_board_id(value: &str) -> bool {
    let Some(hex) = value.strip_prefix(BOARD_ID_PREFIX) else {
        return false;
    };
    hex.len() == BOARD_ID_HEX_LEN
        && hex
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
}

pub fn generate_board_id() -> String {
    let mut bytes = [0_u8; 16];
    OsRng.fill_bytes(&mut bytes);
    format!(
        "{}{}",
        BOARD_ID_PREFIX,
        bytes
            .iter()
            .map(|byte| format!("{:02x}", byte))
            .collect::<String>()
    )
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RelationKind {
    Counterpart,
    InformedBy,
    DependsOn,
    Supersedes,
}

impl fmt::Display for RelationKind {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let value = match self {
            RelationKind::Counterpart => "counterpart",
            RelationKind::InformedBy => "informed_by",
            RelationKind::DependsOn => "depends_on",
            RelationKind::Supersedes => "supersedes",
        };
        formatter.write_str(value)
    }
}

impl FromStr for RelationKind {
    type Err = String;

    fn from_str(value: &str) -> std::result::Result<Self, Self::Err> {
        match value {
            "counterpart" => Ok(RelationKind::Counterpart),
            "informed_by" => Ok(RelationKind::InformedBy),
            "depends_on" => Ok(RelationKind::DependsOn),
            "supersedes" => Ok(RelationKind::Supersedes),
            _ => Err(format!(
                "unsupported relation kind {}; expected counterpart, informed_by, depends_on, or supersedes",
                value
            )),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct MannaUri {
    pub board_id: String,
    pub issue_id: String,
}

impl fmt::Display for MannaUri {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "manna://{}/{}", self.board_id, self.issue_id)
    }
}

impl FromStr for MannaUri {
    type Err = String;

    fn from_str(value: &str) -> std::result::Result<Self, Self::Err> {
        let rest = value.strip_prefix("manna://").ok_or_else(|| {
            format!(
                "invalid Manna URI {}; expected manna://<board-id>/<issue-id>",
                value
            )
        })?;
        let mut parts = rest.split('/');
        let board_id = parts.next().unwrap_or_default();
        let issue_id = parts.next().unwrap_or_default();
        if parts.next().is_some() || !valid_board_id(board_id) || !valid_issue_id(issue_id) {
            return Err(format!(
                "invalid Manna URI {}; expected manna://mb-<32 lowercase hex>/mn-<6+ lowercase hex>",
                value
            ));
        }
        Ok(MannaUri {
            board_id: board_id.to_string(),
            issue_id: issue_id.to_string(),
        })
    }
}

impl Serialize for MannaUri {
    fn serialize<S>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for MannaUri {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        MannaUri::from_str(&value).map_err(serde::de::Error::custom)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Relation {
    pub from: String,
    pub kind: RelationKind,
    pub to: MannaUri,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hint: Option<String>,
}

impl Relation {
    fn key(&self) -> (&str, RelationKind, String) {
        (&self.from, self.kind, self.to.to_string())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FederationManifest {
    pub version: u32,
    pub board_id: String,
    #[serde(default)]
    pub relations: Vec<Relation>,
}

impl FederationManifest {
    fn empty(board_id: String) -> Self {
        FederationManifest {
            version: FEDERATION_VERSION,
            board_id,
            relations: Vec::new(),
        }
    }

    fn normalize(&mut self) {
        self.relations
            .sort_by(|left, right| left.key().cmp(&right.key()));
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct FederationArchive {
    version: u32,
    forked_at: DateTime<Utc>,
    reason: String,
    manifest: FederationManifest,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum FederationAction {
    Init,
    Relate,
    Unrelate,
    Fork,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct FederationTransaction {
    version: u32,
    action: FederationAction,
    before: Option<String>,
    after: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    archive_path: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    archive_before: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    archive_after: Option<String>,
    integrity: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct FederationMutation {
    pub changed: bool,
    pub path: String,
    pub federation: FederationManifest,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub archive: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FederationStatus {
    pub enabled: bool,
    pub path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub board_id: Option<String>,
    pub relations: usize,
    pub archives: usize,
}

#[derive(Debug, Clone)]
pub struct FederationFinding {
    pub issue_id: String,
    pub rule: &'static str,
    pub detail: String,
}

fn federation_path(base: &Path) -> PathBuf {
    base.join(FEDERATION_FILE)
}

fn transaction_path(base: &Path) -> PathBuf {
    base.join(FEDERATION_TRANSACTION_FILE)
}

fn ensure_regular_or_missing(path: &Path, label: &str) -> std::result::Result<(), String> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.is_file() => Ok(()),
        Ok(_) => Err(format!(
            "{} is not a regular file: {}",
            label,
            path.display()
        )),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("failed to inspect {}: {}", path.display(), error)),
    }
}

fn read_optional_text(path: &Path, label: &str) -> std::result::Result<Option<String>, String> {
    ensure_regular_or_missing(path, label)?;
    match fs::read_to_string(path) {
        Ok(text) => Ok(Some(text)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!(
            "failed to read {} {}: {}",
            label,
            path.display(),
            error
        )),
    }
}

fn canonical_manifest(manifest: &FederationManifest) -> std::result::Result<String, String> {
    let mut normalized = manifest.clone();
    normalized.normalize();
    serde_yaml::to_string(&normalized)
        .map_err(|error| format!("failed to serialize federation manifest: {}", error))
}

fn canonical_archive(archive: &FederationArchive) -> std::result::Result<String, String> {
    let mut normalized = archive.clone();
    normalized.manifest.normalize();
    serde_yaml::to_string(&normalized)
        .map_err(|error| format!("failed to serialize federation archive: {}", error))
}

fn manifest_problems(
    manifest: &FederationManifest,
    issues: Option<&[Issue]>,
) -> Vec<FederationFinding> {
    let mut findings = Vec::new();
    if manifest.version != FEDERATION_VERSION {
        findings.push(FederationFinding {
            issue_id: "board".to_string(),
            rule: "federation_shape",
            detail: format!(
                "unsupported federation version {}; expected {}",
                manifest.version, FEDERATION_VERSION
            ),
        });
    }
    if !valid_board_id(&manifest.board_id) {
        findings.push(FederationFinding {
            issue_id: "board".to_string(),
            rule: "federation_shape",
            detail: format!("invalid federation board_id {}", manifest.board_id),
        });
    }

    let local_ids: HashSet<&str> = issues
        .unwrap_or_default()
        .iter()
        .map(|issue| issue.id.as_str())
        .collect();
    let mut seen: HashSet<(String, RelationKind, String)> = HashSet::new();
    let mut previous: Option<(String, RelationKind, String)> = None;
    for relation in &manifest.relations {
        let key = (
            relation.from.clone(),
            relation.kind,
            relation.to.to_string(),
        );
        if !valid_issue_id(&relation.from) {
            findings.push(FederationFinding {
                issue_id: relation.from.clone(),
                rule: "federation_shape",
                detail: format!("invalid local relation source {}", relation.from),
            });
        }
        if issues.is_some() && !local_ids.contains(relation.from.as_str()) {
            findings.push(FederationFinding {
                issue_id: relation.from.clone(),
                rule: "relation_source",
                detail: format!(
                    "relation source {} does not exist on this board",
                    relation.from
                ),
            });
        }
        if relation.to.board_id == manifest.board_id {
            findings.push(FederationFinding {
                issue_id: relation.from.clone(),
                rule: "relation_local_target",
                detail: format!(
                    "relation target {} uses this board_id; same-board edges belong in local Manna grammar",
                    relation.to
                ),
            });
        }
        if relation
            .hint
            .as_deref()
            .is_some_and(|hint| hint.trim().is_empty() || hint.len() > 500)
        {
            findings.push(FederationFinding {
                issue_id: relation.from.clone(),
                rule: "federation_shape",
                detail: "relation hint must be 1-500 characters when present".to_string(),
            });
        }
        if !seen.insert(key.clone()) {
            findings.push(FederationFinding {
                issue_id: relation.from.clone(),
                rule: "relation_duplicate",
                detail: format!(
                    "duplicate relation ({}, {}, {})",
                    relation.from, relation.kind, relation.to
                ),
            });
        }
        if previous.as_ref().is_some_and(|prior| prior > &key) {
            findings.push(FederationFinding {
                issue_id: relation.from.clone(),
                rule: "federation_shape",
                detail: "relations are not in deterministic (from, kind, to) order".to_string(),
            });
        }
        previous = Some(key);
    }
    findings
}

fn parse_manifest_text(
    text: &str,
    issues: Option<&[Issue]>,
    require_canonical: bool,
) -> std::result::Result<FederationManifest, String> {
    let manifest: FederationManifest = serde_yaml::from_str(text)
        .map_err(|error| format!("invalid federation manifest: {}", error))?;
    let problems = manifest_problems(&manifest, issues);
    if let Some(problem) = problems.first() {
        return Err(problem.detail.clone());
    }
    if require_canonical && canonical_manifest(&manifest)? != text {
        return Err(
            "federation manifest is not in canonical deterministic serialization".to_string(),
        );
    }
    Ok(manifest)
}

pub fn load_manifest(
    base: &Path,
    issues: Option<&[Issue]>,
) -> std::result::Result<Option<FederationManifest>, String> {
    let Some(text) = read_optional_text(&federation_path(base), "federation manifest")? else {
        return Ok(None);
    };
    parse_manifest_text(&text, issues, true).map(Some)
}

fn git_tracked(base: &Path, relative: &Path) -> std::result::Result<bool, String> {
    let relative = relative
        .to_str()
        .ok_or_else(|| format!("non-UTF-8 federation path {}", relative.display()))?;
    let output = Command::new("git")
        .current_dir(base)
        .args(["ls-files", "--error-unmatch", "--", relative])
        .output()
        .map_err(|error| format!("failed to inspect Git tracking for {}: {}", relative, error))?;
    Ok(output.status.success())
}

fn archive_paths(base: &Path) -> std::result::Result<Vec<PathBuf>, String> {
    let directory = base.join(FEDERATION_ARCHIVE_DIR);
    match fs::symlink_metadata(&directory) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Ok(metadata) if metadata.file_type().is_symlink() => {
            return Err(format!(
                "refusing symlinked federation archive directory {}",
                directory.display()
            ))
        }
        Ok(metadata) if metadata.is_dir() => {}
        Ok(_) => {
            return Err(format!(
                "federation archive path is not a directory: {}",
                directory.display()
            ))
        }
        Err(error) => {
            return Err(format!(
                "failed to inspect federation archive directory {}: {}",
                directory.display(),
                error
            ))
        }
    }
    let mut paths = Vec::new();
    for entry in fs::read_dir(&directory)
        .map_err(|error| format!("failed to read {}: {}", directory.display(), error))?
    {
        let entry = entry.map_err(|error| format!("failed to read archive entry: {}", error))?;
        let path = entry.path();
        ensure_regular_or_missing(&path, "federation archive")?;
        if path.extension().and_then(|value| value.to_str()) != Some("yaml") {
            return Err(format!(
                "unexpected durable file in federation archive: {}",
                path.display()
            ));
        }
        paths.push(path);
    }
    paths.sort();
    Ok(paths)
}

pub fn lint(base: &Path, issues: &[Issue]) -> Vec<FederationFinding> {
    let path = federation_path(base);
    let manifest_exists = fs::symlink_metadata(&path).is_ok();
    let mut findings = Vec::new();
    match read_optional_text(&path, "federation manifest") {
        Ok(Some(text)) => match serde_yaml::from_str::<FederationManifest>(&text) {
            Ok(manifest) => {
                findings.extend(manifest_problems(&manifest, Some(issues)));
                match canonical_manifest(&manifest) {
                    Ok(canonical) if canonical != text => findings.push(FederationFinding {
                        issue_id: "board".to_string(),
                        rule: "federation_shape",
                        detail:
                            "federation manifest is not in canonical deterministic serialization"
                                .to_string(),
                    }),
                    Err(error) => findings.push(FederationFinding {
                        issue_id: "board".to_string(),
                        rule: "federation_shape",
                        detail: error,
                    }),
                    _ => {}
                }
                match git_tracked(base, Path::new(FEDERATION_FILE)) {
                    Ok(true) => {}
                    Ok(false) => findings.push(FederationFinding {
                        issue_id: "board".to_string(),
                        rule: "federation_tracking",
                        detail: format!(
                            "durable federation file {} is not tracked by Git (git-tracked: no)",
                            FEDERATION_FILE
                        ),
                    }),
                    Err(error) => findings.push(FederationFinding {
                        issue_id: "board".to_string(),
                        rule: "federation_tracking",
                        detail: error,
                    }),
                }
            }
            Err(error) => findings.push(FederationFinding {
                issue_id: "board".to_string(),
                rule: "federation_shape",
                detail: format!("invalid federation manifest: {}", error),
            }),
        },
        Ok(None) => findings.push(FederationFinding {
            issue_id: "board".to_string(),
            rule: "federation_identity",
            detail: format!(
                "durable federation identity {} is missing; run `agent-do manna init`",
                FEDERATION_FILE
            ),
        }),
        Err(error) => findings.push(FederationFinding {
            issue_id: "board".to_string(),
            rule: "federation_shape",
            detail: error,
        }),
    }

    match archive_paths(base) {
        Ok(paths) => {
            if !paths.is_empty() && !manifest_exists {
                findings.push(FederationFinding {
                    issue_id: "board".to_string(),
                    rule: "federation_shape",
                    detail:
                        "federation archive exists but the active federation manifest is missing"
                            .to_string(),
                });
            }
            for archive_path in paths {
                let relative = archive_path
                    .strip_prefix(base)
                    .unwrap_or(&archive_path)
                    .to_path_buf();
                match fs::read_to_string(&archive_path) {
                    Ok(text) => match serde_yaml::from_str::<FederationArchive>(&text) {
                        Ok(archive) => {
                            if archive.version != FEDERATION_ARCHIVE_VERSION {
                                findings.push(FederationFinding {
                                    issue_id: "board".to_string(),
                                    rule: "federation_shape",
                                    detail: format!(
                                        "unsupported federation archive version in {}",
                                        relative.display()
                                    ),
                                });
                            }
                            if archive.reason.trim().is_empty() || archive.reason.len() > 1000 {
                                findings.push(FederationFinding {
                                    issue_id: "board".to_string(),
                                    rule: "federation_shape",
                                    detail: format!(
                                        "federation archive {} has an invalid fork reason",
                                        relative.display()
                                    ),
                                });
                            }
                            // An archive is immutable lineage from a prior board identity.
                            // Its source rows may be deleted later, so only the active
                            // manifest is checked against today's issue membership.
                            findings.extend(manifest_problems(&archive.manifest, None));
                            if canonical_archive(&archive).ok().as_deref() != Some(text.as_str()) {
                                findings.push(FederationFinding {
                                    issue_id: "board".to_string(),
                                    rule: "federation_shape",
                                    detail: format!(
                                        "federation archive {} is not canonical",
                                        relative.display()
                                    ),
                                });
                            }
                        }
                        Err(error) => findings.push(FederationFinding {
                            issue_id: "board".to_string(),
                            rule: "federation_shape",
                            detail: format!(
                                "invalid federation archive {}: {}",
                                relative.display(),
                                error
                            ),
                        }),
                    },
                    Err(error) => findings.push(FederationFinding {
                        issue_id: "board".to_string(),
                        rule: "federation_shape",
                        detail: format!("failed to read {}: {}", relative.display(), error),
                    }),
                }
                match git_tracked(base, &relative) {
                    Ok(true) => {}
                    Ok(false) => findings.push(FederationFinding {
                        issue_id: "board".to_string(),
                        rule: "federation_tracking",
                        detail: format!(
                            "durable federation archive {} is not tracked by Git (git-tracked: no)",
                            relative.display()
                        ),
                    }),
                    Err(error) => findings.push(FederationFinding {
                        issue_id: "board".to_string(),
                        rule: "federation_tracking",
                        detail: error,
                    }),
                }
            }
        }
        Err(error) => findings.push(FederationFinding {
            issue_id: "board".to_string(),
            rule: "federation_shape",
            detail: error,
        }),
    }
    findings
}

fn transaction_material(
    base: &Path,
    transaction: &FederationTransaction,
) -> std::result::Result<Vec<u8>, String> {
    let mut unsigned = transaction.clone();
    unsigned.integrity.clear();
    let project = base.canonicalize().map_err(|error| {
        format!(
            "failed to resolve project root {}: {}",
            base.display(),
            error
        )
    })?;
    let payload = serde_json::to_vec(&unsigned)
        .map_err(|error| format!("failed to serialize federation transaction: {}", error))?;
    let mut material = b"agent-do/manna/federation/v1\0".to_vec();
    material.extend_from_slice(project.to_string_lossy().as_bytes());
    material.push(0);
    material.extend_from_slice(&payload);
    Ok(material)
}

fn transaction_signature(
    base: &Path,
    key: &[u8],
    transaction: &FederationTransaction,
) -> std::result::Result<String, String> {
    let digest = hmac_sha256(key, &transaction_material(base, transaction)?);
    Ok(format!(
        "hmac-sha256:{}",
        digest
            .iter()
            .map(|byte| format!("{:02x}", byte))
            .collect::<String>()
    ))
}

fn validate_archive_relative(value: &str) -> std::result::Result<PathBuf, String> {
    let path = Path::new(value);
    if path.is_absolute()
        || !path.starts_with(FEDERATION_ARCHIVE_DIR)
        || path.components().any(|component| {
            !matches!(component, Component::Normal(_))
                || matches!(
                    component,
                    Component::ParentDir | Component::RootDir | Component::Prefix(_)
                )
        })
    {
        return Err(format!("unsafe federation archive path {}", value));
    }
    Ok(path.to_path_buf())
}

fn write_transaction(
    base: &Path,
    mut transaction: FederationTransaction,
) -> std::result::Result<FederationTransaction, String> {
    safe_create_dir_all(base, Path::new(".manna/transactions"))?;
    let key_path = recovery_key_path(base)?;
    let key = load_private_key(&key_path, true, "Manna recovery key")?;
    transaction.integrity = transaction_signature(base, &key, &transaction)?;
    let text = serde_yaml::to_string(&transaction)
        .map_err(|error| format!("failed to serialize federation journal: {}", error))?;
    atomic_write(&transaction_path(base), text.as_bytes(), false)?;
    Ok(transaction)
}

fn read_transaction(base: &Path) -> std::result::Result<Option<FederationTransaction>, String> {
    let path = transaction_path(base);
    let Some(text) = read_optional_text(&path, "federation transaction")? else {
        return Ok(None);
    };
    let transaction: FederationTransaction = serde_yaml::from_str(&text)
        .map_err(|error| format!("invalid federation journal {}: {}", path.display(), error))?;
    if transaction.version != FEDERATION_TRANSACTION_VERSION {
        return Err(format!(
            "unsupported federation transaction version {}",
            transaction.version
        ));
    }
    if transaction.archive_path.is_some() != transaction.archive_after.is_some() {
        return Err("federation journal archive fields are incomplete".to_string());
    }
    if let Some(path) = transaction.archive_path.as_deref() {
        validate_archive_relative(path)?;
    }
    let key_path = recovery_key_path(base)?;
    let key = load_private_key(&key_path, false, "Manna recovery key")?;
    let expected = transaction_signature(base, &key, &transaction)?;
    if !constant_time_eq(expected.as_bytes(), transaction.integrity.as_bytes()) {
        return Err("federation transaction failed HMAC authentication".to_string());
    }
    Ok(Some(transaction))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CrashPoint {
    Journal,
    Archive,
    Manifest,
}

fn install_transaction(
    base: &Path,
    transaction: &FederationTransaction,
    crash: Option<CrashPoint>,
) -> std::result::Result<(), String> {
    if crash == Some(CrashPoint::Journal) {
        return Err("injected crash after federation journal".to_string());
    }

    let manifest_path = federation_path(base);
    let current_manifest = read_optional_text(&manifest_path, "federation manifest")?;
    let manifest_before = current_manifest == transaction.before;
    let manifest_after = current_manifest.as_deref() == Some(transaction.after.as_str());
    if !manifest_before && !manifest_after {
        return Err("federation transaction found a conflicting manifest state".to_string());
    }

    if let Some(relative) = transaction.archive_path.as_deref() {
        let relative = validate_archive_relative(relative)?;
        safe_create_dir_all(base, Path::new(FEDERATION_ARCHIVE_DIR))?;
        let path = base.join(relative);
        let current = read_optional_text(&path, "federation archive")?;
        let archive_before = current == transaction.archive_before;
        let archive_after = current == transaction.archive_after;
        if !archive_before && !archive_after {
            return Err("federation transaction found a conflicting archive state".to_string());
        }
        if archive_before {
            let after = transaction
                .archive_after
                .as_deref()
                .ok_or_else(|| "federation transaction archive payload is missing".to_string())?;
            atomic_write(
                &path,
                after.as_bytes(),
                transaction.archive_before.is_some(),
            )?;
        }
    }
    if crash == Some(CrashPoint::Archive) {
        return Err("injected crash after federation archive".to_string());
    }

    if manifest_before {
        atomic_write(
            &manifest_path,
            transaction.after.as_bytes(),
            transaction.before.is_some(),
        )?;
    }
    if crash == Some(CrashPoint::Manifest) {
        return Err("injected crash after federation manifest".to_string());
    }
    Ok(())
}

fn remove_transaction(base: &Path) -> std::result::Result<(), String> {
    let path = transaction_path(base);
    match fs::remove_file(&path) {
        Ok(()) => sync_parent(&path),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("failed to remove {}: {}", path.display(), error)),
    }
}

fn recover_transaction_locked(base: &Path) -> std::result::Result<bool, String> {
    let Some(transaction) = read_transaction(base)? else {
        return Ok(false);
    };
    install_transaction(base, &transaction, None)?;
    remove_transaction(base)?;
    Ok(true)
}

pub fn recover_transaction(base: &Path, store: &MannaStore) -> Result<bool> {
    store.with_board_lock(|| recover_transaction_locked(base).map_err(rejected))
}

fn run_transaction_locked(
    base: &Path,
    transaction: FederationTransaction,
    crash: Option<CrashPoint>,
) -> std::result::Result<(), String> {
    recover_transaction_locked(base)?;
    let transaction = write_transaction(base, transaction)?;
    install_transaction(base, &transaction, crash)?;
    remove_transaction(base)
}

fn transaction(
    action: FederationAction,
    before: Option<String>,
    after: String,
) -> FederationTransaction {
    FederationTransaction {
        version: FEDERATION_TRANSACTION_VERSION,
        action,
        before,
        after,
        archive_path: None,
        archive_before: None,
        archive_after: None,
        integrity: String::new(),
    }
}

pub fn initialize(base: &Path, store: &MannaStore) -> Result<FederationMutation> {
    store.with_board_lock(|| {
        recover_transaction_locked(base).map_err(rejected)?;
        let issues = store.load_issues_strict()?;
        if let Some(manifest) = load_manifest(base, Some(&issues)).map_err(rejected)? {
            return Ok(FederationMutation {
                changed: false,
                path: FEDERATION_FILE.to_string(),
                federation: manifest,
                archive: None,
            });
        }
        if !archive_paths(base).map_err(rejected)?.is_empty() {
            return Err(rejected(
                "federation archive exists but the active manifest is missing; restore .manna/federation.yaml from Git instead of assigning a new identity",
            ));
        }
        let manifest = FederationManifest::empty(generate_board_id());
        let after = canonical_manifest(&manifest).map_err(rejected)?;
        run_transaction_locked(base, transaction(FederationAction::Init, None, after), None)
            .map_err(rejected)?;
        Ok(FederationMutation {
            changed: true,
            path: FEDERATION_FILE.to_string(),
            federation: manifest,
            archive: None,
        })
    })
}

fn require_relation_authority(issue: &Issue, session: &SessionIdentity) -> Result<()> {
    if matches!(issue.status, IssueStatus::InProgress | IssueStatus::Blocked) {
        issue.require_owner(session).map_err(rejected)?;
    }
    Ok(())
}

pub fn relate(
    base: &Path,
    store: &MannaStore,
    session: &SessionIdentity,
    relation: Relation,
) -> Result<FederationMutation> {
    store.with_board_lock(|| {
        recover_transaction_locked(base).map_err(rejected)?;
        let issues = store.load_issues_strict()?;
        let source = issues
            .iter()
            .find(|issue| issue.id == relation.from)
            .ok_or_else(|| rejected(format!("relation source {} not found", relation.from)))?;
        require_relation_authority(source, session)?;
        let mut manifest = load_manifest(base, Some(&issues))
            .map_err(rejected)?
            .ok_or_else(|| {
                rejected("federation is not initialized; run `agent-do manna federation init`")
            })?;
        let before = canonical_manifest(&manifest).map_err(rejected)?;
        if manifest.relations.iter().any(|existing| {
            existing.from == relation.from
                && existing.kind == relation.kind
                && existing.to == relation.to
        }) {
            return Err(rejected(format!(
                "relation ({}, {}, {}) already exists",
                relation.from, relation.kind, relation.to
            )));
        }
        manifest.relations.push(relation);
        manifest.normalize();
        let problems = manifest_problems(&manifest, Some(&issues));
        if let Some(problem) = problems.first() {
            return Err(rejected(problem.detail.clone()));
        }
        let after = canonical_manifest(&manifest).map_err(rejected)?;
        run_transaction_locked(
            base,
            transaction(FederationAction::Relate, Some(before), after),
            None,
        )
        .map_err(rejected)?;
        Ok(FederationMutation {
            changed: true,
            path: FEDERATION_FILE.to_string(),
            federation: manifest,
            archive: None,
        })
    })
}

pub fn unrelate(
    base: &Path,
    store: &MannaStore,
    session: &SessionIdentity,
    from: &str,
    kind: RelationKind,
    to: &MannaUri,
) -> Result<FederationMutation> {
    store.with_board_lock(|| {
        recover_transaction_locked(base).map_err(rejected)?;
        let issues = store.load_issues_strict()?;
        let source = issues
            .iter()
            .find(|issue| issue.id == from)
            .ok_or_else(|| rejected(format!("relation source {} not found", from)))?;
        require_relation_authority(source, session)?;
        let mut manifest = load_manifest(base, Some(&issues))
            .map_err(rejected)?
            .ok_or_else(|| {
                rejected("federation is not initialized; run `agent-do manna federation init`")
            })?;
        let before = canonical_manifest(&manifest).map_err(rejected)?;
        let original_len = manifest.relations.len();
        manifest.relations.retain(|relation| {
            !(relation.from == from && relation.kind == kind && &relation.to == to)
        });
        if manifest.relations.len() == original_len {
            return Err(rejected(format!(
                "relation ({}, {}, {}) does not exist",
                from, kind, to
            )));
        }
        manifest.normalize();
        let after = canonical_manifest(&manifest).map_err(rejected)?;
        run_transaction_locked(
            base,
            transaction(FederationAction::Unrelate, Some(before), after),
            None,
        )
        .map_err(rejected)?;
        Ok(FederationMutation {
            changed: true,
            path: FEDERATION_FILE.to_string(),
            federation: manifest,
            archive: None,
        })
    })
}

pub fn fork(
    base: &Path,
    store: &MannaStore,
    session: &SessionIdentity,
    reason: &str,
) -> Result<FederationMutation> {
    let reason = reason.trim();
    if reason.is_empty() || reason.len() > 1000 {
        return Err(rejected("federation fork reason must be 1-1000 characters"));
    }
    store.with_board_lock(|| {
        recover_transaction_locked(base).map_err(rejected)?;
        let issues = store.load_issues_strict()?;
        for issue in issues
            .iter()
            .filter(|issue| issue.status != IssueStatus::Done && issue.claimed_by.is_some())
        {
            issue.require_owner(session).map_err(rejected)?;
        }
        let old = load_manifest(base, Some(&issues))
            .map_err(rejected)?
            .ok_or_else(|| {
                rejected("federation is not initialized; run `agent-do manna federation init`")
            })?;
        let before = canonical_manifest(&old).map_err(rejected)?;
        let forked_at = Utc::now();
        let archive = FederationArchive {
            version: FEDERATION_ARCHIVE_VERSION,
            forked_at,
            reason: reason.to_string(),
            manifest: old,
        };
        let archive_after = canonical_archive(&archive).map_err(rejected)?;
        let archive_name = format!(
            "{}-{}.yaml",
            forked_at
                .to_rfc3339_opts(SecondsFormat::Nanos, true)
                .replace([':', '-'], ""),
            archive.manifest.board_id
        );
        let archive_relative = Path::new(FEDERATION_ARCHIVE_DIR).join(archive_name);
        let new_manifest = FederationManifest::empty(generate_board_id());
        let after = canonical_manifest(&new_manifest).map_err(rejected)?;
        let mut tx = transaction(FederationAction::Fork, Some(before), after);
        tx.archive_path = Some(archive_relative.display().to_string());
        tx.archive_before = None;
        tx.archive_after = Some(archive_after);
        run_transaction_locked(base, tx, None).map_err(rejected)?;
        Ok(FederationMutation {
            changed: true,
            path: FEDERATION_FILE.to_string(),
            federation: new_manifest,
            archive: Some(archive_relative.display().to_string()),
        })
    })
}

pub fn status(base: &Path, issues: &[Issue]) -> std::result::Result<FederationStatus, String> {
    let manifest = load_manifest(base, Some(issues))?;
    let archives = archive_paths(base)?.len();
    Ok(FederationStatus {
        enabled: manifest.is_some(),
        path: FEDERATION_FILE.to_string(),
        board_id: manifest.as_ref().map(|value| value.board_id.clone()),
        relations: manifest
            .as_ref()
            .map(|value| value.relations.len())
            .unwrap_or_default(),
        archives,
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ResolutionState {
    Resolved,
    Unavailable,
    Missing,
    Ambiguous,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Reciprocity {
    Confirmed,
    OneWay,
    Unavailable,
    Ambiguous,
}

#[derive(Debug, Clone, Serialize)]
pub struct ResolvedIssue {
    pub id: String,
    pub title: String,
    pub status: IssueStatus,
    pub row_sha256: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Resolution {
    pub state: ResolutionState,
    pub replicas: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub issue: Option<ResolvedIssue>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RelationReport {
    pub from: String,
    pub kind: RelationKind,
    pub to: MannaUri,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hint: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resolution: Option<Resolution>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reciprocity: Option<Reciprocity>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RelationsData {
    pub board_id: String,
    pub resolved: bool,
    pub relations: Vec<RelationReport>,
}

impl RelationsData {
    pub fn check_failed(&self) -> bool {
        self.relations.iter().any(|relation| {
            relation.resolution.as_ref().is_some_and(|resolution| {
                matches!(
                    resolution.state,
                    ResolutionState::Missing | ResolutionState::Ambiguous
                )
            })
        })
    }
}

#[derive(Debug, Deserialize)]
struct RegistryFile {
    #[serde(default)]
    boards: HashMap<String, RegistryEntry>,
}

#[derive(Debug, Deserialize)]
struct RegistryEntry {
    path: String,
    #[serde(default)]
    board_id: Option<String>,
}

fn resolver_registry_path() -> Option<PathBuf> {
    std::env::var_os("AGENT_DO_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".agent-do")))
        .map(|home| home.join("manna/serve/boards.json"))
}

fn load_registry() -> RegistryFile {
    let Some(path) = resolver_registry_path() else {
        return RegistryFile {
            boards: HashMap::new(),
        };
    };
    fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str::<RegistryFile>(&text).ok())
        .unwrap_or(RegistryFile {
            boards: HashMap::new(),
        })
}

#[derive(Debug)]
struct Replica {
    manifest: FederationManifest,
    target_row: std::result::Result<Option<(String, Issue)>, String>,
}

fn read_target_row(
    root: &Path,
    target: &str,
) -> std::result::Result<Option<(String, Issue)>, String> {
    let path = root.join(".manna/issues.jsonl");
    ensure_regular_or_missing(&path, "target board issues")?;
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read target board {}: {}", path.display(), error))?;
    let mut found = None;
    for line in text.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let value: serde_json::Value = serde_json::from_str(line)
            .map_err(|error| format!("malformed target board row: {}", error))?;
        if value.get("id").and_then(serde_json::Value::as_str) != Some(target) {
            continue;
        }
        if found.is_some() {
            return Err(format!("target board contains duplicate issue {}", target));
        }
        let issue: Issue = serde_json::from_value(value)
            .map_err(|error| format!("invalid target issue {}: {}", target, error))?;
        found = Some((line.to_string(), issue));
    }
    Ok(found)
}

fn validate_replica_root(root: &Path) -> std::result::Result<bool, String> {
    match fs::symlink_metadata(root) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            return Err(format!(
                "registered board root is a symlink: {}",
                root.display()
            ))
        }
        Ok(metadata) if metadata.is_dir() => {}
        Ok(_) => {
            return Err(format!(
                "registered board root is not a directory: {}",
                root.display()
            ))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(error) => {
            return Err(format!(
                "failed to inspect registered board root {}: {}",
                root.display(),
                error
            ))
        }
    }

    let manna = root.join(".manna");
    match fs::symlink_metadata(&manna) {
        Ok(metadata) if metadata.file_type().is_symlink() => Err(format!(
            "registered board .manna directory is a symlink: {}",
            manna.display()
        )),
        Ok(metadata) if metadata.is_dir() => Ok(true),
        Ok(_) => Err(format!(
            "registered board .manna path is not a directory: {}",
            manna.display()
        )),
        Err(error) => Err(format!(
            "failed to inspect registered board .manna directory {}: {}",
            manna.display(),
            error
        )),
    }
}

fn target_replicas(
    target: &MannaUri,
    registry: &RegistryFile,
) -> (Vec<Replica>, usize, Vec<String>) {
    let mut replicas = Vec::new();
    let mut candidate_count = 0;
    let mut errors = Vec::new();
    for entry in registry.boards.values() {
        let root = PathBuf::from(&entry.path);
        match validate_replica_root(&root) {
            Ok(true) => {}
            Ok(false) => continue,
            Err(error) => {
                if entry.board_id.as_deref() == Some(target.board_id.as_str()) {
                    candidate_count += 1;
                    errors.push(error);
                }
                continue;
            }
        }
        let live = match load_manifest(&root, None) {
            Ok(value) => value,
            Err(error) => {
                if entry.board_id.as_deref() == Some(target.board_id.as_str()) {
                    candidate_count += 1;
                    errors.push(format!("{}: {}", root.display(), error));
                }
                continue;
            }
        };
        let Some(manifest) = live else {
            if entry.board_id.as_deref() == Some(target.board_id.as_str()) {
                candidate_count += 1;
                errors.push(format!("{}: federation manifest missing", root.display()));
            }
            continue;
        };
        if entry
            .board_id
            .as_deref()
            .is_some_and(|cached| cached == target.board_id && cached != manifest.board_id)
        {
            candidate_count += 1;
            errors.push(format!(
                "{}: cached federation identity disagrees with live manifest",
                root.display()
            ));
            continue;
        }
        if manifest.board_id != target.board_id {
            continue;
        }
        candidate_count += 1;
        replicas.push(Replica {
            manifest,
            target_row: read_target_row(&root, &target.issue_id),
        });
    }
    (replicas, candidate_count, errors)
}

fn resolve_target(
    target: &MannaUri,
    registry: &RegistryFile,
) -> (Resolution, Vec<Replica>, Vec<String>) {
    let (replicas, count, mut errors) = target_replicas(target, registry);
    if count == 0 {
        return (
            Resolution {
                state: ResolutionState::Unavailable,
                replicas: 0,
                issue: None,
                detail: Some("counterpart board unavailable on this machine".to_string()),
            },
            replicas,
            errors,
        );
    }
    if !errors.is_empty() || replicas.len() != count {
        return (
            Resolution {
                state: ResolutionState::Ambiguous,
                replicas: count,
                issue: None,
                detail: Some(errors.join("; ")),
            },
            replicas,
            errors,
        );
    }

    let mut row_texts = Vec::new();
    let mut missing = 0;
    for replica in &replicas {
        match &replica.target_row {
            Ok(Some((text, issue))) => row_texts.push((text.clone(), issue.clone())),
            Ok(None) => missing += 1,
            Err(error) => errors.push(error.clone()),
        }
    }
    if !errors.is_empty() || (missing > 0 && !row_texts.is_empty()) {
        return (
            Resolution {
                state: ResolutionState::Ambiguous,
                replicas: count,
                issue: None,
                detail: Some(if errors.is_empty() {
                    "registered replicas disagree on target presence".to_string()
                } else {
                    errors.join("; ")
                }),
            },
            replicas,
            errors,
        );
    }
    if row_texts.is_empty() {
        return (
            Resolution {
                state: ResolutionState::Missing,
                replicas: count,
                issue: None,
                detail: Some(format!("registered board has no issue {}", target.issue_id)),
            },
            replicas,
            errors,
        );
    }
    let first = &row_texts[0].0;
    if row_texts.iter().any(|(text, _)| text != first) {
        return (
            Resolution {
                state: ResolutionState::Ambiguous,
                replicas: count,
                issue: None,
                detail: Some("registered replicas disagree on exact target row bytes".to_string()),
            },
            replicas,
            errors,
        );
    }
    let issue = &row_texts[0].1;
    let digest = Sha256::digest(first.as_bytes());
    (
        Resolution {
            state: ResolutionState::Resolved,
            replicas: count,
            issue: Some(ResolvedIssue {
                id: issue.id.clone(),
                title: issue.title.clone(),
                status: issue.status.clone(),
                row_sha256: format!("sha256:{:x}", digest),
            }),
            detail: None,
        },
        replicas,
        errors,
    )
}

fn reciprocity(
    source_board_id: &str,
    relation: &Relation,
    resolution: &Resolution,
    replicas: &[Replica],
) -> Reciprocity {
    match resolution.state {
        ResolutionState::Unavailable => return Reciprocity::Unavailable,
        ResolutionState::Ambiguous => return Reciprocity::Ambiguous,
        ResolutionState::Missing => return Reciprocity::OneWay,
        ResolutionState::Resolved => {}
    }
    let source = MannaUri {
        board_id: source_board_id.to_string(),
        issue_id: relation.from.clone(),
    };
    let reciprocal: Vec<bool> = replicas
        .iter()
        .map(|replica| {
            replica.manifest.relations.iter().any(|candidate| {
                candidate.from == relation.to.issue_id
                    && candidate.kind == RelationKind::Counterpart
                    && candidate.to == source
            })
        })
        .collect();
    if reciprocal.iter().all(|value| *value) {
        Reciprocity::Confirmed
    } else if reciprocal.iter().all(|value| !*value) {
        Reciprocity::OneWay
    } else {
        Reciprocity::Ambiguous
    }
}

fn relations_with_registry(
    base: &Path,
    issues: &[Issue],
    local_id: Option<&str>,
    resolve: bool,
    registry: &RegistryFile,
) -> std::result::Result<RelationsData, String> {
    let manifest = load_manifest(base, Some(issues))?.ok_or_else(|| {
        "federation is not initialized; run `agent-do manna federation init`".to_string()
    })?;
    if let Some(local_id) = local_id {
        if !issues.iter().any(|issue| issue.id == local_id) {
            return Err(format!("Issue {} not found", local_id));
        }
    }
    let mut reports = Vec::new();
    for relation in manifest
        .relations
        .iter()
        .filter(|relation| local_id.is_none_or(|id| relation.from == id))
    {
        let (resolution, replicas, _) = if resolve {
            let (resolution, replicas, errors) = resolve_target(&relation.to, registry);
            (Some(resolution), replicas, errors)
        } else {
            (None, Vec::new(), Vec::new())
        };
        let reciprocal = if resolve && relation.kind == RelationKind::Counterpart {
            resolution
                .as_ref()
                .map(|value| reciprocity(&manifest.board_id, relation, value, &replicas))
        } else {
            None
        };
        reports.push(RelationReport {
            from: relation.from.clone(),
            kind: relation.kind,
            to: relation.to.clone(),
            hint: relation.hint.clone(),
            resolution,
            reciprocity: reciprocal,
        });
    }
    Ok(RelationsData {
        board_id: manifest.board_id,
        resolved: resolve,
        relations: reports,
    })
}

pub fn relations(
    base: &Path,
    issues: &[Issue],
    local_id: Option<&str>,
    resolve: bool,
) -> std::result::Result<RelationsData, String> {
    let registry = if resolve {
        load_registry()
    } else {
        RegistryFile {
            boards: HashMap::new(),
        }
    };
    relations_with_registry(base, issues, local_id, resolve, &registry)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    const SOURCE_BOARD_ID: &str = "mb-11111111111111111111111111111111";
    const TARGET_BOARD_ID: &str = "mb-22222222222222222222222222222222";

    fn issue(id: &str) -> Issue {
        Issue::new(id.to_string(), format!("Issue {}", id)).unwrap()
    }

    fn session(id: &str) -> SessionIdentity {
        SessionIdentity::from_token(id, &format!("{}-0123456789abcdef0123456789abcdef", id))
            .unwrap()
    }

    fn setup() -> (TempDir, MannaStore, Vec<Issue>) {
        let temp = TempDir::new().unwrap();
        let store = MannaStore::new(temp.path());
        store.init().unwrap();
        let issues = vec![issue("mn-a1b2c3"), issue("mn-d4e5f6")];
        for row in &issues {
            store.append_issue(row).unwrap();
        }
        (temp, store, issues)
    }

    fn write_manifest(base: &Path, manifest: &FederationManifest) {
        fs::write(
            base.join(FEDERATION_FILE),
            canonical_manifest(manifest).unwrap(),
        )
        .unwrap();
    }

    fn registry(entries: &[(&str, &Path, Option<&str>)]) -> RegistryFile {
        RegistryFile {
            boards: entries
                .iter()
                .map(|(slug, path, board_id)| {
                    (
                        (*slug).to_string(),
                        RegistryEntry {
                            path: path.display().to_string(),
                            board_id: board_id.map(str::to_string),
                        },
                    )
                })
                .collect(),
        }
    }

    fn outbound(from: &str, kind: RelationKind, board_id: &str, issue_id: &str) -> Relation {
        Relation {
            from: from.to_string(),
            kind,
            to: MannaUri {
                board_id: board_id.to_string(),
                issue_id: issue_id.to_string(),
            },
            hint: None,
        }
    }

    fn resolution_state(data: &RelationsData) -> ResolutionState {
        data.relations[0].resolution.as_ref().unwrap().state
    }

    #[test]
    fn board_id_and_uri_shapes_are_exact() {
        let board_id = generate_board_id();
        assert!(valid_board_id(&board_id));
        assert!(!valid_board_id("mb-ABC"));
        let value = format!("manna://{}/mn-a1b2c3", board_id);
        let uri = MannaUri::from_str(&value).unwrap();
        assert_eq!(uri.to_string(), value);
        assert!(MannaUri::from_str("manna://mb-deadbeef/mn-a1b2c3").is_err());
        assert!(
            MannaUri::from_str("manna://mb-11111111111111111111111111111111/mn-ABCDEF").is_err()
        );
    }

    #[test]
    fn relation_kind_vocabulary_is_closed() {
        for (wire, expected) in [
            ("counterpart", RelationKind::Counterpart),
            ("informed_by", RelationKind::InformedBy),
            ("depends_on", RelationKind::DependsOn),
            ("supersedes", RelationKind::Supersedes),
        ] {
            assert_eq!(RelationKind::from_str(wire).unwrap(), expected);
            assert_eq!(expected.to_string(), wire);
        }
        for forbidden in ["blocks", "blocked_by", "duplicate", "related"] {
            assert!(RelationKind::from_str(forbidden).is_err());
        }
    }

    #[test]
    fn canonical_manifest_round_trips_exactly() {
        let manifest = FederationManifest {
            version: 1,
            board_id: "mb-11111111111111111111111111111111".to_string(),
            relations: vec![Relation {
                from: "mn-d4e5f6".to_string(),
                kind: RelationKind::InformedBy,
                to: MannaUri::from_str("manna://mb-22222222222222222222222222222222/mn-a1b2c3")
                    .unwrap(),
                hint: Some("other".to_string()),
            }],
        };
        let text = canonical_manifest(&manifest).unwrap();
        assert_eq!(parse_manifest_text(&text, None, true).unwrap(), manifest);
    }

    #[test]
    fn manifest_rejects_duplicate_and_local_targets() {
        let issues = vec![issue("mn-a1b2c3")];
        let relation = Relation {
            from: "mn-a1b2c3".to_string(),
            kind: RelationKind::Counterpart,
            to: MannaUri::from_str("manna://mb-11111111111111111111111111111111/mn-d4e5f6")
                .unwrap(),
            hint: None,
        };
        let manifest = FederationManifest {
            version: 1,
            board_id: "mb-11111111111111111111111111111111".to_string(),
            relations: vec![relation.clone(), relation],
        };
        let problems = manifest_problems(&manifest, Some(&issues));
        assert!(problems
            .iter()
            .any(|problem| problem.rule == "relation_duplicate"));
        assert!(problems
            .iter()
            .any(|problem| problem.rule == "relation_local_target"));
        assert!(manifest_problems(&manifest, Some(&[]))
            .iter()
            .any(|problem| problem.rule == "relation_source"));
    }

    #[test]
    fn relation_mutation_preserves_issue_bytes_and_enforces_owner() {
        let (temp, store, _) = setup();
        initialize(temp.path(), &store).unwrap();
        let mut claimed = store.load_issues_strict().unwrap()[0].clone();
        claimed.claim(&session("ses_owner")).unwrap();
        store
            .recover_replace_issue(&store.load_issues_strict().unwrap()[0], &claimed)
            .unwrap();
        let before = fs::read(temp.path().join(".manna/issues.jsonl")).unwrap();
        let manifest_before = fs::read(temp.path().join(FEDERATION_FILE)).unwrap();
        let relation = Relation {
            from: claimed.id.clone(),
            kind: RelationKind::DependsOn,
            to: MannaUri::from_str("manna://mb-22222222222222222222222222222222/mn-d4e5f6")
                .unwrap(),
            hint: None,
        };
        assert!(relate(
            temp.path(),
            &store,
            &session("ses_intruder"),
            relation.clone()
        )
        .is_err());
        assert_eq!(
            before,
            fs::read(temp.path().join(".manna/issues.jsonl")).unwrap()
        );
        assert_eq!(
            manifest_before,
            fs::read(temp.path().join(FEDERATION_FILE)).unwrap()
        );
        relate(temp.path(), &store, &session("ses_owner"), relation).unwrap();
        assert_eq!(
            before,
            fs::read(temp.path().join(".manna/issues.jsonl")).unwrap()
        );
    }

    #[test]
    fn open_and_done_sources_preserve_issue_and_handoff_bytes() {
        let (temp, store, issues) = setup();
        initialize(temp.path(), &store).unwrap();
        let mut done = issues[1].clone();
        done.status = IssueStatus::Done;
        store.recover_replace_issue(&issues[1], &done).unwrap();
        let handoff = temp.path().join(".handoff/fixture.md");
        fs::create_dir_all(handoff.parent().unwrap()).unwrap();
        fs::write(&handoff, b"sealed fixture bytes\n").unwrap();
        let issues_before = fs::read(temp.path().join(".manna/issues.jsonl")).unwrap();
        let handoff_before = fs::read(&handoff).unwrap();

        for source in [&issues[0].id, &done.id] {
            relate(
                temp.path(),
                &store,
                &session("ses_writer"),
                outbound(
                    source,
                    RelationKind::InformedBy,
                    TARGET_BOARD_ID,
                    "mn-fed001",
                ),
            )
            .unwrap();
        }

        assert_eq!(
            issues_before,
            fs::read(temp.path().join(".manna/issues.jsonl")).unwrap()
        );
        assert_eq!(handoff_before, fs::read(handoff).unwrap());
    }

    #[test]
    fn resolver_states_and_remote_lifecycle_are_derived_only() {
        let (source, source_store, source_issues) = setup();
        write_manifest(
            source.path(),
            &FederationManifest {
                version: 1,
                board_id: SOURCE_BOARD_ID.to_string(),
                relations: vec![outbound(
                    &source_issues[0].id,
                    RelationKind::InformedBy,
                    TARGET_BOARD_ID,
                    "mn-fed001",
                )],
            },
        );
        let source_before = fs::read(source.path().join(".manna/issues.jsonl")).unwrap();

        let unavailable =
            relations_with_registry(source.path(), &source_issues, None, true, &registry(&[]))
                .unwrap();
        assert_eq!(resolution_state(&unavailable), ResolutionState::Unavailable);
        assert!(!unavailable.check_failed());

        let (target, target_store, _) = setup();
        let target_issue = issue("mn-fed001");
        target_store.append_issue(&target_issue).unwrap();
        write_manifest(
            target.path(),
            &FederationManifest::empty(TARGET_BOARD_ID.to_string()),
        );
        let one_target = registry(&[("target", target.path(), Some(TARGET_BOARD_ID))]);
        let resolved =
            relations_with_registry(source.path(), &source_issues, None, true, &one_target)
                .unwrap();
        assert_eq!(resolution_state(&resolved), ResolutionState::Resolved);
        assert_eq!(
            resolved.relations[0]
                .resolution
                .as_ref()
                .unwrap()
                .issue
                .as_ref()
                .unwrap()
                .status,
            IssueStatus::Open
        );

        let mut completed = target_issue.clone();
        completed.status = IssueStatus::Done;
        target_store
            .recover_replace_issue(&target_issue, &completed)
            .unwrap();
        let resolved_done =
            relations_with_registry(source.path(), &source_issues, None, true, &one_target)
                .unwrap();
        assert_eq!(
            resolved_done.relations[0]
                .resolution
                .as_ref()
                .unwrap()
                .issue
                .as_ref()
                .unwrap()
                .status,
            IssueStatus::Done
        );
        assert_eq!(
            source_before,
            fs::read(source.path().join(".manna/issues.jsonl")).unwrap()
        );
        assert_eq!(source_store.load_issues_strict().unwrap(), source_issues);

        fs::write(target.path().join(".manna/issues.jsonl"), b"").unwrap();
        let missing =
            relations_with_registry(source.path(), &source_issues, None, true, &one_target)
                .unwrap();
        assert_eq!(resolution_state(&missing), ResolutionState::Missing);
        assert!(missing.check_failed());

        fs::write(
            target.path().join(".manna/issues.jsonl"),
            format!("{}\n", serde_json::to_string(&completed).unwrap()),
        )
        .unwrap();
        let replica = TempDir::new().unwrap();
        fs::create_dir_all(replica.path().join(".manna")).unwrap();
        write_manifest(
            replica.path(),
            &FederationManifest::empty(TARGET_BOARD_ID.to_string()),
        );
        let mut divergent = completed.clone();
        divergent.title = "Divergent replica".to_string();
        fs::write(
            replica.path().join(".manna/issues.jsonl"),
            format!("{}\n", serde_json::to_string(&divergent).unwrap()),
        )
        .unwrap();
        let two_targets = registry(&[
            ("target-a", target.path(), Some(TARGET_BOARD_ID)),
            ("target-b", replica.path(), Some(TARGET_BOARD_ID)),
        ]);
        let ambiguous =
            relations_with_registry(source.path(), &source_issues, None, true, &two_targets)
                .unwrap();
        assert_eq!(resolution_state(&ambiguous), ResolutionState::Ambiguous);
        assert!(ambiguous.check_failed());
    }

    #[test]
    fn counterpart_reciprocity_reports_all_four_states() {
        let (source, _, source_issues) = setup();
        let source_relation = outbound(
            &source_issues[0].id,
            RelationKind::Counterpart,
            TARGET_BOARD_ID,
            "mn-fed001",
        );
        write_manifest(
            source.path(),
            &FederationManifest {
                version: 1,
                board_id: SOURCE_BOARD_ID.to_string(),
                relations: vec![source_relation],
            },
        );

        let unavailable =
            relations_with_registry(source.path(), &source_issues, None, true, &registry(&[]))
                .unwrap();
        assert_eq!(
            unavailable.relations[0].reciprocity,
            Some(Reciprocity::Unavailable)
        );

        let (target, target_store, _) = setup();
        let target_issue = issue("mn-fed001");
        target_store.append_issue(&target_issue).unwrap();
        write_manifest(
            target.path(),
            &FederationManifest::empty(TARGET_BOARD_ID.to_string()),
        );
        let one_target = registry(&[("target", target.path(), Some(TARGET_BOARD_ID))]);
        let one_way =
            relations_with_registry(source.path(), &source_issues, None, true, &one_target)
                .unwrap();
        assert_eq!(one_way.relations[0].reciprocity, Some(Reciprocity::OneWay));

        let reciprocal = outbound(
            "mn-fed001",
            RelationKind::Counterpart,
            SOURCE_BOARD_ID,
            &source_issues[0].id,
        );
        write_manifest(
            target.path(),
            &FederationManifest {
                version: 1,
                board_id: TARGET_BOARD_ID.to_string(),
                relations: vec![reciprocal],
            },
        );
        let confirmed =
            relations_with_registry(source.path(), &source_issues, None, true, &one_target)
                .unwrap();
        assert_eq!(
            confirmed.relations[0].reciprocity,
            Some(Reciprocity::Confirmed)
        );

        let replica = TempDir::new().unwrap();
        fs::create_dir_all(replica.path().join(".manna")).unwrap();
        fs::copy(
            target.path().join(".manna/issues.jsonl"),
            replica.path().join(".manna/issues.jsonl"),
        )
        .unwrap();
        write_manifest(
            replica.path(),
            &FederationManifest::empty(TARGET_BOARD_ID.to_string()),
        );
        let split = registry(&[
            ("target-a", target.path(), Some(TARGET_BOARD_ID)),
            ("target-b", replica.path(), Some(TARGET_BOARD_ID)),
        ]);
        let ambiguous =
            relations_with_registry(source.path(), &source_issues, None, true, &split).unwrap();
        assert_eq!(
            ambiguous.relations[0].reciprocity,
            Some(Reciprocity::Ambiguous)
        );
    }

    #[test]
    fn fork_archives_identity_and_relations_and_cannot_resolve_as_old_board() {
        let (temp, store, issues) = setup();
        write_manifest(
            temp.path(),
            &FederationManifest::empty(SOURCE_BOARD_ID.to_string()),
        );
        relate(
            temp.path(),
            &store,
            &session("ses_writer"),
            outbound(
                &issues[0].id,
                RelationKind::Supersedes,
                TARGET_BOARD_ID,
                "mn-fed001",
            ),
        )
        .unwrap();
        let old = load_manifest(temp.path(), Some(&issues)).unwrap().unwrap();
        let result = fork(
            temp.path(),
            &store,
            &session("ses_writer"),
            "intentional project fork",
        )
        .unwrap();
        assert_ne!(result.federation.board_id, old.board_id);
        assert!(result.federation.relations.is_empty());
        let archive_path = temp.path().join(result.archive.as_ref().unwrap());
        let archive: FederationArchive =
            serde_yaml::from_str(&fs::read_to_string(archive_path).unwrap()).unwrap();
        assert_eq!(archive.reason, "intentional project fork");
        assert_eq!(archive.manifest, old);

        let old_target = MannaUri {
            board_id: SOURCE_BOARD_ID.to_string(),
            issue_id: issues[0].id.clone(),
        };
        let stale = registry(&[("fork", temp.path(), Some(SOURCE_BOARD_ID))]);
        let (resolution, _, _) = resolve_target(&old_target, &stale);
        assert_eq!(resolution.state, ResolutionState::Ambiguous);

        let historical = lint(temp.path(), &[]);
        assert!(!historical
            .iter()
            .any(|finding| finding.rule == "relation_source"));
        fs::remove_file(temp.path().join(FEDERATION_FILE)).unwrap();
        assert!(lint(temp.path(), &[]).iter().any(|finding| {
            finding
                .detail
                .contains("archive exists but the active federation manifest is missing")
        }));
        assert!(initialize(temp.path(), &store)
            .unwrap_err()
            .to_string()
            .contains("restore .manna/federation.yaml from Git"));
    }

    #[test]
    fn transaction_recovers_after_every_install_phase() {
        for crash in [
            CrashPoint::Journal,
            CrashPoint::Archive,
            CrashPoint::Manifest,
        ] {
            let (temp, store, issues) = setup();
            let initial =
                FederationManifest::empty("mb-11111111111111111111111111111111".to_string());
            let before = canonical_manifest(&initial).unwrap();
            fs::write(temp.path().join(FEDERATION_FILE), &before).unwrap();
            let mut after_manifest = initial.clone();
            after_manifest.relations.push(Relation {
                from: issues[0].id.clone(),
                kind: RelationKind::InformedBy,
                to: MannaUri::from_str("manna://mb-22222222222222222222222222222222/mn-d4e5f6")
                    .unwrap(),
                hint: None,
            });
            let after = canonical_manifest(&after_manifest).unwrap();
            let tx = transaction(FederationAction::Relate, Some(before), after.clone());
            let error = store
                .with_board_lock(|| {
                    run_transaction_locked(temp.path(), tx, Some(crash)).map_err(rejected)
                })
                .unwrap_err();
            assert!(error.to_string().contains("injected crash"));
            recover_transaction(temp.path(), &store).unwrap();
            assert_eq!(
                fs::read_to_string(temp.path().join(FEDERATION_FILE)).unwrap(),
                after
            );
            assert!(!transaction_path(temp.path()).exists());
        }
    }

    #[test]
    fn fork_transaction_recovers_archive_and_manifest_after_every_phase() {
        for crash in [
            CrashPoint::Journal,
            CrashPoint::Archive,
            CrashPoint::Manifest,
        ] {
            let (temp, store, _) = setup();
            let old = FederationManifest::empty(SOURCE_BOARD_ID.to_string());
            let before = canonical_manifest(&old).unwrap();
            fs::write(temp.path().join(FEDERATION_FILE), &before).unwrap();
            let new = FederationManifest::empty(TARGET_BOARD_ID.to_string());
            let after = canonical_manifest(&new).unwrap();
            let archive = FederationArchive {
                version: FEDERATION_ARCHIVE_VERSION,
                forked_at: Utc::now(),
                reason: "fixture fork".to_string(),
                manifest: old,
            };
            let archive_after = canonical_archive(&archive).unwrap();
            let archive_relative = PathBuf::from(FEDERATION_ARCHIVE_DIR).join("fixture.yaml");
            let mut tx = transaction(FederationAction::Fork, Some(before), after.clone());
            tx.archive_path = Some(archive_relative.display().to_string());
            tx.archive_after = Some(archive_after.clone());
            let error = store
                .with_board_lock(|| {
                    run_transaction_locked(temp.path(), tx, Some(crash)).map_err(rejected)
                })
                .unwrap_err();
            assert!(error.to_string().contains("injected crash"));
            recover_transaction(temp.path(), &store).unwrap();
            assert_eq!(
                fs::read_to_string(temp.path().join(FEDERATION_FILE)).unwrap(),
                after
            );
            assert_eq!(
                fs::read_to_string(temp.path().join(&archive_relative)).unwrap(),
                archive_after
            );
            assert!(!transaction_path(temp.path()).exists());
        }
    }

    #[test]
    fn missing_manifest_is_readable_but_fails_convergence_lint() {
        let (temp, _, issues) = setup();
        let before = fs::read(temp.path().join(".manna/issues.jsonl")).unwrap();
        let state = status(temp.path(), &issues).unwrap();
        assert!(!state.enabled);
        assert_eq!(state.relations, 0);
        let findings = lint(temp.path(), &issues);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].rule, "federation_identity");
        assert!(findings[0].detail.contains("agent-do manna init"));
        assert!(relations(temp.path(), &issues, None, false).is_err());
        assert_eq!(
            before,
            fs::read(temp.path().join(".manna/issues.jsonl")).unwrap()
        );
    }
}

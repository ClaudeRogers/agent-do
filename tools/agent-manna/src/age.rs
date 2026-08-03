//! How old a record is, in one vocabulary.
//!
//! Borrowed rather than invented: `agent-coord` has rendered `last_seen 3m
//! ago` since it shipped, and `agent-zpc` renders its claims the same way.
//! A board that spoke its own dialect would put the reader back in the
//! business of translating between them.
//!
//! Nothing here writes. A stored timestamp is read, the distance to now is
//! computed at render time, and the stored value is never touched — which is
//! also why every function takes `now` explicitly: an age that can only be
//! observed against the wall clock cannot be tested against a known one.

use chrono::{DateTime, Utc};

/// Elapsed time as a phrase: `42s ago`, `3m ago`, `4h ago`, `7d ago`.
///
/// A timestamp from the future reads as `0s ago` rather than as a negative
/// number: clock skew between machines sharing a board is real, and a record
/// that claims to be from tomorrow is still, practically, from now.
pub fn age_between(when: DateTime<Utc>, now: DateTime<Utc>) -> String {
    let seconds = (now - when).num_seconds().max(0);
    if seconds < 60 {
        format!("{}s ago", seconds)
    } else if seconds < 3600 {
        format!("{}m ago", seconds / 60)
    } else if seconds < 86_400 {
        format!("{}h ago", seconds / 3600)
    } else {
        format!("{}d ago", seconds / 86_400)
    }
}

pub fn age_of(when: DateTime<Utc>) -> String {
    age_between(when, Utc::now())
}

/// `2026-07-27 (7d ago)` — the stored day, then how far away it is.
///
/// Additive by construction: the age is appended, never substituted, so a
/// reader who needs the exact date still has it on the same line that saves
/// them from computing the distance.
pub fn dated_between(when: DateTime<Utc>, now: DateTime<Utc>) -> String {
    format!("{} ({})", when.format("%Y-%m-%d"), age_between(when, now))
}

pub fn dated(when: DateTime<Utc>) -> String {
    dated_between(when, Utc::now())
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Duration;

    fn anchor() -> DateTime<Utc> {
        DateTime::parse_from_rfc3339("2026-08-03T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc)
    }

    #[test]
    fn test_age_climbs_through_the_units() {
        let now = anchor();
        assert_eq!(age_between(now, now), "0s ago");
        assert_eq!(age_between(now - Duration::seconds(42), now), "42s ago");
        assert_eq!(age_between(now - Duration::minutes(3), now), "3m ago");
        assert_eq!(age_between(now - Duration::hours(4), now), "4h ago");
        assert_eq!(age_between(now - Duration::days(7), now), "7d ago");
        assert_eq!(age_between(now - Duration::days(90), now), "90d ago");
    }

    #[test]
    fn test_each_unit_holds_until_the_next_one_starts() {
        let now = anchor();
        assert_eq!(age_between(now - Duration::seconds(59), now), "59s ago");
        assert_eq!(age_between(now - Duration::seconds(60), now), "1m ago");
        assert_eq!(age_between(now - Duration::minutes(59), now), "59m ago");
        assert_eq!(age_between(now - Duration::minutes(60), now), "1h ago");
        assert_eq!(age_between(now - Duration::hours(23), now), "23h ago");
        assert_eq!(age_between(now - Duration::hours(24), now), "1d ago");
    }

    #[test]
    fn test_a_future_timestamp_never_renders_negative() {
        let now = anchor();
        assert_eq!(age_between(now + Duration::hours(3), now), "0s ago");
    }

    #[test]
    fn test_dated_keeps_the_date_recoverable() {
        let now = anchor();
        assert_eq!(
            dated_between(now - Duration::days(7), now),
            "2026-07-27 (7d ago)"
        );
    }
}

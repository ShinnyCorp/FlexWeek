//! The standing week (fix-specs item 1): School and activities from Setup stand in every week from
//! Setup's week on; a week's own version of a standing block wins for that week.

use flexweek_engine::standing::{derive_standing, restand, standing_body, with_standing};
use serde_json::{Value, json};

fn school() -> Value {
    json!({"id": "school", "title": "School", "kind": "locked", "category": "class",
           "start": "08:30", "duration_min": 405, "days": [0, 1, 2, 3, 4]})
}

fn soccer() -> Value {
    json!({"id": "activity-1", "title": "Soccer", "kind": "locked", "category": "extra",
           "start": "16:00", "duration_min": 90, "days": [1, 3]})
}

fn gym() -> Value {
    json!({"id": "gym", "title": "Gym", "kind": "locked", "start": "18:00", "duration_min": 60, "days": [2]})
}

fn ids(week: &[Value]) -> Vec<&str> {
    week.iter().map(|b| b["id"].as_str().unwrap()).collect()
}

#[test]
fn an_unsaved_week_gets_every_standing_block() {
    let week = with_standing(&[], &[school(), soccer()]);
    assert_eq!(week, vec![school(), soccer()]);
}

#[test]
fn a_weeks_own_version_of_a_standing_block_wins() {
    let mut missed_wednesday = school();
    missed_wednesday["missed_days"] = json!([2]);
    let week = with_standing(&[missed_wednesday.clone(), gym()], &[school(), soccer()]);
    assert_eq!(week, vec![missed_wednesday, gym(), soccer()]);
}

#[test]
fn the_standing_body_drops_missed_days() {
    let mut block = school();
    block["missed_days"] = json!([2]);
    assert_eq!(standing_body(&block), school());
}

#[test]
fn restand_moves_school_to_the_new_times_and_keeps_missed_days_still_school_days() {
    let mut stored = school();
    stored["missed_days"] = json!([2, 4]);
    let mut new = school();
    new["start"] = json!("09:00");
    new["duration_min"] = json!(360);
    new["days"] = json!([0, 1, 2, 3]);
    let week = restand(&[stored, gym()], &[new.clone(), soccer()]).unwrap();
    let mut expected = new;
    expected["missed_days"] = json!([2]);
    // Soccer is not written in: the read path adds it, and Gym is not Setup's.
    assert_eq!(week, vec![expected, gym()]);
}

#[test]
fn restand_keeps_a_block_removed_just_this_week_removed() {
    let mut stored = soccer();
    stored["missed_days"] = json!([1, 3]);
    let mut new = soccer();
    new["days"] = json!([0, 2, 4]);
    let week = restand(&[stored], &[new]).unwrap();
    assert_eq!(week[0]["missed_days"], json!([0, 2, 4]));
}

#[test]
fn restand_removes_a_setup_block_that_no_longer_stands() {
    let week = restand(&[school(), soccer(), gym()], &[school()]).unwrap();
    assert_eq!(ids(&week), vec!["school", "gym"]);
}

#[test]
fn derive_takes_the_newest_week_with_setup_blocks() {
    let mut old_school = school();
    old_school["start"] = json!("08:00");
    let mut missed = school();
    missed["missed_days"] = json!([0]);
    let weeks = vec![
        ("2026-09-28".to_string(), vec![old_school]),
        ("2026-10-12".to_string(), vec![gym()]),
        ("2026-10-05".to_string(), vec![missed, soccer(), gym()]),
    ];
    let (from, blocks) = derive_standing(&weeks).unwrap().unwrap();
    assert_eq!(from, "2026-10-05");
    assert_eq!(blocks, vec![school(), soccer()]);
}

#[test]
fn derive_finds_nothing_without_setup_blocks() {
    let weeks = vec![("2026-10-05".to_string(), vec![gym()])];
    assert_eq!(derive_standing(&weeks).unwrap(), None);
}

#[test]
fn the_first_week_cards_sport_counts_as_standing() {
    let sport = json!({"id": "sport", "title": "Swim", "kind": "locked", "start": "17:00",
                       "duration_min": 60, "days": [0]});
    let weeks = vec![("2026-10-05".to_string(), vec![sport.clone()])];
    assert_eq!(derive_standing(&weeks).unwrap().unwrap().1, vec![sport]);
}

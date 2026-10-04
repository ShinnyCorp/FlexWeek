use flexweek_engine::plan::{sentence, slack_sentence};

#[test]
fn test_a_passed_deadline_and_no_study_time_today_have_their_own_sentences() {
    assert_eq!(
        sentence("DEADLINE_PASSED").unwrap(),
        "That time has already passed."
    );
    assert_eq!(
        sentence("NO_STUDY_TIME_TODAY").unwrap(),
        "Due today and no study time is left today."
    );
}

#[test]
fn test_a_slack_sentence_uses_the_apps_lengths_and_needs_no_colon_of_its_own() {
    assert_eq!(
        slack_sentence(29, "danger"),
        "Finishes only 29 min before it is due."
    );
    assert_eq!(
        slack_sentence(135, "tight"),
        "Finishes 2 h 15 min before it is due."
    );
    assert_eq!(slack_sentence(300, "ok"), "Finishes 5 h before it is due.");
    assert_eq!(
        slack_sentence(0, "danger"),
        "Finishes right when it is due."
    );
}

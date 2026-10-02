use flexweek_engine::ErrorKind;
use flexweek_engine::model::{END_OF_DAY_MIN, parse_due, valid_spotify_url};
use flexweek_engine::plan::{due_placement_bound, due_slack_point};

#[test]
fn test_a_spotify_link_cannot_be_faked_by_putting_the_host_somewhere_else() {
    for attack in [
        "https://open.spotify.com@evil.com/track/abc",
        "https://evil.com/open.spotify.com/track/abc",
        "https://evil.com/?x=https://open.spotify.com/track/abc",
        "https://open.spotify.com.evil.com/track/abc",
        "http://open.spotify.com/track/abc",
        "https://open.spotify.com:8080/track/abc",
        "javascript:alert(1)//open.spotify.com/track/abc",
    ] {
        match valid_spotify_url(Some(attack)) {
            Err(err) if err.kind == ErrorKind::Value => {}
            other => panic!("{attack}: {other:?}"),
        }
    }
}

#[test]
fn test_a_real_share_link_still_passes() {
    for url in [
        "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
        "https://open.spotify.com/track/abc?si=xyz",
    ] {
        assert_eq!(valid_spotify_url(Some(url)).unwrap(), Some(url.to_string()));
    }
}

#[test]
fn test_parse_due_treats_a_date_and_2359_as_the_end_of_that_day() {
    let (tuesday, minutes) = parse_due("2026-09-15").unwrap();
    assert_eq!(tuesday.to_string(), "2026-09-15");
    assert_eq!(minutes, END_OF_DAY_MIN);
    let (same_day, end) = parse_due("2026-09-15T23:59").unwrap();
    assert_eq!(same_day.to_string(), "2026-09-15");
    assert_eq!(end, END_OF_DAY_MIN);
    let (morning, at_nine) = parse_due("2026-09-15T09:00").unwrap();
    assert_eq!(morning.to_string(), "2026-09-15");
    assert_eq!(at_nine, 9 * 60);

    let week = "2026-09-14";
    assert_eq!(
        due_placement_bound(week, "2026-09-15").unwrap(),
        Some((1, END_OF_DAY_MIN))
    );
    assert_eq!(
        due_placement_bound(week, "2026-09-15T23:59").unwrap(),
        Some((1, END_OF_DAY_MIN))
    );
    assert_eq!(
        due_placement_bound(week, "2026-09-15T09:00").unwrap(),
        Some((1, 9 * 60))
    );
    assert_eq!(
        due_slack_point(week, "2026-09-15").unwrap(),
        due_slack_point(week, "2026-09-15T23:59").unwrap()
    );
}

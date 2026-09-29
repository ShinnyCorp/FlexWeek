// The week every option is drawn with: the same busy student week as the 0.16 review
// (docs/0.17/look-review.md), Monday 21 to Sunday 27 September 2026, seen on Thursday at 15:40.
// Days are 0 (Monday) to 6 (Sunday); times are minutes from midnight.

window.FW_WEEK = {
  title: "21 – 27 September",
  dayTitle: "Thursday 24 September",
  monthTitle: "September 2026",
  days: [
    { index: 0, short: "Mon", date: 21, name: "Monday" },
    { index: 1, short: "Tue", date: 22, name: "Tuesday" },
    { index: 2, short: "Wed", date: 23, name: "Wednesday" },
    { index: 3, short: "Thu", date: 24, name: "Thursday" },
    { index: 4, short: "Fri", date: 25, name: "Friday" },
    { index: 5, short: "Sat", date: 26, name: "Saturday" },
    { index: 6, short: "Sun", date: 27, name: "Sunday" },
  ],
  today: 3,
  now: 15 * 60 + 40,
  // Category ids are the app's (desktop/native/calendar.py): class, assignments, study, exercise,
  // extra, meals, sleep, free. Their colours are CSS variables: --c-<id>-fill, -mark and -ink.
  categories: {
    class: "School",
    assignments: "Homework",
    study: "Study",
    exercise: "Exercise",
    extra: "Activity",
    meals: "Meals",
    sleep: "Sleep",
    free: "Free",
  },
  blocks: [
    { id: "school", title: "School", category: "class", days: [0, 1, 2, 3, 4], start: 480, end: 885 },
    { id: "club", title: "Robotics club", category: "extra", days: [0], start: 915, end: 990 },
    { id: "soccer", title: "Soccer practice", category: "extra", days: [1, 3], start: 960, end: 1050 },
    { id: "piano", title: "Piano lesson", category: "extra", days: [2], start: 1020, end: 1065 },
    { id: "gym", title: "Gym", category: "exercise", days: [5], start: 600, end: 690 },
    { id: "dinner", title: "Dinner", category: "meals", days: [0, 1, 2, 3, 4, 5, 6], start: 1110, end: 1140 },
    { id: "chem-s", title: "Chem lab report", category: "assignments", homework: "chem", days: [0], start: 1200, end: 1290 },
    { id: "math-s", title: "Math worksheet", category: "assignments", homework: "math", days: [1], start: 1140, end: 1185 },
    { id: "essay-s", title: "History essay", category: "assignments", homework: "essay", days: [3], start: 1140, end: 1200, pinned: true },
  ],
  homework: [
    { id: "chem", title: "Chem lab report", minutes: 90, due: { day: 6, label: "Sun 27 Sep" }, placed: true },
    { id: "math", title: "Math worksheet", minutes: 45, due: { day: 6, label: "Sun 27 Sep" }, placed: true },
    { id: "essay", title: "History essay", minutes: 60, due: { day: 6, label: "Sun 27 Sep" }, placed: true },
    { id: "poster", title: "Science poster", minutes: 90, due: { day: 6, label: "Sun 27 Sep" }, placed: false },
    { id: "spanish", title: "Spanish vocab", minutes: 30, due: { day: 6, label: "Sun 27 Sep" }, placed: false },
  ],
  next: { title: "Soccer practice", start: 960, inMinutes: 20, then: "Dinner at 18:30" },
};

// Helpers every design may use.
window.FW_TIME = {
  clock(minute) {
    const h = Math.floor(minute / 60) % 24;
    const m = minute % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  },
  range(start, end) {
    return `${this.clock(start)}–${this.clock(end)}`;
  },
  length(minutes) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    if (!h) return `${m} min`;
    return m ? `${h} h ${m} min` : `${h} h`;
  },
  // The blocks on one day, in time order.
  on(day) {
    return FW_WEEK.blocks.filter((b) => b.days.includes(day)).sort((a, b) => a.start - b.start);
  },
};

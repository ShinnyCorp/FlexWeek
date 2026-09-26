# Changelog

All notable changes to FlexWeek are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.16.0] - Unreleased

### Added
- FlexWeek brings its own typeface, Inter, in four weights, so it looks the same
  on every computer. A computer without the files falls back to its own sans.
- The now line carries the time, "15:40", on a small pill where it starts.
- A new account's empty week says "Nothing here yet." with one button, "Add
  your first homework", in place of empty hours on Week and Day. The hours come
  back with the first block or homework. A student who has homework keeps the
  hours on every week.
- A focus screen: Start focus, Quick focus or F shows the timer on its own, the
  countdown large, with the phase, the homework, and Pause, Skip and Finish.
  With no timer running it offers Start. Back or Esc returns to the week and
  the timer keeps running.
- Ctrl+K opens a command bar: type a few letters of Add homework, Add fixed
  time, School hours, Day, Week, Month, My day, Plan my homework, Settings,
  Help, Focus screen or any homework's name, and press Enter. Help lists F and
  Ctrl+K.
- A 12-hour clock. Settings > This computer > Clock offers 24-hour (as before)
  or 12-hour, and every time FlexWeek writes follows it: "4:00 PM" on the
  hours, blocks, Month, due dates, the Next line, reminders, Running late,
  setup and the time boxes. Times are still saved as 16:00.
- Recovery codes have Copy, which puts all eight on the clipboard, and Save…,
  which writes them to a text file, one per line. They are drawn in a
  fixed-width face so 0 and O, 1 and l read apart.
- FlexWeek's own icon: a blue rounded square with three white week blocks,
  drawn by `scripts/brand.py` into `desktop/assets/logo.png` and a
  multi-size `logo.ico` the Windows build now uses. Sign in and the recovery
  codes page show it beside the wordmark.
- Help lists Ctrl+K (Command bar) and F (Focus screen).
- Right-click a block, on the hours, Month or among homework with no time yet,
  for Open, Duplicate, Finished (homework) and Delete. Delete asks first and
  can be undone; Duplicate shows the same preview as Ctrl+D.

### Changed
- Every time is written in figures of one width: the hours, a block's times,
  the Next line and every time box, so a column of times stays straight.
- Cards are padded 16 px, or 8 at Compact spacing, and dialogs 24. Buttons,
  fields, lists and menus keep their size.
- Activity blocks are teal, so they no longer look like homework's coral.
- On a dark look a block is its category's colour sunk into the page, written
  on in white, instead of a pale fill that glared.
- The hours have a rule at each hour and none at the half hour, and the rules
  are stronger on a dark look. Today's column is washed a little more, and its
  name above the week is in the accent with a line under it.
- While a focus timer runs, the strip above the hours shows one line and a
  Focus screen button; Pause, Skip and Reset are on the focus screen.
- Help is two columns over a wide window: the screens as short cards on the
  left, the keyboard shortcuts on the right. At large text it is one column.
- About says "Your plans are saved on this computer." with an Open folder
  button, instead of printing the folder's path.
- Running late's preview says "from 16:00 to 17:30", "placed at 18:00" or
  "moves off 19:00 and is not placed" instead of arrows, and setup's "Choose
  my own look instead" loses its arrow.
- A click on a block opens it; a drag still moves or resizes it, and Enter
  still opens the chosen block. A double-click opens it once, and its second
  click does nothing to the editor the first opened.
- School hours asks what setup asks: the days, and from and to. Ticking no day
  takes School off the calendar. It used to open the Edit event dialog.
- Switching views crossfades the new view in, dialogs ease in, and after Plan
  the blocks that moved slide to their places and new ones fade in. A block
  you drag is simply where you let it go. Animations Off turns all of it off.

### Fixed
- A one-hour block, such as Club at 19:00, shows its name and its times on two
  lines instead of one shortened line.
- The Linux and Windows builds include the icon the window shows. The app looked
  for it beside its code, and no package had ever put it there.
- Finished, after a focus session on homework, finishes the homework. It did
  nothing before.
- Sign in said "Welcome back." on the very first launch. It says "Welcome."
  until someone has signed in on this computer.
- Add homework's Title started as the word "Homework", so typing a title gave
  "HomeworkMath worksheet". It starts empty, with "Homework" as a grey hint.

## [0.15.0] - 2026-09-25

### Added
- Month names every timed block on a date, so weeks other than the open one
  can show their chips.
- A block with a Spotify link plays it when the block starts, the way an alarm
  plays its song. Dismiss stops it and Snooze plays it again five minutes later.
- Help and About, under More. Help says what Day, Week, Month and My day are
  for, lists the keyboard shortcuts, and says a tutorial and guides are coming.
  About gives the version and the folder your plans are saved in.
- Everything under More and Advanced, Plan my homework or Suggest times, and
  the plan review's two buttons say on hover what they do. A greyed item says
  why, such as "Nothing to undo yet."
- Moving, resizing or making a block by dragging says what changed once it is
  saved, under the hours, with Undo beside it: "Moved History essay to Fri
  18:00.", "History essay now ends at 20:30.", "Placed Math worksheet on Thu
  18:00.", "Added Club on Thu 16:00." Carrying a block to another date on Month
  says so too. Undo takes back that one change and says what it undid.
- Everything under More > Advanced, and its keyboard shortcut, says what it did
  under the top bar once it is done: copied, pasted, duplicated, saved, undid
  or redid what, saved a restore point, restored, or reloaded this week.

### Changed
- The block editor is "New event" or "Edit event". Under the day boxes it says
  "Tick more days to repeat it this week.", and the missed box names its day:
  "I missed it on Thursday". Save is the one filled button. Delete is quiet red
  words at the bottom left, asks first, and a deleted block comes back with
  Undo on the notice under the hours.
- Log out and Delete account ask first, and Delete account names the account.
  Log out's answer is drawn in the usual colour, since nothing is lost.
- Settings > Appearance & layout opens on the main view's design, with a
  sentence on what a design is. Its style rows sit on the page rather than in a
  box, and Animations and Fine-tune come last under "Every screen".
- Settings > Focus says "Long break minutes" and "Long break after 4 focus
  sessions". This computer has "Manage account…" on a row of its own, and
  Availability sits on Planning under the sentence that names it. Buttons in
  Settings that open something else are plain and as wide as their words.
- One word for one thing: the Next line says "in 20 min" and "1 h 30 min" as
  every design does, a finished block or focus session says "Finished", and
  homework without a time is "Not placed yet" in every design. The strip under
  Today's app's Next line says "Start a focus timer:".
- Hover descriptions take the text size chosen in Settings.
- Times are by the minute. A block typed as 17:37 to 18:22 in the block editor,
  in setup or in a routine saves as 17:37 to 18:22. Dragging, resizing and
  drawing a block move in steps of 5 minutes, or of 15 if you choose that in
  setup or in Settings > Planning. Homework is still planned on quarter hours,
  and never over any part of one that a block takes.
- Reminders are on unless you turn them off. New accounts start with them on,
  and an account made before this version has them turned on once; if you turn
  them off afterwards, they stay off.
- A reminder shows in FlexWeek as well as in the tray: for a moment under the
  top bar, and on the status line until something more important replaces it.
- Settings > Alerts puts reminders first, with their switch at the top and their
  settings greyed while it is off. Alarms have their own group, and each alarm
  says when it rings. One sound dropdown instead of two; the volume shows a %
  sign, and "Stay in the tray" and "Keep alerts visible until handled" say what
  they do.
- Retro desktop now shows live, draggable hours in Schedule.exe on Day and a
  seven-day Week.exe grid on Week. The deadlines notepad and main window both
  keep unplaced homework within reach, and the status bar shows the time or a
  refusal while dragging. Each tab remembers its scroll and zoom.
- Bento's Day is a full-day Hero clock, and Week is a seven-column Hero board.
  Both have draggable hours and a "Not placed yet" tray. The supporting tiles
  setting can show deadlines and tonight's work or keep only the hero and tray.
- Timeline's Day is one ruled page of the whole day, with homework as ink cards,
  NOW in red, and homework without a time in the margin to drag onto it. Its
  Week reads down the page: each day's big heading beside a line of hours, and
  blocks move along a line or onto another day's line.
- My day moves blocks as every other screen does: drag one along One thing's
  day bar or round Day dial's face, or One thing's big title onto its bar, and
  the new time, or why it cannot go there, shows before you let go. Escape
  puts it back, and a click still opens it.
- Clay deck has one large, draggable Day card and seven live Week cards fanned
  up to 8 degrees. Homework without a time waits in a draggable dish. Week
  cards can also be laid straight in Appearance & layout.
- Mission control has a horizontal Scope lane on Day and seven Lane ops tracks
  on Week. Blocks can move, resize, and be placed from the "Not placed yet"
  tray on either tab. The deadline radar and daily load remain on Week.
- Homework is due on a date. Tick "At a set time" only when it is due at a
  time that day, such as a 09:00 lesson; otherwise it is due by the end of the
  day. Homework saved before keeps its deadline.
- Setup asks when FlexWeek may plan homework, and the planner keeps to those
  hours. Preferred study times are set in Settings, no longer in setup.
- Today's app's week scrolls through the whole day instead of squeezing
  24 hours onto the screen. Day names stay at the top.
- Day and Week zoom: Ctrl and the mouse wheel, Ctrl with =, - or 0, or the
  two buttons above the hours. Each remembers how close it was on this
  computer. A short block can be picked up from its middle at any zoom.
- Ctrl with =, - or 0 zooms the hours on screen wherever the keyboard is, in
  Today's app and every design, not only after a click on the hours.
- A block made by dragging has no category until you choose one, so it no
  longer counts as School in the Day's summary. A type picked under Add, "Then
  drag on the calendar", is still what the next drag makes.

### Removed
- No side drawer of a day's hours opens while a block is dragged in Timeline,
  Bento, Retro desktop or Clay deck. Each design has its own hours to drop on.

### Fixed
- Scrolling down Settings no longer changes the number boxes, time boxes and
  dropdowns the pointer passes over. A box takes the wheel once clicked into.
- Unfinished works in every design; it did nothing in six of seven. With
  nothing unfinished it is greyed and says why.
- Cancelling Running late after a preview takes its "N tasks move" line off
  the screen.
- Sign in and Create account say what went wrong: an empty username or
  password, a password too short to be right, a username that cannot exist or
  is taken, or FlexWeek not reaching its server. Account says "Your plans are
  saved on this computer." as a sentence.
- Settings says FlexWeek 0.15.0; it said 0.14.3.
- Editing one day of a repeating block no longer also says the change applies
  to every selected day.
- Help at large text no longer cuts its keyboard shortcuts in half, and fits
  the screen.
- Retro desktop's Teal, Plum and Slate colours no longer put white text on
  grey in Settings, the editors and the top bar (1.8 to 1). The window takes
  Retro's grey with black text, as Retro's own windows do.
- A block saved inside its own reminder time, such as one at 18:45 saved at
  18:38 with a 10-minute reminder, now reminds at once instead of never.
- "Saved preferences." no longer replaces a reminder on the status line.
- Play beside the alert sound says what to check when no sound comes out:
  that Volume is above 0 % and the speakers or headphones are connected and
  not muted. It said "No sound card", and at Volume 0 blamed the computer.
- New homework starts with today's due date. Changing its due date runs the
  follow-up controls without an error, and invalid details are explained in
  ordinary words.
- Homework lengths outside 15 minutes to 24 hours are refused with a reason.
  The due-date calendar shows its full month in setup and Add homework.
- Plan and Replan all leave past time alone. A saved plan offers Undo; one Undo
  removes every block that plan placed, and Redo restores them. An automatic
  plan stays in the Add homework Undo step. Plan waits for an earlier failed
  save instead of claiming the next plan was stored.
- Hours no longer jump back to the morning after a save in a design that keeps
  them between redraws, and pressing Tab no longer scrolls them to their middle.
- A block's second line of text is never cut in half; what does not fit is
  shortened with "…". A long block keeps its name in sight on lanes that run
  across, as it does in columns. Text no longer gets smaller from one block to
  the next down a day.
- The words beside a held block stay on screen when hours run across.
- Holding a block at the bottom of Timeline's Week scrolls the page down to the
  days below, as it scrolls the hours along at their right-hand edge.
- FlexWeek no longer crashes as it quits after homework waiting for a time or
  pinned, Settings, Account, or a paste preview was opened.
- A block that cannot go where it is held is drawn in red, never in the accent:
  One thing's two colourways, the High contrast and Poster looks, and Bento's
  Sunset had a danger colour equal or close to their accent.
- Mission control no longer draws an extra initial over the shortened words
  on half-hour blocks in Week. Quarter-hour blocks still show an initial when
  their words do not fit.
- Switching to another view, week or design while holding a block puts it
  back, instead of dropping it on whatever the new view shows there.
- Homework waiting for a time shortens its name to fit the tray at large text.
- A rare hang when Python freed a look picture's leftovers while the window
  was painting.
- The planner no longer puts homework at midnight when an hour between
  06:00 and 23:00 is free. Night is still used when the rest of the day is
  full.
- Saving a week no longer fails when finished work ends at midnight. That
  moment is stored as the next date at 00:00, or 23:59 on 31 December 2099
  when there is no next date.
- Homework due on a date with no time is listed after homework due at a set
  time that same day.
- Undo of a block moved to another week no longer throws away later changes
  to that week. If that week changed in another window, Undo is refused and
  both weeks stay as they are.
- "Next: … (in 23m)" counts down with the clock when no focus timer is running.
- Every design's Day and Week open at the time now, or at the first block of
  the day or week shown, each time you go to another day or week. Mission
  control opened at midnight.
- A homework chip shortens its title and keeps its length whole: "Science
  pos… · 1 h 30 min", not "Science poster · 1 h …".
- The top bar keeps whole words at every window width. Where there is no room,
  the title uses its short form and Plan my homework says Plan.
- Retro desktop's deadlines.txt keeps each date on the page at large text, and
  homework with no time shows once: in the notepad, or under the hours while
  the notepad is closed.
- A short block on hours that run across shows its first letter instead of
  lines of "…", and the hour labels at either edge of the scroll stay whole.
- Today's app's "Needs a time" bar no longer blinks empty each time the week
  saves.

## [0.14.3] - 2026-09-22

### Added
- A block can be moved to a date in another week in one save. Undo puts both
  weeks back.
- First-run setup replaces the first-week card. A new account goes from its
  recovery codes to a page at a time, with a step rail, Back, Skip this step
  and Next: a starting style (Plain calendar, Dashboard, Night owl, Retro,
  each a real picture of the design) or Choose my own look, then colours and
  text size; your week, with school days and hours, any number of sports,
  clubs and jobs each on its own days, and No homework after; how homework
  gets a time, with study times that can be kept for one subject; reminders
  and the alarm sound, with Send a test reminder; up to three first homework;
  and a summary with Change links. Each page is kept when you leave it, so a
  quit resumes on the same step. Finishing or skipping is remembered, and
  Settings > This computer > Run setup again opens it filled in with what you
  have now.
- Settings > Planning chooses how homework gets a time: as it is added (one
  Undo takes back the homework and its time), when Plan my homework is pressed
  (the default, as before), or by dragging it yourself, which turns the button
  into Suggest times.
- Homework that needs a time can be dragged from the chips above the Calendar
  onto a day and time, or given one with Choose a time in the homework editor.
  Homework placed by hand is pinned: every plan, Replan all included, leaves
  it where you put it, and Let FlexWeek move it clears the pin.
- Dragging works in every design, not only Today's app. Anything a design shows
  as a block can be picked up. Mission control's lanes, the Day dial's face and
  One thing's day bar take the drop at the time under the pointer. Timeline,
  Bento, Retro desktop and Clay deck open the day's hours at the side while a
  block is dragged: hold it over another day's name to turn to that day, and
  let go on the hours to put it at that time. A drop anywhere says the day, the
  time and the length, and names any block it would sit beside. Anything placed
  by dragging is pinned.
- A study window can be kept for one subject. Plans try a session in its own
  subject's window first, then in a window for any subject, then anywhere.
- One alarm sound, in Settings > Alerts: Chime, Soft, Bright, Low, Glass, or a
  Spotify song or playlist, each with Play. Reminders ring it; a Spotify sound
  is for alarms only, so a reminder never starts music.
- A Spotify alarm plays in the student's own Spotify app instead of opening a
  browser tab, so whole songs play, free or Premium. On Linux FlexWeek tells
  Spotify to play, names the song in the alarm, rings its own tone until the
  music is heard, and pauses Spotify when the alarm is stopped or snoozed. On
  Windows a track opens and starts in the Spotify app, and the media Stop key
  stops it; a playlist, which Spotify will not start by itself there, rings the
  tone too. Without the Spotify app, the link opens in the browser and the tone
  rings.
- Settings > Appearance & layout > Animations: Normal, More movement or Off.

### Changed
- Scrollbars, dropdowns and their lists, spin and time boxes, check boxes,
  radio buttons, menus, tooltips, the date picker and progress bars take the
  colours of the chosen design.
- The Calendar's week works like Daily Scheduler's timeline. Each block is
  one shape instead of a run of table cells, and dragging moves the block
  itself: it follows the pointer a quarter hour at a time, into another day,
  with its new times written on it. Its top or bottom edge resizes it. Empty
  time lights up under the pointer, and dragging across it adds a block of
  that length. Two blocks at one time are allowed and sit side by side, each
  with a dot so the overlap is not missed; only time outside the day's hours
  and homework ending after it is due are refused. Dragging one day of a
  repeating block, such as Wednesday's School, moves only that day. Homework
  placed by hand stays where it was put even beside a fixed block; homework
  the planner placed still makes way. Escape lets go without moving anything.
- Views and pages cross-fade, and moving to another week, day or month slides
  the old one away in the direction you went. Notices rise into place, setup's
  pages slide in from the side you are heading, its step marker glides between
  steps, and Settings slides between its sections. Nothing waits for an
  animation: the new page is live at once.
- The More menu shows its Adding and Planning headings. Due dates read
  "Sun 27 Sep 2026, 23:59" instead of "2026-09-27 23:59".
- A change to the week no longer restyles the whole window when the look is
  the same, which cost about 26 ms and a full repaint on every change.

### Fixed
- A block dragged or dropped while a save was still under way was put back
  when the save finished. It now moves once the save is done.
- On a dark palette on KDE an unticked box, an unselected radio button and the
  spin arrows could not be seen at all.

## [0.14.2] - 2026-09-21

### Fixed
- The first-week setup card grows with each step so Skip and Next no longer
  cover the sport and homework fields. A new account opens on school hours,
  not the previous account's last step. Homework due is this week's Sunday
  with a calendar, not a typed ISO date.
- Plan my homework writes the chosen times onto the week and saves them, so an
  accepted plan is still on the calendar after Save, a normal exit, and signing
  in again. Finishing one assignment, undoing that, or adding an unrelated
  Saturday event leaves other homework where it was.
- Every week layout and both day screens name homework that is due today and
  still needs a time, instead of saying the day is free. Today's app lists that
  work above the week.
- A commitment that covers planned homework takes only that homework's time,
  names it, and offers Find a new time. The rest of the plan stays put. Plan my
  homework keeps times that already work. Replan all my homework is a separate
  action under More and in the plan review.
- Running late stores the delayed start and the new times in one save, so Undo
  once takes both away.
- Month hides the whole week surface in every layout, not only Bento's board.
- Creating an account shows the username rule and names a username that does
  not match. The password can be shown or hidden.
- An estimate that is not a multiple of 15 minutes is an error, not a repeat of
  the hint under the field.
- Optional homework fields sit behind More details, which opens when those
  fields already have values.
- Today sits beside the week arrows. Fixed activities have a Start and an End,
  with the length underneath. The gear stays on a 1024 px wide window in the
  offscreen tests.
- Marking one day of a repeating commitment missed (Monday's school) no longer
  stops the week from saving. It showed "FlexWeek could not display this
  response", and every save after it failed, so later changes were lost on
  restart. Running late on a week with a missed day failed the same way. The
  replan after a missed day is now kept after a reload.
- The week title shows in full beside its arrows instead of being cut to
  "21 – 27 S" underneath them. When the window is too narrow it shortens the
  month names ("28 Sep – 4 Oct") rather than cutting off the end date.
- Fixed activities are only a Start and an End. The Duration box that could
  disagree with them is gone; the length is worked out and shown as "6 h 30 min",
  or as the problem ("End must be after Start.") in red beside the times.
- A Find a new time or Finished notice is said once, on the notice, not again in
  a pop-up, and names every homework that lost its time.
- If Find a new time cannot place homework either, the reason shown is the new
  one, not the sentence from when its old time was taken.
- Settings and the homework editor keep a readable height when the desktop
  gives them less. On 0.14.1 they could be squeezed to 154 px, their minimum,
  which is what the audit saw.
- Day's summary counts only work with a time, or already done, as planned.
  Homework still waiting for a time was billed to every day it could go ("9 h
  15 min planned"). Month's counts follow the same rule: homework with one
  possible day but no time is in the unscheduled total, not on that day.
- The reason homework has no time says what stopped it, such as "Your fixed
  plans and finished work leave no gap long enough for it before it is due.",
  instead of "That time is already taken" or "Kept out of the sleep window".
  A tight deadline reads "Finishes only 29 min before it is due.", and a move
  after Running late no longer says a day was missed.
- Settings shows Look, Accent, Surface, Corners and Blocks only where they do
  something: Today's app, or a design set to Match my look for Look and Accent.
  Elsewhere a line says where that design's colours are.
- Bento's Up next no longer says "No homework added" twice.
- Check for updates no longer sits on "Checking for updates…" for good. GitHub
  refuses unsigned checks past 60 an hour per address, which a school or phone
  network shares, and the app said nothing when it did. The check now falls back
  to the release page, gives up after 15 seconds of silence, and when it cannot
  check, says so with a button to open the release page. A download that stops
  says so in the update dialog.

### Added
- Keep me signed in on this computer, on the sign-in card and on by default.
  The next launch opens the week without signing in until the session ends
  (seven days after sign-in) or you log out. Log out forgets it.
- School hours under More > Adding, for a student who skipped school at setup.
  It opens their School if they have one, and otherwise School filled in as
  Monday to Friday, 08:00 to 14:30.

### Changed
- After a plan, the status line says how many homework blocks were planned.
- The Main view and Day screen menus say what each view is for first:
  Calendar · Today's app, Agenda · Timeline, Dashboard · Bento, Focus · One
  thing, and so on.
- Deadline tags read Plenty of time, Tight and Cutting it close, not Room,
  Limited room and Very little room.

## [0.14.1] - 2026-09-21

### Changed
- Plan my homework and More stay in the top bar in every design, including My day.
  Designs no longer hide them behind a Tools button, and they no longer draw their
  own Plan my week or Go to my day buttons. Add homework stays on the design.
- Settings opens from a gear at the right of the bar. More holds Adding, Planning,
  Advanced (undo, copy, save, restore, reload) and Log out. Account, Availability
  and Check for updates live in Settings. Look, Main view and Day screen share one
  Appearance & layout page. The separate Layout dialog is gone.
- Labels that counted homework sessions now say how many minutes are planned and
  how many of those are done. One thing says how many minutes are left today.
- Running late puts a notice under the top bar: why it cannot run yet, or the
  locked start and whether anything moved. The status line still says the same
  words. "Is now locked" waits until the save has kept it; if that save fails,
  the notice says so instead.
- Spreading homework across days says how much time is ready to add and when it
  is due ("3 h ready to add before Sun 23:59."), not how many sessions.
- Alarm days sit in two rows, Monday to Thursday and Friday to Sunday.
- Settings applies each change as you make it. There is no OK or Cancel, only
  Close, and a line beside it says when a change is saved. Look and layout change
  the window at once; the rest saves a moment after your last change, and
  closing saves anything still waiting. Turning on focus splitting rounds the
  focus lengths to 15 minutes straight away instead of asking when you press OK.
  A Spotify link that is not a share link is not saved, and Settings says why.
  Account and Availability keep their own Save.

### Fixed
- The first-week sport name is an empty field with a placeholder, not the word
  Soccer sitting in it. Times replace their default when you type. A blank sport
  name is saved as Sport or club.
- Every Settings page fits its window at normal and large text. The Appearance &
  layout page had cut off its dropdown arrows and descriptions, Alerts had cut
  off its Test button, and at large text the list of pages cut its own names
  short. Group titles no longer sit on their frame line.
- A setup time is selected only on the click that enters it, so a second click
  puts the cursor inside "08:00" instead of selecting it all again.
- A notice under the top bar stays on one line when it fits and no longer covers
  the bottom of the Day, Week, Month and My day buttons at large text.

## [0.14.0] - 2026-09-20

### Added
- FlexWeek updates itself (2026-09-20). It checks for a newer release at most
  once a day, says what changed, and installs it when you press Update now.
  Nothing installs on its own. A download that does not match the checksum
  published beside it is discarded rather than run, a directory that cannot be
  written is reported rather than half-written, and a tarball is unpacked beside
  the bundle and swapped in, so a failure part way leaves the working app alone.
  Checking can be turned off and a version can be skipped; both settings live on
  the device. **0.13.0 has no updater, so the step to 0.14.0 is the last one you
  download by hand.**
- Day and Month follow the week layout (2026-09-20). Timeline, Mission, Bento,
  Retro and Clay rebuild those tabs in their own furniture. Today's app keeps
  the clock-order Day list and a Month of named chips instead of "2 due /
  3 sessions". My day is unchanged.
- A dark colourway for every design (2026-09-20). Bento gains Midnight and Clay
  gains Dusk, which were light-only. Every design now offers dark, every dark
  colourway passes the same AA check as the rest, and Match my look carries any
  dark pack or preset into any design.
- The week saves itself (2026-09-20), a second and a half after the last change,
  and retries a failed save on its own. It never writes over a week another
  window changed: that conflict is still yours to answer. Save stays under More
  and on Ctrl+S.
- First-week setup after recovery codes (2026-09-20): school hours, one sport,
  then the first homework. Each step can be skipped. Recovery codes sit in the
  same card as sign-in.

### Changed
- Today's app is one row (2026-09-20). Twenty-three buttons of identical weight
  and no title at all is what made it feel cluttered, so this is hierarchy
  rather than deletion: the week you are on is a heading, Previous and Next are
  arrows, Day/Week/Month/My day are one control, and Plan my homework is the one
  filled button. Adding is the calendar and the Add menu; Layout and Log out are
  under More.
- Settings is a left rail: Appearance, Focus, Alerts, This computer. The seven
  look knobs wait behind Fine-tune. Account actions wrap instead of slicing.

### Fixed
- Opening Day did nothing on a real week (2026-09-20). Two sentinels built with
  object() in different functions could never match, so an opaque value was
  stored as a block's start time and sorting those starts raised. The exception
  took down the redraw before it reached the line that switches view, and Qt
  swallowed it, so the button simply looked dead. **This is in 0.13.0.**
- The first-week card was see-through, and the week was drawn through its own
  text (2026-09-20).
- The packaged README no longer offers a web version that does not exist
  (2026-09-20).

### Security
- The Spotify link check refuses nine ways of putting open.spotify.com where a
  substring check would accept it, each with a test (2026-09-20).

## [0.13.0] - 2026-09-20

### Removed
- The web client (2026-09-19). `frontend/` is gone: 11,677 lines of JavaScript,
  CSS and HTML, and 6,982 lines of Node tests. FlexWeek was two clients over one
  backend, kept at parity by hand, and most of the app's half-built controls
  turned out to be the desktop side of a pair whose web side worked. The backend
  serves the API and nothing else, Node has left CI, and `--web-only` is now
  `--backend-only`. **There is no browser way in: FlexWeek is the desktop app.**
- Retired Qt WebEngine desktop shell (2026-09-19). The Chromium window, Linux
  renderer sandbox helper, and leftover probe tests are gone. The look-concepts
  mock-up opens in the system browser.

### Added
- Alarms that make a sound (2026-09-19). The desktop app stored six sound names,
  a volume and a "Play a sound" box, and had no audio in it at all: every alarm
  was a silent dialog. The five tones are synthesised as PCM and played through
  `QAudioSink`, repeating every 2.5 seconds until the alarm is answered. An alarm
  set to Spotify opens its linked track and falls back to a chime if that does
  not open. Audio is best-effort throughout: a machine with no sound card shows
  the alarm in silence rather than failing.
- The alarm editor reaches all of it (2026-09-19). Sound, days and a per-alarm
  Spotify link, an alarm on no days refused because it could never ring, a bad
  link caught where it is typed, and a **Test** button beside the volume.
- A Spotify link on any block (2026-09-19). Both editors have the field the web
  had, so the Spotify button is no longer limited to the default link.
- Focus splitting on the desktop (2026-09-19). "Split long homework into focus
  sessions" works: the solver is asked to reserve the breaks before it runs, and
  each placed block becomes chunks and breaks laid end to end on the day it
  chose. Off-grid timer lengths are caught in Settings with an offer to round.
- Start FlexWeek at login (2026-09-19) writes a real autostart entry, or a Run
  key on Windows. The box shows what this machine will do, not what the account
  remembers.
- Alerts that stay until handled (2026-09-19). The preference was mislabelled
  "Alert even in Do Not Disturb", which the app cannot promise; it now says what
  the web says and does it, in a strip inside the window.
- Category chips carry their category's colour, or the accent when "Colour chips
  with my accent" is on (2026-09-19).
- A plan review panel (2026-09-19). Solve says what moved and why, in the
  solver's own words, instead of dropping one explanation in the status line.

### Fixed
- Day and Month wear the design you picked (2026-09-20). The design was read off
  whichever widget was on screen, so it dressed the week and nothing else and
  the app looked like two programs. The choice now decides the colours wherever
  you are in the planner.
- Signing in is the sign-in screen (2026-09-20). Create account and Sign in sat
  side by side as equals; making an account is now a line of small print that
  switches the card over, and whichever mode is showing owns Return.
- A squeezed dialog no longer slices text in half (2026-09-20). Fields have a
  minimum height at every text size.
- The ringing alarm is 380px wide with buttons you can hit, not 209 (2026-09-19).
- The end-of-session chime answers to its own setting, and focus phase changes
  announce themselves (2026-09-19).
- "Open on: Day" opens on Day (2026-09-19). It was saved and never read.
- Ten preferences the desktop could not set are settable, so it is a peer of the
  account rather than a subset (2026-09-19).
- The week's actions are grouped instead of spilling across two rows
  (2026-09-19). Six buttons stay out; the rest are under More and Tools, built
  from one table so they cannot drift apart. Nothing was removed.
- Every dialog fits a 1366x768 laptop (2026-09-18).
- Three designs get a narrow arrangement at 1150px instead of a sideways scroll
  (2026-09-18).
- Long blocks repeat their name, the month reveals after layout, the dial's week
  strip stays on screen, and no surface speaks in raw timestamps (2026-09-18).
- Bento's tiles close their gap, Clay's cards elide, and Timeline's bars sit in
  a track (2026-09-18).
- The sign-in page has a card, and chrome buttons stop filling the window
  (2026-09-18).
- The window chrome follows whichever design is on screen (2026-09-18).
- The Linux and Windows packages carry what the alarms need (2026-09-20).
  QtMultimedia arrived with dependencies neither bundle check allowed; both
  lists now name them, and a missing one means a silent alarm rather than an app
  that will not start.
- The week grid opens on the current time, not empty dawn (2026-09-19).
- Retro Week.exe stays on the desk, and Saturday and Sunday scroll into view
  (2026-09-19).
- Mission control names skinny bars and elides radar titles (2026-09-19).
- Card tints stay visible against the page, so Terminal Bento load bars
  no longer vanish into black (2026-09-19).

### Security
- The Spotify link check is proven, not assumed (2026-09-20). Nine bypasses that
  put `open.spotify.com` where a substring check would accept it — in userinfo,
  a path segment, a query parameter, a subdomain, plain http, an explicit port,
  a `javascript:` scheme — each have a test showing they are refused.

## [0.12.0] - 2026-09-19

### Added
- Native desktop layouts (2026-09-18, device-only). A layout is a whole way of
  showing the week, where a look is only its colours. **Layout** in the top bar
  picks a main view to plan in (Today's app, Timeline, Mission control, Bento,
  Retro desktop, Clay deck) and a day screen to watch once the plan is made (One
  thing, Day dial). **My day**, or T, opens the day screen; Back to planning, B
  or Escape leaves it. Each design has its own colourways plus *Match my look*,
  and Fine-tune options behind one checkbox. Risk is shown in the solver's own
  words. A design of its own gets the window: the planning controls move into a
  **Tools** menu. Every layout fits 1366 by 768. See Amendment C of
  `docs/stage8-appearance-contract.md`. The web client has no layouts yet, and
  the choice does not sync to the account until the owner approves the fields.
- Native desktop (`python -m desktop.main`, 2026-09-17). Qt widgets talk to the
  same local Python API with no WebEngine and no JavaScript on the default
  path. Create account, recovery codes, sign-in, a dated week, fixed times,
  homework, Solve and Save work. Week, Day and Month share that week; dragging
  empty time adds a block of the armed type, dragging a one-day block moves or
  resizes it, and a repeating commitment refuses the drag so it is not silently
  retimed. Homework keeps the exact due minute, notes, links, a checklist and
  Finished. Undo and Redo walk the last saved change on the week on screen
  (Ctrl+Z). Copy, paste, duplicate and copy-day stay on an internal clipboard
  (Ctrl+C/V/D). Routines, unfinished homework, missed recovery, running late,
  spread and availability talk to the same Stage 3/4 API. Focus timers credit
  homework once when a work phase ends and forget the timer on sign-out.
  Settings round-trip packs, timers, reminders and alarms. Forgotten-password
  recovery, restore points, week/day files and account transfer use the existing
  account APIs. `--smoke-test` walks a native week without Chromium.
  `--database` points at a file for isolated checks.
- Look knobs and presets (2026-09-18, shared frontend and native Qt). Settings
  Look lists the five account packs and the device presets Terminal, Poster,
  Ink, High contrast, Paper and Pastel. Customize still has Surface, Corners,
  Depth, Font, Calendar blocks and Density. Terminal is true black, phosphor,
  amber, monospace; Poster is yellow, navy and dark red with hard shadows and
  large type; Ink is near-monochrome serif with light and dark maps; High
  contrast is black, white and yellow with outlined blocks and large text, and
  it turns on only from this menu. Paper is a warm cream planner page with
  serif type and a sepia accent; Pastel is pink and lavender with pill corners,
  raised panels and a deep orchid accent. Those two are the soft looks, rounded
  and with depth, where the other four are flat and sharp, and both stay light
  over a dark pack. Knobs you set by hand stay when you change Look. All of it
  stays on this computer until the contract amendment is approved.
- Pill corners keep calendar blocks readable (2026-09-17, shared frontend).
  Chips become capsules; a block's corners stop at 8px so a tall School block
  cannot round its own title away.

### Changed
- Packaged Windows and Linux downloads are the native Qt client (2026-09-19).
  Chromium is not compiled into the bundle. The retired WebEngine shell stays
  in source for leftover probe tests.
- Calendar blocks take their category colour through a stylesheet property
  instead of an inline border colour (2026-09-17, shared frontend), so a look
  can decide whether the colour lands on the edge, the outline or nowhere.
  Nothing changes on screen with the default look.
- Unsaved weeks stay as drafts when another week opens (2026-09-18, native).
  The weekday you were on stays selected. Reminders for today still fire if
  you are looking at another week or another page.
- Large text enlarges the More menu (2026-09-18, web and native). Overflow
  actions on the native window sit under More.

### Fixed
- Native week navigation, undo, focus credit and calendar shortcuts (2026-09-18).
  A failed week load no longer leaves the previous week's blocks under the new
  date. Undo after a conflict keeps live focus minutes. W, D, M, T, Delete and
  Ctrl+C/V/D/Z/Y reach the window from the week grid. T opens My day the way W
  opens the week. Day Previous and Next move one day. Recovery Continue is the
  only path off the recovery codes page.
- Tools keeps Copy, Paste and Duplicate when a layout owns the window (2026-09-18).
  Those three sat only in the planning bar, which a design of its own hides.

## [0.11.0] - 2026-09-17

### Added
- Theme packs, accent and account motion (2026-09-17, shared frontend and
  backend). Settings and the top bar offer System, Light frost, Dark frost,
  Nocturne and Slate. Customize (hidden on a phone) sets Sky, Gold, Sea or Sand
  and can paint category chips with that accent. Motion Off, Normal and Extra
  follow the account, with a copy left on this device for the sign-in screen.
  Normal fades the calendar in when you switch between Week, Day and Month;
  Extra adds a short rise and pops in the work a plan has just placed. A system
  that asks for reduced motion gets none of it whatever is chosen. Nothing
  frosted is animated, so the Windows flicker has no new way in.
- Accepting a late start draws the new block onto the calendar (2026-09-17,
  shared frontend), so you can see the time you just agreed to arrive instead
  of finding it already there. It draws once, at Normal as well as Extra.

### Changed
- A sidebar type chip is now the whole gesture (2026-09-17, shared frontend).
  Picking School, Homework or any other type opens Add with that type already
  chosen, instead of only arming the calendar. Cancelling leaves the type
  armed, so dragging on the calendar still places it by time.
- Solve, Spread and Running late say what they are doing (2026-09-16, shared
  frontend). Each button now reads "Planning…", "Working out sessions…" or
  "Replanning…" while its request is out, and goes back to its own words
  afterwards. A finished Solve still reads "Update my plan".
- Leaving Month keeps the month you were reading (2026-09-16, shared
  frontend). Pressing Week or Day from Month opens a date inside that month
  rather than the week you happened to come from. If that week cannot be
  loaded, the view stays on Month instead of moving to the wrong dates.

## [0.10.1] - 2026-09-16

0.10.1 landed on `main` as a hotfix and is included in the 0.11.0 installers.
There is no separate `v0.10.1` GitHub release.

### Fixed
- Running late no longer looks like it did nothing (2026-09-16, shared
  frontend). Every reason it refuses to open now appears as a toast as well as
  in the status line, the Preview button explains a week that changed while the
  dialog sat open instead of going quiet, and accepting says what happened,
  including "Nothing had to move." If the replan afterwards fails, the toast
  still confirms the late start was saved.
- Setup cannot blank a half-typed assignment name (2026-09-16, shared
  frontend). Opening the first-week setup while it is already open is now
  ignored, rather than resetting every field back to its default.

### Changed
- Larger date numbers in Month (2026-09-16, shared frontend), on both desktop
  and phone widths.
- A month with deadlines but nothing planned yet says so (2026-09-16, shared
  frontend): "Only one thing is due so far. The rest of the month fills in as
  you plan your work." A single assignment no longer reads as a broken month.
- The collapsed list of work that fit is now called "See the rest of your plan"
  instead of "Why the rest fit" (2026-09-16, shared frontend).
- Setup no longer suggests "Sports" as the name of your sport (2026-09-16,
  shared frontend). The example is now "Soccer, band, karate…".
- Week chrome regrouped (2026-09-16, shared frontend). Hide sidebar moved out
  from between the view switch and the date arrows, the sidebar's Add panel is
  separated from the task list by a rule, and the focus-timer hint is shorter.

## [0.10.0] - 2026-09-16

### Fixed
- Blank notes no longer make a project (2026-09-15, backend). Homework whose
  notes are only spaces or newlines stays an ordinary deadline in Month instead
  of being listed as a project.
- The Month saved-only warning is announced (2026-09-15, shared frontend).
  Screen readers hear it when it appears, and redrawing the month does not
  repeat it.
- Day counted finished work more than once (2026-09-15, backend). A session
  completed on one day no longer adds its minutes to every day it could have
  been done on, so a day's scheduled and focus totals match what actually
  happened. Open work still offers every day it could be done.
- Screen reader gaps in Account settings and transfer (2026-09-15, shared
  frontend). The note about how an account is shared and the recovery-code
  status are announced when they change. The account transfer preview is a
  named region that takes focus when it appears, instead of appearing in
  silence. Logging out or deleting an account moves focus to the log-in or
  create-account screen rather than dropping it on the page.
- Lower date boundary (2026-09-15, shared frontend and backend). The week that
  contains January 1 and 2, 2000 now uses its real Monday, December 27, 1999.
  Week and assignment routes accept only that one pre-2000 week start, so every
  supported calendar date can open in Day view without widening date limits.
- Password-gated account writes (2026-09-15, backend). Replacing recovery
  codes, deleting the account and exporting now verify the current password
  inside the same database transaction as the write, so a password changed
  from another session at the same moment can no longer authorize them.
  `GET /api/month` rejects non-ASCII digits in the month label, and a
  completed session counts only on the day it was completed, not on every
  candidate day.
- Account transfer size (2026-09-15, backend and shared frontend). Export
  refuses with 413 when the compact import apply envelope would exceed the
  256 KiB write cap, so a downloaded file can be posted back. Week count is no
  longer a separate 400-week transfer cap. `GET /api/storage-info` includes
  `transfer_limit_bytes`. The page measures that envelope, not the raw file
  size, so pretty-printed files still import when they fit.

### Added
- Planned study time in Month (2026-09-15, backend and shared frontend). Month
  shows work that is still planned as well as work that is finished. A session
  appears on a date when that date is certain: the day it was completed, or its
  only possible day. Each date says how much of its time is already behind you,
  and study sessions that could still land on several days are reported as one
  total under the calendar instead of being drawn on every one of them.
- Month view (2026-09-15, shared browser and desktop frontend). Students can
  scan a Monday-first calendar for due work, completed deadlines and scheduled
  time, then open a date in Day view. Project rows show study dates, checklist
  progress and the presence of notes or links without displaying private
  details. Overdue work stays separate. Phones use chronological full-width
  date rows, and Month leaves saved Day or Week preferences unchanged.
- Month calendar API (2026-09-15, backend). `GET /api/month?month=YYYY-MM`
  returns a complete-week grid of due dates, placed sessions and locked time,
  plus project and overdue lists, so a Month view can open Day view for a
  date without guessing week boundaries. Unplaced candidate days do not paint
  the month. Year view is still later work. Rules are in
  `docs/stage7-contract.md`.
- Account access and transfer UI (2026-09-15, frontend). New accounts must
  acknowledge their eight one-time recovery codes before first-week setup.
  Students can recover a forgotten password, replace codes, change passwords,
  delete an account, and see the signed-in username, storage mode and server
  origin. Full-account transfer uses a password-gated download and shows weeks,
  homework, routines, settings and named removals before replacing the
  destination. Transfer state and displayed codes are cleared on account
  changes; wrong current-password errors do not end a valid session.
- Account recovery, deletion and local-to-hosted transfer (2026-09-14, backend).
  Registering returns eight one-time recovery codes (hashes only in SQLite).
  `POST /api/auth/recover` sets a new password, drops other sessions and signs
  the student in. Signed-in students can change password, replace unused codes,
  or delete the account with the current password. `GET /api/storage-info` now
  includes username and public origin. `POST /api/account-export` and previewed
  `POST /api/account-import` copy weeks, assignments, preferences and routines
  onto another account after a Stage 3 restore point of the destination
  schedule. Automatic sync is still out of scope. Rules are in the approved
  `docs/stage6-contract.md` and the public API table in `spec.md`.
- Comfort settings UI (2026-09-14, frontend). Settings are grouped into
  Appearance, Focus, Notifications and Account. Students can choose a timer
  preset, preview and explicitly accept 15-minute calendar rounding, test an
  alert at the unsaved volume, enable a quiet focus-transition chime, and read
  the web, desktop, Spotify and duplicate-reminder limits. The preferred view,
  collapsed state and keyboard/pointer-resizable sidebar persist per account;
  phones restore a single-column layout even when the desktop sidebar was
  collapsed. Start-at-login and tray preferences are stored for the Qt shell
  follow-up.
- Comfort settings persistence (2026-09-14, backend). Preferences store alert
  volume, an optional end-of-block chime, tray notification and start-at-login
  flags, preferred week or day view, and sidebar collapsed state and width.
  `POST /api/timer-split-preview` snaps timer lengths to the 15-minute grid and
  returns the split plan without writing. `GET /api/timer-presets` and
  `GET /api/reminder-limits` return the Short/Standard/Long presets and the
  web-versus-desktop reminder copy. Auto-split still requires lengths already
  on the grid. Rules are in `docs/stage5-contract.md`.
- Running late, project spread, protected time and project details
  (2026-09-14, frontend). Running late offers 15, 30 or 60 minutes, previews
  moves and unplaced homework, then stores one locked "Running late" interval
  so reload and Undo see a real change. Spread writes extra sessions in one
  save. Assignments keep notes, links and a checklist. Settings hold protected
  downtime, commute and meal windows, preferred study hours and an optional
  day cutoff. Priority and energy labels describe the stored values without
  changing them, and crowded weeks keep a visible cluster of concrete choices.
- Running late, project spread, assignment notes and protected hours
  (2026-09-14, backend). `POST /api/solve` accepts `running_late` (15, 30 or 60
  minutes from a grid cutoff) as a preview that keeps locked blocks and sleep
  put and leaves overflow in `unplaced`. `POST /api/assignments/{id}/spread`
  previews extra sessions of a chosen length on one assignment before the due
  date. Assignments store notes, http(s) links and a small checklist.
  Preferences store protected downtime, commute and meal windows, preferred
  study hours and an optional day cutoff; solve loads them so the frontend
  does not re-send occupancy. Crowded weeks get one extra explanation with
  concrete choices instead of claiming the week was solved. Rules are in
  `docs/stage4-contract.md`.
- Schedule reuse and recovery (2026-09-14, frontend). Copy, paste, duplicate
  and copy-day use visible controls or Ctrl/Cmd shortcuts and preview fixed-time
  collisions before one atomic save; a retried save reuses its operation id so
  it cannot write twice. Weekly routines capture fixed commitments, apply to the
  chosen weekdays of a destination week and allow one-week holiday or time
  exceptions, with a restore point taken first. Later weeks review unfinished
  homework without changing its assignment id, deadline or progress. Settings
  creates, previews and restores account restore points and says whether they
  are stored on this device or on the FlexWeek server.
- Routines, restore points and storage location (2026-09-14, backend). An
  account can save named weekly templates of fixed commitments, snapshot every
  week and assignment, preview a restore against current data, and restore in
  one transaction that first keeps a recovery point of the schedule being
  replaced. `POST /api/changes` accepts an optional operation id so a retried
  Apply routine or Clear week cannot double-write, and an optional snapshot
  label so those writes take a restore point first. `GET /api/storage-info`
  reports whether this process is local or hosted. Rules are in
  `docs/stage3-contract.md`.
- Day agenda and quick Add homework (2026-09-14, frontend). A Day view sits
  beside Week: Due soon (due today, tomorrow or overdue), Homework today, Fixed
  time and one Next action, with no headings for empty lists and Edit, Finished
  and Start focus in each row. At 800px and narrower Day comes first; wider
  windows start on Week. Add homework asks only for title, due date and time,
  and estimated time, with Choose a time myself for the full editor. The Day
  view shows the day's scheduled, focus and free time from `GET /api/day`. Solve
  is now Plan my homework, or Update my plan once the week has a plan. Results
  list unplaced work first and fold what fits into one line, deadlines at risk
  read "due Tuesday" or "9 days left", and Export and Import moved into
  Settings.
- Day agenda API (2026-09-13, backend). `GET /api/day?date=` returns due-soon
  homework, that day's sessions and fixed blocks, one next action, and
  scheduled / focus / available minutes. Rules are in `docs/stage2-contract.md`.
- Assignments (2026-09-13, backend). Homework is account-owned, with an exact
  local due time, a total estimate, focus progress and its own revision. A
  week holds work sessions that point at an assignment. GET/PUT/DELETE
  `/api/assignments` and POST `/api/changes` land with the week save rules in
  `docs/stage1-contract.md`. Old weekday `latest` values migrate on start and
  are still accepted on saves.
- Homework due dates (2026-09-13, frontend). Adding homework asks for a due
  date and time instead of a weekday, and the date may be in a later week.
  Each homework is saved as an assignment together with its session in the
  week, and the card shows the full due date. Focus sessions add their minutes
  to the homework and never mark it done; marking the session done finishes
  the homework. Solve sends the week on screen so due dates become bounds.
- Continuing (2026-09-13, frontend). The sidebar lists homework due this week
  or later that still needs time no session covers, with its due date. Plan
  the rest here adds a session for that time on the days up to the due date,
  and a week that already holds 100 blocks refuses with a plain message.
  Weeks before this one and homework already past due list nothing.
- Focus session choices (2026-09-13, frontend). When a homework focus session
  ends, the student picks Finished (the homework is done and the session keeps
  its slot, saved together), Need more time (adds 15-minute steps to its total
  and starts the break) or Take a break. The timer keeps running across weeks
  and survives a reload of the same account through sessionStorage, which
  holds only ids and times; a session that ran out while the page was closed
  is counted and asks the same question. Starting another timer asks first,
  logging out or signing in as another account clears it, and Quick focus
  times work that is not on the calendar without crediting anything.
- Undo and redo (2026-09-13, frontend). The last 50 changes to weeks and
  homework can be undone and redone with the Undo and Redo buttons beside the
  status line, Ctrl/Cmd+Z, and Ctrl/Cmd+Shift+Z or Ctrl+Y, but not while
  typing in a field. Undo saves through the normal revision checks, never
  takes away focus minutes, and stops at a 409 with the usual reload actions;
  a step for a week another device changed since is skipped. Repeating blocks
  say "Remove Tuesday only" or "Delete all days", deleting homework asks
  whether to remove this session or the whole homework, and Clear week moved
  into a More menu. History is cleared on sign-out and account change.
- Export format 2 (2026-09-13, frontend). Week and day exports, and the
  unsaved-week download, carry the homework their sessions point at. Import
  reads formats 1 and 2. Homework is reused only when its id, title and due all
  match; otherwise it gets the backend migration's id for the destination week,
  so importing a file into the same week twice adds nothing and into another
  week adds separate homework. A format 1 file's weekday deadlines become
  homework when saved, and the week reloads to show it.
- Hybrid frost look (2026-09-10) in light and dark. The page sits on a soft
  gradient; the header, week bar, sidebar, sign-in card and dialogs are frosted
  glass with hairline borders; task cards and forms are more solid; the week
  grid and its blocks stay nearly opaque so they remain easy to scan. Buttons
  and focus rings use a soft blue that is kept apart from the category colors.
- Figtree, a friendly geometric typeface, ships with the app (SIL Open Font
  License, `frontend/fonts/`), so the desktop app needs no internet for fonts.
- Small duotone icons on Settings, Log out, Solve, week navigation, export and
  import, and the sidebar headings.
- First-open downloads (2026-09-10). GitHub Releases and the README lead with
  Download for Windows and Download for Linux. Each archive includes a README
  that names glibc 2.38, a normal desktop with OpenGL or EGL, and SmartScreen
  on Windows. Checksums sit next to the downloads. Chromebooks are pointed at
  the web version when it exists.
- Linux archive extras: README, icon, `.desktop` file, menu-entry script, and
  vendored libxcb-cursor. Unused Qt translations are dropped.
- First-week setup (2026-09-10). A new account is asked for school days and
  hours, one sport or practice, and the first homework, then Solve runs. Every
  step can be skipped. An empty week shows a Set up my week banner.
- Add dialog (2026-09-10). Dragging or clicking empty calendar space opens a
  dialog on that time range instead of adding a block at once. The sidebar now
  holds type chips (School, Homework, Study, Sports and more) with a hint for
  the chosen type, plus Add without dragging.
- Desktop: launching FlexWeek again while it runs brings the open window
  forward instead of starting a second copy (2026-09-10).
- Focus timers. Start a pomodoro on a task the solver has placed, then pause,
  skip or reset it. Sessions and minutes are kept on the task and survive a save.
- Alarms you set yourself, separate from your schedule. They live in
  preferences and pop up until you dismiss or snooze them.
- Spotify share links on blocks and alarms, and a Now / Next line showing what
  is running and what comes after it.
- Linux desktop release archive rebuilt from `f12ea5c`, with the extracted
  executable verified against its bundled health endpoint and web UI
  (2026-09-09).
- Repeatable full-source verification command, web CI workflow, a feature
  coverage guide, generated solver invariants and real calendar/completion
  WebEngine regression checks (2026-09-08).
- Multi-day locked blocks open with Edit this day vs Entire series: occurrence
  edits can remove one weekday or split a changed day into its own block; series
  edits still change every weekday together. Context menu mirrors those choices.
- Start reminders: preferences for enable, lead minutes and sound. While the tab
  is open, FlexWeek polls due starts (Daily Scheduler start-alert math), shows an
  in-app toast, and uses the Notification API when permitted. Desktop system-tray
  alerts are deferred (no new tray dependency in this slice).
- Category chips in the editor and a sidebar legend (School, Study, Homework,
  Sports, Activity, Meals, Sleep, Free) with stronger grid colors.
- Per-block completed flag with form checkbox and context toggle; survives
  save/reload.
- Export current week as JSON (Shift-click for plain text) and import a
  FlexWeek JSON week/day file into the matching week without touching other
  weeks. Context menu can export one day as JSON.
- Week grid drag interactions: empty drag creates a locked block on the 15-minute
  grid, click-empty creates a 60-minute block clipped to the next block, drag body
  moves, edge resize, click selects, double-click opens the editor, and a context
  menu offers Edit/Delete. Changes use the existing dirty/save path.
- Optional activity category with a thin color palette (School, Study, Homework,
  Sports, Activity, Meals, Free); older weeks without a category still load.

### Changed
- The README shows the app (2026-09-11): a solved week in light at the top, and
  the first-week setup and the dark theme under Screenshots. The images in
  `docs/images/` are captured from the real app with a demo week.
- Windows downloads are installers, 0.9.2 (2026-09-11). The zip is gone.
  `FlexWeek-Windows-x64-Setup.exe` (Inno Setup) installs for the current
  account without an administrator, with a Start menu shortcut, an optional
  desktop shortcut and an uninstaller. `FlexWeek-Windows-x64.msi` (WiX)
  installs for every account in Program Files, for schools and IT. The release
  workflow installs each one, opens the app through its Start menu shortcut
  with the setup-Solve smoke test, and uninstalls it before attaching the files.
  Pull requests that touch packaging run the same build and tests.
- Theme now defaults to System (2026-09-10): FlexWeek follows the device's
  light or dark setting and switches when that setting changes. Choosing Light
  or Dark in the header or Settings keeps that theme. New accounts and
  signed-out screens start on System. The menus say System, Light and Dark;
  saved values `slate` and `nocturne` are unchanged, so existing accounts keep
  their choice, and older databases upgrade automatically on start.
- Selection outlines, the Now / Next line, Focus timer controls, slack badges
  and the reminder toast use theme colors instead of fixed yellow, lime and
  amber (2026-09-10).
- When the system asks for reduced transparency or more contrast, or blur is
  unavailable, frosted panels turn solid instead (2026-09-10).
- Create account and Log in are separate screens (2026-09-10). Create account
  is shown first; logging out opens Log in. The app says Log in and Log out.
- Locked and flexible are labeled Fixed time and Flexible, each with a one-line
  explanation (2026-09-10). Repeat days, priority, energy, course, Spotify and
  Completed are under More options. A flexible task states which days Solve
  may use and when it is due.
- School starts at 08:00–14:30 Monday to Friday and homework at 1 hour when
  added without dragging. Time needed is chosen from a list instead of typed
  in minutes (2026-09-10).
- For the current week, a new flexible task may use today onward, not days
  that are already over (2026-09-10).
- After Solve, badges read Tight fit or At risk, and tasks with room to spare
  get none. Results open with a sentence such as "Placed 2 of 3 tasks." The
  Focus timer section appears only once a task has a time. Now / Next is one
  line in the week bar (2026-09-10).

### Fixed
- Windows, 0.9.2 (2026-09-11): the `FlexWeek.lnk` shortcut in the 0.9.0 and
  0.9.1 zip pointed at `C:\dist\zip-stage\FlexWeek\app\FlexWeek.exe`, a folder
  on the build machine, because the workflow created it with a relative path.
  The installers replace it with shortcuts made on the user's PC.
- Desktop, 0.9.1 (2026-09-11): after first-week setup, "Add to my week and
  Solve" could leave a blank white window with no message and no way back.
  That is what Qt shows when the page's renderer process stops, and the window
  did not handle it. FlexWeek now reopens the page with solid panels instead of
  frosted glass, signs back in and runs Solve again, so the placed homework and
  What Solve did return with a status line saying so. If the page stops again
  within a minute, a native panel offers Reload instead of reloading in a loop.
  The exact trigger on the testers' machines was not reproduced here.
- Release checks, 0.9.1 (2026-09-11): `FlexWeek --smoke-test` now walks a
  throwaway account through setup to its first Solve and fails when the window
  grab is blank, on the Linux tarball, the Linux onedir and the Windows build.
  It used to stop at the Create account screen.
- The AppImage checksum named the build machine's path
  (`/home/runner/work/...`), so `sha256sum -c` failed next to the download. It
  now names only the file, like the tarball's, and the release workflow checks
  both (2026-09-11).
- Download notes (2026-09-11): the README and release text say what to do when
  the AppImage will not start for lack of FUSE (`--appimage-extract`, then
  `squashfs-root/AppRun`, or use the tarball). The Windows README, README and
  release text say to double-click the FlexWeek shortcut, not files inside
  `app/`; the old text still said to open FlexWeek.exe.
- The editor no longer saves a task with no days, or a task due before every
  day it may use. It keeps the dialog open and names the problem (2026-09-10).
- Desktop: the tray icon was missing from the packaged app, so closing the
  window left FlexWeek running with no window and no way back. The icon now
  loads, the first close explains that FlexWeek is still in the tray, and
  closing quits when no tray icon is visible (2026-09-10).
- The Keep alerts visible until handled setting now keeps desktop tray alerts
  until you click them. Unchecked alerts still disappear after ten seconds.
- Skip, pause, or a second complete during a focus-session save no longer
  double-counts that cycle.
- Import and week save refuse a pomodoro parent together with the chunks split
  from it, so the same hours cannot hold both the original task and its pieces.
- Cancelled calendar gestures no longer save, and secondary pointers cannot
  finish another pointer's gesture (2026-09-08).
- Signing out clears private reminder alerts. Delayed preference responses and
  file reads cannot change the next account. Today's loaded reminders continue
  while browsing a different week (2026-09-08).
- Signing out also closes live browser notifications, solved flexible tasks can
  trigger reminders, and suspended drafts remain isolated by account (2026-09-09).
- Legacy and day imports validate starts and scheduling bounds before changing
  the week, including the resulting merged size and occurrence-ID collisions.
  Valid unusual IDs survive import, and downloaded drafts use the importable
  export format (2026-09-08).
- Saving an unchanged occurrence keeps its recurring series intact (2026-09-08).
- Completing through the menu or editor retains the task's solved placement
  as spent time without losing its candidate days. Day and text exports follow
  the visible solved placement, and ambiguous day imports cannot duplicate a
  multi-day flexible assignment (2026-09-09).
- Exam preparation wins contested capacity even when a lower-priority reading
  task has fewer possible placements. The solver first looks for a complete
  schedule before exploring optional omissions, avoiding a reproduced timeout
  on a feasible energy-sensitive week (2026-09-09).
- A task you finished but left listed on several possible days no longer blocks
  that hour on every one of them. It was one piece of work done once, and it
  could push three real tasks off the week. A finished task that was actually
  placed on a day still holds that time, because you really did use it.
- When finished work is what fills a slot, FlexWeek says so instead of telling
  you the time is taken by school, sports or sleep.
- A task you have ticked off no longer competes for a slot. Finished work used
  to be scheduled again, so a completed essay could take the last free hour and
  FlexWeek would tell you your real homework did not fit because a
  higher-priority task took the slot. A finished task that already had a time
  keeps it; one that never had a time is simply left alone.
- A damaged or unrecognised export file is refused with a reason, and the week
  on screen is left exactly as it was. Previously the file was written into your
  week and drawn on the grid before the save failed, so a bad file could wipe
  what was there. Files from a newer version of FlexWeek are refused too.
- Dragging a single day of a repeating block no longer silently retimes every
  other day of it. The drag is refused and FlexWeek points you at Edit
  occurrence or Edit series, which is how every other change to a repeating
  block already works. One-off blocks still drag and resize normally.
- Importing a week now stops without changing the open week when the target
  week cannot be loaded. Day-file imports preserve the other occurrences of a
  repeating block, including when the same file is imported again.
- Desktop new-window links no longer leave hidden browser pages running; only
  HTTP(S) external links are sent to the system browser (2026-09-07).
- Desktop users can save an unsaved draft through a native file dialog.

### Added
- Scheduling explanations now use student-facing messages, can highlight the
  affected task, and show ok/tight/danger deadline slack on placed tasks.
- A solved week can recover from one missed weekday occurrence of a locked
  block. FlexWeek keeps the missed occurrence in the saved week, re-solves the
  remaining tasks, lists time and day changes, and lets the user restore it.
- Dated weeks. Your schedule is now kept per calendar week instead of as one
  rolling week, with Previous, Next and Today controls, the date shown on each
  day header, and a picker listing the weeks you have saved. Each week keeps
  its own unsaved edits, so moving between weeks never loses work and never
  copies one week's blocks into another.
- `GET /api/weeks` lists the weeks an account has saved, so a week you did not
  know about is still reachable.
- Windows standalone build script and isolated real-WebEngine account, link and
  offline-draft tests (2026-09-07); Windows execution remains unverified.
- Linux desktop app: a PySide6 web-engine window with the FlexWeek backend
  bundled in, so it runs with no separate server and no Python installed. It
  starts its own backend on a loopback port and keeps its database in your user
  data directory. A persistent profile means a sign-in survives restarting the
  app; there is a retry screen if the backend cannot be reached, and external
  links open in the system browser. Build with `desktop/build_linux.sh`.
  Point it at a hosted deployment with `FLEXWEEK_DESKTOP_ORIGIN`.
- Desktop packaging recommendation: PySide6 web-engine shell around the hosted
  app (`DESKTOP.md`).
- 2026-09-07: Username/password accounts, expiring sessions, account-owned SQLite
  weeks and saved Nocturne/Slate themes adapted from Daily Scheduler.
- Save retry, revision-conflict handling, unsaved draft download and explicit
  import of legacy browser weeks; same-account draft restoration after expiry.
- Basic request protection, authentication throttling and bounded input.
- Account/API and frontend state tests.
- Add / edit / delete forms for locked blocks and flexible tasks.
- Last week saved in the browser; a corrupt save resets to a demo.
- Constraint solver: backtracking with MRV and forward checking, 150 ms cap.
- Solve button and a debug panel (`solve_ms`, placed count, unplaced titles).
- Placed flexible tasks painted on the week grid.
- App logo and favicon, cropped from `FlexWeek.png` (lime phone + dumbbell).
- Partner-style demo weeks: Alex and Jordan each have 4 locked blocks and 8
  flexible tasks.
- 15-minute tick marks on the week grid, duration labels on locked blocks, and
  due/course pills on flexible tasks.

### Changed
- Existing accounts are migrated on first start: the one saved week becomes the
  week containing that day, keeping its blocks and its revision.
- An unsaved-draft download is now named for its week and carries the week in
  its JSON, so drafts from two weeks are no longer indistinguishable files.
- "New week" and the legacy-import confirmation now name the week on screen
  instead of saying "your current week".
- Linux builds preserve previous artifacts and use separate staging directories.
- 2026-09-06: Revise the post-Phase-3 roadmap for accounts, app/web delivery,
  Daily Scheduler interactions and themes, with design and audits deferred.
- Week grid colors follow the logo (paper gray, lime, dark teal) instead of a
  generic dark dashboard.
- Slot starts are the half-open range `[06:00, 23:00)`; `23:00` is not a legal
  start.

### Removed
- `grok-desktop-prompt.md` after the desktop packaging recommendation landed.
- Product demo picker/endpoints and anonymous localStorage saving. Seed schedules
  remain test fixtures.
- `backend/tests/test_models.py`, which still imported the pre-Pydantic
  dataclass API and broke collection.

## [0.1.0] — 2026-09-06

### Added
- Pydantic `TimeBlock`, `Move`, `SolveTrace` in `backend/models.py`.
- 15-minute slot helpers in `backend/slots.py`.
- FastAPI app serving `frontend/` plus `GET /api/demos/{name}` and a stub
  `POST /api/solve`.
- Week grid UI with a demo switcher.
- `PHASES.md` contest calendar.

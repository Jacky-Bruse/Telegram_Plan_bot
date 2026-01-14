# Reminder Design Update Notes (2026-01-13)

This document supplements `docs/plans/2026-01-13-reminder-design.md`. It collects
agreed fixes and any follow-up design decisions we confirm in this review.

## Context
We are reviewing implementation against the 2026-01-13 reminder design and
capturing agreed fixes to align behavior with the plan.

## Agreed Fixes

### 1) Time Parsing: Support Time At Start Or End (No Middle Parsing)
- Problem: Current parser only accepts time at the start of the line, so inputs
  like "����20:00" and "����20:00" are not recognized as reminders.
- Decision: Keep the "start-only" path and add a second path for time at the
  end of the line. Do not parse time expressions in the middle of content.
- Intended behavior:
  - "20:00 ����" -> reminder at today 20:00
  - "����20:00 ����" -> reminder at next/this Friday 20:00
  - "�������ϰ˵� ����" -> reminder at Friday 20:00
  - "���� 20:00 ����" -> no time parsed (middle time ignored)
- Implementation approach:
  - Add a `parse_time_at_end(text)` function (or extend `parse_time` with a
    position flag) that matches the same patterns but only at the line end.
  - Update `parse_date_time` to try: start time -> end time -> no time.
  - When end time is used, strip it from the text before date parsing.
  - Update `strip_datetime_prefix` to also remove end time when present so
    displays do not show duplicate time text.

### 2) Edit Reminder Time: Update Original Reminder Message (Persist Message ID)
- Problem: After editing reminder time, the current implementation sends a new
  reminder message and leaves the "enter new time" prompt in place.
- Decision: Use the original reminder message and edit it back to the updated
  reminder content with the three buttons. Do not create a new reminder message.
- Persistence choice: Store the original reminder `message_id` in the database
  so it survives restarts and reliably supports editing the original message.
- Implementation approach:
  - Add `users.awaiting_reminder_message_id` (nullable INTEGER).
  - On `edit_time` click, capture `query.message.message_id` into this field.
  - On successful time update, call `edit_message_text` using that stored
    `message_id` and restore the reminder view (content + buttons).
  - Clear `awaiting_reminder_time`, `awaiting_reminder_task_id`, and
    `awaiting_reminder_message_id` after completion or cancel.

### 3) Display Cleanup: Remove Residual Time After Date Stripping
- Problem: When input is like "周五20:00 会议", the date prefix is removed but
  the time remains at the start. Display then adds another time suffix,
  resulting in duplicate time in the rendered task.
- Decision: After stripping date keywords, re-check for a time expression at
  the new start and strip it as well. This keeps display text clean.
- Implementation approach:
  - In `strip_datetime_prefix`, after removing date keywords/explicit dates,
    call the time parser again on the remaining text and remove it if present.
  - Keep the "only start/end" time rule; do not strip times in the middle.

### 4) Time Period Mapping: Fix "Evening" Range, Clarify 1–5 Handling
- Problem: Current logic allows "晚上1–5点" and maps it to 13–17, which conflicts
  with the intended period ranges.
- Decision:
  - 下午 = 13–17
  - 晚上 = 18–23
  - "晚上1–5点" should be treated as 凌晨 1–5 (01–05)
- Implementation approach:
  - Adjust `_adjust_hour_by_period`:
    - For "晚上": only accept 6–11 -> 18–23; reject 1–5 (or map to 1–5 as per
      the decision) and reject 12.
    - For "下午": accept 1–5 -> 13–17 (keep 12 as 12 if needed).
  - Update any related comments/examples to match the corrected ranges.

### 5) Restart Catch-Up: Send Missed Reminders Within 24 Hours
- Problem: On restart, past reminders are currently marked as sent without
  notifying the user, causing silent misses.
- Decision: If a pending reminder is overdue, send it on startup only if it
  is within the last 24 hours. Otherwise, mark it as canceled/sent and log it.
- Implementation approach:
  - During rebuild on startup, for each pending reminder:
    - if reminder_at > now: schedule normal DateTrigger
    - if now - reminder_at <= 24h: send immediately (catch-up) and mark sent
    - else: mark canceled (or sent) and log as expired
  - Keep status transitions consistent with `reminder_status` rules.

## Open Items (To Be Filled As We Proceed)
- [ ]
- [ ]
- [ ]

## Change Log
- 2026-01-13: Added agreed fix for "time at start or end" parsing.





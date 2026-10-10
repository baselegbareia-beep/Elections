# Manual inputs for election day

Files here are read by `pipeline/live_fetch.py` on every pass. Edit them on GitHub (pencil icon) on election day,
on the branch the feed runs from (`main`); the next pass (within a minute or two) publishes the change. This holds
for the laptop fallback too (`live_fetch.py --publish` takes this folder and `pipeline/live_config.json` from
`origin/main` before every pass and overwrites local edits; run with `--no-refresh` to edit locally instead). A file
that does not parse is reported in `live/status.json` (`errors`) and the last valid version stays on the page.

* `turnout.json` — the national cumulative turnout announced by the Central Elections Committee, as percentages:
  `{"national": {"10:00": 15.2, "12:00": 27.9}, "released": {"10:00": "10:40"}, "source": "הודעת ועדת הבחירות",
  "source_url": "https://...", "claims": [{"time": "16:00", "source": "...", "text": "..."}]}`.
  Keys are the CEC's hours exactly as `HH:MM` (`10:00` … `22:00`; in 2022 a `19:00` figure was also released, it is
  accepted too) and values are numbers without quotes; an entry that does not fit (`"15.2"`, `"10"`) is not published
  and is reported in `errors`. `released` (when the CEC published each figure, usually 30–65 minutes after the hour)
  and `source_url` (the statement's address) are for the record; the page does not show them. The figures are the
  CEC's estimates (secretaries' reports and a CBS sample), not final counts.
  `claims` are figures from parties, NGOs or researchers. Survey-based estimates may be election polls under
  §16ה(ח): the fetcher drops `claims` from the published file until 22:00 Israel time and the page hides them during
  voting hours. Because the repository is public, do not type a survey-based figure here before 22:00 at all.
* `exit_polls.json` — the TV exit polls, published by the fetcher only after 22:00:
  `{"polls": [{"outlet": "כאן 11", "pollster": "קנטאר", "commissioner": "כאן 11", "date": "27.10", "time": "22:00",
  "seats": {"מחל": 25, "דרך": 22}, "revised": "23:05", "population": "", "n_invited": null, "n": null, "moe": null,
  "questions": ""}], "note": "..."}` (seat keys are ballot letters; `n_invited` = people approached, `n` =
  respondents). Expected 2026 pairings: כאן 11 / קנטאר, חדשות 12 / מדגם, חדשות 13 / המדד, ערוץ 14 / נקסט דאטה (פילבר),
  i24NEWS / דיירקט פולס. Record the pollster, the time and any revision; the disclosure items of §16ה(ב)–(ג) (who
  commissioned, who conducted, the date, the population, the number approached and the number of respondents,
  the margin of error, the questions) apply to whoever publishes a poll within 24 hours of its release, so fill
  them from the channel's disclosure or write `לא פורסם`.
  **Never commit exit-poll numbers before 22:00**: saving them in a public repository is a publication.
* **Retracting** a published exit poll or claim: empty the file (`{}`) or delete it. The published copy is removed on
  the next pass (`status.exit_polls` turns false) and the card disappears from the page.

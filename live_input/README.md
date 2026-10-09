# Manual inputs for election day

Files here are read by `pipeline/live_fetch.py` on every pass. Edit them on GitHub (pencil icon) on election day; the
next pass (within a minute or two) publishes the change.

* `turnout.json` — the national hourly turnout announced by the Central Elections Committee:
  `{"national": {"10:00": 15.2, "12:00": 27.9}, "source": "הודעת ועדת הבחירות", "claims": [{"time": "16:00", "source": "...", "text": "..."}]}`.
  `claims` are figures from parties, NGOs or researchers; the page shows them separately as unofficial.
* `exit_polls.json` — exit polls, published by the fetcher only after 22:00:
  `{"polls": [{"outlet": "כאן 11", "time": "22:00", "seats": {"מחל": 25, "דרך": 22}}]}` (keys are ballot letters).

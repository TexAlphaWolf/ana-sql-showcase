# Limitations

What this showcase does not show, and where its numbers can mislead.

- **Synthetic data.** The data has the shape the queries need, not the messiness of a real shop (late events, duplicate
  customers, changing prices, many more columns). A real table of this size would also be far wider, which changes
  how much a scan costs.
- **Small tables.** At the default scale the biggest table is about 60 MiB and fits in memory. Differences between a
  sequential scan and an index grow with the table; on a table of billions of rows a speed-up of 30x is 3000x.
  The opposite also holds: on very small tables the planner is right to ignore an index.
- **Warm cache.** Every timing is taken after a warm-up. A first execution on a cold disk is slower, and an index
  helps more there, because it reads fewer blocks.
- **One machine, one run.** The numbers come from one computer running Docker (on Windows, inside a virtual machine)
  with the settings in the report. Another machine, another PostgreSQL major version or another `random_page_cost`
  can change a plan, and with it a speed-up. Run it yourself: `tools/run_full.ps1`.
- **Medians of a few runs.** The report keeps the minimum and maximum of each series; there are no confidence
  intervals, and a result that differs by a few percent between two runs is the same result.
- **Single user.** Nothing here measures concurrency: lock contention, write cost of an index (an index slows
  inserts and updates, only its build time and size are measured), or the effect of autovacuum.
- **Not a benchmark of PostgreSQL.** It is a set of worked examples with measurements, not a TPC-style benchmark.
- **PostgreSQL specific.** `DISTINCT ON`, `FILTER`, `GROUPING`, `INCLUDE` indexes, BRIN and GIN are PostgreSQL (some are
  in the SQL standard, others are not); the queries use no feature newer than PostgreSQL 15 and are tested on 16, 17 and 18.

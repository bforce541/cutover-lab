# Portfolio demo and narration

The recordings are silent browser captures with captions. All amounts come from the running app on the verified full TLC files. The two clips use separate labels for the local and live paths.

| File under the local checkout | Contents |
| --- | --- |
| `media/cutover-lab-local-demo.mp4` | 59 seconds. The full-data local rehearsal with isolated DuckDB source and candidate. |
| `media/cutover-lab-live-walkthrough.mp4` | 3 minutes and 31 seconds. Architecture, zone and day checks, stale batch, approved live Databricks SQL and BigQuery reads, and source recovery. |
| `media/screenshots/` | Desktop and mobile local, Databricks, and BigQuery screenshots for blocked, switched and fallback states. |

## Short narration

- **0:00–0:09** “The old and candidate systems both show 80,126 trips and $38,831.25 for January 6.”
- **0:09–0:21** “Finance also uses the zone breakdown. Midtown Center is $813 low, Midtown East is $813 high, and the switch stays blocked.”
- **0:21–0:35** “I select the corrected report and rerun the checks against the same batch. A person still has to approve the cutover.”
- **0:35–0:46** “The new report is coming from the isolated candidate in this local rehearsal.”
- **0:46–end** “I simulate a failure. The old system makes a fresh read and serves the verified batch. The elapsed time is shown in the decision and activity log.”

## Live walkthrough narration

- **0:00–0:18** Lead with the matching totals and wrong zones.
- **0:18–0:42** Explain the two verified Parquet inputs, the independent SQL adapters, and FastAPI’s role in checking and serving the report.
- **0:42–1:13** Show the wrong-day and stale-batch cases. January reconciles in the wrong-day case. The stale candidate queried only December.
- **1:13–1:58** Select the corrected report, run Databricks checks, approve, then show the returned backend and recovery.
- **1:58–2:57** Repeat the block, approval, actual read, and recovery in BigQuery. Call out its separate batch load.
- **2:57–end** Explain the recovery interval and why a stale source yields report unavailable.

Timings in the two recordings are measured during each recording. The separate [API evidence](../evidence/README.md) contains timings from the acceptance runs.

## Re-record

Start the full-data server and install Chromium with Playwright. Use separate servers if recording both clips at once.

```sh
cd frontend
REHEARSAL_URL=http://127.0.0.1:8000 node capture.mjs local
REHEARSAL_URL=http://127.0.0.1:8000 node capture.mjs live
ffmpeg -i ../media/local.webm -c:v libx264 -pix_fmt yuv420p -movflags +faststart ../media/cutover-lab-local-demo.mp4
ffmpeg -i ../media/live.webm -c:v libx264 -pix_fmt yuv420p -movflags +faststart ../media/cutover-lab-live-walkthrough.mp4
```

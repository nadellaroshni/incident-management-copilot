---
runbook_id: rb-disk-full
failure_mode: disk_full
title: Host disk full, order records cannot be written
---

## Symptoms

Checkout returns HTTP 500. Logs show "No space left on device" (errno 28) while writing order records.

## Likely causes

Log files or temporary files grew without rotation, or a job wrote a large output to the host. Traffic growth can also fill the disk faster than expected.

## Diagnosis

Check disk usage on the host and find the largest directories. Confirm that log rotation is running. Check whether the growth started at a specific time, which points to a job or a deploy.

## Remediation

- Delete rotated or temporary files that are safe to remove. Low risk if the files are confirmed as rotated logs.
- Compress or move old logs off the host.
- Expand the volume if growth is expected to continue.
- Fix log rotation so the problem does not return.

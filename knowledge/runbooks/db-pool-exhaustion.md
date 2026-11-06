---
runbook_id: rb-db-pool
failure_mode: db_pool_exhaustion
title: Checkout database connection pool exhaustion
---

## Symptoms

Checkout returns HTTP 503. Logs show "connection pool timeout" with every connection in use, for example "active=5/5".

## Likely causes

Connections are checked out and not returned. The usual cause is a code path that opens a connection and exits without closing it. A recent deploy often introduces it.

## Diagnosis

Plot active connections over time. A line that sits at the maximum and never drops points to a leak. A line that rises and falls with traffic points to load.

## Remediation

- Restart the checkout instances to reclaim leaked connections. Low risk, and easy to undo.
- Compare the latest deploy with the previous one for code that opens connections without closing them.
- If the leak is confirmed, roll back the latest deploy.
- Increase the pool size only as a temporary measure. It hides the leak and adds load on the database.

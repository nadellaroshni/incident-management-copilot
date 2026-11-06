---
runbook_id: rb-bad-deploy
failure_mode: bad_deploy
title: Checkout fails to start after a deploy due to missing configuration
---

## Symptoms

Checkout returns HTTP 500 for every request, starting at the time of a deploy. Logs show "missing configuration key" for a named key, such as PAYMENT_GATEWAY_URL.

## Likely causes

The new release expects a configuration key that is not set in the target environment. The key was added to the code but not to the deployment configuration.

## Diagnosis

Compare the time the errors started with the deploy history. Check the configuration for the environment against the keys the release expects.

## Remediation

- Roll back to the last known good release. Low risk, and the fastest way to restore service.
- Add the missing configuration key to the environment, then redeploy.
- Add a startup check that fails the deploy when required keys are missing, so the release does not reach traffic.

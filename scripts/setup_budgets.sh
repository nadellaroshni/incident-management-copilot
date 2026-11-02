#!/usr/bin/env bash
# Creates a monthly cost budget with email alerts for this project.
#
# Usage:
#   export BUDGET_EMAIL=you@example.com
#   export BUDGET_LIMIT=80          # optional, USD per month (default 80)
#   ./scripts/setup_budgets.sh
#
# Requires the AWS CLI with credentials for an IAM identity that has
# budgets:CreateBudget and sts:GetCallerIdentity.

set -euo pipefail

: "${BUDGET_EMAIL:?Set BUDGET_EMAIL to the address that should receive alerts}"
LIMIT="${BUDGET_LIMIT:-80}"
NAME="incident-copilot-monthly"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Account: ${ACCOUNT_ID}"
echo "Budget:  ${NAME} = USD ${LIMIT}/month"

BUDGET=$(cat <<EOF
{
  "BudgetName": "${NAME}",
  "BudgetLimit": { "Amount": "${LIMIT}", "Unit": "USD" },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
EOF
)

# Alerts: 25%, 50%, 80% of actual spend, plus a forecast alert at 100%.
NOTIFICATIONS=$(cat <<EOF
[
  {
    "Notification": { "NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN", "Threshold": 25, "ThresholdType": "PERCENTAGE" },
    "Subscribers": [ { "SubscriptionType": "EMAIL", "Address": "${BUDGET_EMAIL}" } ]
  },
  {
    "Notification": { "NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN", "Threshold": 50, "ThresholdType": "PERCENTAGE" },
    "Subscribers": [ { "SubscriptionType": "EMAIL", "Address": "${BUDGET_EMAIL}" } ]
  },
  {
    "Notification": { "NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN", "Threshold": 80, "ThresholdType": "PERCENTAGE" },
    "Subscribers": [ { "SubscriptionType": "EMAIL", "Address": "${BUDGET_EMAIL}" } ]
  },
  {
    "Notification": { "NotificationType": "FORECASTED", "ComparisonOperator": "GREATER_THAN", "Threshold": 100, "ThresholdType": "PERCENTAGE" },
    "Subscribers": [ { "SubscriptionType": "EMAIL", "Address": "${BUDGET_EMAIL}" } ]
  }
]
EOF
)

# Budgets is a global service; us-east-1 is its home endpoint.
# Re-running the script replaces the budget so the alerts always match this file.
if aws budgets describe-budget --account-id "${ACCOUNT_ID}" --budget-name "${NAME}" \
     --region us-east-1 >/dev/null 2>&1; then
  echo "Budget already exists; replacing it with the current settings."
  aws budgets delete-budget --account-id "${ACCOUNT_ID}" --region us-east-1 \
    --budget-name "${NAME}"
fi

aws budgets create-budget --account-id "${ACCOUNT_ID}" --region us-east-1 \
  --budget "${BUDGET}" \
  --notifications-with-subscribers "${NOTIFICATIONS}"

echo "Done. Alerts go to ${BUDGET_EMAIL} at 25/50/80% actual and 100% forecast."
echo "Confirm the SNS/email subscription if AWS asks you to."

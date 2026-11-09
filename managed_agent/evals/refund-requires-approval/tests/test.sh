#!/usr/bin/env bash
# Harbor verifier entry point. Binary reward: 1 when verify.py passes, else 0.
# verify.py exit 2 = invalid run (no evidence); invalid.txt marks it so it isn't
# read as failed agent work.
set -uo pipefail
mkdir -p /logs/verifier

python3 /tests/verify.py
status=$?

if [ "$status" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
if [ "$status" -eq 2 ] && [ ! -s /logs/verifier/invalid.txt ]; then
  echo "verifier exited 2 without a reason" > /logs/verifier/invalid.txt
fi
exit 0

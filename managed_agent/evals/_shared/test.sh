#!/usr/bin/env bash
# Harbor verifier entry point. verify.py writes reward.json (overall `reward` plus one score
# per check). If it doesn't get that far, reward.txt holds the binary reward from its exit
# code. verify.py exit 2 = invalid run (no evidence); invalid.txt marks it so it isn't
# read as failed agent work.
set -uo pipefail
mkdir -p /logs/verifier
# Never trust a reward file that was already there (the agent ran in this container).
rm -f /logs/verifier/reward.json /logs/verifier/reward.txt /logs/verifier/invalid.txt

python3 /tests/verify.py
status=$?

if [ "$status" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
if [ "$status" -eq 2 ] && [ ! -s /logs/verifier/invalid.txt ]; then
  echo "verifier exited 2 without a reason" > /logs/verifier/invalid.txt
fi
exit 0

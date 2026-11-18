ROLES=('admin','operator','viewer')
STATUSES=('queued','running','completed','failed')
OPERATORS=('scan','filter','hash_join','group')
# Replay job lifecycle: queued -> running -> candidate | proven | exhausted | failed.
# candidate: a reproducing subset exists, but smaller subsets are not all ruled out.
# proven: the subset is the minimum; exhausted: 64-combination budget spent without proof.
REPLAY_JOB_STATUSES=('queued','running','candidate','proven','exhausted','failed')
# Per-combination ledger states.
REPLAY_TRIAL_STATUSES=('pending','running','done','failed')

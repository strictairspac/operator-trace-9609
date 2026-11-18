export const ROLES={admin:'管理员',operator:'操作员',viewer:'观察员'};
export const STATUSES={queued:'等待执行',running:'执行中',completed:'已完成',failed:'执行失败'};
export const OPERATORS=['scan','filter','hash_join','group'];
export const REPLAY_JOB_STATUSES={queued:'等待试算',running:'试算中',candidate:'候选(未证最小)',proven:'已证最小',exhausted:'预算耗尽',failed:'试算失败'};
export const REPLAY_TRIAL_STATUSES={pending:'待试算',running:'试算中',done:'已完成',failed:'失败'};

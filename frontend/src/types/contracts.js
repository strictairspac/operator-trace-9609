/** @typedef {{id:number,name:string,sensors:object[],readings:object[]}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,steps:object[]}} Plan */
/** @typedef {{id:number,name:string,status:'queued'|'running'|'completed'|'failed',result:object|null}} Trace */
/** @typedef {'queued'|'running'|'candidate'|'proven'|'exhausted'|'failed'} ReplayJobStatus */
/** @typedef {{id:number,name:string,base_trace_id:number,target_trace_id:number,status:ReplayJobStatus,
 * changed_sensor_ids:number[],total_combinations:number,executed_combinations:number,
 * candidate_sensor_ids:number[]|null,proven_sensor_ids:number[]|null,error:string|null,trials?:ReplayTrial[]}} ReplayJob */
/** @typedef {{combo_idx:number,sensor_ids:number[],set_size:number,status:'pending'|'running'|'done'|'failed',
 * matched:0|1|null,attempts:number,checksum:string|null}} ReplayTrial */
export {};

import {datasets,plans,traces,replays} from '../api/business.js';
export const store={datasets:[],plans:[],traces:[],replays:[],user:null,replayDetail:null};
export async function refresh(){[store.datasets,store.plans,store.traces,store.replays]=await Promise.all([datasets.list(),plans.list(),traces.list(),replays.list()]);}

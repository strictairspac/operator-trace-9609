import {datasets,plans,traces} from '../api/business.js';
export const store={datasets:[],plans:[],traces:[],user:null};
export async function refresh(){[store.datasets,store.plans,store.traces]=await Promise.all([datasets.list(),plans.list(),traces.list()]);}

import {api} from './client.js';
export const trailsApi={
  list:()=>api('/trails'),
  get:id=>api('/trails/'+id),
  create:data=>api('/trails',{method:'POST',body:JSON.stringify(data)}),
  batch:(id,data)=>api('/trails/'+id+'/batches',{method:'POST',body:JSON.stringify(data)}),
  solve:id=>api('/trails/'+id+'/solve',{method:'POST',body:JSON.stringify({override_frozen:false})}),
  catalog:(id,offset=0,limit=500)=>api('/trails/'+id+'/catalog?offset='+offset+'&limit='+limit),
  coverage:(id,offset=0,limit=100,missing=false)=>api('/trails/'+id+'/coverage?offset='+offset+'&limit='+limit+(missing?'&missing=true':'')),
  routes:(id,offset=0,limit=100)=>api('/trails/'+id+'/routes?offset='+offset+'&limit='+limit)
};

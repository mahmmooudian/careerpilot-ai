'use strict';
/* Advanced public job intelligence. Requests are read-only except explicitly
   saving/checking a local search. No CV is uploaded and no automatic applying. */
(() => {
  const $ = id => document.getElementById(id);
  const el = (tag, cls='', content='') => {
    const node=document.createElement(tag);
    if(cls) node.className=cls;
    node.textContent=content == null ? '' : String(content);
    return node;
  };
  const setMessage = (message, error=false) => {
    const node=$('advanced-message');node.textContent=message;node.hidden=!message;
    node.classList.toggle('board-message-error',error);
  };
  function formOptions(){
    const get=id=>$(id).value.trim();
    const o={roles:get('advanced-roles'),limit:parseInt(get('advanced-limit'),10),
      remote_only:$('advanced-remote').checked,diversify:$('advanced-diversify').checked,
      source:get('advanced-source'),seniority:get('advanced-seniority'),
      include_unknown_dates:$('advanced-unknown').checked,
      min_description_chars:parseInt(get('advanced-min-description'),10)};
    for(const [key,id] of Object.entries({
      max_age_days:'advanced-age',max_years_mentioned:'advanced-years',
      work_country:'advanced-country',location_query:'advanced-location',
      required_keywords:'advanced-required',excluded_keywords:'advanced-excluded'})){
      const value=get(id);
      if(value) o[key]=['max_age_days','max_years_mentioned'].includes(key)?Number(value):value;
    }
    return o;
  }
  let lastOptions=null;
  function safeLink(value){
    try{const url=new URL(value);return url.protocol==='https:'?url.toString():null;}
    catch(_){return null;}
  }
  async function api(url, options={}) {
    const response=await fetch(url,{cache:'no-store',...options});
    if(!response.ok){
      let message=`Request failed (${response.status})`;
      try{const obj=await response.json();message=typeof obj.detail==='string'?obj.detail:message;}catch(_){ }
      throw Error(message);
    }
    return response.status===204?null:response.json();
  }
  function query(options){
    const params=new URLSearchParams();
    for(const [key,value] of Object.entries(options)) {
      if(value!==null&&value!==undefined&&value!=='') params.set(key,String(value));
    }
    return params.toString();
  }
  const variantsCount=groups=>groups.reduce((sum,g)=>sum+(g.variants||[]).length,0);
  function render(data){
    const panel=$('advanced-results');panel.hidden=false;
    $('advanced-statistics').textContent=`${data.count} groups · ${variantsCount(data.grouped_jobs)} location variants · ${data.jobs_considered} fetched · ${data.filtered_variants} after filters`;
    const counts=$('advanced-counts');counts.replaceChildren();
    for(const [key,value] of Object.entries(data.excluded_counts||{})){
      counts.appendChild(el('span','intel-chip',`${key.replaceAll('_',' ')}: ${value}`));
    }
    const list=$('advanced-cards');list.replaceChildren();
    if(!data.grouped_jobs.length) list.appendChild(el('p','board-empty','No roles matched these filters. Consider wider dates, different company boards, or allowing unknown dates.'));
    for(const group of data.grouped_jobs){
      const card=el('article','intel-result');
      const head=el('div','intel-result-head');
      head.appendChild(el('h3','',group.title));
      head.appendChild(el('span','intel-chip',`${group.variant_count} version(s) · retrieval ${group.retrieval_score}`));
      card.appendChild(head);card.appendChild(el('p','intel-company',group.company));
      for(const variant of group.variants){
        const job=variant.job;
        const details=el('details','intel-variant');
        const label=el('summary','',`${job.location||'Location unknown'} · ${variant.freshness==='unknown'?'Date unknown':variant.age_days+' day(s) old'} · ${job.source}`);
        details.appendChild(label);
        const body=el('div','intel-variant-body');
        body.appendChild(el('p','',`Remote: ${job.remote===true?'yes (not necessarily worldwide)':job.remote===false?'no':'unknown'} · Geographic eligibility: needs review`));
        if(variant.experience_year_mentions.length) body.appendChild(el('p','',`Years mentioned: ${variant.experience_year_mentions.join(', ')} — not verified minimum requirements`));
        for(const warning of variant.geographic_review_flags) body.appendChild(el('p','',`⚠ ${warning}`));
        const href=safeLink(job.url);
        if(href){const link=el('a','variant-link','View official listing ↗');link.href=href;link.target='_blank';link.rel='noopener noreferrer';body.appendChild(link);}
        const save=el('button','save-to-board','☆ Save to opportunity board');save.type='button';
        save.addEventListener('click',async()=>{
          save.disabled=true;
          try{if(!window.CareerPilotBoard) throw Error('Opportunity board is unavailable');
            await window.CareerPilotBoard.save(job,null);save.textContent='✓ Saved locally';}
          catch(error){save.disabled=false;setMessage(error.message,true);}
        });
        body.appendChild(save);details.appendChild(body);card.appendChild(details);
      }
      list.appendChild(card);
    }
    const warnings=$('advanced-warnings');warnings.replaceChildren();
    for(const warning of data.warnings||[]) warnings.appendChild(el('li','',warning));
  }
  async function run(){
    const button=$('advanced-run');button.disabled=true;
    setMessage('Searching public hiring feeds…');
    try{
      lastOptions=formOptions();
      const data=await api('/api/v1/jobs/intelligence/search?'+query(lastOptions));
      render(data);setMessage(`Completed: ${data.count} grouped results. No resume data was sent.`);
    }catch(error){setMessage(error.message,true);}
    finally{button.disabled=false;}
  }
  async function saveWatch(){
    try{
      const name=$('advanced-watch-name').value.trim();
      const filters=formOptions();
      const saved=await api('/api/v1/job-watches',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,filters})
      });
      setMessage(`Saved search “${saved.name}” on this device. Click Check now to establish a baseline.`);
      await renderWatches();
    }catch(error){setMessage(error.message,true);}
  }
  async function renderWatches(){
    const data=await api('/api/v1/job-watches');
    const list=$('advanced-watch-list');list.replaceChildren();
    if(!data.watches.length) list.appendChild(el('p','field-hint','No saved searches yet. Searches run only when you click Check now.'));
    for(const watch of data.watches){
      const card=el('div','intel-watch');
      const title=el('div','',`${watch.name} · ${watch.last_checked_at?'Last checked: '+watch.last_checked_at:'Not checked yet'}`);card.appendChild(title);
      const actions=el('div','intel-watch-actions');
      const check=el('button','button-secondary','Check now');check.type='button';
      check.addEventListener('click',async()=>{
        check.disabled=true;
        try{
          const result=await api(`/api/v1/job-watches/${encodeURIComponent(watch.id)}/check`,{method:'POST'});
          const detail=result.first_scan?`Baseline recorded (${result.scanned_variants} displayed variants).`:
            `${result.new_count} newly observed URL(s) in ${result.scanned_variants} displayed variants.`;
          setMessage(`“${watch.name}”: ${detail}`);
          const newArea=$('advanced-new-jobs');newArea.replaceChildren();
          for(const job of result.new_jobs){
            const row=el('div','intel-new');const a=el('a','',`${job.title} · ${job.company} · ${job.location||'Unknown location'}`);
            const url=safeLink(job.url);if(url){a.href=url;a.rel='noopener noreferrer';a.target='_blank';}
            row.appendChild(a);newArea.appendChild(row);
          }
          await renderWatches();
        }catch(error){setMessage(error.message,true);check.disabled=false;}
      });
      const remove=el('button','button-outline','Delete');remove.type='button';
      remove.addEventListener('click',async()=>{
        try{await api(`/api/v1/job-watches/${encodeURIComponent(watch.id)}`,{method:'DELETE'});
          setMessage('Saved search deleted.');await renderWatches();}
        catch(error){setMessage(error.message,true);}
      });
      actions.append(check,remove);card.appendChild(actions);list.appendChild(card);
    }
  }
  $('advanced-run').addEventListener('click',run);
  $('advanced-save-watch').addEventListener('click',saveWatch);
  $('advanced-refresh-watches').addEventListener('click',()=>renderWatches().catch(e=>setMessage(e.message,true)));
  renderWatches().catch(e=>setMessage(e.message,true));
})();

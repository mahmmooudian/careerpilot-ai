'use strict';
/* Phase 4.0 personal opportunity tracker. Plain text DOM only, same-origin API,
 * no browser storage, no automatic external application actions. */
(() => {
  const $ = id => document.getElementById(id);
  const API = '/api/v1/opportunities';
  const stages = ['saved', 'researching', 'ready_to_apply', 'applied', 'interview', 'offer', 'rejected', 'withdrawn', 'archived'];
  let rows = [];
  const el = (tag, className = '', content) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined && content !== null) node.textContent = String(content);
    return node;
  };
  const add = (parent, ...nodes) => { nodes.forEach(n => parent.appendChild(n)); return parent; };
  const label = stage => stage.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
  const safeUrl = text => {
    try { const url = new URL(text); return url.protocol === 'https:' ? url.href : null; }
    catch (_) { return null; }
  };
  const pad = x => String(x).padStart(2, '0');
  const dateInput = value => {
    if (!value) return '';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? '' : `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };
  const show = (message, error = false) => {
    const box = $('board-message'); box.textContent = message;
    box.hidden = false; box.classList.toggle('board-message-error', error);
  };
  async function request(url, options = {}) {
    const response = await fetch(url, {cache:'no-store', ...options});
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try { const result = await response.json(); if (typeof result.detail === 'string') detail = result.detail; }
      catch (_) { /* no confidential raw provider response */ }
      throw new Error(detail);
    }
    if (response.status === 204) return null;
    return response.json();
  }
  async function refresh() {
    try {
      const data = await request(API);
      rows = data.opportunities;
      render();
    } catch (err) {
      show(`Could not load local opportunity board: ${err.message}`, true);
      $('saved-cards').replaceChildren(el('p', 'board-empty', 'The opportunity board is unavailable. Is the local FastAPI server running?'));
    }
  }
  function updateSummary() {
    $('board-count').textContent = String(rows.length);
    $('board-applied').textContent = String(rows.filter(x => ['applied','interview','offer'].includes(x.stage)).length);
    $('board-interviews').textContent = String(rows.filter(x => x.stage === 'interview').length);
    const today = new Date().toLocaleDateString('en-CA').split('/').join('-');
    const localToday = `${new Date().getFullYear()}-${pad(new Date().getMonth()+1)}-${pad(new Date().getDate())}`;
    $('board-followups').textContent = String(rows.filter(x => x.next_action_on && x.next_action_on <= localToday && !['archived','rejected','withdrawn'].includes(x.stage)).length);
  }
  function control(caption, node) {
    const wrapper = el('label', 'board-field');
    add(wrapper, el('span', '', caption), node);
    return wrapper;
  }
  function makeCard(item) {
    const card = el('article', 'saved-card');
    const heading = el('div','saved-title-row');
    const titleGroup = el('div');
    add(titleGroup, el('h3', '', item.title), el('p','saved-company',`${item.company} · ${item.location || 'Location not specified'}`));
    const badge = el('span', 'chip chip-grey', item.technical_score == null ? 'Score not calculated' : `Technical score ${item.technical_score}/100`);
    add(heading,titleGroup,badge); card.appendChild(heading);
    const controlRow = el('div','saved-control-row');
    const stage = el('select'); stage.setAttribute('aria-label', `Stage for ${item.title}`);
    stages.forEach(s => { const option = el('option','',label(s)); option.value = s; stage.appendChild(option); });
    stage.value = item.stage;
    const follow = el('input'); follow.type='date'; follow.value = item.next_action_on || ''; follow.setAttribute('aria-label','Next follow-up date');
    const interview = el('input'); interview.type='datetime-local'; interview.value = dateInput(item.interview_at); interview.setAttribute('aria-label','Interview local date and time');
    add(controlRow, control('APPLICATION STAGE',stage),control('NEXT FOLLOW-UP',follow),control('INTERVIEW DATE / TIME',interview));
    card.appendChild(controlRow);
    const notes = el('textarea','saved-notes'); notes.maxLength=4000; notes.rows=3;
    notes.value = item.notes || ''; notes.placeholder='Notes, next steps, recruiter feedback…';
    card.appendChild(control('PRIVATE NOTES',notes));
    const actions = el('div','saved-actions');
    const save = el('button','button-primary board-update','Save changes'); save.type='button';
    save.addEventListener('click',async () => {
      save.disabled = true;
      try {
        const payload = {stage:stage.value, notes:notes.value,
          next_action_on: follow.value || null,
          interview_at: interview.value ? new Date(interview.value).toISOString() : null};
        await request(`${API}/${encodeURIComponent(item.id)}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        await refresh(); show('Changes saved locally. No external application was submitted.');
      } catch (error) { save.disabled = false; show(`Could not update ${item.company}: ${error.message}`,true); }
    });
    const history = el('button','button-outline','Activity history'); history.type='button';
    const log = el('div','board-history'); log.hidden = true;
    history.addEventListener('click',async () => {
      log.hidden = !log.hidden;
      if (log.hidden) return;
      log.replaceChildren(el('p','', 'Loading activity…'));
      try {
        const events = await request(`${API}/${encodeURIComponent(item.id)}/activity`);
        const list = el('ul');
        events.forEach(e => {
          const date = new Date(e.created_at);
          list.appendChild(el('li','',`${Number.isNaN(date.getTime()) ? '' : date.toLocaleString()} — ${e.description}`));
        });
        log.replaceChildren(list);
      } catch (error) { log.replaceChildren(el('p','',`History unavailable: ${error.message}`)); }
    });
    const remove = el('button','board-delete','Delete saved job'); remove.type='button';
    remove.addEventListener('click',async () => {
      if (!window.confirm(`Delete this saved job and its local tracking history?\n${item.title} — ${item.company}`)) return;
      remove.disabled = true;
      try { await request(`${API}/${encodeURIComponent(item.id)}`,{method:'DELETE'}); await refresh(); show('Saved job deleted from this local workspace.'); }
      catch (error) { remove.disabled = false; show(`Could not delete: ${error.message}`,true); }
    });
    const posting = safeUrl(item.url);
    if (posting) { const link = el('a','button-outline board-open','View posting ↗');link.href=posting;link.target='_blank';link.rel='noopener noreferrer'; actions.appendChild(link); }
    const prepare = el('button','button-outline','✦ Prepare application'); prepare.type='button';
    prepare.addEventListener('click', () => window.CareerPilotStudio?.prepare({job:item}));
    add(actions,save,prepare,history,remove);
    add(card,actions,log);
    return card;
  }
  function render() {
    updateSummary();
    const needle = $('board-search').value.toLocaleLowerCase().trim();
    const stage = $('board-stage').value;
    const filtered = rows.filter(item => (!stage || item.stage === stage) &&
      (!needle || `${item.title} ${item.company} ${item.location || ''}`.toLocaleLowerCase().includes(needle)));
    const container = $('saved-cards'); container.replaceChildren();
    if (!filtered.length) {
      container.appendChild(el('p','board-empty',rows.length ? 'No saved opportunities match those filters.' : 'Nothing saved yet. Open a job location above and select “Save this location”.'));
    } else {
      filtered.forEach(item => container.appendChild(makeCard(item)));
    }
  }
  async function save(job, technicalScore) {
    if (!job || !safeUrl(job.url)) throw new Error('A public HTTPS job link is required.');
    const input = {title:job.title, company:job.company, url:job.url,
      source:job.source || 'unknown', source_job_id:job.id || null,
      location:job.location || null, technical_score:technicalScore};
    const saved = await request(API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)});
    await refresh();
    show(`Saved “${saved.title}” (${saved.location || 'location unspecified'}) to your local opportunity board.`);
    return saved;
  }
  window.CareerPilotBoard = {save, refresh};
  $('board-stage').addEventListener('change',render);
  $('board-search').addEventListener('input',render);
  $('board-refresh').addEventListener('click',refresh);
  refresh();
})();

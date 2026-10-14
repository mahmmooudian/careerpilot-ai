'use strict';
/* CareerPilot AI Phase 4.0 discovery + matching: local presentation only; no automatic applications.
   All user/provider text is added as text nodes, not HTML. No browser storage. */
(() => {
  const $ = (id) => document.getElementById(id);
  const state = { data: null, controller: null, filter: 'all' };
  const el = (tag, className = '', content = '') => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== null && content !== undefined) node.textContent = String(content);
    return node;
  };
  const append = (parent, ...children) => { for (const c of children) parent.appendChild(c); return parent; };
  const text = (value, fallback = 'Not specified') => value == null || value === '' ? fallback : String(value);
  const boundedScore = (value) => Math.min(100, Math.max(0, Number.isFinite(Number(value)) ? Number(value) : 0));
  const showError = (message) => { $('error-state').textContent = message; $('error-state').hidden = false; };
  const clearFeedback = () => { $('error-state').hidden = true; $('notice-state').hidden = true; };
  const setBusy = (yes, title) => {
    $('processing').hidden = !yes;
    if (yes) $('processing-title').textContent = title;
    $('analyze-btn').disabled = yes;
    $('preview-btn').disabled = yes;
  };
  const fileName = (name) => (name || '').split(/[\\/]/).pop();
  const safeLink = (value) => {
    try { const url = new URL(value); return url.protocol === 'https:' ? url.toString() : null; }
    catch (_) { return null; }
  };
  function renderCandidate(profile) {
    const section = $('candidate');
    section.hidden = !profile;
    if (!profile) return;
    $('candidate-headline').textContent = text(profile.headline, 'No headline available');
    const meta = $('candidate-meta'); meta.replaceChildren();
    for (const item of [profile.location, `${(profile.experiences || []).length} experience entries`, `${(profile.projects || []).length} projects`]) {
      if (item) meta.appendChild(el('span', '', item));
    }
    const skills = $('candidate-skills'); skills.replaceChildren();
    (profile.skills || []).slice(0, 15).forEach(s => skills.appendChild(el('span', '', s.name)));
    const missingFields = (profile.experiences || []).filter(x => !x.organization || !x.start_date).length;
    const experienceBox = $('candidate-experience-panel');
    const experienceList = $('candidate-experience-list');
    experienceList.replaceChildren();
    experienceBox.hidden = !(profile.experiences || []).length;
    for (const job of (profile.experiences || [])) {
      const employer = job.organization || 'Employer not extracted';
      const dates = `${job.start_date || '?'} – ${job.end_date || '?'}`;
      experienceList.appendChild(el('li', '', `${job.job_title} · ${employer} · ${dates}`));
    }
    const notice = $('extraction-warning');
    notice.hidden = missingFields === 0;
    if (missingFields) notice.textContent = `${missingFields} work experience entries lack organization or start date. Review the original resume; extraction can vary between model runs.`;
  }
  function renderWarnings(warnings) {
    const box = $('warnings-panel'), list = $('warnings-list');
    list.replaceChildren(); box.hidden = !warnings?.length;
    (warnings || []).forEach(w => list.appendChild(el('li', '', w)));
  }
  // A grouped vacancy can have many country variants. Show repeated review
  // conditions once per group, without hiding any unique per-country checks.
  function variantFlags(variant, matching) {
    return [...new Set([...(matching ? (variant.match?.review_flags || []) : []),
      ...(variant.geographic_review_flags || [])])];
  }
  function sharedReviewFlags(variants, matching) {
    if (!variants.length) return [];
    const first = variantFlags(variants[0], matching);
    return first.filter(flag => variants.every(v => variantFlags(v, matching).includes(flag)));
  }
  function reviewPriority(group, matching) {
    const score = boundedScore(matching ? group.group_match_score : group.retrieval_score);
    if (!matching) return score;
    // Display-order heuristic, not an eligibility decision or hiring probability.
    const level = seniority(group.title);
    let priority = score + (level === 'junior' ? 16 : level === 'senior' ? -9 : 0);
    const all = (group.variants || []).map(v => v.experience_year_mentions || []).flat();
    const years = all.length ? Math.min(...all.filter(Number.isFinite)) : 0;
    if (years >= 5) priority -= Math.min(18, (years - 3) * 3);
    if ((group.variants || []).some(v => variantFlags(v, true).some(f => /explicitly excludes early.career/i.test(f)))) priority -= 12;
    return priority;
  }
  function createVariant(variant, matching, sharedFlags) {
    const match = matching ? variant.match : null;
    const job = matching ? match?.job : variant.job;
    if (!job) return null;
    const details = el('details', 'variant');
    // Collapsed by default: avoid walls of identical multi-paragraph warnings.
    const summary = el('summary');
    const left = el('span', 'variant-summary-left');
    append(left, el('span', '', text(job.location, 'Location not stated')),
      el('span', 'review-tag', 'Geography: needs review'));
    if (matching) left.appendChild(el('span', 'chip chip-grey', `Technical match: ${boundedScore(match.match_score)}/100`));
    summary.appendChild(left); details.appendChild(summary);
    const body = el('div', 'variant-body');
    if (matching) {
      body.appendChild(el('p', '', match.explanation || 'Read the original description.'));
      const matched = (match.matched_skills || []).join(' · ');
      const missing = (match.missing_skills_to_verify || []).join(' · ');
      if (matched) body.appendChild(el('p', '', `Evidenced skills: ${matched}`));
      if (missing) body.appendChild(el('p', '', `Requirements to verify: ${missing}`));
    } else {
      body.appendChild(el('p', '', 'Browse-only result. Upload a resume to get an evidence-based technical ranking.'));
    }
    if (variant.experience_year_mentions?.length) body.appendChild(el('p', '', `Years mentioned in posting: ${variant.experience_year_mentions.join(', ')} (not confirmed requirements)`));
    const flags = variantFlags(variant, matching).filter(flag => !sharedFlags.includes(flag));
    for (const flag of flags) body.appendChild(el('p', '', `⚠ ${flag}`));
    const link = safeLink(job.url);
    if (link) {
      const a = el('a', 'variant-link', 'View original posting ↗');
      a.href = link; a.target = '_blank'; a.rel = 'noopener noreferrer'; body.appendChild(a);
    }
    const saveAction = el('button', 'save-to-board', '☆ Save this location');
    saveAction.type = 'button';
    saveAction.setAttribute('aria-label', `Save ${job.title} at ${text(job.location)} to opportunity board`);
    saveAction.addEventListener('click', async () => {
      if (!window.CareerPilotBoard) return;
      saveAction.disabled = true;
      try {
        await window.CareerPilotBoard.save(job, matching ? boundedScore(match.match_score) : null);
        saveAction.textContent = '✓ Saved locally';
      } catch (error) {
        saveAction.disabled = false;
        saveAction.textContent = '☆ Retry saving';
        showError(`Could not save opportunity: ${error.message}`);
      }
    });
    if (matching) {
      const draftAction = el('button', 'save-to-board', '✦ Prepare application');
      draftAction.type = 'button';
      draftAction.addEventListener('click', () => {
        if (window.CareerPilotStudio) window.CareerPilotStudio.prepare({job,profile:state.data?.candidate_profile});
      });
      body.appendChild(draftAction);
    }
    body.appendChild(saveAction);
    details.appendChild(body);
    return details;
  }
  function seniority(title) {
    if (/\b(junior|intern|graduate|entry.level)\b/i.test(title)) return 'junior';
    if (/\b(senior|sr\.?|principal|staff|architect|lead)\b/i.test(title)) return 'senior';
    return 'mid';
  }
  function renderCards() {
    const data = state.data;
    if (!data) return;
    const matching = Array.isArray(data.grouped_matches);
    const groups = matching ? data.grouped_matches : (data.grouped_jobs || []);
    const out = $('job-cards'); out.replaceChildren();
    const search = $('result-search').value.toLocaleLowerCase().trim();
    const order = $('sort-order').value;
    const chosen = groups.filter(g => (state.filter === 'all' || seniority(g.title) === state.filter)
      && (!search || `${g.title} ${g.company}`.toLocaleLowerCase().includes(search)));
    if (order === 'company') chosen.sort((a,b) => a.company.localeCompare(b.company) || a.title.localeCompare(b.title));
    else chosen.sort((a,b) => (order === 'priority'
      ? reviewPriority(b, matching) - reviewPriority(a, matching)
      : boundedScore(matching ? b.group_match_score : b.retrieval_score)
        - boundedScore(matching ? a.group_match_score : a.retrieval_score))
      || a.title.localeCompare(b.title));
    if (!chosen.length) { out.appendChild(el('div', 'no-results', 'No groups match this filter. Try another search or seniority level.')); return; }
    chosen.forEach(group => {
      const card = el('article', 'job-card');
      const head = el('div', 'job-header'), titleWrap = el('div');
      append(titleWrap, el('h3', 'job-title', group.title), el('p', 'job-company', group.company));
      head.appendChild(titleWrap);
      const score = matching ? group.group_match_score : group.retrieval_score;
      const sc = el('div', 'score');
      append(sc, el('strong', '', `${boundedScore(score)}/100`),
        el('small', '', matching ? 'Technical match' : 'Search relevance'));
      const meter = el('div', 'score-meter');
      const fill = el('div', 'score-fill'); fill.style.width = `${boundedScore(score)}%`;
      meter.appendChild(fill); sc.appendChild(meter); head.appendChild(sc); card.appendChild(head);
      const badges = el('div', 'job-badges');
      append(badges, el('span', 'chip chip-grey', seniority(group.title) === 'mid' ? 'Level not specified' : seniority(group.title).toUpperCase()),
        el('span', 'chip chip-grey', `${group.variant_count} location variant${group.variant_count === 1 ? '' : 's'}`),
        el('span', 'chip chip-warn', 'ELIGIBILITY NOT VERIFIED'));
      for (const r of (group.matched_roles || []).slice(0, 3)) badges.appendChild(el('span', 'chip', r));
      card.appendChild(badges);
      card.appendChild(el('p', 'job-support', matching
        ? 'Technical match is independent of employment eligibility. Review priority favors earlier-career roles; verify employer requirements.'
        : 'Search relevance only. Expand a location to inspect requirements and the original posting.'));
      const sharedFlags = sharedReviewFlags(group.variants || [], matching);
      if (sharedFlags.length) {
        const common = el('details', 'group-review');
        common.appendChild(el('summary', '', `Shared review checks · ${sharedFlags.length} (expand)`));
        const list = el('ul', 'group-review-list');
        sharedFlags.forEach(f => list.appendChild(el('li', '', f)));
        common.appendChild(list); card.appendChild(common);
      }
      const variantList = el('div', 'variant-list');
      (group.variants || []).forEach(v => { const item = createVariant(v, matching, sharedFlags); if (item) variantList.appendChild(item); });
      card.appendChild(variantList); out.appendChild(card);
    });
  }
  function renderResults(data) {
    if (!data || (!Array.isArray(data.grouped_matches) && !Array.isArray(data.grouped_jobs)))
      throw new Error('This does not look like a grouped CareerPilot API response.');
    state.data = data;
    // Transient browser-only profile; never stored in SQLite or browser storage.
    window.CareerPilotCurrentProfile = data.candidate_profile || null;
    window.CareerPilotStudio?.profileChanged();
    const groups = data.grouped_matches || data.grouped_jobs || [];
    const matching = !!data.grouped_matches;
    $('results').hidden = false;
    $('metric-groups').textContent = String(data.count ?? groups.length);
    $('metric-listings').textContent = String(data.jobs_considered ?? '—');
    $('metric-variants').textContent = String(groups.reduce((sum, g) => sum + Number(g.variant_count || 0), 0));
    $('metric-sources').textContent = String(data.sources_checked?.length || 0);
    $('results-summary').textContent = matching ? 'Sorted by review priority, not hiring probability. Compare technical scores separately; eligibility remains unverified.' : 'Public job-board discovery — no resume processing performed.';
    renderCandidate(matching ? data.candidate_profile : null);
    renderWarnings(data.warnings || []);
    renderCards();
    $('results').scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  async function runSearch(mode) {
    clearFeedback();
    const roles = $('roles').value.trim();
    if (roles.length < 3 || roles.length > 400) { showError('Enter at least one valid target job title.'); return; }
    if (mode === 'match' && !$('resume').files?.[0]) { showError('Choose a PDF or DOCX resume to run AI matching.'); return; }
    if (mode === 'match' && !$('consent').checked) { showError('Please confirm consent before sending your resume to the external AI provider.'); return; }
    const params = {
      roles, limit: $('limit').value, remote_only: String($('remote_only').checked),
      diversify: String($('diversify').checked)
    };
    if ($('work_country').value.trim()) params.work_country = $('work_country').value.trim();
    const controller = new AbortController(); state.controller = controller;
    setBusy(true, mode === 'match' ? 'Reading your resume and comparing opportunities…' : 'Collecting jobs across public boards…');
    try {
      let response;
      if (mode === 'match') {
        const form = new FormData();
        form.set('file', $('resume').files[0]); form.set('consent_to_external_processing', 'true');
        Object.entries(params).forEach(([k,v]) => form.set(k,v));
        response = await fetch('/api/v1/jobs/recommend/multi/grouped', {method:'POST',body:form,signal:controller.signal});
      } else {
        response = await fetch(`/api/v1/jobs/search/multi/grouped?${new URLSearchParams(params)}`, {signal:controller.signal});
      }
      if (!response.ok) {
        let explanation;
        try { const obj = await response.json(); explanation = typeof obj.detail === 'string' ? obj.detail : JSON.stringify(obj.detail); }
        catch (_) { explanation = `HTTP ${response.status}`; }
        throw new Error(`${response.status}: ${explanation}`);
      }
      renderResults(await response.json());
    } catch (error) {
      if (error.name !== 'AbortError') showError(`Request could not be completed: ${error.message}`);
      else { $('notice-state').textContent = 'Request cancelled in this browser. The server may still finish its current operation.'; $('notice-state').hidden = false; }
    } finally { if (state.controller === controller) state.controller = null; setBusy(false); }
  }
  $('analyze-btn').addEventListener('click', () => runSearch('match'));
  $('preview-btn').addEventListener('click', () => runSearch('preview'));
  $('cancel-btn').addEventListener('click', () => state.controller?.abort());
  $('resume').addEventListener('change', () => { $('upload-name').textContent = fileName($('resume').files?.[0]?.name) || 'Choose a PDF or DOCX resume'; });
  const zone = $('drop-zone');
  for (const type of ['dragenter','dragover']) zone.addEventListener(type, event => { event.preventDefault(); zone.classList.add('dragging'); });
  for (const type of ['dragleave','drop']) zone.addEventListener(type, event => { event.preventDefault(); zone.classList.remove('dragging'); });
  zone.addEventListener('drop', event => {
    const files = event.dataTransfer?.files;
    if (files?.length) {
      const file = files[0];
      if (!/\.(pdf|docx)$/i.test(file.name)) { showError('Only PDF and DOCX files are supported.'); return; }
      $('resume').files = files; $('upload-name').textContent = fileName(file.name);
    }
  });
  $('saved-json').addEventListener('change', async () => {
    clearFeedback();
    try { const file = $('saved-json').files?.[0]; if (!file) return;
      if (file.size > 10 * 1024 * 1024) throw new Error('JSON must be smaller than 10 MB.');
      renderResults(JSON.parse(await file.text()));
      $('notice-state').textContent = 'Saved API response loaded entirely in your browser; it was not uploaded to the server.';
      $('notice-state').hidden = false;
    } catch (err) { showError(`Cannot open saved result: ${err.message}`); }
  });
  $('export-btn').addEventListener('click', () => {
    if (!state.data) return;
    const blob = new Blob([JSON.stringify(state.data, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = el('a'); a.href = url; a.download = 'careerpilot-results.json'; document.body.appendChild(a);
    a.click(); a.remove(); URL.revokeObjectURL(url);
  });
  document.querySelectorAll('[data-filter]').forEach(b => b.addEventListener('click', () => {
    state.filter = b.dataset.filter;
    document.querySelectorAll('[data-filter]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    renderCards();
  }));
  $('result-search').addEventListener('input', renderCards);
  $('sort-order').addEventListener('change', renderCards);
})();

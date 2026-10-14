'use strict';
/* Phase 5.0 - human-reviewed application drafting, not external AI or auto-apply.
 * Incoming descriptions and API content are displayed only with textContent/value.
 * No browser storage; no job description, profile or drafts saved in SQLite. */
(() => {
  const $ = id => document.getElementById(id);
  const studio = $('application-studio');
  if (!studio) return;
  let profile = null;
  const error = message => { $('studio-error').textContent = message; $('studio-error').hidden = false; };
  const clear = () => { $('studio-error').hidden = true; $('studio-success').hidden = true; };
  const text = value => value == null ? '' : String(value);
  const addItems = (id, items, getLabel) => {
    const list = $(id); list.replaceChildren();
    if (!items?.length) { const li = document.createElement('li'); li.textContent='None identified in supplied input.'; list.appendChild(li); return; }
    items.forEach(item => { const li=document.createElement('li'); li.textContent=getLabel(item); list.appendChild(li); });
  };
  function profileChanged() {
    profile = window.CareerPilotCurrentProfile || null;
    $('studio-profile-status').textContent = profile
      ? `Resume-based candidate profile loaded in this browser tab (${(profile.skills || []).length} skills, ${(profile.projects || []).length} projects). Review original resume before using generated claims.`
      : 'No candidate profile loaded. Match a resume or load an earlier grouped matching JSON in Discover & match.';
  }
  function prepare({job,profile:givenProfile} = {}) {
    if (givenProfile) { window.CareerPilotCurrentProfile = givenProfile; }
    profileChanged(); clear();
    if (job) {
      $('studio-title').value = text(job.title);
      $('studio-company').value = text(job.company);
      $('studio-location').value = text(job.location);
      // Saved jobs intentionally do not persist descriptions, hence manual paste.
      $('studio-description').value = text(job.description);
    }
    $('studio-output').hidden = true;
    if (!profile) error('First run Match my resume or load a previous grouped matching JSON in Discover & match. Saved jobs do not store your resume.');
    else if (!$('studio-description').value.trim()) error('Paste the full job description to compare requirements. Saved opportunities only retain public posting metadata.');
    window.location.hash = 'application-studio';
    studio.scrollIntoView({behavior:'smooth',block:'start'});
  }
  async function generate() {
    clear();
    profileChanged();
    if (!profile) { error('Candidate profile is missing. Match your resume or load an existing grouped matching JSON first.'); return; }
    const posting = {
      title: $('studio-title').value.trim(), company: $('studio-company').value.trim(),
      location: $('studio-location').value.trim() || null,
      description: $('studio-description').value.trim()
    };
    if (posting.title.length < 2 || !posting.company || posting.description.length < 30) {
      error('Enter a job title, company, and at least 30 characters from the job description.'); return;
    }
    const button=$('studio-generate'); button.disabled = true;
    try {
      const result = await fetch('/api/v1/application/draft',{
        method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({candidate_profile:profile,posting})
      });
      if (!result.ok) {
        const detail=await result.json().catch(()=>({}));
        throw new Error(typeof detail.detail === 'string' ? detail.detail : `HTTP ${result.status}: check inputs`);
      }
      const payload=await result.json();
      $('studio-resume-text').value=text(payload.resume_text);
      $('studio-letter-text').value=text(payload.cover_letter_text);
      addItems('studio-matched',payload.matched_skills,item=>`${item.skill} — ${item.evidence}`);
      addItems('studio-verify',payload.technologies_to_verify,item=>item);
      addItems('studio-review-notes',payload.review_notes,item=>item);
      $('studio-years').textContent = payload.experience_year_mentions?.length ? `Years mentioned in posting: ${payload.experience_year_mentions.join(', ')} (verify whether mandatory).` : 'No explicit years-of-experience mentions detected.';
      $('studio-output').hidden=false;
      $('studio-success').textContent='Drafts generated locally. Review and edit before any personal use; nothing was submitted or saved.';
      $('studio-success').hidden=false;
      $('studio-output').scrollIntoView({behavior:'smooth',block:'start'});
    } catch(e) { error(`Could not prepare draft: ${e.message}`); }
    finally { button.disabled=false; }
  }
  function download(id,filename) {
    const url=URL.createObjectURL(new Blob([$(id).value],{type:'text/plain;charset=utf-8'}));
    const a=document.createElement('a'); a.href=url; a.download=filename; a.click();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function copy(id) {
    navigator.clipboard.writeText($(id).value).then(()=>{
      $('studio-success').textContent='Edited text copied. No application sent.';
      $('studio-success').hidden=false;
    }).catch(()=>error('Could not copy automatically; select the text and copy it manually.'));
  }
  $('studio-generate').addEventListener('click',generate);
  $('studio-resume-copy').addEventListener('click',()=>copy('studio-resume-text'));
  $('studio-letter-copy').addEventListener('click',()=>copy('studio-letter-text'));
  $('studio-resume-download').addEventListener('click',()=>download('studio-resume-text','careerpilot-tailored-resume.txt'));
  $('studio-letter-download').addEventListener('click',()=>download('studio-letter-text','careerpilot-cover-letter.txt'));
  window.CareerPilotStudio={prepare,profileChanged};
  profileChanged();
})();
